# Requirements Document

## Introduction

本文档定义 AEMO Intelligence 平台的投资前景情景分析模块（Investment Outlook Scenarios）需求。该功能为澳大利亚 NEM/WEM 电力市场的 BESS（电池储能系统）投资者提供 4 个方向性市场展望工具，帮助投资者判断某个区域是否值得投资。

这些模块不是价格预测模型，而是基于供需模型、历史统计和情景模拟的方向性分析工具。每个模块都包含真实市场数据示例，直接回答投资决策问题。

## Glossary

- **Cannibalization_Simulator**: 收入蚕食模拟器，基于管道容量数据模拟前瞻性收入稀释效应的分析引擎
- **FCAS_Collapse_Forecaster**: FCAS 崩塌预判器，基于供需平衡模型预测各 FCAS 服务类型价格天花板的分析引擎
- **Regional_Timing_Scorer**: 区域时机评分器，基于前瞻性因素（煤电退役、管道容量、可再生能源渗透率）计算区域投资吸引力评分的分析引擎
- **Merchant_Risk_Quantifier**: 商户风险量化器，基于蒙特卡洛模拟生成收入分布（P10/P50/P90）并计算合约覆盖需求的分析引擎
- **Dilution_Curve**: 稀释曲线，描述 BESS 容量增加与单位收入下降之间关系的数学模型
- **Pipeline_Capacity**: 管道容量，包括已承诺、在建和规划中的 BESS 项目总容量
- **FCAS_Service**: 频率控制辅助服务，包括 raise/lower 的 1sec、6sec、60sec、5min、reg 共 10 种服务类型
- **Market_Requirement_Volume**: AEMO 为维持系统安全所需的各 FCAS 服务最低采购量
- **Revenue_Distribution**: 收入分布，通过历史情景回测生成的收入概率分布
- **Bankability_Threshold**: 银行融资门槛，银行要求项目 60-80% 收入来自合约以获得项目债务融资
- **Coal_Retirement_Schedule**: 煤电退役时间表，各区域计划退役的煤电机组及其时间节点
- **Renewable_Penetration_Rate**: 可再生能源渗透率，可再生能源发电量占区域总发电量的比例
- **Platform**: AEMO Intelligence 平台，包含 FastAPI 后端、React 前端和 SQLite 数据层的完整分析系统
- **Capacity_Data_Source**: 容量数据源，即 data/capacity_data.json 文件，包含所有 BESS 项目管道信息

## Requirements

### Requirement 1: Revenue Cannibalization Simulation (收入蚕食模拟)

**User Story:** As a BESS investor, I want to simulate how future capacity additions will dilute existing project revenues, so that I can assess the long-term revenue risk before committing capital.

#### Acceptance Criteria

1. WHEN a user selects a target region and a future capacity scenario, THE Cannibalization_Simulator SHALL calculate the projected revenue dilution percentage based on the Dilution_Curve model and Pipeline_Capacity data.
2. WHEN the simulation completes, THE Cannibalization_Simulator SHALL display a dilution curve chart showing the relationship between cumulative BESS capacity (MW) and estimated revenue per MW (AUD/MW/year) for the selected region.
3. THE Cannibalization_Simulator SHALL load Pipeline_Capacity data from the Capacity_Data_Source, including projects with status "committed", "construction", and "planning".
4. WHEN historical revenue data is available, THE Cannibalization_Simulator SHALL annotate the dilution curve with real market examples showing actual revenue decline (e.g., QLD revenue decline from $280k/MW/yr to $73k/MW/yr as capacity tripled).
5. THE Cannibalization_Simulator SHALL support year-by-year projection from the current year to at least 3 years forward, based on expected commissioning dates in the Pipeline_Capacity data.
6. WHEN the projected dilution exceeds 50% of current revenue levels, THE Cannibalization_Simulator SHALL display a warning indicator alongside the projection results.
7. IF the Capacity_Data_Source fails to load or contains no projects for the selected region, THEN THE Cannibalization_Simulator SHALL display an error message indicating the data source issue and suggest verifying the capacity data file.
8. THE Cannibalization_Simulator SHALL provide a summary conclusion stating the expected revenue impact in plain language (e.g., "If 2GW more BESS comes online in NSW by 2027, existing project revenues are projected to decline by 35%").

### Requirement 2: FCAS Revenue Collapse Forecast (FCAS 崩塌预判)

**User Story:** As a BESS investor, I want to understand the price ceiling for each FCAS service given current registered capacity, so that I can avoid overestimating FCAS revenue in my financial models.

#### Acceptance Criteria

1. THE FCAS_Collapse_Forecaster SHALL calculate a supply-demand ratio for each of the 10 FCAS_Service types by dividing registered FCAS-capable capacity by the Market_Requirement_Volume.
2. WHEN the supply-demand ratio for an FCAS_Service exceeds 3.0, THE FCAS_Collapse_Forecaster SHALL classify that service as "collapsed" and display a price ceiling estimate near zero.
3. WHEN the supply-demand ratio for an FCAS_Service is between 1.5 and 3.0, THE FCAS_Collapse_Forecaster SHALL classify that service as "at risk" and display the estimated price ceiling based on the historical price-vs-supply relationship.
4. THE FCAS_Collapse_Forecaster SHALL display a summary table showing each FCAS_Service with its current supply-demand ratio, classification (healthy/at-risk/collapsed), and estimated price ceiling in AUD/MW/hr.
5. WHEN historical FCAS price data is available, THE FCAS_Collapse_Forecaster SHALL include a time-series chart showing the historical revenue decline trajectory (e.g., from $384k/MW/yr in 2020 to $11k/MW/yr in 2025).
6. THE FCAS_Collapse_Forecaster SHALL provide a total estimated FCAS revenue ceiling per MW per year by summing the price ceilings across all 10 services weighted by enablement probability.
7. IF FCAS price data is unavailable for a specific year or service, THEN THE FCAS_Collapse_Forecaster SHALL indicate the data gap and exclude that service from the total ceiling calculation.
8. THE FCAS_Collapse_Forecaster SHALL provide a conclusion statement quantifying the maximum realistic FCAS revenue contribution for new BESS projects (e.g., "Maximum realistic FCAS revenue: $15k/MW/yr, down from $384k/MW/yr in 2020").

### Requirement 3: Regional Timing Selection (区域时机选择)

**User Story:** As a BESS investor, I want to compare regions based on forward-looking factors that drive future BESS economics, so that I can select the optimal region and timing for my investment.

#### Acceptance Criteria

1. THE Regional_Timing_Scorer SHALL calculate a forward-looking attractiveness score for each NEM region incorporating at least these dimensions: Coal_Retirement_Schedule impact, Pipeline_Capacity growth rate, Renewable_Penetration_Rate trend, and historical revenue trajectory.
2. WHEN a user requests the regional timing analysis, THE Regional_Timing_Scorer SHALL display a ranked list of NEM regions with their composite scores and individual dimension scores for the target investment year.
3. THE Regional_Timing_Scorer SHALL incorporate Coal_Retirement_Schedule data to estimate the volatility increase expected from each planned coal plant closure in each region.
4. THE Regional_Timing_Scorer SHALL project the Pipeline_Capacity growth for each region over the next 3 years using expected commissioning dates from the Capacity_Data_Source.
5. WHEN historical data demonstrates a correlation between a factor and revenue outcomes, THE Regional_Timing_Scorer SHALL annotate the results with real examples (e.g., "SA outperformed because coal retirements increased price volatility by 40%").
6. THE Regional_Timing_Scorer SHALL allow users to select a target investment year (current year to current year + 5) to shift the forward-looking projection window.
7. THE Regional_Timing_Scorer SHALL provide a conclusion statement recommending the top region and timing with supporting rationale (e.g., "VIC is projected to be the most attractive region in 2027-2028 due to Yallourn closure and moderate pipeline growth").
8. IF Coal_Retirement_Schedule data is unavailable, THEN THE Regional_Timing_Scorer SHALL proceed with the remaining dimensions and indicate that coal retirement impact is excluded from the analysis.

### Requirement 4: Contract vs Merchant Risk Quantification (合约风险量化)

**User Story:** As a BESS investor seeking project finance, I want to understand the probability distribution of merchant revenue outcomes, so that I can determine the minimum contract coverage needed to meet bankability requirements.

#### Acceptance Criteria

1. WHEN a user selects a region and BESS configuration, THE Merchant_Risk_Quantifier SHALL run a Monte Carlo simulation using historical price scenarios to generate a Revenue_Distribution with P10, P50, and P90 outcomes in AUD/MW/year.
2. THE Merchant_Risk_Quantifier SHALL use the existing backtest engine to generate revenue samples across at least 3 historical years of price data for the selected region.
3. THE Merchant_Risk_Quantifier SHALL display the Revenue_Distribution as a histogram or probability density chart with P10, P50, and P90 values clearly marked.
4. WHEN the Revenue_Distribution is calculated, THE Merchant_Risk_Quantifier SHALL compute the minimum contract coverage percentage needed to meet the Bankability_Threshold (assuming banks require the P90 revenue to cover at least 60% of debt service).
5. THE Merchant_Risk_Quantifier SHALL display a summary output in the format: "P50 = $X/MW/yr, P90 = $Y/MW/yr → need Z% contract coverage for bankability".
6. THE Merchant_Risk_Quantifier SHALL allow users to adjust the debt service coverage ratio assumption (default 1.3x) and the bank contract requirement percentage (default 60-80% range).
7. IF fewer than 2 years of historical price data are available for the selected region, THEN THE Merchant_Risk_Quantifier SHALL display a warning that the distribution may not be statistically representative and indicate the number of scenarios used.
8. THE Merchant_Risk_Quantifier SHALL provide a conclusion statement with a clear investment recommendation regarding contract strategy (e.g., "With P90 at $65k/MW/yr, a minimum 40% contract coverage at $100k/MW/yr is recommended for bankability").

### Requirement 5: Platform Integration (平台集成)

**User Story:** As a platform user, I want the outlook scenario modules to integrate seamlessly with the existing analysis workflow, so that I can access them within the familiar stage-based navigation.

#### Acceptance Criteria

1. THE Platform SHALL register all 4 outlook scenario modules in the MODULE_REGISTRY within marketConfig.js with appropriate category and description metadata.
2. THE Platform SHALL expose each outlook scenario module through a dedicated FastAPI route under the `/api/v1/nem/outlook/` prefix, following the existing route pattern conventions.
3. WHEN a user navigates to the outlook scenarios stage, THE Platform SHALL render the modules using the existing ModuleRenderer component with lazy loading.
4. THE Platform SHALL include the standard `metadata` response object in all outlook scenario API responses, consistent with the existing API contract (market, region, timezone, currency, methodology_version fields).
5. IF an outlook scenario API request fails due to missing data, THEN THE Platform SHALL return a structured error response with error_code, message, and suggested_action fields consistent with existing error handling patterns.
6. THE Platform SHALL support the NEM market for all 4 modules, and the WEM market for the Cannibalization_Simulator and Regional_Timing_Scorer where applicable data exists.

### Requirement 6: Real Market Examples and Trust Building (真实市场示例)

**User Story:** As a BESS investor, I want to see real historical market data examples in the analysis outputs, so that I can trust the projections are grounded in actual market behavior.

#### Acceptance Criteria

1. THE Cannibalization_Simulator SHALL include at least one annotated real example per region where historical data demonstrates revenue decline correlated with capacity growth.
2. THE FCAS_Collapse_Forecaster SHALL include the historical FCAS revenue trajectory from 2020 to the latest available year with actual dollar values per MW per year.
3. THE Regional_Timing_Scorer SHALL include at least one comparative example showing how a region's revenue changed after a significant market event (coal retirement, capacity addition, or policy change).
4. THE Merchant_Risk_Quantifier SHALL display the actual historical revenue range observed in backtest results alongside the Monte Carlo distribution.
5. WHEN displaying real market examples, THE Platform SHALL cite the data source year and region to enable user verification.
6. THE Platform SHALL clearly label projected values as "projected" and historical values as "actual" to prevent confusion between forecasts and observed data.
