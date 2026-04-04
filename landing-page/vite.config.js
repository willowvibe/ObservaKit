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
  base: '/ObservaKit/'
})
