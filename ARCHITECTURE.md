# Postbell — Architecture Notes

> Audience: a future AI assistant (or human contributor) extending this app, or building a sibling app that needs to coexist with it under `Desktop\projetos\`.
> Goal of this document: capture *why* the moving parts are arranged the way they are, so you can pick up context without re-deriving the design.

## Vision

Postbell sits inside the user's `Desktop\projetos\` ecosystem alongside other personal apps (currently **ChannelOrganizer**, future ones planned). The user wants every app in this folder to:

1. Run individually (each has its own .exe / installer).
2. Share data when relevant (via `Desktop\projetos\shared-data\`).
3. Eventually be launchable from a single hub.

We are **not** building the hub yet. We are pre-positioning Postbell so the hub can drop in later without a data migration. Concretely: shared filesystem namespace for data, no assumptions that Postbell is the only app on the machine, and a runtime architecture that other apps can copy by template.

The existing pattern (set by ChannelOrganizer):
- App source lives in `Desktop\projetos\<appname>\`.
- Shared/cross-app data lives in `Desktop\projetos\shared-data\` and apps access it via an absolute hardcoded path.
- Each app has its own data namespace inside shared-data when its data isn't truly cross-app.

## Current state

Postbell today is a standalone desktop application:

- **Shell**: Electron 42.4.0 (`Desktop\projetos\postbellelectron\`).
- **Backend**: Python 3.11 + FastAPI, packaged with PyInstaller into `postbell-backend.exe`. Source still at `Desktop\postbell2\backend\` (will be relocated when the dev folder is consolidated).
- **Frontend**: React + Vite SPA. Source still at `Desktop\postbell2\frontend\`. Built into `dist-renderer/`.
- **Storage**: SQLite + JSON + file blobs, all under one data root.

Packaging: electron-builder NSIS, target Windows x64. Installer at `dist\Postbell Setup 0.1.0.exe`.

## Data architecture

All Postbell runtime data lives under:

```
C:\Users\juanh\Desktop\projetos\shared-data\
├── (ChannelOrganizer's files — channels.json, config.json, cookies.txt, etc.)
├── thumb_cache\
├── pdfs-gerados\
└── postbell\                          ← THIS APP's namespace
    ├── postbell.db                    ← SQLite (accounts, channels, uploads, history)
    ├── settings.json                  ← Postbell-specific settings
    ├── tokens\                        ← Google OAuth tokens (per-account JSON)
    ├── logs\
    ├── temp\                          ← Upload staging area + chunked-upload chunks
    └── .migrated                      ← First-run flag, see migration.js
```

### Why this shape

- **`Desktop\projetos\shared-data\` parent**: matches the convention ChannelOrganizer already established (see `Desktop\projetos\shared-data\README.md`). Any future app the user adds will live here too, by convention.
- **`postbell/` subfolder**: Postbell's data is rich (SQL DB + multiple OAuth tokens + uploads) so it gets its own namespace rather than mixing flat JSON files in the root the way Organizer does. If a future app legitimately needs to *share* something with Postbell (e.g., consume `postbell.db`'s upload history), it reads from this subfolder via absolute path.
- **Absolute hardcoded path** (`C:\Users\juanh\Desktop\projetos\shared-data\postbell`): set in `main.js` via `app.setPath('userData', ...)` before any other code touches userData. This matches the ChannelOrganizer pattern of using `SHARED = Path(r"C:\Users\juanh\Desktop\projetos\shared-data")`. Yes it's hardcoded for one user's machine — that's the explicit design choice. This is a personal toolset, not a public distribution.

### Path threading

The redirect happens once in `main.js`:

```js
const customDataRoot = 'C:\\Users\\juanh\\Desktop\\projetos\\shared-data\\postbell';
fs.mkdirSync(customDataRoot, { recursive: true });
app.setPath('userData', customDataRoot);
```

After that, everything downstream reads through `app.getPath('userData')` (which is now the shared-data path), and the backend gets `POSTBELL_DATA_DIR=<userData>` passed in spawn env. The backend in turn derives every state path from `settings.data_dir` (see `backend/config.py`).

## Runtime architecture

Electron main process spawns two children at startup:

```
electron main
  ├── postbell-backend.exe              # Python/FastAPI, random port BACKEND_PORT
  └── built-in static HTTP server       # Node http module, random port STATIC_PORT
         ├── GET /api/*    → proxy → http://127.0.0.1:BACKEND_PORT
         ├── UPGRADE /ws/* → tunnel → http://127.0.0.1:BACKEND_PORT
         └── *             → serve from dist-renderer/ (SPA fallback to index.html)

BrowserWindow.loadURL("http://127.0.0.1:STATIC_PORT/")
```

The BrowserWindow loads the renderer from the static server URL — never `file://`. That makes the renderer same-origin with `/api` and `/ws`, so:

- Relative API calls (`fetch('/api/health')`) work as-is.
- WebSocket URLs derive from `window.location` (`ws://<host>/ws/uploads/...`).
- No CORS preflight, no `electronAPI.getBackendUrl` IPC round-trip.
- ES module `import` statements load cleanly (Chromium imposes restrictions on ES modules over `file://` — those restrictions caused a blank-screen bug in the earlier `loadFile` build).

The static server is bound to `127.0.0.1` only. It is not reachable from the LAN.

### Lifecycle

- `app.whenReady`: redirect userData → first-run migration check → pick backend port → spawn backend → poll `/api/health` (30s timeout) → pick static port → start static server → create BrowserWindow → schedule autoUpdater check (30s later).
- `before-quit`: set `isQuitting = true` → kill backend (SIGTERM → SIGKILL → `taskkill /T` on Windows) → close static server.
- Backend `exit` while not quitting → fatal modal, app exits.

## Multi-app vision (future, NOT implemented)

What the hub will need on top of what exists today:

- **Single backend per app, multiple shells**. Today every BrowserWindow has its own backend. Eventually launching Postbell while it's already running (e.g., from a hub) should connect to the existing process instead of spawning a duplicate that fights for the SQLite lock.
- **Lock file**. `C:\Users\juanh\Desktop\projetos\shared-data\postbell\postbell.lock` containing `{pid, port, started_at}`. On startup: read lock → if pid alive and port responds with `/api/health` → connect → else nuke stale lock and spawn fresh.
- **Coordinated shutdown**. When the *last* UI shell closes, the shell signals backend to shut down, then removes the lock. Other shells subscribing to the same WebSocket channel observe state changes for free.
- **Cross-app data via shared-data root**. ChannelOrganizer already lists YouTube channels (channels it consumes from). Postbell uploads to YouTube channels. There's a natural cross-app data point: a "YouTube cookies / auth" layer. Today both apps have their own; eventually they should consume a common pool stored at `shared-data\auth\` or similar.

### Decisions log

| Decision | Why |
|---|---|
| Static server + proxy instead of `loadFile` | Chromium restricts ES module loading over `file://`, which produced the blank-white-screen bug in the earlier packaged build. Same-origin HTTP sidesteps it entirely. |
| Random port, picked by kernel (`net.createServer({}).listen(0)`) | No collisions with other apps or other Postbell instances. |
| Hardcoded `C:\Users\juanh\Desktop\projetos\shared-data\postbell` path | Matches the ChannelOrganizer convention exactly (see `shared-data\README.md`). This is a personal toolset; one absolute path is simpler than overrides via env vars when the entire ecosystem lives in one known place. |
| No lock file yet | User chose "opção 1" — minimum complexity until a second postbell-aware app actually exists. Lock file becomes essential the moment a hub can launch Postbell while a standalone Postbell is also running. |
| Node built-ins only for the static server | Avoids new npm deps in the Electron bundle, keeps install size down, one fewer dependency that could break the packaged build. |
| `postbell/` subfolder inside `shared-data\` (not flat) | Organizer's data is mostly flat JSON. Postbell's data includes a SQLite DB + multiple OAuth tokens — needs its own namespace. Future apps with rich data should follow the same pattern. |

## How to add a new app to this ecosystem

Step-by-step recipe for the future you adding a third app:

1. **Source location**: drop it at `Desktop\projetos\<newapp>\` alongside `organizer\` and `postbellelectron\`.
2. **Data location**: store its data under `Desktop\projetos\shared-data\<newapp>\` (subfolder) or directly in `shared-data\` (flat files, Organizer-style) depending on richness.
3. **If it's an Electron + backend app**: copy `postbellelectron\` as a template. Rename in:
   - `package.json`: `name`, `productName`.
   - `electron-builder.json`: `appId`, `productName`, `nsis.shortcutName`.
   - `main.js`: replace the hardcoded data root, rename the backend env vars (`<APPNAME>_PORT`, `<APPNAME>_DATA_DIR`).
   - `LEGACY_DATA_PATH`: set or remove based on whether there's pre-existing data to import.
4. **If it's a Python-only app like ChannelOrganizer**: copy that one's structure (PyInstaller spec + ChannelOrganizer.exe + install.bat pattern) and use `SHARED = Path(r"C:\Users\juanh\Desktop\projetos\shared-data")` to read data.
5. **Update `Desktop\projetos\README.md`** with a section for the new app: what it does, where its exe is, where its source is, what shared-data files it touches.
6. **Update `Desktop\projetos\shared-data\README.md`** if the new app introduces new files in shared-data or new subfolders.
7. **Cross-app integration**: if the new app needs data from Postbell (or vice versa), read the relevant files via absolute paths. No HTTP between apps unless both happen to be running and you can hit the other's lock-file port.

## Pointers to code

| File | Purpose |
|---|---|
| `postbellelectron/main.js` | Electron entry; spawns backend, runs static HTTP server, drives lifecycle. The userData redirect, the proxy + WebSocket tunnel, and shutdown logic all live here. |
| `postbellelectron/preload.js` | Context-isolated IPC bridge. Currently exposes an empty `electronAPI` — kept around for future expansion. |
| `postbellelectron/migration.js` | First-run import of a legacy `data/` directory into `userData`. Gated by a `.migrated` flag. |
| `postbellelectron/electron-builder.json` | Packaging config. `extraResources` controls how `dist-backend/` ships inside the installer. |
| `postbellelectron/ARCHITECTURE.md` | This file. |
| `postbell2/backend/__main__.py` | Backend entry point used by PyInstaller. Reads `POSTBELL_PORT` and `POSTBELL_DATA_DIR` from env. (Source lives at `postbell2/` until the dev folder consolidates.) |
| `postbell2/backend/config.py` | Single source of truth for every data path the backend writes to. Derives everything from `data_dir`. |
| `postbell2/backend/main.py` | FastAPI app factory; CORS is intentionally permissive for any localhost origin so the random-port static server can hit it. |
| `postbell2/backend/services/oauth_service.py` | InstalledAppFlow Google OAuth. Tokens live in `data_dir/tokens/`. |
| `postbell2/frontend/src/api/client.ts` | `apiFetch` / `resolveWebSocketBase`. Same-origin only — works in dev (Vite proxy) and packaged (static server) identically. |
| `postbell2/frontend/src/hooks/useWebSocket.ts`, `useJob.ts` | The two consumers of `resolveWebSocketBase`. |
| `Desktop\projetos\README.md` | Hub-level index of all projects. |
| `Desktop\projetos\shared-data\README.md` | Cross-app data conventions, file formats, integration examples. |
| `Desktop\projetos\organizer\` | Reference implementation of an existing app in this ecosystem. Python + PyInstaller, simpler than Postbell. |

## Quick orientation for AI helpers

If you're a future AI being asked to extend / debug / integrate this app, start by reading in this order:

1. `Desktop\projetos\README.md` — understand the ecosystem.
2. `Desktop\projetos\shared-data\README.md` — understand the cross-app data conventions.
3. This file (`ARCHITECTURE.md`) — Postbell-specific design.
4. `postbellelectron/main.js` lines 480-540 — the userData redirect + spawn lifecycle.
5. `postbell2/backend/config.py` — how data paths flow from env to disk.

If the task is "integrate Postbell with another `projetos/` app", you almost certainly do NOT need to add HTTP between them. Read each other's files in `shared-data/` and call it a day. HTTP comes in only if both apps must be live simultaneously AND respond to each other's state changes in real time — at which point the lock-file / shared-backend design in the "Multi-app vision" section is the right answer.
