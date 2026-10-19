/// <reference types="vitest/config" />
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Spec 04 v0.7 §9.5: the page reads runtime.json first. In `vite` dev it
// comes from here — the local server by default (the app then talks to
// `slingology-eis serve` on 127.0.0.1:8420), the in-browser engine with
// EIS_HOST=browser (`npm run dev:browser`, after `npm run engine` has
// built the wheel into public/engine/).
function devRuntime(): Plugin {
  return {
    name: 'eis-dev-runtime',
    configureServer(server) {
      server.middlewares.use('/runtime.json', (_req, res) => {
        let body: unknown = { host: 'server' }
        if (process.env.EIS_HOST === 'browser') {
          const wheel = readdirSync(resolve(import.meta.dirname, 'public/engine')).find((f) => f.endsWith('.whl'))
          body = {
            host: 'browser',
            pyodide: readFileSync(resolve(import.meta.dirname, '../PYODIDE_VERSION'), 'utf8').trim(),
            engine_wheel: `engine/${wheel}`,
          }
        }
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-store')
        res.end(JSON.stringify(body))
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), devRuntime()],
  worker: { format: 'es' },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
