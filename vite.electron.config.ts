import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// __dirname shim for ESM
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const frontendDir = path.resolve(__dirname, 'frontend')

// Reuse the existing React SPA at ../frontend as-is. We point Vite's `root`
// at the frontend folder so it picks up its index.html, src/, tailwind.config.js
// and postcss.config.js automatically.
//
// `base: './'` is REQUIRED for Electron: assets must be loaded via relative
// URLs because the renderer runs from file:// in production.
//
// Output goes to postbell-electron/dist-renderer/ (absolute path so it lands
// next to main.js no matter where Vite resolves it).
export default defineConfig({
  root: frontendDir,
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror the frontend's tsconfig.json `paths` entry "@/*" -> "src/*"
      '@': path.resolve(frontendDir, 'src'),
    },
  },
  css: {
    // Inline the PostCSS pipeline here instead of letting Vite auto-discover
    // frontend/postcss.config.js. The frontend's tailwind.config.js uses
    // relative `content` globs ("./index.html", "./src/**/*"), which Tailwind
    // resolves against process.cwd(). When invoked from postbell-electron/
    // those globs miss everything and Tailwind purges all utility classes
    // (CSS shrinks from ~23 kB to ~5 kB). Passing absolute content paths to
    // a fresh Tailwind plugin instance bypasses that resolution entirely.
    postcss: {
      plugins: [
        tailwindcss({
          content: [
            path.resolve(frontendDir, 'index.html'),
            path.resolve(frontendDir, 'src/**/*.{js,ts,jsx,tsx}'),
          ],
          theme: { extend: {} },
          plugins: [],
        }),
        autoprefixer(),
      ],
    },
  },
  build: {
    outDir: path.resolve(__dirname, 'dist-renderer'),
    emptyOutDir: true,
  },
})
