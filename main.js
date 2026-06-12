const { app, BrowserWindow, dialog } = require('electron');
// NOTE: electron-updater is LAZY-LOADED inside the setTimeout in createWindow()
// (search for `require('electron-updater')` below). In v6.8.x its top-level
// require triggers `app.getVersion()` immediately, which throws on Electron 42
// because the app singleton isn't fully initialized yet. Deferring the require
// dodges the crash. See POST_MORTEM.md for the debug history.
const fs = require('node:fs');
const path = require('path');
const net = require('node:net');
const http = require('node:http');
const url = require('node:url');
const { spawn, execFile } = require('node:child_process');
const { migrateLegacyData } = require('./migration');

// Hardcoded legacy data path for first-run migration. This is the location of
// the dev/legacy `data/` directory used before the Electron-packaged build
// existed. It's specific to the developer's machine; for distribution this
// would be made configurable, but for the prototype the assumption is fine.
const LEGACY_DATA_PATH = 'C:\\Users\\juanh\\Desktop\\postbell2\\data';

// In dev (npm run dev) we point at the Vite dev server.
// In packaged builds (electron-builder) we load the built renderer from a
// local static HTTP server we spawn from this process — see startStaticServer.
// ELECTRON_RENDERER_URL is set by `start:wait` indirectly via `dev`; we also
// fall back to detecting non-packaged mode for ad-hoc `electron .` invocations.
const DEV_SERVER_URL =
  process.env.ELECTRON_RENDERER_URL || 'http://localhost:5174';

// Process-wide references so before-quit can clean up regardless of which
// window triggered the shutdown.
let backendProcess = null;
let backendPort = null;
let backendUrl = null;
let backendStartupError = null;
let staticServer = null;
let staticPort = null;
let staticUrl = null;
// Tracks whether we're shutting the app down on purpose, so the backend
// `exit` handler doesn't fire a panic dialog.
let isQuitting = false;

// Map of file extension -> Content-Type used by the static server. Anything
// not in this map gets served as application/octet-stream, which is fine for
// downloads but not for things the browser needs to parse.
const STATIC_CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
};

/**
 * Resolve the path to the bundled backend executable.
 * In dev: dist-backend/postbell-backend/postbell-backend.exe (sibling of main.js).
 * In a packaged app (electron-builder extraResources later): under resourcesPath.
 */
function resolveBackendExePath() {
  const exeName =
    process.platform === 'win32' ? 'postbell-backend.exe' : 'postbell-backend';
  if (app.isPackaged) {
    // Packaged path (will be wired up properly in the electron-builder feature).
    return path.join(process.resourcesPath, 'backend', exeName);
  }
  return path.join(__dirname, 'dist-backend', 'postbell-backend', exeName);
}

/**
 * Ask the kernel for a free TCP port on 127.0.0.1 by binding to port 0 and
 * reading back what we got. Close the socket immediately — there's a tiny
 * race between close and the backend's own bind, but in practice on Windows
 * the port stays free long enough for the subsequent spawn.
 */
function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close((closeErr) => {
        if (closeErr) reject(closeErr);
        else resolve(port);
      });
    });
  });
}

/**
 * GET http://127.0.0.1:<port>/api/health and resolve true on 2xx, false on
 * any failure. Never rejects — the polling loop above only cares about
 * success/failure, not the exception type.
 */
function pingHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: '127.0.0.1',
        port,
        path: '/api/health',
        timeout: 1500,
      },
      (res) => {
        // Drain the response so the socket can be reused/closed cleanly.
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      },
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Poll /api/health every `intervalMs` until it returns true or `timeoutMs`
 * elapses. Returns true on success, false on timeout.
 */
async function waitForHealth(port, { timeoutMs = 30000, intervalMs = 500 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await pingHealth(port)) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

/**
 * Hard-kill the spawned backend, escalating SIGTERM -> SIGKILL -> taskkill /T
 * because Windows doesn't honor POSIX signals.
 */
function killBackend() {
  if (!backendProcess || backendProcess.killed) return;
  const pid = backendProcess.pid;
  try {
    backendProcess.kill('SIGTERM');
  } catch (e) {
    console.error('[main] SIGTERM failed:', e);
  }
  // Fallback after 5s: try SIGKILL.
  setTimeout(() => {
    if (backendProcess && !backendProcess.killed) {
      try {
        backendProcess.kill('SIGKILL');
      } catch (e) {
        console.error('[main] SIGKILL failed:', e);
      }
    }
    // Last resort on Windows: taskkill the whole tree (covers child python
    // workers PyInstaller may spawn). Fire-and-forget — Electron is exiting.
    if (process.platform === 'win32' && pid) {
      execFile(
        'taskkill',
        ['/pid', String(pid), '/T', '/F'],
        (err) => {
          if (err) console.error('[main] taskkill failed:', err.message);
        },
      );
    }
  }, 5000);
}

/**
 * Spawn the backend exe with POSTBELL_PORT set, wire up stdout/stderr to our
 * console, and register exit handlers. Does NOT wait for health — caller
 * runs waitForHealth() separately.
 */
function spawnBackend(port) {
  const exePath = resolveBackendExePath();
  // Point the bundled backend at the per-user state directory so SQLite,
  // OAuth tokens, logs, and temp uploads all live under the chosen userData
  // path (which we redirect to %APPDATA%/projetos/postbell on Windows below).
  // The backend derives every state path from this single root via
  // settings.data_dir.
  const dataDir = app.getPath('userData');
  console.log(
    `[main] spawning backend: ${exePath} (POSTBELL_PORT=${port}, POSTBELL_DATA_DIR=${dataDir})`,
  );
  const proc = spawn(exePath, [], {
    env: {
      ...process.env,
      POSTBELL_PORT: String(port),
      POSTBELL_DATA_DIR: dataDir,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  proc.stdout.on('data', (d) => {
    const line = d.toString().trim();
    if (line) console.log('[backend]', line);
  });
  proc.stderr.on('data', (d) => {
    const line = d.toString().trim();
    if (line) console.error('[backend]', line);
  });

  proc.on('error', (err) => {
    console.error('[main] backend spawn error:', err);
    backendStartupError = err;
  });

  proc.on('exit', (code, signal) => {
    console.log(
      `[main] backend exited code=${code} signal=${signal} quitting=${isQuitting}`,
    );
    if (!isQuitting) {
      // Crashed while the app was running. Don't auto-restart — show the user
      // and bail out cleanly so they can re-launch from scratch.
      dialog.showErrorBox(
        'Backend crashed',
        `The Postbell backend exited unexpectedly (code=${code}, signal=${signal}). ` +
          'The application will now quit.',
      );
      app.quit();
    }
  });

  return proc;
}

/**
 * On first run, detect a legacy `data/` directory from the dev/standalone
 * installation and offer to import it. A `.migrated` marker file in userData
 * makes this a one-time check: present (any contents) means we've already
 * asked, so we skip.
 */
function maybeMigrateLegacyData() {
  const userDataPath = app.getPath('userData');
  const migrationFlag = path.join(userDataPath, '.migrated');

  if (fs.existsSync(migrationFlag)) {
    // Already migrated or already skipped — never ask again.
    return;
  }
  if (!fs.existsSync(LEGACY_DATA_PATH)) return;
  if (!fs.existsSync(path.join(LEGACY_DATA_PATH, 'postbell.db'))) return;

  // Ask via native modal (synchronous: we want a definitive answer before
  // proceeding to spawn the backend, so it sees the migrated files).
  const choice = dialog.showMessageBoxSync({
    type: 'question',
    buttons: ['Importar', 'Pular'],
    defaultId: 0,
    cancelId: 1,
    title: 'Postbell',
    message:
      'Detectamos uma instalação anterior do Postbell. Importar os dados (canais, histórico, tokens OAuth)?',
  });

  if (choice === 0) {
    try {
      migrateLegacyData(LEGACY_DATA_PATH, userDataPath);
      console.log(
        `[main] migrated legacy data from ${LEGACY_DATA_PATH} -> ${userDataPath}`,
      );
    } catch (err) {
      console.error('[main] migration failed:', err);
      dialog.showErrorBox(
        'Falha ao importar dados',
        `A importação dos dados anteriores falhou parcialmente: ${err.message}. ` +
          'O aplicativo seguirá com o que foi possível copiar.',
      );
    }
    // Stamp flag with timestamp so we know when migration ran.
    try {
      fs.writeFileSync(migrationFlag, new Date().toISOString() + '\n', 'utf8');
    } catch (err) {
      console.error('[main] could not write .migrated flag:', err);
    }
  } else {
    // User opted out — drop an empty flag so we don't ask again next launch.
    try {
      fs.writeFileSync(migrationFlag, '', 'utf8');
    } catch (err) {
      console.error('[main] could not write .migrated flag:', err);
    }
  }
}

/**
 * Proxy an incoming HTTP request to the backend on 127.0.0.1:backendPort.
 * Streams body in, streams response out. Preserves method, path, query and
 * headers (rewriting Host to point at the backend so virtual-host-aware
 * frameworks see the right name).
 */
function proxyHttpToBackend(req, res) {
  const reqUrl = req.url || '/';
  const headers = { ...req.headers };
  headers.host = `127.0.0.1:${backendPort}`;
  // Strip hop-by-hop headers — they don't apply to the upstream connection.
  delete headers.connection;
  delete headers['keep-alive'];

  const options = {
    hostname: '127.0.0.1',
    port: backendPort,
    path: reqUrl,
    method: req.method,
    headers,
  };

  const upstream = http.request(options, (upstreamRes) => {
    // Copy status + headers verbatim; FastAPI sets Content-Type, etc.
    res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
    upstreamRes.pipe(res);
  });

  upstream.on('error', (err) => {
    console.error('[static] proxy error:', err.message);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
    }
    res.end(`Bad Gateway: ${err.message}`);
  });

  req.pipe(upstream);
}

/**
 * Serve a static file from dist-renderer/. If the resolved path doesn't
 * exist (or is a directory), fall back to index.html so a deep-link reload
 * still resolves the SPA entry. Also guards against path traversal by
 * verifying the resolved file stays inside the renderer root.
 */
function serveStaticFile(req, res) {
  const renderRoot = path.join(__dirname, 'dist-renderer');
  const parsed = url.parse(req.url || '/');
  let urlPath = decodeURIComponent(parsed.pathname || '/');

  // Default + SPA fallback: anything that doesn't look like an asset goes to
  // index.html. We keep the literal SPA fallback simple — try the path, if
  // it's not a file, serve index.html.
  if (urlPath === '/' || urlPath === '') {
    urlPath = '/index.html';
  }

  let filePath = path.join(renderRoot, urlPath);
  // Guard against `..` escapes.
  const normalized = path.normalize(filePath);
  if (!normalized.startsWith(renderRoot)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Forbidden');
    return;
  }
  filePath = normalized;

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      // SPA fallback to index.html for any path that doesn't resolve to a
      // real file. This lets client-side routes survive a refresh.
      filePath = path.join(renderRoot, 'index.html');
    }
    const ext = path.extname(filePath).toLowerCase();
    const contentType =
      STATIC_CONTENT_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath)
      .on('error', (streamErr) => {
        console.error('[static] read error:', streamErr.message);
        if (!res.headersSent) {
          res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
        }
        res.end(`Internal Server Error: ${streamErr.message}`);
      })
      .pipe(res);
  });
}

/**
 * Start the local static HTTP server that the BrowserWindow will load.
 * - Requests to /api/* and /ws/* are proxied to the backend on backendPort.
 * - WebSocket upgrades are tunneled bidirectionally to the backend.
 * - Everything else is served from dist-renderer/ with SPA fallback.
 *
 * Resolves once the server is listening with the chosen port. Uses 127.0.0.1
 * only — never binds to 0.0.0.0 — so the renderer surface isn't reachable
 * from other machines on the LAN.
 */
function startStaticServer(chosenPort) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const reqUrl = req.url || '/';
      if (reqUrl.startsWith('/api/') || reqUrl.startsWith('/ws/')) {
        proxyHttpToBackend(req, res);
        return;
      }
      serveStaticFile(req, res);
    });

    // WebSocket upgrade handler: open a raw TCP socket to the backend and
    // forward the upgrade request bytes, then pipe both directions until one
    // side closes.
    server.on('upgrade', (req, clientSocket, head) => {
      const reqUrl = req.url || '/';
      if (!reqUrl.startsWith('/api/') && !reqUrl.startsWith('/ws/')) {
        clientSocket.write('HTTP/1.1 404 Not Found\r\n\r\n');
        clientSocket.destroy();
        return;
      }
      const upstream = net.connect(backendPort, '127.0.0.1', () => {
        // Re-serialize the upgrade request line and headers exactly as the
        // backend's HTTP parser will expect them.
        const headerLines = [`${req.method} ${reqUrl} HTTP/1.1`];
        for (const [name, value] of Object.entries(req.headers)) {
          if (Array.isArray(value)) {
            for (const v of value) headerLines.push(`${name}: ${v}`);
          } else if (value != null) {
            headerLines.push(`${name}: ${value}`);
          }
        }
        upstream.write(headerLines.join('\r\n') + '\r\n\r\n');
        if (head && head.length) upstream.write(head);
        upstream.pipe(clientSocket);
        clientSocket.pipe(upstream);
      });
      upstream.on('error', (err) => {
        console.error('[static] ws proxy error:', err.message);
        clientSocket.destroy();
      });
      clientSocket.on('error', (err) => {
        console.error('[static] ws client error:', err.message);
        upstream.destroy();
      });
    });

    server.on('error', (err) => {
      reject(err);
    });

    server.listen(chosenPort, '127.0.0.1', () => {
      const port = server.address().port;
      console.log(`[main] static server listening on http://127.0.0.1:${port}`);
      resolve({ server, port });
    });
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      // Preload stays wired even though the renderer no longer needs to ask
      // for the backend URL — keeps the surface open for future IPC.
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    // Dev (vite-managed): load directly from the Vite dev server and open
    // DevTools. The static-server path below is only used in packaged builds
    // (and in `electron .` runs where ELECTRON_RENDERER_URL isn't set).
    win.loadURL(DEV_SERVER_URL);
    win.webContents.openDevTools();
  } else {
    // Prod/packaged (and ad-hoc `electron .`): load from our local static
    // server. Same-origin, so /api and /ws are reachable as relative paths
    // and we sidestep the file:// ES-module restrictions Chromium imposes.
    win.loadURL(staticUrl);
  }

  // Schedule an autoUpdater check 30 seconds after window open. `checkForUpdatesAndNotify`
  // resolves silently when no update is available and emits a native OS notification when
  // one is. We swallow errors here because the most likely failure modes (no GitHub release
  // feed published yet — see `publish` block in electron-builder.json — or the user being
  // offline) are not actionable for the user. The 30s delay keeps the network request out
  // of the startup critical path.
  setTimeout(() => {
    try {
      const { autoUpdater } = require('electron-updater');
      autoUpdater.checkForUpdatesAndNotify().catch((err) => {
        // Graceful: log and move on. Most likely cause: no release feed
        // configured yet (placeholder owner/repo) or user is offline.
        console.warn('[updater] check failed:', err.message);
      });
    } catch (err) {
      console.warn('[updater] failed to load electron-updater:', err.message);
    }
  }, 30 * 1000); // wait 30s after window open
}

app.whenReady().then(async () => {
  // 0a. Redirect userData to C:\Users\juanh\Desktop\projetos\shared-data\postbell\
  //     so this app sits inside the existing "projetos" multi-app ecosystem
  //     alongside ChannelOrganizer (which also reads/writes under
  //     projetos\shared-data\). See ARCHITECTURE.md and shared-data/README.md
  //     for the full layout. This MUST happen BEFORE any other code reads
  //     app.getPath('userData') — that includes maybeMigrateLegacyData and
  //     the backend spawn.
  try {
    const customDataRoot = 'C:\\Users\\juanh\\Desktop\\projetos\\shared-data\\postbell';
    fs.mkdirSync(customDataRoot, { recursive: true });
    app.setPath('userData', customDataRoot);
    console.log(`[main] userData -> ${customDataRoot}`);
  } catch (err) {
    console.error('[main] failed to redirect userData:', err);
    // Non-fatal: fall back to Electron's default location.
  }

  // 0b. First-run data migration: if a legacy `data/` dir exists and the user
  //     hasn't been asked yet, prompt to import it into userData. Must run
  //     BEFORE the backend spawn so the backend sees the migrated files when
  //     it first opens postbell.db / reads settings.json.
  try {
    maybeMigrateLegacyData();
  } catch (err) {
    // Defensive: any unexpected error here should not block app startup.
    console.error('[main] maybeMigrateLegacyData threw unexpectedly:', err);
  }

  // 1. Pick a free port and spawn the backend bound to it.
  try {
    backendPort = await getFreePort();
  } catch (err) {
    console.error('[main] could not pick a free port:', err);
    dialog.showErrorBox(
      'Startup failed',
      `Could not pick a free port: ${err.message}`,
    );
    app.quit();
    return;
  }
  backendUrl = `http://127.0.0.1:${backendPort}`;

  try {
    backendProcess = spawnBackend(backendPort);
  } catch (err) {
    console.error('[main] failed to spawn backend:', err);
    dialog.showErrorBox(
      'Backend failed to start',
      `Could not spawn backend executable: ${err.message}`,
    );
    app.quit();
    return;
  }

  // 2. Wait for /api/health to come up.
  const healthy = await waitForHealth(backendPort);
  if (!healthy) {
    const detail = backendStartupError
      ? backendStartupError.message
      : 'no response from /api/health within 30s';
    console.error(`[main] backend health check failed: ${detail}`);
    dialog.showErrorBox(
      'Backend did not start',
      `The Postbell backend did not respond on ${backendUrl} within 30 seconds (${detail}). ` +
        'The application will now quit.',
    );
    isQuitting = true;
    killBackend();
    app.quit();
    return;
  }
  console.log(`[main] backend healthy at ${backendUrl}`);

  // 3. Start the local static HTTP server that the BrowserWindow will load.
  //    Same-origin proxy to /api and /ws — see startStaticServer.
  try {
    staticPort = await getFreePort();
    const { server } = await startStaticServer(staticPort);
    staticServer = server;
    staticUrl = `http://127.0.0.1:${staticPort}/`;
  } catch (err) {
    console.error('[main] failed to start static server:', err);
    dialog.showErrorBox(
      'Renderer failed to start',
      `Could not start the local static server: ${err.message}`,
    );
    isQuitting = true;
    killBackend();
    app.quit();
    return;
  }

  // 4. Open the window.
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  killBackend();
  if (staticServer) {
    try {
      staticServer.close();
    } catch (err) {
      console.error('[main] static server close failed:', err.message);
    }
    staticServer = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
