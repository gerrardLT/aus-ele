import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { resolveRootPage } from './lib/pageRouter.js'
import { FilterProvider } from './contexts/FilterContext'

const rootPage = resolveRootPage(globalThis.location?.pathname || '/')
const MarketPage = lazy(() => import('./pages/MarketPage.jsx'))
const FinlandPage = lazy(() => import('./pages/FinlandPage.jsx'))
const FingridPage = lazy(() => import('./pages/FingridPage.jsx'))
const DeveloperPortalPage = lazy(() => import('./pages/DeveloperPortalPage.jsx'))

function BootFallback() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-6 text-sm text-[var(--color-muted)]">
        Loading workspace...
      </div>
    </div>
  )
}

const rootElement = rootPage === 'wem'
  ? <FilterProvider><MarketPage market="WEM" /></FilterProvider>
  : rootPage === 'finland'
    ? <FinlandPage />
    : rootPage === 'fingrid'
      ? <FingridPage />
      : rootPage === 'developer'
        ? <DeveloperPortalPage />
        : <FilterProvider><MarketPage market="NEM" /></FilterProvider>

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Suspense fallback={<BootFallback />}>
      {rootElement}
    </Suspense>
  </StrictMode>,
)
