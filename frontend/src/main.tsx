import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
// Self-hosted (no Google Fonts CDN -- the portal must work on flaky links
// and inside a MikroTik walled garden). Latin subset only, the five weights
// the Savanna design uses.
import '@fontsource/plus-jakarta-sans/latin-400.css'
import '@fontsource/plus-jakarta-sans/latin-500.css'
import '@fontsource/plus-jakarta-sans/latin-600.css'
import '@fontsource/plus-jakarta-sans/latin-700.css'
import '@fontsource/plus-jakarta-sans/latin-800.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
