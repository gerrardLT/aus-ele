# Requirements Document

## Introduction

修正 ForwardPriceEngine 中 BESS 饱和压缩曲线的计算逻辑，使模型输出的年化收入预测贴合 Modo Energy 公开基准数据。当前压缩公式 `compression = 1 / (1 + bess_ratio × sensitivity)` 严重低估了 BESS 饱和对价差的压缩效应（模型偏差 55-440%），需要从三个维度修正：完善 BESS 容量统计、拟合更激进的压缩系数、引入区域差异化参数。

## Glossary

- **ForwardPriceEngine**: 前向价格情景引擎，负责基于供需事件建模未来电价分布并输出 20 年收入预测
- **Compression_Factor**: 压缩因子，取值 [0, 1]，表示 BESS 饱和对价差的压缩程度（0 = 完全压缩，1 = 无压缩）
- **BESS_Ratio**: BESS 容量比率，等于区域累计 BESS 容量除以区域峰值需求
- **Modo_Benchmark**: Modo Energy 公开发布的 NEM 电池储能收入基准数据
- **Price_Setting_Frequency**: BESS 价格设定频率，表示 BESS 在调度间隔中设定边际价格的比例
- **Saturation_Sensitivity**: 情景敏感度系数，用于在 Central/High/Low 情景间调整压缩强度
- **Regional_Volatility_Factor**: 区域波动性因子，反映不同区域因供需结构差异导致的压缩强度差异
- **Capacity_Data**: 存储在 capacity_data.json 中的 BESS 项目容量数据，包含已投产和规划中的项目
- **Event_Registry**: 供需事件注册表，包含煤电退役和 BESS 投产事件

## Requirements

### Requirement 1: 完善 BESS 容量统计

**User Story:** As a financial analyst, I want the BESS capacity ratio to include all committed and under-construction projects, so that the saturation compression reflects the true market supply picture.

#### Acceptance Criteria

1. WHEN calculating cumulative BESS capacity for a target year, THE ForwardPriceEngine SHALL include all projects from Capacity_Data with status "registered", "construction", or "committed" whose commissioning date is on or before the target year
2. WHEN a project in Capacity_Data has an actual_commissioning_date, THE ForwardPriceEngine SHALL use actual_commissioning_date as the commissioning date
3. WHEN a project in Capacity_Data has no actual_commissioning_date, THE ForwardPriceEngine SHALL use expected_commissioning_date as the commissioning date
4. THE ForwardPriceEngine SHALL combine capacity from both Event_Registry BESS_COMMISSIONING events and Capacity_Data projects without double-counting projects that appear in both sources
5. IF a project appears in both Event_Registry and Capacity_Data, THEN THE ForwardPriceEngine SHALL use the Capacity_Data entry and skip the duplicate Event_Registry entry

### Requirement 2: 拟合更激进的压缩公式

**User Story:** As a financial analyst, I want the compression formula to match real-world Modo Energy benchmark data, so that revenue projections are within ±30% of observed market outcomes.

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL compute Compression_Factor using a formula calibrated to produce compression levels consistent with Modo_Benchmark data (QLD1: ~73% compression at bess_ratio=0.03 effective, NSW1: ~51% at bess_ratio=0.12 effective, SA1: ~34% at bess_ratio=0.18 effective, VIC1: ~50% at bess_ratio=0.09 effective)
2. WHEN bess_ratio equals zero, THE ForwardPriceEngine SHALL output a Compression_Factor of 1.0 (no compression)
3. WHEN bess_ratio increases, THE ForwardPriceEngine SHALL output a monotonically decreasing Compression_Factor
4. THE ForwardPriceEngine SHALL clamp Compression_Factor to the range [0.05, 1.0] to prevent complete revenue elimination
5. WHEN the compression formula is applied, THE ForwardPriceEngine SHALL produce annual revenue per MW that deviates no more than ±30% from the corresponding Modo_Benchmark value for each NEM region

### Requirement 3: 引入区域波动性差异化

**User Story:** As a financial analyst, I want the compression model to account for regional volatility differences, so that high-volatility regions like SA1 show weaker compression than low-volatility regions like QLD1.

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL apply a Regional_Volatility_Factor that modifies the effective compression strength per region
2. WHEN computing compression for SA1, THE ForwardPriceEngine SHALL apply a weaker compression (higher Compression_Factor) compared to QLD1 at the same BESS_Ratio, reflecting SA1's higher price volatility
3. THE ForwardPriceEngine SHALL define Regional_Volatility_Factor values for all supported NEM regions (NSW1, QLD1, VIC1, SA1, TAS1)
4. WHEN Regional_Volatility_Factor is 1.0, THE ForwardPriceEngine SHALL apply the baseline compression strength without modification

### Requirement 4: 引入 BESS 价格设定频率因子

**User Story:** As a financial analyst, I want the model to incorporate BESS price-setting frequency as an additional compression driver, so that the accelerating trend of batteries setting marginal prices is reflected in forward projections.

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL incorporate Price_Setting_Frequency as an input to the compression calculation
2. WHEN Price_Setting_Frequency increases, THE ForwardPriceEngine SHALL produce a lower Compression_Factor (stronger compression)
3. THE ForwardPriceEngine SHALL interpolate Price_Setting_Frequency between known data points: 1% in 2020, 22% in 2025, and 41% in Q1 2026
4. WHEN projecting beyond 2026, THE ForwardPriceEngine SHALL extrapolate Price_Setting_Frequency using a logistic growth curve capped at 70% maximum
5. IF Price_Setting_Frequency data is unavailable for a region, THEN THE ForwardPriceEngine SHALL fall back to the NEM-wide average value

### Requirement 5: 验证与回归测试

**User Story:** As a developer, I want automated validation against Modo benchmarks, so that future changes do not regress the model accuracy below the ±30% threshold.

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL provide a validation method that compares model output against stored Modo_Benchmark data points
2. WHEN the validation method is executed, THE ForwardPriceEngine SHALL report the percentage deviation between model output and Modo_Benchmark for each region-year combination
3. FOR ALL region-year combinations with available Modo_Benchmark data, THE ForwardPriceEngine SHALL produce revenue estimates within ±30% of the benchmark value
4. WHEN a new Modo_Benchmark data point is added to financial_evidence.json, THE ForwardPriceEngine SHALL include the new data point in subsequent validation runs without code changes
5. IF any region-year deviation exceeds ±30%, THEN THE ForwardPriceEngine SHALL log a warning with the region, year, model value, benchmark value, and percentage deviation

### Requirement 6: 向后兼容与情景差异化

**User Story:** As a developer, I want the updated compression logic to maintain scenario differentiation and API compatibility, so that existing consumers of ForwardPriceEngine are not broken.

#### Acceptance Criteria

1. THE ForwardPriceEngine SHALL maintain the existing method signature of calculate_price_distribution(region, scenario, year, bess_capacity_ratio)
2. WHEN scenario is HIGH (faster BESS deployment), THE ForwardPriceEngine SHALL produce stronger compression than CENTRAL scenario for the same region and year
3. WHEN scenario is LOW (slower BESS deployment), THE ForwardPriceEngine SHALL produce weaker compression than CENTRAL scenario for the same region and year
4. THE ForwardPriceEngine SHALL continue to output PriceDistribution objects with all existing fields (mean_spread, std_dev, spike_frequency, compression_factor, capture_rate)
5. WHEN bess_capacity_ratio is zero and no events are applied, THE ForwardPriceEngine SHALL produce output identical to the base spread parameters for the region
