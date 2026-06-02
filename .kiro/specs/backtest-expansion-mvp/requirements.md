# Requirements Document

## Introduction

本特性将 Forward Price Engine 的回测框架从当前 16 个 Modo Energy 基准时段扩展到 96+ 个月度数据点，利用本地 `data/aemo_data.db` 中已有的 247 万行 AEMO 5 分钟级实测数据。扩展包含三个核心能力：月度基准重构（A）、独立 capture rate 直算（D）、月度自动 reconciliation（H）。所有新增验证逻辑不替换现有 Modo 基准验证，仅作为补充层叠加。

## Glossary

- **Forward_Price_Engine**: 远期价格引擎，负责计算各区域各年度的 mean_spread、price_distribution 和 20 年投资预测
- **AEMO_Database**: 本地 SQLite 数据库 `data/aemo_data.db`，包含 2020–2026 年 5 分钟级交易价格数据
- **Monthly_Benchmark_Calculator**: 新增模块，从 AEMO 实测数据按月×区域聚合计算月度 mean_spread 基准值
- **Capture_Rate_Calculator**: 新增模块，基于 AEMO 实测数据计算"4h 完美预见"理论最优 BESS capture rate
- **Reconciliation_Scheduler**: 月度自动对账调度任务，每月对比上月实测值与模型预测
- **Mean_Spread**: 日内价差指标。本 spec 的月度基准采用此规范定义：某日历月内每日 max(rrp) - min(rrp) 的算术平均值（按自然月聚合）。注：ML calibration engine 的 rolling_30d_spread 是相关但不同的概念（30 天滚动均值），本 spec 的月度基准以上述自然月算术均值为准
- **Capture_Rate**: BESS 套利效率指标，表示实际（或理论最优）套利收入占理论最大收入的比例
- **Perfect_Foresight_Strategy**: 完美预见策略，假设电池每天精确知道未来价格，选择最优充放电时段
- **NEM_Region**: NEM 市场区域，包括 NSW1、QLD1、SA1、TAS1、VIC1 五个区域（不含 WEM）
- **Modo_Benchmark**: 现有 16 时段基准数据，来源于 Modo Energy 公开摘要，保持不变
- **Deviation_Threshold**: 偏差告警阈值，月度 reconciliation 中触发告警的百分比界限
- **Backtest_Expansion_Module**: 新增 Python 模块 `backend/engines/backtest_expansion.py`，封装月度基准计算和 capture rate 直算逻辑

## Requirements

### Requirement 1: 月度 Mean Spread 基准计算

**User Story:** As a model developer, I want to compute monthly mean_spread benchmarks from AEMO actual trading data, so that I can validate the Forward Price Engine against 96+ real data points instead of only 16 Modo benchmarks.

#### Acceptance Criteria

1. WHEN a target region and year-month are provided, THE Monthly_Benchmark_Calculator SHALL query the corresponding `trading_price_{year}` table from AEMO_Database and compute the monthly mean_spread as the average of daily (max_rrp - min_rrp) values over that calendar month
2. THE Monthly_Benchmark_Calculator SHALL support all five NEM_Region values (NSW1, QLD1, SA1, TAS1, VIC1) and exclude WEM from monthly benchmark calculations
3. WHEN computing daily spread for a given day, THE Monthly_Benchmark_Calculator SHALL use all 5-minute intervals within that calendar day (00:00:00 to 23:55:00 AEST) grouped by DATE(settlement_date)
4. THE Monthly_Benchmark_Calculator SHALL produce benchmark data points for all months from 2024-01 through the latest complete month available in AEMO_Database
5. IF a month contains fewer than 20 days of valid data (fewer than 20 distinct dates with at least 200 intervals each), THEN THE Monthly_Benchmark_Calculator SHALL mark that month as "insufficient_data" and exclude it from validation comparisons
6. THE Monthly_Benchmark_Calculator SHALL store computed monthly benchmarks in a structured format containing region, year_month, mean_spread_aud_mwh, sample_days, and data_quality_flag fields

### Requirement 2: 月度基准验证方法

**User Story:** As a model developer, I want to compare the Forward Price Engine's mean_spread predictions against monthly AEMO benchmarks, so that I can measure model accuracy across a much larger validation set.

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL expose a `validate_against_monthly_benchmarks` method that compares model-predicted mean_spread against AEMO-derived monthly benchmarks for each region-month combination
2. WHEN `validate_against_monthly_benchmarks` is invoked, THE Forward_Price_Engine SHALL call `calculate_price_distribution` for each region-month and extract the mean_spread value for comparison
3. THE Forward_Price_Engine SHALL compute deviation_pct as (model_mean_spread - benchmark_mean_spread) / benchmark_mean_spread × 100 for each data point
4. THE Forward_Price_Engine SHALL report aggregate metrics including MAPE, RMSE, Bias, and Hit Rate (percentage of data points with |deviation| ≤ 30%) across all monthly benchmarks
5. THE Forward_Price_Engine SHALL return results in a structure compatible with the existing `validate_against_benchmarks` output format, containing per-point results and summary statistics
6. WHEN `validate_against_monthly_benchmarks` is invoked, THE Forward_Price_Engine SHALL NOT modify or replace the existing Modo benchmark validation logic in `validate_against_benchmarks`

### Requirement 3: 理论最优 Capture Rate 直算

**User Story:** As a model developer, I want to compute the theoretical optimal BESS capture rate directly from AEMO data using a perfect foresight strategy, so that I have an independent ground truth to validate the model's capture rate estimates.

#### Acceptance Criteria

1. WHEN a target region and year-month are provided, THE Capture_Rate_Calculator SHALL compute the theoretical optimal daily arbitrage revenue using a 4-hour battery Perfect_Foresight_Strategy: identify the 4 highest-price hours for discharge and 4 lowest-price hours for charge within each day
2. THE Capture_Rate_Calculator SHALL apply round-trip efficiency (RTE = 0.87) to the charge cost, computing daily_revenue as Σ(discharge_price × 1MW × 1h) - Σ(charge_price × 1MW × 1h / RTE) for each day
3. THE Capture_Rate_Calculator SHALL compute monthly_capture_rate as monthly_actual_revenue / (monthly_mean_spread × days_in_month × 4h × RTE), where monthly_actual_revenue is the sum of daily revenues
4. THE Capture_Rate_Calculator SHALL produce capture rate values for all five NEM_Region values and all months from 2024-01 through the latest complete month
5. WHEN the computed capture_rate exceeds 1.0 for a given month, THE Capture_Rate_Calculator SHALL cap the value at 1.0 and flag it as "capped" in the output
6. THE Capture_Rate_Calculator SHALL provide a comparison method that validates the Forward_Price_Engine's `_compute_capture_rate` output is less than or equal to the perfect foresight capture rate (with a 5% tolerance margin for numerical precision)

### Requirement 4: Capture Rate 合理性验证

**User Story:** As a model developer, I want to verify that the model's predicted capture rate is bounded by the theoretical optimum, so that I can detect when the model produces unrealistically high capture rate estimates.

#### Acceptance Criteria

1. WHEN comparing model capture rate against perfect foresight capture rate, THE Capture_Rate_Calculator SHALL flag any region-month where model_capture_rate > perfect_foresight_capture_rate + 0.05 as a "violation"
2. THE Capture_Rate_Calculator SHALL report the total violation count and list all violating region-month pairs with their respective values
3. WHILE the model's capture rate is within the valid range (model ≤ perfect_foresight + 0.05), THE Capture_Rate_Calculator SHALL report the ratio model/perfect_foresight as "efficiency_ratio" (expected range: 0.50–0.95 for realistic autobidder performance)
4. IF the efficiency_ratio falls below 0.40 for any region-month, THEN THE Capture_Rate_Calculator SHALL log a warning indicating the model may be underestimating capture potential for that period

### Requirement 5: 月度自动 Reconciliation 调度

**User Story:** As a platform operator, I want the system to automatically compare last month's actual data against model predictions on the 1st of each month, so that I can detect model drift without manual intervention.

#### Acceptance Criteria

1. THE Reconciliation_Scheduler SHALL execute on the 1st day of each month at a configurable hour (default: 03:00 UTC), using the existing APScheduler infrastructure in `backend/app.py`
2. WHEN triggered, THE Reconciliation_Scheduler SHALL compute the monthly mean_spread benchmark for the previous calendar month across all five NEM_Region values
3. WHEN triggered, THE Reconciliation_Scheduler SHALL compare the computed benchmark against the Forward_Price_Engine's predicted mean_spread for the same region-month
4. THE Reconciliation_Scheduler SHALL write results to `reports/monthly_reconciliation.json` in append mode, preserving historical reconciliation records
5. IF the absolute deviation exceeds 40% for any region-month, THEN THE Reconciliation_Scheduler SHALL emit a `logger.warning` message containing the region, month, model value, actual value, and deviation percentage
6. THE Reconciliation_Scheduler SHALL be configurable via environment variable `AUS_ELE_RECONCILIATION_HOUR` (default: 3) and `AUS_ELE_RECONCILIATION_ENABLED` (default: true)

### Requirement 6: Reconciliation 报告格式

**User Story:** As a model developer, I want reconciliation results stored in a structured, queryable format, so that I can track model drift over time and identify systematic biases.

#### Acceptance Criteria

1. THE Reconciliation_Scheduler SHALL write each monthly reconciliation as a JSON object containing: run_date, target_month, results (array of per-region comparisons), and summary (MAPE, max_deviation, violation_count)
2. WHEN writing to `reports/monthly_reconciliation.json`, THE Reconciliation_Scheduler SHALL maintain a JSON array of all historical reconciliation records, appending new results without overwriting previous entries
3. THE Reconciliation_Scheduler SHALL include in each per-region result: region, model_mean_spread, actual_mean_spread, deviation_pct, capture_rate_comparison (model vs perfect_foresight), and alert_triggered (boolean)
4. IF the reconciliation report file does not exist, THEN THE Reconciliation_Scheduler SHALL create it with an initial empty array structure

### Requirement 7: 回测脚本扩展

**User Story:** As a model developer, I want the full backtest script to include monthly AEMO benchmark validation as a new section, so that I can run comprehensive validation in a single command.

#### Acceptance Criteria

1. THE `run_full_backtest.py` script SHALL include a new section "I. 月度 AEMO 基准验证" that invokes `validate_against_monthly_benchmarks` and reports results
2. THE new section SHALL report per-region-month deviations, aggregate MAPE, RMSE, Bias, and Hit Rate metrics consistent with Section A's reporting format
3. THE new section SHALL report the total number of monthly benchmark data points validated (target: 96+ for 24 months × 4+ regions)
4. WHEN the new section executes, THE script SHALL NOT affect the pass/fail counts of existing sections A through H
5. THE new section SHALL add its own pass/fail metrics to the overall backtest summary, using the same threshold conventions (MAPE ≤ 30%, Hit Rate ≥ 75%)

### Requirement 8: 非回归约束

**User Story:** As a model developer, I want all new backtest expansion code to coexist with existing validated logic without causing regressions, so that the current 33/33 backtest pass rate and 20 PBT tests remain intact.

#### Acceptance Criteria

1. THE Backtest_Expansion_Module SHALL NOT modify the existing `validate_against_benchmarks` method, `_compute_capture_rate` method, `SEASONAL_CAPTURE_MULTIPLIER` constant, or `REGIONAL_VOLATILITY_FACTOR` constant in Forward_Price_Engine
2. THE Backtest_Expansion_Module SHALL NOT modify `data/capacity_data.json` or `data/financial_evidence.json`
3. WHEN the full backtest suite is executed, THE existing 33 validation points in sections A through H SHALL continue to pass with identical results
4. WHEN the property-based test suite is executed, THE existing 20 PBT tests SHALL continue to pass without modification
5. THE Backtest_Expansion_Module SHALL be implemented as a separate module `backend/engines/backtest_expansion.py` with clear interface boundaries to the existing Forward_Price_Engine

### Requirement 9: 数据完整性与错误处理

**User Story:** As a platform operator, I want the backtest expansion to handle missing or corrupt AEMO data gracefully, so that partial data availability does not crash the validation pipeline.

#### Acceptance Criteria

1. IF the AEMO_Database file `data/aemo_data.db` is not accessible, THEN THE Monthly_Benchmark_Calculator SHALL log a warning and return an empty result set without raising an exception
2. IF a `trading_price_{year}` table does not exist for a requested year, THEN THE Monthly_Benchmark_Calculator SHALL skip that year and log an informational message
3. IF a region has no data in a requested month (zero rows returned), THEN THE Monthly_Benchmark_Calculator SHALL exclude that region-month from results and log a debug message
4. WHEN computing daily spreads, THE Monthly_Benchmark_Calculator SHALL handle negative prices (rrp_aud_mwh < 0) as valid data points without filtering or capping
5. IF the SQLite query exceeds 30 seconds for any single month-region computation, THEN THE Monthly_Benchmark_Calculator SHALL abort that computation, log a warning, and continue with remaining region-months
