// Electron preload script — runs in an isolated context with access to a
// limited subset of Node.js / Electron APIs, and exposes a tiny, safe surface
// to the renderer via `window.electronAPI`.
//
// As of the static-server refactor the renderer no longer needs to ask main
// for the backend URL: it's served from a local static HTTP server that also
// proxies /api and /ws, so same-origin relative URLs just work. We keep an
// empty `electronAPI` object exposed so existing presence checks in the
// renderer (e.g. `if (window.electronAPI)`) and future IPC additions have a
// stable surface to attach to.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {});
