import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import FingridPage from './pages/FingridPage.jsx'
import DeveloperPortalPage from './pages/DeveloperPortalPage.jsx'
import { resolveRootPage } from './lib/pageRouter.js'

const rootPage = resolveRootPage(globalThis.location?.pathname || '/')
const rootElement = rootPage === 'fingrid'
  ? <FingridPage />
  : rootPage === 'developer'
    ? <DeveloperPortalPage />
    : <App />

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {rootElement}
  </StrictMode>,
)
