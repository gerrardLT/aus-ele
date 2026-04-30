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

### 8.3 `POST /api/bess/backtests`

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

### 8.4 `POST /api/investment-analysis`

请求示例：

```json
{
  "region": "NSW1",
  "power_mw": 50,
  "duration_hours": 2,
  "backtest_years": [2025]
}
```

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
