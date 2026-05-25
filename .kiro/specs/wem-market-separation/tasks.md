# Implementation Plan: WEM Market Separation

## Overview

将 WEM 从 NEM 的区域列表中分离为独立页面，包括：更新路由、创建 WemPage、提取共享侧边栏导航、创建 WEM 专属 ESS 分析组件、参数化共享组件。实现按增量方式推进，每步可验证。

## Tasks

- [x] 1. Create market config module and update page router
  - [x] 1.1 Create `web/src/lib/marketConfig.js` with NEM and WEM market configurations
    - Define MARKET_CONFIGS object with id, label, regions, settlementIntervalMinutes, timezone, timezoneLabel, currency, ancillaryServiceType, ancillaryServices, defaultRegion, path
    - Export `getMarketConfig(marketId)` helper function
    - NEM regions: ['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1'] (no WEM)
    - WEM config: 30-min interval, AWST timezone, ESS services
    - _Requirements: 2.1, 2.2, 4.1, 6.3, 6.4_

  - [x] 1.2 Update `web/src/lib/pageRouter.js` to add `/wem` route
    - Add `if (pathname.startsWith('/wem')) return 'wem';` before the finland check
    - Ensure existing routes remain unchanged
    - _Requirements: 1.1_

  - [ ]* 1.3 Write property tests for pageRouter and marketConfig
    - **Property 1: Route Resolution Determinism** — For any path starting with /wem, resolveRootPage returns 'wem'
    - **Property 2: Market Config Completeness** — For any market config, all required fields are present with valid values
    - **Property 3: NEM Region Exclusion** — NEM regions array does not contain 'WEM'
    - **Property 4: Navigation Path Consistency** — Each market config path resolves correctly via pageRouter
    - **Validates: Requirements 1.1, 2.1, 2.2, 6.3, 6.4**

- [x] 2. Extract SidebarNavigation as shared component
  - [x] 2.1 Create `web/src/components/SidebarNavigation.jsx`
    - Extract the `<aside>` sidebar from App.jsx into a standalone component
    - Props: activePage, sectionLinks, activeSection, onSectionClick, lang
    - Add "澳洲市场" group with NEM (`/`) and WEM (`/wem`) as sibling nav items
    - Keep "其他入口" group with Finland, Fingrid, Developer links
    - Highlight active page based on `activePage` prop
    - Use `<a href>` for cross-page navigation (full page reload)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2_

  - [x] 2.2 Update `web/src/App.jsx` to use extracted SidebarNavigation
    - Import SidebarNavigation component
    - Replace inline `<aside>` with `<SidebarNavigation activePage="aemo" ... />`
    - Remove WEM from the REGIONS array: change to `['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1']`
    - Pass sectionLinks, activeSection, onSectionClick, lang props
    - _Requirements: 2.1, 2.2, 5.5, 8.1_

  - [ ]* 2.3 Write property test for SidebarNavigation active state
    - **Property 5: Sidebar Active State Consistency** — For any activePage value, exactly one nav item is highlighted
    - **Validates: Requirements 5.4, 5.5**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Verify NEM page still works correctly without WEM in regions
  - Verify sidebar renders correctly on NEM page

- [x] 4. Create WemPage with basic structure
  - [x] 4.1 Create `web/src/pages/WemPage.jsx`
    - Import and use FilterContext (wrapped by parent in main.jsx)
    - Import SidebarNavigation with `activePage="wem"`
    - Define WEM-specific section links (e.g., stage-wem-market, stage-wem-ess, stage-wem-capacity)
    - Set up basic page layout matching App.jsx structure (sidebar + main content area)
    - Initialize with WEM market config defaults (region='WEM', 30-min interval)
    - Use same design system: font-serif headings, font-sans body, CSS variables
    - Add language toggle (zh/en) matching App.jsx pattern
    - _Requirements: 1.2, 1.4, 5.4, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 4.2 Update `web/src/main.jsx` to add WEM route
    - Add `const WemPage = lazy(() => import('./pages/WemPage.jsx'))`
    - Add `rootPage === 'wem'` case in the rootElement ternary
    - Wrap WemPage in `<FilterProvider>` (same as App)
    - Ensure Suspense fallback covers WemPage loading
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 4.3 Add WEM price data fetching and PriceChart to WemPage
    - Fetch price-trend data with `interval_minutes=30` and `region=WEM`
    - Render PriceChart component with WEM data
    - Use AWST timezone labels on X-axis
    - Add year/filter controls (reuse filter pattern from App.jsx)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.4 Write property test for WEM settlement interval enforcement
    - **Property 6: WEM Settlement Interval Enforcement** — For any WEM price request, interval_minutes=30 is included
    - **Validates: Requirements 4.1, 4.2**

- [x] 5. Create WEM ESS analysis component
  - [x] 5.1 Create `web/src/components/wem/WemEssAnalysis.jsx`
    - Display 5 ESS service types: Regulation Raise, Regulation Lower, Contingency Raise, Contingency Lower, RoCoF
    - Fetch data from `/fcas-analysis?region=WEM` (backend already supports this)
    - Show price trend chart (AreaChart with Recharts)
    - Show service breakdown bar chart
    - Show hourly distribution chart
    - Show summary KPI cards (total avg price, estimated revenue, viable services)
    - Show constraint binding frequency analysis
    - Include error state with reason and suggested action
    - Use same visual patterns as FcasAnalysis (design system compliance)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.1_

  - [x] 5.2 Create `web/src/components/wem/WemCapacityAnalysis.jsx`
    - Display capacity credit and capacity price data
    - Show capacity price trend chart
    - Show storage capacity credit estimation
    - Handle data unavailable state gracefully
    - _Requirements: 7.2, 7.3, 7.4_

  - [x] 5.3 Integrate WemEssAnalysis and WemCapacityAnalysis into WemPage
    - Add ESS analysis section with DeferredSection for lazy rendering
    - Add capacity analysis section
    - Wire up year/region/filter props from WemPage state
    - _Requirements: 3.1, 7.1, 7.2_

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Verify WEM page loads at /wem with ESS analysis
  - Verify NEM page no longer shows WEM region

- [x] 7. Integrate shared components and finalize navigation
  - [x] 7.1 Add InvestmentAnalysis to WemPage with WEM market parameters
    - Pass WEM-specific params: 30-min interval, AWST timezone, WEM region
    - Ensure component renders correctly with WEM data
    - _Requirements: 6.1, 6.3_

  - [x] 7.2 Add DataQualityBadge to WemPage sections
    - Pass WEM metadata (data_grade, regulatory_scope='WEM', coverage_mode)
    - _Requirements: 6.2, 6.3_

  - [x] 7.3 Ensure browser history navigation works
    - Verify `<a href="/wem">` and `<a href="/">` links in SidebarNavigation
    - Browser back/forward triggers full page reload to correct route
    - Ensure page transition is consistent with existing navigation pattern
    - _Requirements: 8.3, 8.4_

- [x] 8. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Verify complete flow: NEM → WEM navigation via sidebar
  - Verify WEM page shows ESS (not FCAS), 30-min intervals, AWST timezone
  - Verify NEM page shows only 5 NEM regions
  - Verify browser back/forward works between pages

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The backend already supports WEM ESS data via `/fcas-analysis?region=WEM` — no backend changes needed
- SidebarNavigation extraction is the largest refactoring step; test NEM page thoroughly after
- WemCapacityAnalysis may need a new backend endpoint if capacity data isn't yet served — handle gracefully with "data unavailable" state
