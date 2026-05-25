# Implementation Plan: Frontend Rewrite

## Overview

将 App.jsx（1000+ 行）和 WemPage.jsx 合并为统一的 MarketPage 组件，通过配置驱动市场差异化渲染。实现分三个阶段：基础设施（无破坏性）、新组件创建（并行）、切换与清理（破坏性）。每个新文件 < 200 行，不引入新依赖。

## Tasks

- [x] 1. Phase 1: 基础设施（无破坏性变更）
  - [x] 1.1 扩展 marketConfig.js 添加 stages 配置
    - 在 `web/src/lib/marketConfig.js` 中为 NEM 和 WEM 配置对象添加 `stages` 字段
    - NEM stages: market-opportunity (PriceChart, SummaryStats, HourlyDistributionChart), opportunity-identification (PeakAnalysis, FcasAnalysis, ChargingWindow, GridForecast), revenue-estimation (BessSimulator, RevenueStacking, CycleCost), investment-decision (InvestmentAnalysis, ReportPreview)
    - WEM stages: market-opportunity (PriceChart, SummaryStats), opportunity-identification (WemEssAnalysis), revenue-estimation (WemCapacityAnalysis), investment-decision (InvestmentAnalysis)
    - 添加 STAGE_DEFINITIONS 常量（双语 title + coreQuestion）
    - 添加 MODULE_REGISTRY 映射表
    - _Requirements: 2.1, 2.3, 11.3_

  - [ ]* 1.2 Write property test for market config completeness
    - **Property 1: 市场配置完整性**
    - 对任意有效 market ID，stages 配置包含全部 4 个 stage 且 modules 非空
    - 使用 fast-check 生成 market ID 并验证
    - **Validates: Requirements 2.1, 2.3**

  - [x] 1.3 创建 useMarketData.js hook
    - 创建 `web/src/hooks/useMarketData.js`
    - 从 App.jsx 提取价格数据获取逻辑
    - 接受 config 和 filters 参数，返回 { chartData, visibleData, loading, error, onWindowChange }
    - 使用 config.settlementIntervalMinutes 作为 interval_minutes 参数
    - 处理 API 错误：设置 error 状态，loading 设为 false
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 1.4 Write property test for useMarketData filter propagation
    - **Property 3: 筛选器状态传播**
    - 对任意 filter 组合，验证 API 请求参数与 filter 状态一致
    - 验证 interval_minutes 参数等于 config.settlementIntervalMinutes
    - **Validates: Requirements 6.2, 6.3**

  - [x] 1.5 创建 useStageSummaries.js hook
    - 创建 `web/src/hooks/useStageSummaries.js`
    - 从 App.jsx/WemPage.jsx 提取 funnel reducer 逻辑
    - 并行获取 4 个 stage 的 summary 数据
    - 返回 { summaries, loading } 对象，key 为 stageId
    - 单个 stage 请求失败时设置该 stage summary 为 null，不影响其他 stage
    - 参数变化时自动重新获取
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 1.6 Write property test for stage independence
    - **Property 4: Stage 独立性（故障隔离）**
    - 对任意失败 stage 子集，验证其他 stage 的 summary 不受影响
    - **Validates: Requirements 5.1, 7.2**

- [x] 2. Checkpoint - Phase 1 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2: 新组件创建（与旧代码并行）
  - [x] 3.1 创建 FilterBar.jsx 组件
    - 创建 `web/src/components/FilterBar.jsx`（< 200 行）
    - 接受 props: config, years, lang
    - 渲染 region 选择器（基于 config.regions）
    - 渲染年份按钮组、季度筛选器（Q1-Q4 + ALL）、日类型筛选器（workday/weekend/all）
    - 通过 useFilters() hook 读写 FilterContext 状态
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 3.2 Write property test for FilterBar region rendering
    - **Property 7: FilterBar 区域渲染**
    - 对任意 MarketConfig.regions 数组，验证 FilterBar 渲染的 region 数量与配置一致
    - **Validates: Requirements 4.1, 4.2**

  - [x] 3.3 创建 PageShell.jsx 组件
    - 创建 `web/src/components/PageShell.jsx`（< 200 行）
    - 接受 props: config, sectionLinks, activeSection, onSectionClick, lang, onLangToggle, children
    - 渲染 SidebarNavigation（传入 activePage、sectionLinks）
    - 渲染 Header（市场名称、结算间隔、时区）
    - 渲染 FilterBar
    - 提供 main content 区域（children slot）
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.4 创建 MarketOpportunityStage.jsx
    - 创建 `web/src/pages/stages/MarketOpportunityStage.jsx`（< 200 行）
    - 接受 props: config, conclusionData, isLoading, onVisible, lang
    - 从 FilterContext 读取 region/year/quarter/dayType
    - 调用 useMarketData 获取价格数据
    - 根据 config.stages['market-opportunity'].modules 渲染对应模块
    - 管理 visibleChartData 状态（窗口选择）
    - 价格数据请求失败时显示错误面板 + 重试按钮
    - _Requirements: 2.2, 5.2, 5.3, 8.4, 12.1_

  - [x] 3.5 创建 OpportunityIdentificationStage.jsx
    - 创建 `web/src/pages/stages/OpportunityIdentificationStage.jsx`（< 200 行）
    - 根据 config.stages['opportunity-identification'].modules 决定渲染模块
    - NEM: PeakAnalysis, FcasAnalysis, ChargingWindow, GridForecast
    - WEM: WemEssAnalysis
    - 每个模块包裹在 CollapsibleModule 中
    - 未注册模块静默跳过 + console.warn
    - _Requirements: 2.2, 2.4, 5.2, 8.4, 12.3_

  - [x] 3.6 创建 RevenueEstimationStage.jsx
    - 创建 `web/src/pages/stages/RevenueEstimationStage.jsx`（< 200 行）
    - 根据 config.stages['revenue-estimation'].modules 决定渲染模块
    - NEM: BessSimulator, RevenueStacking, CycleCost
    - WEM: WemCapacityAnalysis
    - _Requirements: 2.2, 5.2, 8.4_

  - [x] 3.7 创建 InvestmentDecisionStage.jsx
    - 创建 `web/src/pages/stages/InvestmentDecisionStage.jsx`（< 200 行）
    - 根据 config.stages['investment-decision'].modules 决定渲染模块
    - 渲染 InvestmentAnalysis + ReportPreview（NEM）或仅 InvestmentAnalysis（WEM）
    - _Requirements: 2.2, 5.2, 8.4_

  - [ ]* 3.8 Write property test for config-driven rendering
    - **Property 2: 配置驱动渲染一致性**
    - 对任意 MarketConfig 和 stageId，验证 Stage 组件渲染的模块集合等于 config.stages[stageId].modules
    - **Validates: Requirements 1.4, 2.2**

  - [ ]* 3.9 Write property test for unknown module graceful degradation
    - **Property 5: 未知模块静默降级**
    - 对任意包含未注册模块名的 config，验证 Stage 组件不崩溃且其他模块正常渲染
    - **Validates: Requirements 2.4, 12.3**

  - [x] 3.10 创建 MarketPage.jsx 编排组件
    - 创建 `web/src/pages/MarketPage.jsx`（< 200 行）
    - 接受 market prop ('NEM' | 'WEM')
    - 从 marketConfig 获取配置
    - 管理 lang 状态、activeSection 状态
    - 调用 useStageSummaries 获取结论数据
    - 渲染 PageShell + ExecutiveSummary + 4 个 Stage 组件
    - 实现 scroll-spy 和 KPI 点击跳转
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.1, 11.1, 11.2, 11.4_

- [x] 4. Checkpoint - Phase 2 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 3: 切换与清理（破坏性变更）
  - [x] 5.1 修改 main.jsx 使用 MarketPage
    - 修改 `web/src/main.jsx`
    - 用 MarketPage(market='NEM') 替换 App 组件引用
    - 用 MarketPage(market='WEM') 替换 WemPage 组件引用
    - 保留 FilterProvider 包裹 MarketPage
    - 保留 FinlandPage、FingridPage、DeveloperPortalPage 路由不变
    - _Requirements: 1.1, 1.2, 9.1, 9.2, 9.3_

  - [x] 5.2 删除 App.jsx 和 WemPage.jsx
    - 删除 `web/src/App.jsx`
    - 删除 `web/src/pages/WemPage.jsx`
    - 确认无其他文件引用这两个已删除文件
    - _Requirements: 1.3, 1.4_

  - [ ]* 5.3 Write integration tests for route equivalence
    - 验证 '/' 路由渲染 NEM 市场页面
    - 验证 '/wem' 路由渲染 WEM 市场页面
    - 验证 '/finland', '/fingrid', '/developer' 路由不受影响
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [ ]* 5.4 Write unit tests for backward compatibility
    - 验证所有现有分析组件 props 接口未被修改
    - 验证所有 funnel 组件接口未被修改
    - 验证无新增第三方依赖（检查 package.json）
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

- [x] 6. Final checkpoint - 全面验证
  - Ensure all tests pass, ask the user if questions arise.
  - 验证 build 通过（`npm run build`）
  - 验证所有新文件 < 200 行

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Phase 1 和 Phase 2 不会破坏现有功能，Phase 3 是唯一的破坏性变更
- 所有新文件必须 < 200 行，不引入新依赖

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.5"] },
    { "id": 2, "tasks": ["1.4", "1.6", "3.1", "3.3"] },
    { "id": 3, "tasks": ["3.2", "3.4", "3.5", "3.6", "3.7"] },
    { "id": 4, "tasks": ["3.8", "3.9", "3.10"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4"] }
  ]
}
```
