# Requirements Document

## Introduction

ML 校准反推验证功能，验证 ML 校准后的 ForwardPriceEngine 输出是否贴合真实市场数据。核心目标：修复 R²=0.99 过拟合问题、将模型预测反推为年化收入与 Modo Energy 基准对比、在前端展示校准状态。

## Glossary

- **ML_Calibration_Engine**: ML 校准引擎（ml_calibration_engine.py），使用 LightGBM 分位数回归
- **ForwardPriceEngine**: 前瞻价格引擎（forward_price_engine.py），基于供需事件建模未来电价分布
- **ForwardSpreadCurve_Component**: 前端前瞻价差曲线组件（ForwardSpreadCurve.jsx）
- **mean_spread**: 30 天滚动平均价差（$/MWh），ForwardPriceEngine 的核心输出
- **Modo_Benchmark**: Modo Energy 公开发布的 NEM BESS 收入基准数据
- **lag_30_spread**: 前 30 天日均价差均值（特征），与目标变量 rolling_30d_spread 共享 29/30 天数据
- **rolling_30d_spread**: 前 30 天（含当天）daily_spread 均值（目标变量）
- **Annualized_Revenue**: 年化 BESS 收入 = spread × 365 × 4h × capture_rate(0.65) × RTE(0.87)

## Requirements

### Requirement 1: 过拟合修复 — 移除冗余特征

**User Story:** As a ML 工程师, I want to 消除 lag_30_spread 与目标变量的数据重叠, so that 模型学习真正的预测能力而非记忆近似值。

#### Acceptance Criteria

1. THE ML_Calibration_Engine SHALL exclude lag_30_spread from the feature_cols list in both `_train_model` and `_generate_calibrated_params` methods
2. THE ML_Calibration_Engine SHALL retain lag_1_spread and lag_7_spread as short-term lag features
3. WHEN the retrained model achieves R² between 0.3 and 0.85 on the validation set and direction_accuracy above 0.45, THE ML_Calibration_Engine SHALL accept the model as properly calibrated
4. WHEN the retrained model achieves R² above 0.85, THE ML_Calibration_Engine SHALL log a warning indicating potential residual overfitting but still accept the model
5. IF R² below 0.3 or direction_accuracy at or below 0.45, THEN THE ML_Calibration_Engine SHALL set status to "quality_insufficient" and fall back to default parameters

### Requirement 2: 收入反推验证与 Modo 基准对比

**User Story:** As a 投资分析师, I want to 将模型预测的 mean_spread 反推为年化 BESS 收入并与 Modo 基准对比, so that 我能验证模型预测的商业合理性。

#### Acceptance Criteria

1. THE backvalidation endpoint SHALL compute annualized revenue using: mean_spread × 365 × 4 × 0.65 × 0.87
2. THE backvalidation endpoint SHALL load Modo benchmark data from the existing `data/financial_evidence.json` file (extending the revenue_benchmarks section with per-region per-period values)
3. THE backvalidation endpoint SHALL support benchmark periods: 2024 full year, 2025 H1, 2025 H2 — with per-region values for NSW1, QLD1, VIC1, SA1 and a NEM-wide average fallback
4. THE backvalidation endpoint SHALL express deviation as: (model_revenue - benchmark) / benchmark × 100, and classify as "within_range" (≤30%) or "out_of_range" (>30%)
5. THE backvalidation endpoint SHALL return results for all four NEM regions ranked by absolute deviation descending, with a summary count of within_range vs out_of_range regions
6. WHEN a region's model YoY direction disagrees with Modo benchmark YoY direction (ignoring ±1% neutral zone), THE endpoint SHALL flag it as "direction_mismatch"

### Requirement 3: 反推验证 API 端点

**User Story:** As a 前端开发者, I want to 通过 API 获取反推验证结果, so that 前端能展示校准验证状态。

#### Acceptance Criteria

1. THE system SHALL expose GET /api/v1/narrative/backvalidation/summary returning all-region results (route defined before /{region} to avoid path capture)
2. THE system SHALL expose GET /api/v1/narrative/backvalidation/{region} returning single-region result
3. IF region is invalid, THEN return HTTP 422; IF ML calibration unavailable, THEN return HTTP 503
4. THE response SHALL include: model_revenue, benchmark_revenue, deviation_percent, status, confidence_interval (P10/P50/P90), benchmark_period

### Requirement 4: 前端校准状态与验证结果展示

**User Story:** As a 投资分析师, I want to 在前瞻价差曲线图上看到 AI 校准状态和验证结果, so that 我能判断预测的可信度。

#### Acceptance Criteria

1. WHEN calibration status is "calibrated", THE ForwardSpreadCurve_Component SHALL display a green "AI 校准" badge; WHEN status is "failed" or "insufficient_data", display amber badge with tooltip
2. WHEN calibration-status response contains non-null validation_r2, validation_mae, direction_accuracy, THE component SHALL display these metrics below the chart title
3. WHEN backvalidation data is loaded, THE component SHALL display a validation summary showing model revenue vs Modo benchmark with color coding: green (≤15%), amber (15-30%), red (>30%)
4. THE component SHALL display "数据来源: Modo Energy" attribution below validation results
5. IF calibration-status or backvalidation API fails, THE component SHALL hide the respective section without blocking chart rendering
6. THE component SHALL support zh/en localization for all new labels via the existing LABELS object
