import { Fragment, StrictMode, Suspense, lazy, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { useRoute } from './hooks/useRoute.js'
import { FilterProvider } from './contexts/FilterContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { GlobalErrorBoundary } from './components/GlobalErrorBoundary'
import { capture, initAnalytics } from './lib/analytics.js'

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

// 分析 SDK 只在 flag 打开时才会被注入（lib/analytics.js 关闭态零副作用）。这里不 await、
// 不重试、不抛错：采集失败绝不能变成页面打不开。
initAnalytics(import.meta.env)
// page_view 原来是在模块加载期打一次的。R3.3 把导航改成 SPA 之后那样做会静默失效 ——
// 首屏之后再也不会有第二条 page_view，激活漏斗的「看过几个页面」全部塌成 1，而所有测试
// 依旧全绿。所以把它挪进路由订阅里，与地址栏的实际变化同源。
const MarketPage = lazy(() => import('./pages/MarketPage.jsx'))
const FinlandPage = lazy(() => import('./pages/FinlandPage.jsx'))
const FingridPage = lazy(() => import('./pages/FingridPage.jsx'))
const DeveloperPortalPage = lazy(() => import('./pages/DeveloperPortalPage.jsx'))
const AgentPage = lazy(() => import('./pages/AgentPage.jsx'))
const LoginPage = lazy(() => import('./pages/LoginPage.jsx'))
const RegisterPage = lazy(() => import('./pages/RegisterPage.jsx'))
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage.jsx'))
const InviteAcceptPage = lazy(() => import('./pages/InviteAcceptPage.jsx'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage.jsx'))
const AccountPage = lazy(() => import('./pages/AccountPage.jsx'))
const PricingPage = lazy(() => import('./pages/PricingPage.jsx'))
const LegalPage = lazy(() => import('./pages/LegalPage.jsx'))
const ReportsPage = lazy(() => import('./pages/ReportsPage.jsx'))
const HelpPage = lazy(() => import('./pages/HelpPage.jsx'))
// R3 全局外壳（移动抽屉 + ⌘K）。lazy 是硬性要求而不是优化：AppChrome 静态引 SidebarNavigation
// 那张导航表，而 CommandPalette 又带着一份 OpenAPI 解析器 —— 两者都不该在首屏关键路径上。
const AppChrome = lazy(() => import('./components/AppChrome.jsx'))

function BootFallback() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-6 text-sm text-[var(--color-muted)]">
        Loading workspace...
      </div>
    </div>
  )
}

function renderRoute(rootPage) {
  return rootPage === 'wem'
  ? <FilterProvider><GlobalErrorBoundary><MarketPage market="WEM" /></GlobalErrorBoundary></FilterProvider>
  : rootPage === 'finland'
    ? <GlobalErrorBoundary><FinlandPage /></GlobalErrorBoundary>
    : rootPage === 'fingrid'
      ? <GlobalErrorBoundary><FingridPage /></GlobalErrorBoundary>
      : rootPage === 'developer'
        ? <GlobalErrorBoundary><DeveloperPortalPage /></GlobalErrorBoundary>
        : rootPage === 'agent'
          ? <GlobalErrorBoundary><AgentPage /></GlobalErrorBoundary>
          : rootPage === 'login'
            ? <GlobalErrorBoundary><LoginPage /></GlobalErrorBoundary>
            : rootPage === 'invite'
              ? <GlobalErrorBoundary><InviteAcceptPage /></GlobalErrorBoundary>
              : rootPage === 'forgot'
                ? <GlobalErrorBoundary><ForgotPasswordPage /></GlobalErrorBoundary>
                : rootPage === 'account'
                ? <GlobalErrorBoundary><AccountPage /></GlobalErrorBoundary>
                : rootPage === 'pricing'
                  ? <GlobalErrorBoundary><PricingPage /></GlobalErrorBoundary>
                  : rootPage === 'legal'
                    ? <GlobalErrorBoundary><LegalPage /></GlobalErrorBoundary>
                    : rootPage === 'reports'
                      ? <GlobalErrorBoundary><ReportsPage /></GlobalErrorBoundary>
                      : rootPage === 'help'
                        ? <GlobalErrorBoundary><HelpPage /></GlobalErrorBoundary>
                        : rootPage === 'register'
                          ? <GlobalErrorBoundary><RegisterPage /></GlobalErrorBoundary>
                          : rootPage === 'verifyEmail'
                            ? <GlobalErrorBoundary><VerifyEmailPage /></GlobalErrorBoundary>
                            : <FilterProvider><GlobalErrorBoundary><MarketPage market="NEM" /></GlobalErrorBoundary></FilterProvider>
}

/**
 * R3.3：路由从「模块加载期求值一次」变成「订阅 routeStore」。
 *
 * `key={route.page}` 是刻意的：NEM/WEM 两页共用 MarketPage，仅换 props 时 React 会复用
 * 同一棵子树，而页内若干状态是在挂载时一次性读取的；不给 key 就等于把「切市场」从整页加载
 * 变成组件复用 —— 那是一次静默的行为变更。给 key 后语义与改造前完全一致（等价于重新挂载）。
 */
function Root() {
  const route = useRoute()
  useEffect(() => {
    // 只带路由名，不带查询串：查询串里可能有用户输入的 region/keyword，那属于自由文本。
    capture('page_view', { page: route.page || 'nem' }, import.meta.env)
  }, [route.page])
  return (
    <Suspense fallback={<BootFallback />}>
      {/* key 挂在 Fragment 上而不是包一层 div：包 div 会改 #root 的直接子节点，
          而全站若干高度/布局样式是按「页面自己就是根」写的。Fragment 不留 DOM 痕迹。 */}
      <Fragment key={route.page}>{renderRoute(route.page)}</Fragment>
      {/* R3 chrome（移动抽屉 + ⌘K）挂在路由之外：PageShell 只覆盖 MarketPage，而「手机上
          没有导航」在所有页面都成立。AppChrome 自己再 lazy 引 CommandPalette，两层分开 ——
          fallback={null}：外壳晚一帧出现不影响内容，反之若用 BootFallback 会让整页在
          chrome 加载期间被遮成「加载中」。 */}
      <Suspense fallback={null}>
        <AppChrome />
      </Suspense>
    </Suspense>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <Root />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
