import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { getRuntime } from './lib/engineClient'

// End-to-end checks only (spike/browser-host, built with VITE_E2E=1): the
// chosen host and client. Not in a shipped build.
if (import.meta.env.VITE_E2E === '1') {
  ;(window as unknown as { __eis: unknown }).__eis = { getRuntime }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
