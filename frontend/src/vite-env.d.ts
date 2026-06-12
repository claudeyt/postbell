/// <reference types="vite/client" />

// Surface exposed by postbell-electron/preload.js via contextBridge.
// Only present when the SPA is running inside the Electron shell — pure
// browser builds leave `window.electronAPI` undefined.
declare global {
  interface Window {
    electronAPI?: {
      getBackendUrl: () => Promise<string>
    }
  }
}

export {}
