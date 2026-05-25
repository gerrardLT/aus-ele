# Requirements Document

## Introduction

Financial Accuracy Modules（财务精度模块）为 AEMO Intelligence Platform 的投资分析引擎提供三个关键增强模块：费用分解引擎（Cost Structure Engine）、税务模型（Tax Model）和前瞻电价情景引擎（Forward Price Scenario Engine）。当前平台使用单一合并的 $/MWh 网络费用、无税务计算、且仅依赖历史回测进行收入预测，导致 BESS 投资回报率被显著高估。本功能通过精确建模澳大利亚电力市场的真实费用结构、税务影响和前瞻性价格情景，使财务模型达到投资决策级精度。

## Glossary

- **Cost_Structure_Engine**: 费用分解引擎模块，将网络费用分解为 AEMO 参与者费用、TUOS、DUOS、MLF、FPP 等独立组件
- **Tax_Model**: 税务模型模块，计算公司税、折旧、利息抵扣和税后现金流
- **Forward_Price_Engine**: 前瞻电价情景引擎模块，基于供需事件建模未来电价分布和收入影响
- **Financial_Model**: 现有的 20 年现金流模型（backend/engines/financial_model.py）
- **BESS**: Battery Energy Storage System，电池储能系统
- **NEM**: National Electricity Market，澳大利亚国家电力市场（覆盖 NSW1、QLD1、VIC1、SA1、TAS1）
- **WEM**: Wholesale Electricity Market，西澳批发电力市场
- **AEMO**: Australian Energy Market Operator，澳大利亚能源市场运营商
- **TUOS**: Transmission Use of System，输电使用费
- **DUOS**: Distribution Use of System，配电使用费
- **MLF**: Marginal Loss Factor，边际损耗因子，应用于结算价格的乘数（范围 0.90-1.05）
- **FPP**: Frequency Performance Payments，频率性能支付（2025年6月取代旧 Causer-pays 机制）
- **TNSP**: Transmission Network Service Provider，输电网络服务提供商
- **IESS**: Integrated Energy Storage System，综合储能系统（AEMO 注册类别）
- **ATO**: Australian Taxation Office，澳大利亚税务局
- **IRR**: Internal Rate of Return，内部收益率
- **NPV**: Net Present Value，净现值
- **DSCR**: Debt Service Coverage Ratio，偿债覆盖率
- **CAPEX**: Capital Expenditure，资本支出
- **ISP**: Integrated System Plan，AEMO 综合系统规划

## Requirements

### Requirement 1: Fee Component Classification

**User Story:** As an investment analyst, I want each network fee component to be classified as FIXED or VARIABLE, so that I can understand the cost structure sensitivity to utilization levels.

#### Acceptance Criteria

1. THE Cost_Structure_Engine SHALL classify AEMO Participant Fees as VARIABLE cost calculated on Gross Energy (charge plus discharge volume) at a rate within the range of $0.30 to $0.50 per MWh
2. THE Cost_Structure_Engine SHALL classify AEMO Registration Fee as a one-time FIXED cost applied at project commencement, with a configurable value within the range of $5,000 to $50,000
3. THE Cost_Structure_Engine SHALL classify TUOS Demand Component as a FIXED cost in dollars per MW per year, with values ranging from $5,000 to $15,000 per MW per year depending on region and TNSP
4. THE Cost_Structure_Engine SHALL classify TUOS Energy Component as a VARIABLE cost in dollars per MWh, with values ranging from $1 to $3 per MWh
5. IF the BESS is transmission-connected, THEN THE Cost_Structure_Engine SHALL classify DUOS as exempt with a zero cost applied; IF the BESS is distribution-connected, THEN THE Cost_Structure_Engine SHALL classify DUOS as a VARIABLE time-of-use cost with rates ranging from $5 to $30 per MWh depending on time-of-use period and distributor tariff
6. THE Cost_Structure_Engine SHALL classify MLF as a settlement price multiplier (range 0.90 to 1.05) applied per connection point, not as an additive fee
7. THE Cost_Structure_Engine SHALL classify FPP as a double-sided VARIABLE mechanism with a configurable net earning value within the range of $500 to $1,500 per MW per year for BESS

### Requirement 2: Regional Fee Configuration

**User Story:** As an investment analyst, I want fee parameters to vary by NEM region and WEM, so that the model reflects actual geographic cost differences.

#### Acceptance Criteria

1. THE Cost_Structure_Engine SHALL maintain separate fee parameter sets for each of the six regions: NSW1, QLD1, VIC1, SA1, TAS1, and WEM
2. THE Cost_Structure_Engine SHALL store region-specific TUOS demand charges that reflect the applicable TNSP tariff for each region
3. THE Cost_Structure_Engine SHALL store region-specific MLF values that are updated annually based on AEMO published data
4. WHEN a user selects a region, THE Cost_Structure_Engine SHALL apply the corresponding regional fee parameters to the cost calculation
5. THE Cost_Structure_Engine SHALL allow users to override any individual fee parameter while retaining defaults for unmodified parameters

### Requirement 3: Annual Cost Calculation

**User Story:** As an investment analyst, I want the engine to calculate total annual cost per MW broken down by component, so that I can assess the full cost impact on BESS economics.

#### Acceptance Criteria

1. WHEN battery specifications and region are provided, THE Cost_Structure_Engine SHALL calculate total annual FIXED costs per MW by summing TUOS demand charges, land lease, and fixed O&M
2. WHEN battery specifications, region, and annual throughput are provided, THE Cost_Structure_Engine SHALL calculate total annual VARIABLE costs by multiplying each variable rate by the corresponding energy volume
3. THE Cost_Structure_Engine SHALL calculate Gross Energy as the sum of charge energy and discharge energy for AEMO Participant Fee computation
4. THE Cost_Structure_Engine SHALL apply MLF as a multiplier to the settlement price in revenue calculations rather than as a cost line item
5. THE Cost_Structure_Engine SHALL produce a cost breakdown summary showing each component's annual dollar amount and its percentage of total cost
6. THE Cost_Structure_Engine SHALL integrate the calculated costs into the existing 20-year cash flow model by replacing the current single combined network fee

### Requirement 4: Company Tax Calculation

**User Story:** As an investment analyst, I want the model to calculate Australian company tax on BESS operating profits, so that after-tax returns accurately reflect investor outcomes.

#### Acceptance Criteria

1. THE Tax_Model SHALL apply a company tax rate of 30 percent to taxable income for standard entities
2. WHERE the base rate entity option is selected (turnover less than $50 million), THE Tax_Model SHALL apply a company tax rate of 25 percent
3. THE Tax_Model SHALL calculate taxable income for each year as total revenue minus operating expenses minus interest expense minus depreciation deduction, where total revenue includes all income streams produced by the Financial_Model (arbitrage revenue, FCAS revenue, and any other modeled revenue)
4. IF taxable income is negative in a given year, THEN THE Tax_Model SHALL record a tax loss, set tax payable to zero for that year, and carry forward the full loss amount indefinitely to offset taxable income in subsequent years until the accumulated loss balance is fully utilized
5. THE Tax_Model SHALL allow users to select between standard entity (30 percent) and base rate entity (25 percent) tax rates, with standard entity as the default selection
6. IF taxable income is positive and a carried-forward tax loss balance exists, THEN THE Tax_Model SHALL reduce taxable income by the lesser of the current year taxable income and the remaining loss balance before calculating tax payable

### Requirement 5: Depreciation Calculation

**User Story:** As an investment analyst, I want the model to calculate BESS asset depreciation using ATO-compliant methods, so that the depreciation tax shield is accurately quantified.

#### Acceptance Criteria

1. THE Tax_Model SHALL support Diminishing Value depreciation method calculated as (200 percent divided by effective life in years) multiplied by the asset's written-down value each year
2. THE Tax_Model SHALL support Prime Cost depreciation method calculated as (100 percent divided by effective life in years) multiplied by the asset's original cost each year
3. THE Tax_Model SHALL use a configurable effective life parameter with a default value of 20 years for BESS assets
4. THE Tax_Model SHALL allow users to select between Diminishing Value and Prime Cost depreciation methods
5. THE Tax_Model SHALL calculate the depreciation tax shield as the annual depreciation amount multiplied by the applicable tax rate
6. THE Tax_Model SHALL calculate the NPV of total depreciation tax savings over the project life using the project discount rate

### Requirement 6: After-Tax Cash Flow Integration

**User Story:** As an investment analyst, I want after-tax cash flows integrated into the existing 20-year financial model, so that I can compare pre-tax and after-tax investment metrics side by side.

#### Acceptance Criteria

1. THE Tax_Model SHALL calculate after-tax net cash flow for each year as pre-tax cash flow minus tax payable plus depreciation (non-cash add-back)
2. THE Tax_Model SHALL deduct debt interest expense from taxable income as a tax-deductible item
3. THE Tax_Model SHALL compute after-tax IRR from the series of after-tax cash flows including initial equity investment
4. THE Tax_Model SHALL compute after-tax NPV by discounting after-tax cash flows at the project discount rate
5. THE Financial_Model SHALL present both pre-tax and after-tax metrics (IRR, NPV) in the investment analysis response
6. THE Tax_Model SHALL integrate with the existing CashFlowYear model by adding tax-related fields without removing existing pre-tax fields

### Requirement 7: Supply-Demand Event Registry

**User Story:** As an investment analyst, I want a database of known future supply-demand events with their expected price impact, so that forward-looking scenarios are grounded in real market intelligence.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL maintain a registry of future supply-demand events including coal plant closures, new BESS commissioning dates, and renewable generation buildout schedules
2. THE Forward_Price_Engine SHALL store for each event: event type, affected region, expected date, capacity in MW, and estimated impact on daily price spread distribution
3. THE Forward_Price_Engine SHALL integrate with existing coal_retirement_schedule.json as a data source for coal closure events
4. THE Forward_Price_Engine SHALL integrate with existing capacity_data.json as a data source for new capacity additions
5. WHEN a new event is added to the registry, THE Forward_Price_Engine SHALL recalculate affected scenario projections

### Requirement 8: Price Distribution Modeling

**User Story:** As an investment analyst, I want price scenarios modeled as distributions rather than point forecasts, so that I can understand the range of possible revenue outcomes.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL model daily price spread (defined as the difference between the maximum and minimum settlement price within a trading day, in $/MWh) as a log-normal probability distribution characterized by mean, standard deviation, and spike frequency parameters for each future year
2. THE Forward_Price_Engine SHALL define spike frequency as the proportion of settlement intervals where the price exceeds $3,000 per MWh, expressed as a value between 0.0 and 1.0
3. THE Forward_Price_Engine SHALL adjust distribution parameters for each future year by applying event impacts from the Supply-Demand Event Registry multiplicatively, where each event's impact factor is applied sequentially in chronological order to the prior year's parameters
4. THE Forward_Price_Engine SHALL model BESS price-setting saturation by applying a spread compression factor to the mean spread parameter, where the compression factor decreases as the ratio of total BESS capacity to peak demand increases, producing a compression factor between 0.0 and 1.0
5. THE Forward_Price_Engine SHALL estimate capture rates as a value between 0.0 and 1.0, representing the proportion of the modeled daily spread that a BESS can realize as revenue, based on the relationship between evening peak prices (defined as the 16:00-21:00 local time window) and the aggregate battery bid stack in the region
6. WHEN distribution parameters are calculated for a future year, THE Forward_Price_Engine SHALL output mean spread in $/MWh (range 0 to 10,000), standard deviation in $/MWh (range 0 to 5,000), and spike frequency (range 0.0 to 1.0) as numeric values

### Requirement 9: Three-Scenario Framework

**User Story:** As an investment analyst, I want three defined price scenarios (Central, High, Low), so that I can assess BESS investment viability across a range of market futures.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL define a Central scenario aligned with the AEMO ISP central development path assumptions
2. THE Forward_Price_Engine SHALL define a High scenario assuming accelerated coal retirement and slower-than-planned BESS buildout
3. THE Forward_Price_Engine SHALL define a Low scenario assuming faster BESS buildout and coal plant life extensions
4. THE Forward_Price_Engine SHALL calculate distinct price distribution parameters (mean spread, standard deviation, spike frequency) for each scenario for each future year
5. THE Forward_Price_Engine SHALL produce scenario results for each of the six regions (NSW1, QLD1, VIC1, SA1, TAS1, WEM)

### Requirement 10: Scenario Revenue Impact Calculation

**User Story:** As an investment analyst, I want each scenario to produce an estimated annual revenue per MW, so that I can directly compare scenario outcomes in the financial model.

#### Acceptance Criteria

1. WHEN a scenario's price distribution parameters and battery specifications are provided, THE Forward_Price_Engine SHALL estimate annual arbitrage revenue per MW based on the modeled spread distribution
2. THE Forward_Price_Engine SHALL account for battery round-trip efficiency, duration, and daily cycle limits when calculating revenue from the price distribution
3. THE Forward_Price_Engine SHALL account for state-of-health degradation when projecting revenue across the 20-year project life
4. THE Forward_Price_Engine SHALL produce a 20-year revenue projection for each scenario showing annual revenue per MW
5. THE Forward_Price_Engine SHALL integrate scenario revenue projections with the existing Financial_Model to produce scenario-specific NPV, IRR, and payback metrics

### Requirement 11: Cost Structure Serialization

**User Story:** As a developer, I want the cost structure configuration to be serializable and deserializable, so that fee parameters can be stored, transmitted via API, and restored without data loss.

#### Acceptance Criteria

1. THE Cost_Structure_Engine SHALL serialize all fee parameters to JSON format for API transmission and storage
2. THE Cost_Structure_Engine SHALL deserialize JSON fee parameters back into the internal cost model without data loss
3. FOR ALL valid cost structure configurations, serializing then deserializing SHALL produce an equivalent configuration object (round-trip property)

### Requirement 12: Tax Model Serialization

**User Story:** As a developer, I want the tax model configuration and results to be serializable, so that tax parameters and computed values can be stored and transmitted via API.

#### Acceptance Criteria

1. THE Tax_Model SHALL serialize all tax parameters (tax rate, depreciation method, effective life) to JSON format
2. THE Tax_Model SHALL deserialize JSON tax parameters back into the internal tax model without data loss
3. FOR ALL valid tax model configurations, serializing then deserializing SHALL produce an equivalent configuration object (round-trip property)

### Requirement 13: Forward Price Engine Serialization

**User Story:** As a developer, I want scenario definitions and results to be serializable, so that forward price configurations can be stored and shared.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL serialize scenario definitions and event registry entries to JSON format
2. THE Forward_Price_Engine SHALL deserialize JSON scenario data back into internal model objects without data loss
3. FOR ALL valid scenario configurations, serializing then deserializing SHALL produce an equivalent configuration object (round-trip property)

### Requirement 14: Error Handling for Invalid Inputs

**User Story:** As a developer, I want the modules to handle invalid inputs gracefully, so that the system remains stable when receiving malformed or out-of-range parameters.

#### Acceptance Criteria

1. IF an MLF value outside the range 0.50 to 1.50 is provided, THEN THE Cost_Structure_Engine SHALL reject the input and return a descriptive validation error
2. IF a negative fee rate is provided, THEN THE Cost_Structure_Engine SHALL reject the input and return a descriptive validation error
3. IF a tax rate outside the range 0 to 1 is provided, THEN THE Tax_Model SHALL reject the input and return a descriptive validation error
4. IF an effective life of zero or negative years is provided, THEN THE Tax_Model SHALL reject the input and return a descriptive validation error
5. IF a scenario contains an event with a date in the past, THEN THE Forward_Price_Engine SHALL log a warning and exclude the event from future projections
6. IF required data files (coal_retirement_schedule.json, capacity_data.json) are missing, THEN THE Forward_Price_Engine SHALL return a descriptive error indicating which file is unavailable

### Requirement 15: API Integration

**User Story:** As a frontend developer, I want the financial accuracy modules exposed through the existing FastAPI backend, so that the React frontend can access decomposed costs, tax results, and scenario projections.

#### Acceptance Criteria

1. THE Cost_Structure_Engine SHALL expose a GET endpoint returning the default fee breakdown for a specified region
2. THE Cost_Structure_Engine SHALL accept fee override parameters in the existing investment-analysis POST endpoint
3. THE Tax_Model SHALL expose tax calculation results as part of the investment-analysis response payload
4. THE Forward_Price_Engine SHALL expose a GET endpoint returning available scenarios and their summary parameters
5. THE Forward_Price_Engine SHALL accept a scenario selection parameter in the investment-analysis POST endpoint to run forward-looking analysis
6. WHEN the investment-analysis endpoint is called with cost structure and tax parameters, THE Financial_Model SHALL return both pre-tax and after-tax metrics in a single response
