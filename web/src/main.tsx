import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// IBM Plex, bundled with the app rather than fetched from Google Fonts: the
// page loads nothing from anywhere but its own site (Spec 04 §9.7).
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-sans/latin-700.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import '@fontsource/ibm-plex-mono/latin-600.css'
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
