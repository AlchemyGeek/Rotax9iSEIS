/// <reference types="vitest/config" />
import { execSync } from 'node:child_process'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Spec 04 v0.7 §9.5: the page reads runtime.json first. In `vite` dev it
// comes from here — the local server by default (the app then talks to
// `slingology-eis serve` on 127.0.0.1:8420), the in-browser engine with
// EIS_HOST=browser (`npm run dev:browser`, after `npm run engine` has
// built the wheel into public/engine/ and staged Pyodide in public/pyodide/).
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
            pyodide_url: 'pyodide/',
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

// Which build this is (Settings → App): the package version, the commit
// it was built from, whether tracked files differed from that commit, and
// when. Stamped into the bundle as __APP_BUILD__.
function buildInfo() {
  const git = (cmd: string) => {
    try { return execSync(cmd, { cwd: import.meta.dirname, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() } catch { return '' }
  }
  const pyproject = readFileSync(resolve(import.meta.dirname, '../pyproject.toml'), 'utf8')
  return {
    version: /^version\s*=\s*"([^"]+)"/m.exec(pyproject)?.[1] ?? 'unknown',
    commit: git('git rev-parse --short=7 HEAD') || 'unknown',
    modified: git('git status --porcelain --untracked-files=no') !== '',
    built_at: new Date().toISOString(),
  }
}

// https://vite.dev/config/
export default defineConfig({
  // Relative asset paths: the built site works at any sub-path (Spec 04 §9.7).
  base: './',
  plugins: [react(), devRuntime()],
  worker: { format: 'es' },
  define: { __APP_BUILD__: JSON.stringify(buildInfo()) },
  test: {
    environment: 'jsdom',
    globals: true,
    // Spec 15 §9: theme/brand.test.ts reads index.css as text (?raw);
    // without this vitest hands every CSS import back empty.
    css: { include: [/index\.css/] },
  },
})
