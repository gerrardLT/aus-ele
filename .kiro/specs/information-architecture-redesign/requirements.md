# Requirements Document

## Introduction

AEMO Intelligence 平台当前的信息架构按技术模块组织（PriceChart、SummaryStats、PeakAnalysis 等 10+ 模块平铺），而非按用户决策流程组织。用户需要在分散的模块间自行拼凑分析结论，缺乏聚合视图和叙事引导。

本需求定义信息架构重组方案：将模块重新组织为"决策漏斗"（Decision Funnel），引导用户从市场机会评估 → 机会识别 → 收入估算 → 投资决策，逐步深入。同时新增执行摘要视图、重构导航层级、并提供后端聚合 API 以减少前端请求次数和认知负荷。

## Glossary

- **Platform**: AEMO Intelligence 澳洲电网智能观测站，即本系统整体
- **Decision_Funnel**: 决策漏斗，将分析模块按决策阶段组织的信息架构模式，包含四个阶段
- **Executive_Summary**: 执行摘要视图，聚合各阶段关键结论的单屏仪表板
- **Funnel_Stage**: 漏斗阶段，Decision_Funnel 中的一个分析层级，对应一个核心问题
- **Market_Page**: 市场页面，NEM 或 WEM 的主分析页面
- **Navigation_System**: 导航系统，侧边栏及页内导航的整体结构
- **Aggregation_API**: 聚合 API，后端将多个模块数据合并为单次响应的接口
- **Progressive_Disclosure**: 渐进式披露，先展示结论再按需展开细节的交互模式
- **Stage_Conclusion**: 阶段结论，每个 Funnel_Stage 输出的核心判断摘要
- **Research_Tools**: 研究工具区，导航中用于非核心 BESS 分析的辅助页面分组
- **Module**: 分析模块，如 PriceChart、FcasAnalysis、InvestmentAnalysis 等独立功能组件
- **KPI_Card**: 关键指标卡片，展示单个聚合数值及其语义状态的 UI 组件

## Requirements

### Requirement 1: Decision Funnel Structure

**User Story:** As a 储能投资分析师, I want the analysis modules organized into a clear decision flow, so that I can follow a logical path from market assessment to investment decision without mentally piecing together scattered information.

#### Acceptance Criteria

1. THE Platform SHALL organize all BESS analysis modules on each Market_Page into exactly four sequential Funnel_Stages: Market Opportunity Assessment (市场机会评估), Opportunity Identification (机会识别), Revenue Estimation (收入估算), and Investment Decision (投资决策)
2. WHEN a Market_Page loads, THE Platform SHALL render the four Funnel_Stages in sequential order from top to bottom
3. THE Platform SHALL assign each existing Module to exactly one Funnel_Stage based on its analytical purpose
4. WHEN a user views a Funnel_Stage, THE Platform SHALL display a stage header containing the stage name, the core question the stage answers, and the Stage_Conclusion
5. THE Platform SHALL assign modules to stages as follows: Stage 1 (PriceChart, SummaryStats, HourlyDistributionChart), Stage 2 (PeakAnalysis, FcasAnalysis, ChargingWindow, GridForecast), Stage 3 (BessSimulator, RevenueStacking, CycleCost), Stage 4 (InvestmentAnalysis, ReportPreview)

### Requirement 2: Executive Summary View

**User Story:** As a 能源基金 PM, I want a single-screen summary of key conclusions at the top of each market page, so that I can quickly assess the investment opportunity without scrolling through all modules.

#### Acceptance Criteria

1. WHEN a Market_Page loads, THE Platform SHALL display an Executive_Summary section above all Funnel_Stages
2. THE Executive_Summary SHALL aggregate and display key metrics from each of the four Funnel_Stages using KPI_Cards
3. THE Executive_Summary SHALL include at minimum: current price spread (价差), FCAS revenue potential (FCAS 收入潜力), estimated daily BESS revenue (日收入估算), and NPV/IRR indicators (净现值/内部收益率)
4. WHEN underlying data changes due to filter selection, THE Executive_Summary SHALL update all displayed metrics within 2 seconds
5. THE Executive_Summary SHALL apply semantic color coding to each KPI_Card: positive (green) for favorable metrics, negative (red) for unfavorable metrics, and warning (amber) for borderline metrics
6. WHEN a user clicks a KPI_Card in the Executive_Summary, THE Platform SHALL scroll to the corresponding Funnel_Stage that produced the metric

### Requirement 3: Stage Conclusions

**User Story:** As a 电力交易员, I want each analysis stage to present a clear conclusion, so that I can quickly determine whether to investigate further or move to the next stage.

#### Acceptance Criteria

1. THE Platform SHALL display a Stage_Conclusion panel at the top of each Funnel_Stage
2. THE Stage_Conclusion SHALL contain a one-sentence natural language summary answering the stage's core question
3. THE Stage_Conclusion SHALL contain 2-4 supporting KPI_Cards with the most relevant metrics for that stage
4. WHEN the data for a Funnel_Stage has not yet loaded, THE Stage_Conclusion SHALL display a loading state with a descriptive message indicating what is being calculated
5. WHEN a Stage_Conclusion indicates an unfavorable result, THE Platform SHALL visually de-emphasize subsequent Funnel_Stages to signal reduced relevance

### Requirement 4: Progressive Disclosure Within Stages

**User Story:** As a 储能投资分析师, I want to see conclusions first and expand into detailed charts on demand, so that I can work efficiently without information overload.

#### Acceptance Criteria

1. WHEN a Funnel_Stage renders, THE Platform SHALL display the Stage_Conclusion and KPI_Cards in expanded state and all detailed Module content in collapsed state by default
2. WHEN a user clicks the expand control on a collapsed Module, THE Platform SHALL reveal the full Module content with an expand animation of 200ms duration
3. WHILE a Module is in collapsed state, THE Platform SHALL display the Module title and a one-line metric summary
4. THE Platform SHALL allow users to expand all modules within a Funnel_Stage simultaneously via a single "展开全部" control
5. THE Platform SHALL persist the user's expand/collapse preferences for the current browser session

### Requirement 5: Navigation Restructuring

**User Story:** As a 储能投资分析师, I want the navigation to prioritize BESS investment analysis pages and demote unrelated tools, so that I can find core functionality without distraction.

#### Acceptance Criteria

1. THE Navigation_System SHALL organize sidebar items into three groups: "BESS 投资分析" (primary), "研究工具" (secondary), and "系统" (tertiary)
2. THE Navigation_System SHALL place NEM and WEM market pages in the "BESS 投资分析" group
3. THE Navigation_System SHALL place Finland and Fingrid pages in the "研究工具" group with reduced visual prominence
4. THE Navigation_System SHALL place the Developer Portal in the "系统" group
5. WHEN a user is on a Market_Page, THE Navigation_System SHALL display in-page navigation links corresponding to the four Funnel_Stages and the Executive_Summary
6. WHEN a user scrolls through a Market_Page, THE Navigation_System SHALL highlight the currently visible Funnel_Stage in the sidebar
7. THE Navigation_System SHALL visually distinguish the "研究工具" group from the primary group using reduced opacity or smaller text size

### Requirement 6: Backend Aggregation API

**User Story:** As a 电力交易员, I want the executive summary to load quickly from a single API call, so that I do not wait for 5-6 separate module requests before seeing key conclusions.

#### Acceptance Criteria

1. THE Aggregation_API SHALL expose a GET endpoint at `/api/market-summary/{market}/{region}` that returns aggregated metrics for the Executive_Summary in a single response
2. THE Aggregation_API SHALL return the response within 3 seconds for a standard request with default parameters
3. THE Aggregation_API SHALL include in its response: price spread statistics, FCAS opportunity score, estimated BESS daily revenue, NPV indicator, IRR indicator, and an overall opportunity rating
4. THE Aggregation_API SHALL include a `metadata` object conforming to the existing API response contract (market, region, timezone, currency, data_grade, freshness, source_version)
5. IF the Aggregation_API cannot compute one or more metrics due to missing data, THEN THE Aggregation_API SHALL return partial results with a `warnings` array indicating which metrics are unavailable and why
6. THE Aggregation_API SHALL support query parameters for `year`, `region`, and `bess_params` (power_mw, duration_hours, round_trip_efficiency) to customize the aggregation context

### Requirement 7: Stage-Level Data Endpoints

**User Story:** As a 储能投资分析师, I want each decision stage to load its conclusion data efficiently, so that I can see stage summaries without waiting for all detailed module data.

#### Acceptance Criteria

1. THE Aggregation_API SHALL expose a GET endpoint at `/api/stage-summary/{market}/{region}/{stage_id}` for each of the four Funnel_Stages
2. WHEN a stage-summary endpoint is called, THE Aggregation_API SHALL return the Stage_Conclusion text and 2-4 key metrics for that stage within 2 seconds
3. THE Platform frontend SHALL request stage-summary data independently of detailed module data, enabling the Stage_Conclusion to render before module content loads
4. IF a stage-summary request fails, THEN THE Platform SHALL display a graceful error message and allow the user to retry without affecting other stages

### Requirement 8: Funnel Stage Core Questions

**User Story:** As a 能源基金 PM, I want each stage to clearly state what question it answers, so that I understand the purpose of each analysis section at a glance.

#### Acceptance Criteria

1. THE Platform SHALL display the following core questions for each Funnel_Stage: Stage 1 "市场是否存在套利机会？规模多大？" (Is there arbitrage opportunity? How big?), Stage 2 "何时交易？哪些时段？哪些服务？" (When to trade? Which slots? Which services?), Stage 3 "电池能赚多少？扣除成本后呢？" (How much can a battery earn? After costs?), Stage 4 "项目是否值得投资？NPV/IRR/回收期？" (Is the project worth investing? NPV/IRR/payback?)
2. THE Platform SHALL display each core question in the stage header using the Chinese primary text with English parenthetical annotation
3. THE Platform SHALL render core questions in a visually distinct style (muted color, smaller font size) below the stage title

### Requirement 9: WEM Page Consistency

**User Story:** As a 电力交易员, I want the WEM page to follow the same decision funnel structure as the NEM page, so that I have a consistent analysis experience across markets.

#### Acceptance Criteria

1. THE Platform SHALL apply the same four-stage Decision_Funnel structure to the WEM Market_Page
2. THE Platform SHALL display an Executive_Summary on the WEM page with the same layout and interaction patterns as the NEM page
3. WHERE a Module is not available for WEM (due to data limitations), THE Platform SHALL display a placeholder indicating the module is not yet supported for WEM with an explanation
4. THE Platform SHALL use the same Navigation_System structure for WEM as for NEM, with stage-level in-page navigation

### Requirement 10: Responsive Funnel Layout

**User Story:** As a 储能投资分析师, I want the decision funnel to remain usable on smaller desktop screens, so that I can work on a laptop without losing the narrative flow.

#### Acceptance Criteria

1. WHILE the viewport width is 1280px or greater, THE Platform SHALL render the Executive_Summary KPI_Cards in a horizontal row layout
2. WHILE the viewport width is between 1024px and 1279px, THE Platform SHALL stack the Executive_Summary KPI_Cards into a 2x2 grid layout
3. WHILE the viewport width is below 1024px, THE Platform SHALL hide the sidebar Navigation_System and display a mobile-friendly top navigation bar
4. THE Platform SHALL maintain the sequential top-to-bottom ordering of Funnel_Stages at all supported viewport widths

### Requirement 11: Transition from Current Architecture

**User Story:** As a 储能投资分析师, I want the transition to the new architecture to preserve all existing analysis capabilities, so that I do not lose access to any current functionality.

#### Acceptance Criteria

1. THE Platform SHALL retain all existing Module functionality (PriceChart, SummaryStats, PeakAnalysis, FcasAnalysis, BessSimulator, RevenueStacking, ChargingWindow, CycleCost, InvestmentAnalysis, GridForecast, ReportPreview) within the new Decision_Funnel structure
2. THE Platform SHALL preserve all existing filter controls (region, year, quarter, day type, month) and their behavior within the reorganized layout
3. THE Platform SHALL maintain backward compatibility with all existing backend API endpoints while adding the new Aggregation_API endpoints
4. IF a user has bookmarked or linked to a specific section of the current page, THEN THE Platform SHALL redirect or scroll to the equivalent location in the new structure
