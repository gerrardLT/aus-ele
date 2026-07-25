import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { resolveRootPage } from './lib/pageRouter.js'
import { FilterProvider } from './contexts/FilterContext'
import { ThemeProvider } from './contexts/ThemeContext'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // 30s — matches apiClient cache TTL
      gcTime: 5 * 60_000,      // 5min — garbage collect after 5min unused
      retry: 1,                // 1 retry on failure
      refetchOnWindowFocus: false,
    },
  },
})

const rootPage = resolveRootPage(globalThis.location?.pathname || '/')
const MarketPage = lazy(() => import('./pages/MarketPage.jsx'))
const FinlandPage = lazy(() => import('./pages/FinlandPage.jsx'))
const FingridPage = lazy(() => import('./pages/FingridPage.jsx'))
const DeveloperPortalPage = lazy(() => import('./pages/DeveloperPortalPage.jsx'))
const AgentPage = lazy(() => import('./pages/AgentPage.jsx'))

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
        : rootPage === 'agent'
          ? <AgentPage />
          : <FilterProvider><MarketPage market="NEM" /></FilterProvider>

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <Suspense fallback={<BootFallback />}>
          {rootElement}
        </Suspense>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
