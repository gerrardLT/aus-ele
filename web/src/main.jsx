import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import FingridPage from './pages/FingridPage.jsx'
import { resolveRootPage } from './lib/pageRouter.js'

const rootElement = resolveRootPage(globalThis.location?.pathname || '/') === 'fingrid'
  ? <FingridPage />
  : <App />

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {rootElement}
  </StrictMode>,
)
