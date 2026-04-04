import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'fs'
import { join } from 'path'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// Read version from project root
const version = readFileSync(join(__dirname, '../VERSION'), 'utf-8').trim();

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  // When building for FastAPI serving: base = '/ui/'
  // When deploying to GitHub Pages: base = '/ObservaKit/'
  base: process.env.VITE_BUILD_SERVE === 'fastapi' ? '/ui/' : '/ObservaKit/',
  build: {
    // Output to backend/static so FastAPI can serve at /ui
    outDir: process.env.VITE_BUILD_SERVE === 'fastapi'
      ? '../backend/static'
      : 'dist',
    emptyOutDir: true,
  },
  server: {
    // Proxy API calls to backend during local development
    proxy: {
      '/status':    { target: 'http://localhost:8000', changeOrigin: true },
      '/checks':    { target: 'http://localhost:8000', changeOrigin: true },
      '/suppress':  { target: 'http://localhost:8000', changeOrigin: true },
      '/profiling': { target: 'http://localhost:8000', changeOrigin: true },
      '/webhooks':  { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
