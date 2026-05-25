# Requirements Document

## Introduction

本文档定义了 NEM/WEM 前端页面重写的功能需求。重写的核心目标是将 `App.jsx`（1000+ 行）和 `WemPage.jsx` 合并为一个统一的 `MarketPage` 组件，通过配置驱动市场差异化渲染，同时保持所有现有功能和路由不变。

## Glossary

- **MarketPage**: 统一的市场页面编排组件，根据 market prop 加载对应配置并渲染完整页面
- **PageShell**: 布局外壳组件，包含侧边栏导航、页面头部和筛选器栏
- **FilterBar**: 提取的筛选器控件组件，渲染年份、季度、日类型、月份、区域筛选按钮
- **Stage_Component**: 自包含的阶段组件，独立获取数据并渲染对应分析模块
- **MarketConfig**: 市场配置对象，定义市场属性和各阶段可用模块
- **FilterContext**: React Context，管理全局筛选器状态（region、year、quarter、dayType）
- **useMarketData**: 自定义 Hook，获取市场价格数据并支持窗口选择
- **useStageSummaries**: 自定义 Hook，并行获取 4 个阶段的 summary 数据
- **MODULE_REGISTRY**: 模块注册表，将模块名映射到对应的 React 组件

## Requirements

### Requirement 1: 统一市场页面

**User Story:** As a developer, I want a single MarketPage component to serve both NEM and WEM markets, so that market-specific logic is driven by configuration rather than duplicated code.

#### Acceptance Criteria

1. WHEN the pathname is '/', THE MarketPage SHALL render with market='NEM' configuration
2. WHEN the pathname is '/wem', THE MarketPage SHALL render with market='WEM' configuration
3. THE MarketPage SHALL accept a market prop of value 'NEM' or 'WEM' and render the corresponding market view
4. THE MarketPage SHALL not contain any hardcoded market-specific conditional branches for determining which modules to render

### Requirement 2: 配置驱动渲染

**User Story:** As a developer, I want market configuration to be the single source of truth for module availability, so that adding or removing modules requires only a config change.

#### Acceptance Criteria

1. THE MarketConfig SHALL define a stages object containing entries for all four stage identifiers: 'market-opportunity', 'opportunity-identification', 'revenue-estimation', 'investment-decision'
2. WHEN a Stage_Component renders, THE Stage_Component SHALL read its module list exclusively from MarketConfig.stages[stageId].modules
3. THE MarketConfig SHALL specify a non-empty modules array for each stage
4. WHEN a module name in the config does not exist in MODULE_REGISTRY, THE Stage_Component SHALL skip that module silently and log a console warning

### Requirement 3: PageShell 布局组件

**User Story:** As a user, I want a consistent page layout with sidebar navigation, header, and filters, so that I can navigate and filter data regardless of which market I am viewing.

#### Acceptance Criteria

1. THE PageShell SHALL render a SidebarNavigation component with section links and active section highlighting
2. THE PageShell SHALL render a Header displaying the market name, settlement interval, and timezone from MarketConfig
3. THE PageShell SHALL render a FilterBar component
4. THE PageShell SHALL provide a content area that renders its children components

### Requirement 4: FilterBar 组件

**User Story:** As a user, I want a unified filter bar to select region, year, quarter, day type, and month, so that I can control the data displayed across all stages.

#### Acceptance Criteria

1. THE FilterBar SHALL render region selection options based on MarketConfig.regions
2. THE FilterBar SHALL render year selection buttons from the available years list
3. THE FilterBar SHALL render quarter filter options (Q1, Q2, Q3, Q4, ALL)
4. THE FilterBar SHALL render day type filter options (workday, weekend, all)
5. WHEN a user selects a filter value, THE FilterBar SHALL update FilterContext with the new value
6. WHEN FilterContext updates, THE FilterBar SHALL reflect the current filter state in its UI

### Requirement 5: Stage 组件独立性

**User Story:** As a user, I want each analysis stage to operate independently, so that a failure in one stage does not prevent me from viewing other stages.

#### Acceptance Criteria

1. WHEN a Stage_Component's API request fails, THE other Stage_Components SHALL continue rendering with their own data unaffected
2. THE Stage_Component SHALL fetch its own data independently using FilterContext values
3. WHEN FilterContext changes, THE Stage_Component SHALL re-fetch its data with the updated filter parameters
4. IF a stage summary request fails, THEN THE Stage_Component SHALL display the stage content without conclusion data rather than showing an error state

### Requirement 6: useMarketData Hook

**User Story:** As a developer, I want a reusable hook for fetching market price data, so that price data fetching logic is centralized and consistent.

#### Acceptance Criteria

1. THE useMarketData SHALL accept a MarketConfig object and a filters object containing region, year, quarter, and dayType
2. WHEN filters change, THE useMarketData SHALL fetch new price data from the /price-trend API endpoint
3. THE useMarketData SHALL include config.settlementIntervalMinutes as the interval_minutes parameter in API requests
4. THE useMarketData SHALL return chartData, visibleData, loading state, error state, and an onWindowChange callback
5. IF the API request fails, THEN THE useMarketData SHALL set the error state with the error message and set loading to false

### Requirement 7: useStageSummaries Hook

**User Story:** As a developer, I want a hook that fetches all four stage summaries in parallel, so that stage conclusion data loads efficiently without blocking.

#### Acceptance Criteria

1. THE useStageSummaries SHALL fetch summary data for all four stages in parallel
2. WHEN any single stage request fails, THE useStageSummaries SHALL set that stage's summary to null without affecting other stages
3. THE useStageSummaries SHALL return a summaries object keyed by stageId and a loading object keyed by stageId
4. WHEN market, region, year, or bessParams change, THE useStageSummaries SHALL re-fetch all stage summaries

### Requirement 8: 文件大小约束

**User Story:** As a developer, I want each new file to remain under 200 lines, so that the codebase stays maintainable and readable.

#### Acceptance Criteria

1. THE MarketPage file SHALL contain fewer than 200 lines of code
2. THE PageShell file SHALL contain fewer than 200 lines of code
3. THE FilterBar file SHALL contain fewer than 200 lines of code
4. WHEN a Stage_Component file is created, THE Stage_Component file SHALL contain fewer than 200 lines of code

### Requirement 9: 路由等价性

**User Story:** As a user, I want the same URLs to work after the rewrite, so that bookmarks and shared links continue to function correctly.

#### Acceptance Criteria

1. WHEN a user navigates to '/', THE system SHALL render the NEM market page with identical functionality to the pre-rewrite App.jsx
2. WHEN a user navigates to '/wem', THE system SHALL render the WEM market page with identical functionality to the pre-rewrite WemPage.jsx
3. THE system SHALL preserve all existing non-market routes (/finland, /fingrid, /developer) without modification

### Requirement 10: 向后兼容性

**User Story:** As a user, I want all existing analysis modules to remain available after the rewrite, so that no functionality is lost.

#### Acceptance Criteria

1. THE system SHALL preserve all existing analysis components (PriceChart, SummaryStats, FcasAnalysis, InvestmentAnalysis, BessSimulator, RevenueStacking, WemEssAnalysis, WemCapacityAnalysis) without modifying their internal implementation
2. THE system SHALL preserve all existing analysis components' props interfaces without modification
3. THE system SHALL preserve all funnel components (KpiCard, FunnelStage, StageConclusion, CollapsibleModule, ExecutiveSummary) without modifying their internal implementation
4. THE system SHALL not introduce any new third-party dependencies

### Requirement 11: 国际化支持

**User Story:** As a user, I want all UI text to be available in both Chinese and English, so that I can use the application in my preferred language.

#### Acceptance Criteria

1. THE MarketPage SHALL maintain a language state with values 'zh' or 'en'
2. WHEN a user toggles the language, THE system SHALL re-render all text content in the selected language
3. THE STAGE_DEFINITIONS SHALL provide title and coreQuestion in both zh and en
4. THE PageShell SHALL pass the current language to all child components that render text

### Requirement 12: 错误处理

**User Story:** As a user, I want graceful error handling when data requests fail, so that I can still use the parts of the application that are working.

#### Acceptance Criteria

1. IF a price data request fails, THEN THE MarketOpportunityStage SHALL display an error panel with a retry button
2. IF a stage summary request fails, THEN THE Stage_Component SHALL render module content normally without conclusion data
3. IF a MarketConfig module name is not found in MODULE_REGISTRY, THEN THE Stage_Component SHALL skip that module and log a warning to the console
4. IF a Stage_Component is rendered outside FilterProvider, THEN THE useFilters hook SHALL throw an error with message "useFilters must be used within FilterProvider"
