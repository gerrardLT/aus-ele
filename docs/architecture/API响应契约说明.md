# API响应契约说明

本文档定义当前项目主分析接口的统一响应契约，用于前端展示、接口联调、回归验证和后续 OpenAPI 细化。

## 1. 统一 metadata 对象

以下接口的响应都应包含 `metadata`：

- `GET /api/price-trend`
- `GET /api/peak-analysis`
- `GET /api/hourly-price-profile`
- `GET /api/fcas-analysis`
- `GET /api/event-overlays`
- `GET /api/grid-forecast`
- `POST /api/bess/backtests`
- `POST /api/investment-analysis`
- `GET /api/fingrid/datasets/{dataset_id}/status`

标准字段：

| 字段 | 含义 |
| --- | --- |
| `market` | 市场代码，如 `NEM`、`WEM`、`FINGRID` |
| `region_or_zone` | 区域或分区标识，如 `NSW1`、`WEM`、`317` |
| `timezone` | 本地展示时区 |
| `currency` | 币种，如 `AUD`、`EUR` |
| `unit` | 核心数值单位，如 `AUD/MWh`、`AUD/MW/year` |
| `interval_minutes` | 源数据或主粒度间隔，未知时可为 `null` |
| `data_grade` | 当前结果等级，如 `analytical`、`preview`、`analytical-preview` |
| `data_quality_score` | 数据质量分数，当前大多为 `null` |
| `coverage` | 覆盖情况摘要对象 |
| `freshness` | 新鲜度对象，通常含 `last_updated_at` |
| `source_name` | 上游来源名称 |
| `source_version` | 数据源版本标识 |
| `methodology_version` | 当前算法/响应契约版本标识 |
| `warnings` | 风险或预览提示列表 |

## 2. 版本字段约定

### 2.1 `source_version`

用于标记结果所依赖的数据版本或快照版本。

当前典型值：

- AEMO/NEM/WEM 主链：数据库最近更新时间
- Fingrid 状态：数据集代码，如 `fcrn_hourly_market_price`
- 事件叠加：事件覆盖数据版本哈希
- 电网预测：预测依赖源的组合版本哈希

### 2.2 `methodology_version`

用于标记当前结果生成逻辑的版本。

当前已使用值：

- `price_trend_v1`
- `peak_analysis_v1`
- `hourly_price_profile_v1`
- `fcas_analysis_v1`
- `event_overlays_v1`
- `grid_forecast_v1`
- `bess_backtest_v1`
- `investment_analysis_v1`
- `fingrid_status_v1`

## 3. 主接口专用字段补充

统一 metadata 不替代业务专用字段，接口仍可保留各自专有语义。

### 3.1 `GET /api/event-overlays`

除标准字段外，`metadata` 还保留：

- `coverage_quality`
- `sources_used`
- `time_granularity`
- `no_verified_event_explanation`
- `filters`

### 3.2 `GET /api/grid-forecast`

除标准字段外，`metadata` 还保留：

- `horizon`
- `forecast_mode`
- `coverage_quality`
- `issued_at`
- `as_of`
- `confidence_band`
- `sources_used`
- `investment_grade`

### 3.3 `POST /api/investment-analysis`

除标准字段外，顶层响应还保留：

- `backtest_reference`
- `backtest_observed`
- `backtest_fallback_used`
- `arbitrage_baseline_source`
- `fcas_baseline_source`

### 3.4 `POST /api/bess/backtests`

除标准字段外，顶层响应还保留：

- `params_summary`
- `revenue_breakdown`
- `cost_breakdown`
- `soc_summary`
- `cycle_summary`
- `timeline_points`
- `timeline`

## 4. 当前等级口径

当前默认口径：

- NEM 主历史分析链路：`analytical`
- WEM slim/预估链路：`preview`
- Fingrid 当前状态页：`analytical-preview`
- NEM/WEM 预测结果：NEM 一般为 `analytical-preview`，WEM 为 `preview`

`investment-grade` 目前不应被默认推断为已实现。

## 5. 联调检查要点

前后端联调时至少确认：

1. 响应中存在 `metadata`
2. `metadata.market` 与 `metadata.region_or_zone` 正确
3. `metadata.currency`、`metadata.unit` 与页面展示一致
4. `metadata.source_version`、`metadata.methodology_version` 可用于问题追踪
5. WEM / Fingrid 等预览链路的 `data_grade` 与 `warnings` 没有被前端吞掉

## 6. 当前边界

这是一份当前实现口径文档，不是最终稳定对外 API 规范。

当前已完成的辅助接口契约覆盖包括：

- 数据质量辅助接口：`/api/data-quality/summary`、`/api/data-quality/markets`、`/api/data-quality/issues`
- 观测与运营辅助接口：`/api/observability/status`、`/api/jobs*`、`/api/reports/*`
- 业务辅助接口：`/api/market-screening`、`/api/grid-forecast/coverage`
- Finland / Fingrid 辅助接口：`/api/fingrid/datasets`、`/api/finland/market-model`
- 通用辅助接口：`/api/years`、`/api/network-fees`

后续若继续补充更细的字段级嵌套模型和逐接口示例，属于契约增强，而不是当前缺口。

## 7. 错误响应契约

当前主接口统一使用 FastAPI `HTTPException` 风格错误响应：

```json
{
  "detail": "Internal server error"
}
```

外部 `/api/v1/*` 接口当前已补充结构化错误响应：

```json
{
  "code": "access_denied",
  "message": "Workspace access denied",
  "retryable": false
}
```

常见状态码：

| 状态码 | 含义 | 典型接口 |
| --- | --- | --- |
| `404` | 请求对应的数据表、年份、数据集或回测源数据不存在 | `price-trend`、`peak-analysis`、`hourly-price-profile`、`bess/backtests`、`fingrid status` |
| `500` | 服务内部错误、数据库异常、上游解析异常 | 全部主分析接口 |
| `501` | 功能入口存在，但当前部署未实现 | `POST /api/data-quality/refresh` 在部分环境下可能返回 |

外部 `/api/v1/*` 当前统一错误码矩阵：

| 状态码 | code | 含义 |
| --- | --- | --- |
| `401` | `missing_api_key` / `invalid_api_key` | 缺少 API Key 或 API Key 无效 |
| `403` | `access_denied` | workspace、market、region 或 job scope 不允许 |
| `404` | `not_found` | 外部 API 请求的资源不存在 |
| `500` | `internal_error` | 服务内部异常 |

说明：

- 当前错误响应仍是简化版，只保证 `detail` 字段稳定可读。
- 内部主分析接口还没有统一引入 `error_code`、`request_id`、`retryable` 等结构化错误字段。
- 外部 `/api/v1/*` OpenAPI 已声明 `401 / 403 / 404 / 500` 结构化错误 schema，当前字段为 `code / message / retryable`。

## 8. 请求与响应示例

### 8.1 `GET /api/price-trend`

请求示例：

```http
GET /api/price-trend?year=2026&region=NSW1&limit=1500
```

响应示例（节选）：

```json
{
  "region": "NSW1",
  "year": 2026,
  "total_points": 1500,
  "stats": {
    "min": -42.5,
    "max": 389.1,
    "avg": 71.3
  },
  "data": [
    { "datetime": "2026-04-01 00:00:00", "price": 58.2 }
  ],
  "metadata": {
    "market": "NEM",
    "region_or_zone": "NSW1",
    "timezone": "Australia/Sydney",
    "currency": "AUD",
    "unit": "AUD/MWh",
    "interval_minutes": 5,
    "data_grade": "analytical",
    "source_version": "2026-04-27 00:10:00",
    "methodology_version": "price_trend_v1"
  }
}
```

### 8.2 `GET /api/grid-forecast`

请求示例：

```http
GET /api/grid-forecast?market=NEM&region=NSW1&horizon=24h
```

响应示例（节选）：

```json
{
  "summary": {
    "grid_stress_score": 81.0,
    "price_spike_risk_score": 74.0
  },
  "coverage": {
    "source_status": {
      "recent_market_history": "ok",
      "event_state": "ok",
      "nem_predispatch": "ok"
    }
  },
  "metadata": {
    "market": "NEM",
    "region_or_zone": "NSW1",
    "timezone": "Australia/Sydney",
    "currency": "AUD",
    "unit": "mixed",
    "interval_minutes": 5,
    "data_grade": "analytical-preview",
    "forecast_mode": "hybrid_signal_calibrated",
    "coverage_quality": "full",
    "source_version": "grid-forecast-version-hash",
    "methodology_version": "grid_forecast_v1"
  }
}
```

### 8.3 Finland Board Routes

以下契约对应 Finland board 第一版聚合接口：

- `GET /api/finland/board/overview`
- `GET /api/finland/board/table`
- `GET /api/finland/board/chart`
- `GET /api/finland/board/field-catalog`
- `GET /api/finland/board/readiness`

这些接口当前不复用第 1 节中的统一 `metadata` 包装，而是返回面向 board 视图的轻量聚合结构。错误响应仍遵循第 7 节：参数错误返回 `400`，不支持的 field / view 返回 `404`，未捕获异常返回 `500`。

#### 8.3.1 `GET /api/finland/board/overview`

请求参数：

- `start`：可选，ISO-8601 起始时间
- `end`：可选，ISO-8601 结束时间

响应字段：

- `cards`：长度固定为 6 的概览卡片数组，当前顺序由后端 registry 固定
- `window.start` / `window.end`：原样回传请求时间窗口
- `generated_at_utc`：后端生成时间

`cards[*]` 当前字段：

- `field_key`
- `label`
- `unit`
- `granularity`
- `value`
- `change_vs_previous`
- `sparkline`
- `latest_coverage_utc`：仅 `join_completeness` 卡片包含

响应示例：

```json
{
  "cards": [
    {
      "field_key": "fcr_n_price_eur_mw",
      "label": "FCR-N Capacity Price",
      "unit": "EUR/MW",
      "granularity": "1h",
      "value": 12.5,
      "change_vs_previous": null,
      "sparkline": [10.0, 14.0, 13.5]
    },
    {
      "field_key": "join_completeness",
      "label": "Join Completeness And Freshness",
      "unit": "%",
      "granularity": "board",
      "value": 100.0,
      "change_vs_previous": null,
      "sparkline": [100.0],
      "latest_coverage_utc": "2026-04-02T00:00:00Z"
    }
  ],
  "window": {
    "start": "2026-04-01T00:00:00Z",
    "end": "2026-04-02T00:00:00Z"
  },
  "generated_at_utc": "2026-04-02T01:00:00Z"
}
```

#### 8.3.2 `GET /api/finland/board/table`

请求参数：

- `view`：必填，当前支持 `capacity_hourly`、`activation_15m`、`daily_capacity`、`daily_activation`
- `start`：可选，ISO-8601 起始时间
- `end`：可选，ISO-8601 结束时间
- `tz`：可选，默认 `Europe/Helsinki`

说明：

- `summary_stats` 与 `field_dictionary` 是 registry 中保留 view key，但当前不是 tabular board table view；传入这两个值时接口返回 `400`
- 未注册的 `view` 返回 `404`

响应字段：

- `view`
- `title`
- `granularity`
- `timezone`
- `columns`：列定义数组
- `rows`：表格数据数组

`columns[*]` 当前字段：

- `field_key`
- `label`
- `unit`
- `granularity`
- `source_name`
- `source_type`
- `category`

响应示例：

```json
{
  "view": "capacity_hourly",
  "title": "capacity_1h",
  "granularity": "1h",
  "timezone": "Europe/Helsinki",
  "columns": [
    {
      "field_key": "timestamp_helsinki",
      "label": "Time (Europe/Helsinki)",
      "unit": null,
      "granularity": "display",
      "source_name": "Derived",
      "source_type": "derived",
      "category": "time"
    },
    {
      "field_key": "spot_price_fi_eur_mwh",
      "label": "Finland Spot Price",
      "unit": "EUR/MWh",
      "granularity": "1h",
      "source_name": "Nord Pool",
      "source_type": "external_join",
      "category": "spot"
    }
  ],
  "rows": [
    {
      "timestamp_utc": "2026-04-01T00:00:00Z",
      "timestamp_helsinki": "2026-04-01T03:00:00+03:00",
      "date": "2026-04-01",
      "spot_price_fi_eur_mwh": 75.0
    }
  ]
}
```

#### 8.3.3 `GET /api/finland/board/chart`

请求参数：

- `fields`：必填，可重复 query 参数；`mode=single|compare` 时支持 1..n 个 field，`mode=spread` 时必须恰好 2 个 field
- `mode`：可选，默认 `single`；当前支持 `single`、`compare`、`spread`
- `start`：可选，ISO-8601 起始时间
- `end`：可选，ISO-8601 结束时间
- `granularity`：可选，默认 `1h`；当前支持 `1h`、`hour`、`15m`、`day`

说明：

- `hour` 会在响应中归一化为 `1h`
- 不支持的 `mode` 或 `granularity` 返回 `400`
- 不支持的 `field` 返回 `404`

响应字段：

- `mode`
- `granularity`
- `series`
- `window`

`series[*]` 当前字段：

- `field_key`
- `label`
- `points`

`points[*]` 当前字段：

- `timestamp_utc`
- `timestamp_local`：`single` / `compare` 模式下按数据源原样透传，`spread` 模式当前不返回
- `value`

响应示例：

```json
{
  "mode": "spread",
  "granularity": "1h",
  "series": [
    {
      "field_key": "imbalance_price_eur_mwh-minus-spot_price_fi_eur_mwh",
      "label": "Imbalance Settlement Price - Finland Spot Price",
      "points": [
        {
          "timestamp_utc": "2026-04-01T00:00:00Z",
          "value": 30.0
        }
      ]
    }
  ],
  "window": {
    "start": "2026-04-01T00:00:00Z",
    "end": "2026-04-02T00:00:00Z"
  }
}
```

#### 8.3.4 `GET /api/finland/board/field-catalog`

请求参数：无。

响应字段：

- `items`

`items[*]` 当前字段：

- `field_key`
- `label`
- `unit`
- `granularity`
- `source_name`
- `source_dataset_id`
- `source_type`
- `category`
- `methodology_note`

响应示例：

```json
{
  "items": [
    {
      "field_key": "spot_price_fi_eur_mwh",
      "label": "Finland Spot Price",
      "unit": "EUR/MWh",
      "granularity": "1h",
      "source_name": "Nord Pool",
      "source_dataset_id": "nordpool_day_ahead_fi",
      "source_type": "external_join",
      "category": "spot",
      "methodology_note": "Nord Pool Finland day-ahead reference joined into board views."
    }
  ]
}
```

#### 8.3.5 `GET /api/finland/board/readiness`

请求参数：无。

说明：

- 该接口内部复用 `/api/finland/market-model` 的 source summary / sources / metadata.warnings 语义
- 当前 route 不会触发 `fingrid_service.seed_dataset_catalog(db)` 副作用

响应字段：

- `summary.live_source_count`
- `summary.configured_external_source_count`
- `summary.field_count`
- `sources`
- `warnings`

响应示例：

```json
{
  "summary": {
    "live_source_count": 1,
    "configured_external_source_count": 1,
    "field_count": 16
  },
  "sources": [
    {
      "source_key": "fingrid",
      "status": "live"
    },
    {
      "source_key": "nord_pool",
      "status": "configured",
      "integration": {
        "readiness": "configured"
      }
    }
  ],
  "warnings": ["planned_external_sources"]
}
```

### 8.4 `POST /api/bess/backtests`

请求示例：

```json
{
  "market": "NEM",
  "region": "NSW1",
  "year": 2025,
  "power_mw": 50,
  "energy_mwh": 100,
  "duration_hours": 2,
  "round_trip_efficiency": 0.88,
  "min_soc_pct": 0.1,
  "max_soc_pct": 0.9,
  "initial_soc_pct": 0.5,
  "network_fee_per_mwh": 12,
  "degradation_cost_per_mwh": 4,
  "variable_om_per_mwh": 1,
  "availability_pct": 0.98,
  "max_cycles_per_day": 1.2
}
```

响应示例（节选）：

```json
{
  "market": "NEM",
  "region": "NSW1",
  "year": 2025,
  "revenue_breakdown": {
    "gross_energy_revenue": 1250000.0,
    "net_revenue": 1080000.0
  },
  "cycle_summary": {
    "equivalent_cycles": 312.4
  },
  "metadata": {
    "market": "NEM",
    "region_or_zone": "NSW1",
    "currency": "AUD",
    "unit": "AUD",
    "methodology_version": "bess_backtest_v1"
  }
}
```

### 8.5 `POST /api/investment-analysis`

请求示例：

```json
{
  "region": "NSW1",
  "power_mw": 50,
  "duration_hours": 2,
  "backtest_years": [2025]
}
```

## 9. P2 / P3 / P4 当前契约补充

### 9.1 `GET /api/p2/forecast-layer`

当前 P2 预测层返回的核心顶层字段为：

- `metadata`
- `summary`
- `coverage`
- `market_context`
- `drivers`
- `windows`
- `baseline_forecast`
- `governance`
- `regime_compact`

其中 `governance` 当前至少包含：

- `lineage`
- `freshness`
- `drift`
- `forecast_value_attribution`
- `disclaimer`

这意味着前端主工作台和外部消费方可以直接使用 `governance.freshness.status`、`governance.drift.status`、`governance.disclaimer.usage_scope` 做轻量治理提示，而不需要再自行推断。

### 9.2 `POST /api/p3/bess/decision-layer`

当前 P3 决策层返回的核心顶层字段为：

- `metadata`
- `decision_summary`
- `forecast_context`
- `strategy_bundle`
- `revenue_attribution`
- `governance`
- `warnings`

其中：

- `decision_summary` 用于表达推荐策略、风险模式、reserve SoC、rolling horizon / co-optimization / degradation mode
- `strategy_bundle` 用于表达 `rule_based_dispatch / forecast_driven_dispatch / stochastic_dispatch`
- `revenue_attribution` 用于表达 timing alpha、regime capture alpha、FCAS stack proxy、decision-adjusted net revenue
- `governance` 用于表达当前 P3 输出的 freshness / drift / disclaimer / forecast value attribution

### 9.3 `GET /api/model-governance/summary`

当前 P4 治理摘要接口返回的核心顶层字段为：

- `freshness`
- `quality`
- `source_rows`
- `drift`
- `disclaimer`
- `summary`

其中：

- `freshness.sources` 表达系统级 freshness 与 job 状态摘要
- `source_rows` 表达 source-level governance rows，当前至少包含：
  - `source_id`
  - `source_key`
  - `market`
  - `dataset_family`
  - `status`
  - `freshness_status`
  - `freshness_minutes`
  - `last_updated_at`
  - `data_grade`
  - `quality_score`
  - `coverage_ratio`
  - `issue_count`
  - `issues`
  - `dataset_key`
  - `lineage`
- `drift.models` 表达当前已接入治理载荷的模型覆盖情况
- `disclaimer` 表达研究用途与非 investment-grade 边界

### 9.4 OpenAPI 当前状态

当前以下接口已经不再只使用宽松对象 schema，而是具备专用响应模型引用：

- `/api/p2/forecast-layer` -> `P2ForecastLayerPayload`
- `/api/p3/bess/decision-layer` -> `P3BessDecisionLayerPayload`
- `/api/model-governance/summary` -> `ModelGovernanceSummaryPayload`

这一步的目标不是把所有嵌套字段全部刚性 typed 到最细，而是先把主 contract anchor 固定下来，便于前后端联调、OpenAPI 导出和后续进一步细化。

响应示例（节选）：

```json
{
  "base_metrics": {
    "npv": 1234567.0,
    "irr": 0.143,
    "roi_pct": 38.6
  },
  "backtest_reference": {
    "methodology_version": "bess_backtest_v1"
  },
  "backtest_fallback_used": false,
  "arbitrage_baseline_source": "observed_net_revenue",
  "metadata": {
    "market": "NEM",
    "region_or_zone": "NSW1",
    "currency": "AUD",
    "unit": "AUD/year",
    "methodology_version": "investment_analysis_v1"
  }
}
```
