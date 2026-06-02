# Design Document: ML Calibration Backvalidation

## Overview

精简版设计：修复过拟合 + 收入反推验证 + 前端展示。不新建独立引擎类，反推验证逻辑内联在路由层，基准数据扩展现有 financial_evidence.json。

设计决策：
- **不新建 BackvalidationEngine 类** — 核心逻辑仅 ~50 行，作为 narrative_routes.py 的辅助函数
- **扩展现有 financial_evidence.json** — 不新建 modo_benchmark.json，复用已有数据结构
- **移除 Requirement 4（前瞻预测模式）** — 作为独立后续优化，不混入本次修复
- **精简 PBT** — 仅保留非平凡属性（校准状态分类、区域排序、方向不匹配检测）

## Architecture

```
ForwardPriceEngine (existing, unchanged)
  └── _try_ml_calibration() → MLCalibrationEngine (modified: remove lag_30_spread)

narrative_routes.py (extended)
  ├── GET /backvalidation/summary  ← 新增，内联计算逻辑
  ├── GET /backvalidation/{region} ← 新增
  └── _compute_backvalidation()    ← 辅助函数（~50 行）

financial_evidence.json (extended)
  └── modo_benchmarks: {period → {region → revenue_per_mw_year}}

ForwardSpreadCurve.jsx (extended)
  ├── 校准 badge（绿色/琥珀色）
  ├── 精度指标面板（R², MAE, 方向准确率）
  └── 验证摘要（model vs benchmark + 偏差）
```

## Components and Interfaces

### 1. MLCalibrationEngine 修改（2 处改动）

```python
# backend/engines/ml_calibration_engine.py

# _train_model() 中的 feature_cols — 移除 "lag_30_spread"
feature_cols = [
    "lag_1_avg_price",
    "lag_1_spike_ratio",
    "day_of_week",
    "month_sin",
    "month_cos",
    "is_weekend",
    "bess_capacity_ratio",
    "lag_1_spread",
    "lag_7_spread",
    # "lag_30_spread",  ← 移除
    "rolling_7d_volatility",
    "region_encoded",
]

# _generate_calibrated_params() 中同样移除 "lag_30_spread"

# 质量阈值调整（已有逻辑，确认 R² > 0.85 时加 warning）
if r2 > 0.85:
    logger.warning(f"ML 校准: R²={r2:.3f} 可能存在残余过拟合")
```

### 2. 反推验证辅助函数（narrative_routes.py 内联）

```python
# backend/routes/narrative_routes.py — 新增辅助函数

def _compute_backvalidation(engine: ForwardPriceEngine, region: str) -> dict:
    """反推验证：mean_spread → 年化收入 → 与 Modo 基准对比。"""
    # 获取当前 mean_spread
    current_year = date.today().year
    bess_capacity = engine._get_cumulative_bess_capacity(region, ScenarioType.CENTRAL, current_year + 1)
    peak_demand = PEAK_DEMAND.get(region, 10000.0)
    dist = engine.calculate_price_distribution(
        region=region, scenario=ScenarioType.CENTRAL,
        year=current_year + 1, bess_capacity_ratio=bess_capacity / peak_demand,
    )
    
    # 反推年化收入
    mean_spread = dist.mean_spread
    revenue = mean_spread * 365 * 4 * 0.65 * 0.87
    
    # 加载 Modo 基准
    benchmark = _get_modo_benchmark(region)
    
    # 计算偏差
    deviation = (revenue - benchmark) / benchmark * 100 if benchmark > 0 else None
    status = "out_of_range" if abs(deviation or 0) > 30 else "within_range"
    
    return {
        "region": region,
        "model_revenue": round(revenue, 2),
        "benchmark_revenue": benchmark,
        "deviation_percent": round(deviation, 1) if deviation else None,
        "status": status,
        "mean_spread": round(mean_spread, 2),
    }
```

### 3. 基准数据扩展（financial_evidence.json）

在现有 `data/financial_evidence.json` 的 `cross_validation` 部分添加：

```json
{
  "modo_benchmarks": {
    "source": "Modo Energy",
    "publication_date": "2025-03-15",
    "benchmarks": {
      "2024_full": {
        "NEM_AVG": 148000, "NSW1": 148000, "QLD1": 125000, "VIC1": 135000, "SA1": 165000
      },
      "2025_H1": {
        "NEM_AVG": 157000, "NSW1": 152000, "QLD1": 130000, "VIC1": 145000, "SA1": 175000
      },
      "2025_H2": {
        "NEM_AVG": 73000, "NSW1": 72000, "QLD1": 34000, "VIC1": 68000, "SA1": 109000
      }
    }
  }
}
```

### 4. ForwardSpreadCurve.jsx 扩展

新增两个 API 调用（calibration-status + backvalidation/summary），条件渲染：
- 校准 badge（已有 calibration-status 端点）
- 精度指标（R², MAE, direction_accuracy）
- 验证摘要表格（model revenue vs benchmark）

## Data Models

### API 响应结构

```python
# 单区域验证结果（内联 dict，不新建 Pydantic 模型）
{
    "region": "NSW1",
    "model_revenue": 95949.60,       # $/MW/year
    "benchmark_revenue": 148000.00,  # $/MW/year
    "deviation_percent": -35.2,
    "status": "out_of_range",        # within_range | out_of_range | direction_mismatch
    "mean_spread": 120.0,            # $/MWh
    "confidence_interval": {"p10": 85.0, "p50": 120.0, "p90": 155.0},
    "benchmark_period": "2025_H2"
}

# 摘要响应
{
    "regions": [...],                # 按 |deviation| 降序
    "within_range_count": 2,
    "out_of_range_count": 2,
    "benchmark_source": "Modo Energy",
    "validated_at": "2026-05-26T10:00:00"
}
```

### 基准数据结构（financial_evidence.json 扩展）

```json
{
  "modo_benchmarks": {
    "source": "Modo Energy",
    "publication_date": "2025-03-15",
    "benchmarks": {
      "2024_full": {"NEM_AVG": 148000, "NSW1": 148000, "QLD1": 125000, "VIC1": 135000, "SA1": 165000},
      "2025_H1": {"NEM_AVG": 157000, "NSW1": 152000, "QLD1": 130000, "VIC1": 145000, "SA1": 175000},
      "2025_H2": {"NEM_AVG": 73000, "NSW1": 72000, "QLD1": 34000, "VIC1": 68000, "SA1": 109000}
    }
  }
}
```

## Correctness Properties

仅保留 3 个非平凡属性：

### Property 1: Calibration status classification

*For any* R² ∈ [0, 1] and direction_accuracy ∈ [0, 1]:
- R² ∈ [0.3, 0.85] AND direction_accuracy > 0.45 → "calibrated"
- R² > 0.85 AND direction_accuracy > 0.45 → "calibrated" (with warning)
- R² < 0.3 OR direction_accuracy ≤ 0.45 → "quality_insufficient"

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 2: Region ranking by absolute deviation

*For any* set of region results, output SHALL be sorted by |deviation_percent| descending.

**Validates: Requirements 2.5**

### Property 3: Direction mismatch with neutral zone

*For any* model_yoy and benchmark_yoy, mismatch flagged only when one > +1% and other < -1%.

**Validates: Requirements 2.6**

## Error Handling

| 场景 | 处理 |
|------|------|
| 无效区域 | HTTP 422 |
| ML 校准不可用 | HTTP 503 |
| 基准数据缺失 | 使用 NEM_AVG fallback；全缺失时 deviation=null |
| 前端 API 失败 | 隐藏对应面板，不阻塞图表 |

## Testing Strategy

- **修改现有 `tests/test_ml_calibration_engine.py`**：添加 1 个测试验证 lag_30_spread 已移除
- **新增 `tests/test_backvalidation_routes.py`**：API 端点集成测试（~5 个用例）
- **PBT**：3 个属性测试（校准分类、排序、方向检测），加入现有 test 文件
- **手动验证**：跑一次校准，确认 R² 从 0.99 降到合理范围
