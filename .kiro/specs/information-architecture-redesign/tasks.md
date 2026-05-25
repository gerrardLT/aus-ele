# Implementation Plan: Information Architecture Redesign

## Overview

将 AEMO Intelligence 平台从平铺模块列表重构为决策漏斗（Decision Funnel）信息架构。实现分为四个阶段：后端聚合 API → 共享 UI 组件 + 前端重构 → 导航 + 渐进式披露 → WEM 一致性 + 响应式布局。

## Tasks

- [x] 1. Backend Aggregation API
  - [x] 1.1 Create market-summary endpoint and stage computation logic
    - Create `backend/routes/aggregation_routes.py` with GET `/api/market-summary/{market}/{region}` endpoint
    - Define Pydantic response models: `MarketSummaryResponse`, `StageSummaryData`, `KpiMetric`, `Warning`
    - Implement query parameters: `year`, `bess_power_mw`, `bess_duration_hours`, `bess_efficiency`
    - Implement stage computation functions that call existing engines (PriceAnalysisEngine, RevenueAnalysisEngine, bess_backtest)
    - Implement per-stage fault tolerance: catch exceptions per stage, return partial results with `warnings` array
    - Derive `overall_rating` from available stage sentiments
    - Include `metadata` object conforming to existing API response contract
    - Register route in FastAPI app
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.2 Create stage-summary endpoint
    - Add GET `/api/stage-summary/{market}/{region}/{stage_id}` endpoint to `aggregation_routes.py`
    - Validate `stage_id` against allowed values: `market-opportunity`, `opportunity-identification`, `revenue-estimation`, `investment-decision`
    - Return `summary_text`, `sentiment`, and 2-4 `kpis` for the requested stage
    - Ensure response time within 2 seconds by querying only the relevant stage's data sources
    - _Requirements: 7.1, 7.2_

  - [x] 1.3 Add Redis caching for aggregation endpoints
    - Implement cache-aside pattern: check Redis before computation, store with 6-hour TTL
    - Cache key format: `market-summary:{market}:{region}:{year}:{bess_params_hash}`
    - Invalidate cache on data refresh events
    - Ensure partial-result responses are NOT cached (only full successful responses)
    - _Requirements: 6.2_

  - [x]* 1.4 Write property tests for API response contract (Hypothesis)
    - **Property 7: Market-summary API response contract**
    - Test that for any valid combination of market, region, year, and bess_params, the response contains all required fields
    - Generator: `st.sampled_from(['NEM', 'WEM'])`, `st.sampled_from(REGIONS)`, `st.integers(2020, 2026)`, `st.floats(50, 500)`
    - **Validates: Requirements 6.3, 6.4**

  - [x]* 1.5 Write property tests for stage conclusion structure (Hypothesis)
    - **Property 4: Stage conclusion response structure**
    - Test that any valid stage-summary response contains non-empty `summary_text` and `kpis` array with 2-4 items
    - Generator: `st.sampled_from(VALID_STAGES)`, `st.sampled_from(REGIONS)`
    - **Validates: Requirements 3.2, 3.3**

  - [x]* 1.6 Write property tests for partial results graceful degradation (Hypothesis)
    - **Property 8: Partial results graceful degradation**
    - Mock various data source failures and verify API returns HTTP 200 with partial results and non-empty `warnings`
    - Generator: `st.sets(st.sampled_from(DATA_SOURCES))` for failure combinations
    - **Validates: Requirements 6.5**

- [x] 2. Shared UI Components
  - [x] 2.1 Create KpiCard component
    - Create `web/src/components/funnel/KpiCard.jsx`
    - Implement props: `label`, `value`, `unit`, `sentiment`, `onClick`, `size` (sm/md)
    - Apply semantic color mapping: positive → green, negative → red, warning → amber, neutral → default text
    - Support click handler for Executive Summary navigation
    - Implement `sm` size for StageConclusion and `md` size for ExecutiveSummary
    - _Requirements: 2.5, 3.3_

  - [x]* 2.2 Write property test for semantic color mapping (fast-check)
    - **Property 3: Semantic color mapping correctness**
    - Test that for any sentiment value, KpiCard applies exactly the corresponding color class
    - Generator: `fc.oneof(fc.constant('positive'), fc.constant('negative'), fc.constant('warning'), fc.constant('neutral'))`
    - **Validates: Requirements 2.5**

  - [x] 2.3 Create CollapsibleModule component
    - Create `web/src/components/funnel/CollapsibleModule.jsx`
    - Implement collapsed state: show module title + one-line metric summary
    - Implement expanded state: reveal full module content with 200ms Framer Motion animation
    - Use React.lazy + Suspense for lazy-loading module content on first expand
    - Persist expand/collapse state to `sessionStorage` keyed by `moduleId`
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 2.4 Create StageConclusion component
    - Create `web/src/components/funnel/StageConclusion.jsx`
    - Display one-sentence summary text with serif font (Playfair Display)
    - Render 2-4 KpiCard (size=sm) below summary
    - Apply border-left color based on sentiment
    - Show loading state with descriptive message (e.g., "正在计算套利窗口...")
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 2.5 Create FunnelStage component
    - Create `web/src/components/funnel/FunnelStage.jsx`
    - Render stage header: number badge, title, core question (Chinese primary + English annotation)
    - Core question in muted color, smaller font below title
    - Contain StageConclusion panel at top
    - Wrap children (CollapsibleModule instances) below conclusion
    - Provide "展开全部 / 收起全部" toggle button
    - Apply `opacity-60` when `isDeemphasized` prop is true
    - Register IntersectionObserver for scroll-spy
    - _Requirements: 1.4, 4.4, 8.1, 8.2, 8.3_

  - [x]* 2.6 Write property test for de-emphasis propagation (fast-check)
    - **Property 5: De-emphasis propagation**
    - Test that for any stage with negative sentiment, all subsequent stages are de-emphasized and prior stages are not
    - Generator: `fc.array(fc.oneof(fc.constant('positive'), fc.constant('negative'), fc.constant('neutral')), {minLength: 4, maxLength: 4})`
    - **Validates: Requirements 3.5**

- [x] 3. Checkpoint - Backend API and shared components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Executive Summary and Market Page Restructuring
  - [x] 4.1 Create ExecutiveSummary component
    - Create `web/src/components/funnel/ExecutiveSummary.jsx`
    - Fetch data from `/api/market-summary/{market}/{region}` on mount and filter change
    - Render 4-6 KpiCard (size=md) in responsive row/grid layout
    - Implement skeleton loading state while data is in flight
    - Implement debounced fetch (update within 2 seconds of filter change)
    - Handle click on KPI card → scroll to corresponding FunnelStage via smooth scroll
    - Handle error state with retry button ("重试")
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [x] 4.2 Refactor NEM Market Page (App.jsx) into Decision Funnel structure
    - Restructure App.jsx to render: ExecutiveSummary → FunnelStage×4
    - Assign existing modules to stages per design: Stage 1 (PriceChart, SummaryStats, HourlyDistributionChart), Stage 2 (PeakAnalysis, FcasAnalysis, ChargingWindow, GridForecast), Stage 3 (BessSimulator, RevenueStacking, CycleCost), Stage 4 (InvestmentAnalysis, ReportPreview)
    - Wrap each module in CollapsibleModule with appropriate `title` and `metricSummary`
    - Wire each FunnelStage to fetch its stage-summary data independently
    - Preserve all existing filter controls (region, year, quarter, day type, month) and their behavior
    - Implement `FunnelPageState` via useReducer for coordinated state management
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 11.1, 11.2_

  - [x]* 4.3 Write property test for module-to-stage assignment uniqueness (fast-check)
    - **Property 2: Module-to-stage assignment uniqueness**
    - Test that every module appears in exactly one stage and the union equals the complete module registry
    - Generator: arbitrary module lists to verify the mapping function
    - **Validates: Requirements 1.3**

  - [x]* 4.4 Write unit tests for Executive Summary and FunnelStage rendering
    - Test NEM page renders 4 stages in correct DOM order
    - Test Executive Summary renders above all stages
    - Test KPI click scrolls to correct stage
    - Test module assignment matches spec exactly
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.6_

- [x] 5. Navigation Restructuring
  - [x] 5.1 Restructure SidebarNavigation into three groups
    - Modify existing sidebar component to organize items into: "BESS 投资分析" (NEM, WEM), "研究工具" (Finland, Fingrid with `opacity-60` + smaller text), "系统" (Developer Portal)
    - Apply visual distinction: primary group full opacity, secondary group reduced opacity/smaller text
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7_

  - [x] 5.2 Implement in-page stage navigation links
    - Add stage links section to sidebar when on a Market Page: Executive Summary + 4 stage links
    - Implement smooth scroll to stage on link click via `onStageClick`
    - _Requirements: 5.5_

  - [x] 5.3 Implement ScrollSpy for active stage highlighting
    - Use IntersectionObserver to detect currently visible FunnelStage
    - Update `activeStage` state and highlight corresponding sidebar link
    - _Requirements: 5.6_

- [x] 6. Progressive Disclosure Polish
  - [x] 6.1 Implement stage de-emphasis logic
    - Derive `deemphasizedStages` from stage sentiments: if stage N has negative sentiment, stages N+1 through 4 get `opacity-60`
    - Wire into FunnelStage `isDeemphasized` prop
    - _Requirements: 3.5_

  - [x] 6.2 Implement expand/collapse sessionStorage persistence
    - Create utility functions: `saveExpandState(market, region, state)` and `loadExpandState(market, region)`
    - Storage key format: `funnel-expand-state-{market}-{region}`
    - Restore persisted state on page load
    - _Requirements: 4.5_

  - [x]* 6.3 Write property test for expand/collapse persistence round-trip (fast-check)
    - **Property 6: Expand/collapse persistence round-trip**
    - Test that writing expand state to sessionStorage and reading it back produces identical state
    - Generator: `fc.dictionary(fc.string(), fc.boolean())`
    - **Validates: Requirements 4.5**

- [x] 7. Checkpoint - Core funnel functionality complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. WEM Page Consistency
  - [x] 8.1 Apply Decision Funnel structure to WEM page
    - Refactor WemPage.jsx to use same FunnelStage structure as NEM page
    - Render ExecutiveSummary + 4 FunnelStages with same layout and interaction patterns
    - Wire to `/api/market-summary/WEM/{region}` and `/api/stage-summary/WEM/{region}/{stage_id}`
    - _Requirements: 9.1, 9.2_

  - [x] 8.2 Add placeholder modules for unsupported WEM features
    - For modules not available in WEM (due to data limitations), render a placeholder component
    - Placeholder shows module name + explanation of why it's not yet supported for WEM
    - _Requirements: 9.3_

  - [x] 8.3 Implement WEM in-page navigation
    - Apply same stage-level in-page navigation and scroll-spy to WEM page
    - _Requirements: 9.4_

- [x] 9. Responsive Layout and Legacy Support
  - [x] 9.1 Implement responsive breakpoints for Executive Summary and navigation
    - ≥ 1280px: KPI cards in horizontal row, sidebar visible with stage links
    - 1024-1279px: KPI cards in 2×2 grid, sidebar visible
    - < 1024px: KPI cards stacked vertically, sidebar hidden, top navigation bar displayed
    - Maintain sequential stage ordering at all viewport widths
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 9.2 Implement legacy bookmark redirect mapping
    - Create mapping from legacy URL hash fragments (e.g., `#peak-analysis`, `#bess-simulator`) to new locations (stage ID + module ID)
    - On page load, check `window.location.hash` and scroll to equivalent module in its assigned FunnelStage
    - Auto-expand the target CollapsibleModule if it's collapsed
    - _Requirements: 11.4_

  - [x]* 9.3 Write property test for bookmark redirect mapping (fast-check)
    - **Property 9: Bookmark redirect mapping**
    - Test that for any legacy hash fragment, the mapping produces a valid stage + module location
    - Generator: `fc.oneof(...LEGACY_HASHES)`
    - **Validates: Requirements 11.4**

  - [x]* 9.4 Write property test for stage ordering invariant (fast-check)
    - **Property 1: Stage ordering invariant**
    - Test that for any viewport width and data state combination, stages render in DOM order 1→2→3→4 with Executive Summary preceding all
    - Generator: `fc.integer({min: 320, max: 2560})` for viewport, `fc.array(fc.oneof(...states))` for data states
    - **Validates: Requirements 1.2, 10.4**

  - [x]* 9.5 Write integration tests for backward compatibility
    - Verify all existing backend API endpoints still respond correctly
    - Verify all existing filter controls work within reorganized layout
    - Verify all modules render correctly within FunnelStage containers
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 10. Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Frontend uses fast-check for property-based testing, backend uses Hypothesis
- Checkpoints ensure incremental validation at key milestones
- All existing module functionality is preserved — modules are reorganized, not rewritten
- Backend aggregation endpoints reuse existing engines (PriceAnalysisEngine, RevenueAnalysisEngine, bess_backtest)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "2.5", "2.6"] },
    { "id": 3, "tasks": ["4.1", "4.2", "5.1"] },
    { "id": 4, "tasks": ["4.3", "4.4", "5.2", "5.3", "6.1", "6.2"] },
    { "id": 5, "tasks": ["6.3", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "9.1", "9.2"] },
    { "id": 7, "tasks": ["9.3", "9.4", "9.5"] }
  ]
}
```
