# Requirements Document

## Introduction

Investment Narrative Layer（投资叙事层）将 AEMO Intelligence Platform 从"数据展示工具"转型为"有说服力的投资故事生成器"。当前平台虽然具备完整的数据分析能力（ForwardPriceEngine、CostStructureEngine、TaxModel），但输出仅为原始数字和图表，缺乏专业投资分析师所需的因果归因、风险分层、时间叙事、假设透明度、多源交叉验证和资产特异性。本功能通过 6 个结构化叙事模式（Part A）和 6 个具体数据增强（Part B: P0-P2）实现这一转型，覆盖后端逻辑和前端组件。

## Glossary

- **Narrative_Engine**: 叙事引擎，负责为每个分析模块的输出生成因果归因文本和结构化解释
- **Risk_Stratification_Engine**: 风险分层引擎，将收入拆分为不同置信度层级并应用差异化折现率
- **Event_Annotation_Service**: 事件标注服务，从事件注册表中提取关键事件并在时间序列图表上标注
- **Assumption_Panel**: 假设面板，展示所有模型输入假设并支持用户覆盖
- **Cross_Validation_Service**: 交叉验证服务，聚合多数据源对同一数据点的不同估计值
- **Asset_Configuration_Panel**: 资产配置面板，用户定义特定项目参数（位置、规模、时长、MLF、接入点）
- **Forward_Price_Engine**: 前瞻电价情景引擎（已有），基于供需事件建模未来电价分布
- **Financial_Model**: 现有 20 年现金流模型
- **Cost_Structure_Engine**: 费用分解引擎（已有），计算各类网络费用
- **Revenue_Layer**: 收入层级，按价格阈值划分的收入组成部分（基础套利层 vs 极端事件层）
- **Confidence_Level**: 置信度等级，标识收入预测的可靠程度（HIGH、MEDIUM、LOW）
- **Inflection_Point**: 拐点，时间序列上导致趋势显著变化的事件（如煤电退役、新互联线投运）
- **Causal_Attribution**: 因果归因，将数值结果追溯到具体驱动因素的文本解释
- **Spread_Threshold**: 价差阈值，用于区分基础套利收入和极端事件收入的价格边界（默认 $300/MWh）
- **Discount_Rate**: 折现率，用于 NPV 计算的年化折现比率
- **BESS**: Battery Energy Storage System，电池储能系统
- **NEM**: National Electricity Market，澳大利亚国家电力市场（NSW1、QLD1、VIC1、SA1、TAS1）
- **WEM**: Wholesale Electricity Market，西澳批发电力市场
- **AEMO**: Australian Energy Market Operator，澳大利亚能源市场运营商
- **ISP**: Integrated System Plan，AEMO 综合系统规划
- **ESOO**: Electricity Statement of Opportunities，电力机会声明
- **MLF**: Marginal Loss Factor，边际损耗因子
- **FCAS**: Frequency Control Ancillary Services，频率控制辅助服务
- **Forward_Spread_Curve**: 前瞻价差曲线，展示 20 年价差预测的三情景可视化组件

## Requirements

### Requirement 1: Causal Chain Attribution for Module Outputs

**User Story:** As an investment analyst, I want every key metric to include an explanation of WHY it has that value, so that I can understand the causal drivers behind the numbers and build conviction in the analysis.

#### Acceptance Criteria

1. WHEN the Narrative_Engine generates a conclusion for any analysis module, THE Narrative_Engine SHALL include at least one causal attribution statement linking the output value to a specific market driver
2. WHEN a key metric (spread, revenue, NPV, IRR) is displayed, THE Narrative_Engine SHALL provide an expandable tooltip containing a causal explanation referencing specific events or parameters from the Forward_Price_Engine event registry
3. WHEN revenue projections change between years, THE Narrative_Engine SHALL attribute the change to specific events (coal closures, BESS commissioning, saturation effects) with their individual contribution amounts
4. THE Narrative_Engine SHALL generate causal text using structured templates that reference data from coal_retirement_schedule.json, capacity_data.json, and the Forward_Price_Engine scenario parameters
5. WHEN a spread value is displayed for a region, THE Narrative_Engine SHALL explain the supply-side driver (coal retirement reducing baseload) and demand-side driver (BESS saturation compressing peaks) contributing to that spread level

### Requirement 2: Risk Stratification Revenue Layers

**User Story:** As an investment analyst, I want revenue split into layers by predictability, so that I can apply appropriate discount rates to each layer and avoid overvaluing uncertain income streams.

#### Acceptance Criteria

1. THE Risk_Stratification_Engine SHALL split annual revenue into three layers: Layer 1 (base arbitrage from price intervals below the Spread_Threshold), Layer 2 (FCAS and ancillary services), and Layer 3 (extreme price events from intervals above the Spread_Threshold)
2. THE Risk_Stratification_Engine SHALL assign a Confidence_Level of HIGH to Layer 1, MEDIUM to Layer 2, and LOW to Layer 3
3. THE Risk_Stratification_Engine SHALL apply a configurable discount rate to each layer independently, with defaults of 8 percent for Layer 1, 10 percent for Layer 2, and 12 percent for Layer 3
4. THE Risk_Stratification_Engine SHALL calculate a layer-weighted NPV by discounting each layer's cash flow series at its respective discount rate and summing the results
5. THE Risk_Stratification_Engine SHALL calculate the percentage contribution of each layer to total annual revenue for each year of the 20-year projection
6. WHEN the user modifies a layer's discount rate, THE Risk_Stratification_Engine SHALL recalculate the layer-weighted NPV and display updated results
7. THE Risk_Stratification_Engine SHALL use a configurable Spread_Threshold with a default value of $300 per MWh to separate Layer 1 and Layer 3 revenue

### Requirement 3: Revenue Stratification Visualization

**User Story:** As an investment analyst, I want to see revenue layers displayed as a stacked area chart over time, so that I can visually assess how revenue composition changes across the project life.

#### Acceptance Criteria

1. THE Frontend SHALL render a stacked area chart showing Layer 1, Layer 2, and Layer 3 revenue contributions over the 20-year projection period
2. THE Frontend SHALL color-code each layer distinctly: Layer 1 in a stable color (blue), Layer 2 in a moderate color (amber), and Layer 3 in a volatile color (red)
3. WHEN the user hovers over a year on the stacked area chart, THE Frontend SHALL display a tooltip showing each layer's dollar amount and percentage of total revenue for that year
4. THE Frontend SHALL display the layer-weighted NPV alongside the standard single-rate NPV for comparison
5. THE Frontend SHALL include a legend identifying each layer with its name, Confidence_Level, and applied discount rate

### Requirement 4: Temporal Narrative with Inflection Points

**User Story:** As an investment analyst, I want key market events annotated on time-series charts, so that I can understand what drives each slope change in the forward price curve and build a coherent investment story.

#### Acceptance Criteria

1. WHEN rendering a time-series chart (price, spread, or revenue), THE Event_Annotation_Service SHALL overlay event markers at the dates of significant Inflection_Points sourced from the Forward_Price_Engine event registry
2. THE Event_Annotation_Service SHALL color-code event markers by event type: coal closure in red, BESS commissioning in blue, and network augmentation in green
3. WHEN the user clicks an event marker, THE Event_Annotation_Service SHALL display a detail panel showing the event name, affected region, capacity in MW, expected date, confidence level, and estimated spread impact factor
4. THE Event_Annotation_Service SHALL annotate the Forward_Spread_Curve component with event markers explaining each significant slope change in the projected spread
5. THE Event_Annotation_Service SHALL source events from coal_retirement_schedule.json and capacity_data.json, filtering to show events relevant to the currently selected region

### Requirement 5: Forward Spread Curve Display

**User Story:** As an investment analyst, I want to see the ForwardPriceEngine's 20-year spread projection as a visual chart with three scenarios, so that I can assess the range of future spread outcomes and their drivers.

#### Acceptance Criteria

1. THE Frontend SHALL render a line chart displaying the Forward_Price_Engine's 20-year mean spread projection for Central, High, and Low scenarios as three distinct lines
2. THE Frontend SHALL display historical actual spread data for the most recent 3 years preceding the projection start, connected to the forward projection to provide context
3. THE Frontend SHALL visually distinguish the historical period (solid line) from the projected period (dashed line) on the same chart
4. WHEN the user selects a different region, THE Frontend SHALL reload the Forward_Spread_Curve with region-specific scenario data
5. THE Frontend SHALL display a shaded confidence band between the High and Low scenario lines to indicate the range of uncertainty

### Requirement 6: Assumption Transparency Panel

**User Story:** As an investment analyst, I want to see all model input assumptions in one place and trace any output back to its driving assumptions, so that I can assess model credibility and perform sensitivity analysis.

#### Acceptance Criteria

1. THE Assumption_Panel SHALL display all configurable model inputs grouped by category: battery specifications, cost parameters, tax parameters, forward price assumptions, and scenario selections
2. THE Assumption_Panel SHALL show the current value, default value, and valid range for each assumption parameter
3. WHEN the user modifies an assumption value, THE Assumption_Panel SHALL trigger recalculation of all dependent outputs and update displayed results
4. THE Assumption_Panel SHALL display source attribution for each default value, referencing the relevant entry from financial_evidence.json
5. WHEN the user hovers over any output metric, THE Assumption_Panel SHALL highlight which assumption parameters contribute to that metric's calculation
6. THE Assumption_Panel SHALL provide a reset button that restores all assumptions to their default values

### Requirement 7: Multi-Source Cross-Validation Display

**User Story:** As an investment analyst, I want key data points validated against multiple independent sources, so that I can assess data reliability and identify where sources disagree.

#### Acceptance Criteria

1. THE Cross_Validation_Service SHALL aggregate coal retirement dates from at least three sources: the platform's coal_retirement_schedule.json, AEMO ISP published dates, and operator public announcements
2. THE Cross_Validation_Service SHALL aggregate revenue benchmarks from at least two sources: the platform's model output and published industry data (Modo Energy reported $148k per MW for NEM BESS in 2024)
3. THE Cross_Validation_Service SHALL aggregate price forecasts from at least two sources: the platform's Central, High, and Low scenarios and AEMO ISP scenario projections
4. THE Frontend SHALL render a comparison table for each cross-validated data point showing source name, source date, reported value, and any discrepancy from the platform's value
5. WHEN sources disagree on a data point by more than 10 percent, THE Frontend SHALL highlight the discrepancy with a visual indicator and display the range of reported values

### Requirement 8: Asset Specificity Configuration

**User Story:** As an investment analyst, I want to configure my specific BESS project parameters and see all results labeled for my asset, so that the analysis reflects my project's unique characteristics rather than generic market data.

#### Acceptance Criteria

1. THE Asset_Configuration_Panel SHALL allow users to define project-specific parameters: location (NEM region or WEM), power capacity in MW, storage duration in hours, round-trip efficiency, MLF at connection point, and connection point identifier
2. WHEN the user saves an asset configuration, THE Asset_Configuration_Panel SHALL persist the configuration and apply it to all downstream calculations across all analysis modules
3. THE Frontend SHALL label all results with the user's specific asset parameters (example: "For YOUR 100MW/4h BESS at NSW1") rather than displaying generic market data labels
4. THE Asset_Configuration_Panel SHALL validate that all user-entered parameters fall within physically realistic ranges: power capacity between 1 and 2000 MW, duration between 0.5 and 12 hours, round-trip efficiency between 0.70 and 0.95, and MLF between 0.80 and 1.10
5. WHEN the user changes any asset parameter, THE Asset_Configuration_Panel SHALL trigger recalculation of all dependent outputs using the updated parameters
6. THE Asset_Configuration_Panel SHALL distinguish between market-wide analysis results and project-specific results by using separate visual sections with clear labeling

### Requirement 9: Revenue Stratification Backend Calculation

**User Story:** As a developer, I want the backend to calculate revenue split by price threshold, so that the frontend can display stratified revenue layers with accurate data.

#### Acceptance Criteria

1. WHEN historical price data is available, THE Risk_Stratification_Engine SHALL calculate Layer 1 revenue by summing arbitrage profits from intervals where the settlement price is below the Spread_Threshold
2. WHEN historical price data is available, THE Risk_Stratification_Engine SHALL calculate Layer 3 revenue by summing arbitrage profits from intervals where the settlement price exceeds the Spread_Threshold
3. THE Risk_Stratification_Engine SHALL calculate Layer 2 revenue from FCAS earnings data independent of the Spread_Threshold
4. FOR the 20-year forward projection, THE Risk_Stratification_Engine SHALL estimate Layer 1 and Layer 3 proportions based on the Forward_Price_Engine's spike_frequency parameter and mean_spread distribution
5. THE Risk_Stratification_Engine SHALL expose a GET endpoint returning the stratified revenue breakdown for a specified region, scenario, and asset configuration
6. THE Risk_Stratification_Engine SHALL serialize stratified revenue results to JSON format including layer amounts, percentages, discount rates, and layer-weighted NPV

### Requirement 10: Forward Spread Curve Backend Endpoint

**User Story:** As a frontend developer, I want an API endpoint that returns the 20-year spread projection data with event annotations, so that the frontend can render the Forward_Spread_Curve component.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL expose a GET endpoint returning the 20-year mean spread projection for all three scenarios (Central, High, Low) for a specified region
2. THE Forward_Price_Engine SHALL include in the response a list of event annotations with event name, date, type, capacity, and spread impact factor for events affecting the specified region
3. THE Forward_Price_Engine SHALL include historical spread data for the most recent 3 years in the response when available
4. THE Forward_Price_Engine SHALL return the projection data in a format compatible with Recharts line chart rendering (array of objects with year, central_spread, high_spread, low_spread fields)
5. IF historical spread data is unavailable for the requested region, THEN THE Forward_Price_Engine SHALL return the projection data without historical context and include a flag indicating historical data is absent

### Requirement 11: Event Annotation Overlay on Charts

**User Story:** As an investment analyst, I want event markers overlaid on any time-series chart in the platform, so that I can correlate market events with observed data patterns across all analysis stages.

#### Acceptance Criteria

1. THE Event_Annotation_Service SHALL provide a reusable frontend component that overlays event markers on any Recharts time-series chart
2. THE Event_Annotation_Service SHALL filter events by the currently selected region and the time range visible on the chart
3. THE Event_Annotation_Service SHALL support three event types with distinct visual markers: coal closure (red downward triangle), BESS commissioning (blue upward triangle), and network augmentation (green diamond)
4. WHEN multiple events occur within the same visual pixel range on the chart, THE Event_Annotation_Service SHALL cluster them into a single marker showing the count, expandable on click
5. THE Event_Annotation_Service SHALL source event data from the Forward_Price_Engine event registry endpoint without duplicating data storage

### Requirement 12: Multi-Source Comparison Table Backend

**User Story:** As a frontend developer, I want an API endpoint that returns multi-source comparison data, so that the frontend can render cross-validation tables.

#### Acceptance Criteria

1. THE Cross_Validation_Service SHALL expose a GET endpoint returning comparison data for coal retirement dates, aggregating dates from the platform's event registry and external source references stored in financial_evidence.json
2. THE Cross_Validation_Service SHALL expose a GET endpoint returning revenue benchmark comparisons, including the platform's model output and published industry reference values
3. THE Cross_Validation_Service SHALL include for each data point: source name, source publication date, reported value, and the percentage difference from the platform's calculated value
4. THE Cross_Validation_Service SHALL return comparison data in a tabular JSON format with columns for source, date, value, and discrepancy percentage
5. IF a referenced external source value is outdated (publication date more than 12 months old), THEN THE Cross_Validation_Service SHALL include a staleness warning flag in the response

### Requirement 13: Fuel Cost Pass-Through Sensitivity Model

**User Story:** As an investment analyst, I want to understand how gas price changes affect my BESS revenue, so that I can assess fuel price risk exposure and communicate it to stakeholders.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL model the relationship between gas price changes and peak electricity price using a configurable pass-through coefficient (default: 1 dollar per GJ increase in gas price produces approximately 7 to 12 dollars per MWh increase in peak electricity price)
2. THE Forward_Price_Engine SHALL accept user-configurable gas price assumptions (base price in dollars per GJ and annual escalation rate) or use default values sourced from financial_evidence.json
3. WHEN the user adjusts gas price assumptions, THE Forward_Price_Engine SHALL recalculate the impact on peak electricity prices and resulting BESS revenue
4. THE Frontend SHALL display a sensitivity table showing the revenue impact of gas price variations: minus 20 percent, minus 10 percent, base case, plus 10 percent, and plus 20 percent relative to the base gas price assumption
5. THE Forward_Price_Engine SHALL calculate and return the sensitivity coefficient: the percentage change in annual BESS revenue per 10 percent change in gas price

### Requirement 14: Network Augmentation Impact Model

**User Story:** As an investment analyst, I want to understand how new interconnectors affect regional price spreads, so that I can assess the risk of spread compression from network augmentation projects.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL include network augmentation events in the event registry with a negative spread_impact_factor representing regional price convergence
2. THE Forward_Price_Engine SHALL model interconnector commissioning as reducing the price spread differential between connected regions by a configurable convergence factor (range 0.05 to 0.30)
3. WHEN a network augmentation event date is reached in the projection, THE Forward_Price_Engine SHALL apply the negative spread_impact_factor to the affected region's mean spread for all subsequent years
4. THE Frontend SHALL display a before-and-after comparison for key network projects showing the projected spread with and without the interconnector commissioning
5. THE Event_Annotation_Service SHALL include network augmentation events as green diamond markers on time-series charts with details showing the affected regions and estimated spread reduction

### Requirement 15: Causal Attribution Serialization

**User Story:** As a developer, I want causal attribution data to be serializable, so that narrative explanations can be transmitted via API and rendered by the frontend.

#### Acceptance Criteria

1. THE Narrative_Engine SHALL serialize causal attribution objects to JSON format containing: metric name, metric value, list of causal factors (each with driver name, driver type, contribution amount, and source reference)
2. THE Narrative_Engine SHALL deserialize JSON causal attribution data back into internal objects without data loss
3. FOR ALL valid causal attribution objects, serializing then deserializing SHALL produce an equivalent object (round-trip property)

### Requirement 16: Risk Stratification Serialization

**User Story:** As a developer, I want stratified revenue data to be serializable, so that layer breakdowns can be stored and transmitted via API.

#### Acceptance Criteria

1. THE Risk_Stratification_Engine SHALL serialize stratified revenue results to JSON format containing: layer definitions, annual layer amounts, discount rates, and layer-weighted NPV
2. THE Risk_Stratification_Engine SHALL deserialize JSON stratified revenue data back into internal objects without data loss
3. FOR ALL valid stratified revenue configurations, serializing then deserializing SHALL produce an equivalent configuration object (round-trip property)

### Requirement 17: Error Handling for Narrative Layer Inputs

**User Story:** As a developer, I want the narrative layer modules to handle invalid inputs gracefully, so that the system remains stable when receiving malformed parameters.

#### Acceptance Criteria

1. IF a Spread_Threshold value outside the range of $0 to $16,600 per MWh (NEM market price cap) is provided, THEN THE Risk_Stratification_Engine SHALL reject the input and return a descriptive validation error
2. IF a discount rate outside the range of 0 to 1 is provided for any revenue layer, THEN THE Risk_Stratification_Engine SHALL reject the input and return a descriptive validation error
3. IF an asset configuration contains a power capacity of zero or negative MW, THEN THE Asset_Configuration_Panel SHALL reject the input and return a descriptive validation error
4. IF the gas price pass-through coefficient is negative, THEN THE Forward_Price_Engine SHALL reject the input and return a descriptive validation error
5. IF a network augmentation convergence factor is outside the range of 0.0 to 1.0, THEN THE Forward_Price_Engine SHALL reject the input and return a descriptive validation error
6. IF the event registry contains no events for the requested region, THEN THE Event_Annotation_Service SHALL return an empty annotation list without error

### Requirement 18: API Integration for Narrative Layer

**User Story:** As a frontend developer, I want all narrative layer capabilities exposed through the existing FastAPI backend, so that the React frontend can access causal explanations, stratified revenue, event annotations, and cross-validation data.

#### Acceptance Criteria

1. THE Narrative_Engine SHALL expose a GET endpoint returning causal attribution data for a specified module output and region
2. THE Risk_Stratification_Engine SHALL expose a GET endpoint returning stratified revenue breakdown for a specified region, scenario, and asset configuration
3. THE Event_Annotation_Service SHALL expose a GET endpoint returning event annotations filtered by region and date range
4. THE Cross_Validation_Service SHALL expose a GET endpoint returning multi-source comparison data for a specified data category (coal retirements, revenue benchmarks, or price forecasts)
5. THE Asset_Configuration_Panel SHALL expose a POST endpoint for saving asset configurations and a GET endpoint for retrieving the current configuration
6. THE Forward_Price_Engine SHALL expose a GET endpoint returning the fuel cost sensitivity analysis for a specified region and gas price assumptions
