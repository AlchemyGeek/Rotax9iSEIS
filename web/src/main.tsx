import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { getRuntime } from './lib/engineClient'

// For end-to-end checks (spike/browser-host): the chosen host and client.
;(window as unknown as { __eis: unknown }).__eis = { getRuntime }

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
