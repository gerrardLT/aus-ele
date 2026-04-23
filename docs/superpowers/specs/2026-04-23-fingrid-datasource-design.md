# Fingrid 数据源框架设计说明

> 日期：2026-04-23
> 状态：draft
> 目标：为仓库引入一个可扩展的 Fingrid 数据源框架，本次先落地 dataset `317`，以独立页面/路由方式接入，不混入现有 `NEM/WEM` 主工作台。

## 1. 背景与结论

当前仓库的数据主链路围绕澳洲 `NEM/WEM` 构建，核心假设包括：

- 主表为 `trading_price_{year}`
- 主键语义为 `settlement_date + region_id`
- 主值语义为能量价格 `rrp_aud_mwh`
- 大量后端与前端逻辑默认 `NEM/WEM/FCAS/region`

Fingrid dataset `317` 的官方语义并不匹配这套主链路。根据官方页面，它是 `FCR-N hourly market prices`，粒度为 `1h`，单位为 `EUR/MW`，不是能量现货价格。[数据集页面](https://data.fingrid.fi/en/datasets/317)

同时，Fingrid API 访问需要 `x-api-key`，并受速率限制约束：每两秒一请求、每天一万次请求上限。[官方说明](https://data.fingrid.fi/en/instructions)

因此，本设计的核心结论是：

- 不把 Fingrid 数据塞入现有 `trading_price_*` 体系
- 不把 Fingrid 首版并入现有 `NEM/WEM` 主工作台
- 采用独立数据域、独立 API、独立页面的方式接入
- 本次只落地 dataset `317`
- 但后端和页面都按“后续可继续接其他 Fingrid dataset”来设计

## 2. 范围与非范围

### 2.1 本次范围

- 新增独立的 Fingrid 数据源框架
- 新增 dataset catalog、timeseries、sync state 三类持久化能力
- 新增 Fingrid API client 与同步逻辑
- 新增独立后端 API 前缀 `/api/fingrid/...`
- 新增独立页面/路由 `/fingrid`
- 首次落地 dataset `317`
- 页面能力做到：
  - 数据接入
  - 本地存储
  - 基础查询
  - 手动同步
  - 最近更新时间与同步状态
  - 导出
  - 轻量分析卡片

### 2.2 明确不做

- 不重构现有 `NEM/WEM` 主数据模型
- 不把 Fingrid 接入现有套利、FCAS、投资分析主链路
- 不做跨市场对比
- 不做 Fingrid 套利分析或 BESS 收益模拟
- 不做全球电力市场统一抽象层
- 不把 Fingrid 同步并入现有 AEMO nightly 主任务

## 3. 方案选择

本次在 3 个方向中选择中间方案：

1. 只为 `317` 做一次性接入
2. 做独立的 Fingrid 数据源框架，本次先落 `317`
3. 直接抽象成全球电力市场统一层

最终选择 `2`。

原因：

- `317` 的业务语义、粒度、单位与现有主表不一致
- 后续还需要支持更多 Fingrid dataset
- 当前代码库中 `NEM/WEM` 假设很重，过早做全球统一抽象成本过高
- 独立框架既能快速落地，又能避免污染现有主链路

## 4. 总体架构

### 4.1 后端模块边界

新增 `backend/fingrid/` 目录，建议拆分为：

- `backend/fingrid/client.py`
  - 负责官方 API 调用
  - 管理 `x-api-key`
  - 处理限流、重试、超时和基础响应解析

- `backend/fingrid/catalog.py`
  - 维护本地支持的数据集注册表
  - 定义 dataset 元信息、默认窗口、字段映射、`series_key`

- `backend/fingrid/service.py`
  - 负责回填、增量同步、查询、聚合、状态汇总

- `backend/fingrid/schemas.py`
  - 定义 API 响应模型和内部数据结构

- `backend/fingrid/export.py`
  - 负责 CSV 导出

同步入口建议放在：

- `scrapers/fingrid_sync.py`

### 4.2 前端模块边界

新增 Fingrid 独立页面与 API 封装：

- `web/src/pages/FingridPage.jsx`
- `web/src/lib/fingridApi.js`
- 必要时增加 `web/src/components/fingrid/*`

Fingrid 页面独立于现有 `App.jsx` 主工作台逻辑，只通过新路由入口访问。

## 5. 数据模型设计

Fingrid 不采用 `trading_price_{year}` 年分表模型，而采用“数据集统一长表”模型。

### 5.1 `fingrid_dataset_catalog`

用于保存本地支持的数据集元信息。

建议字段：

- `dataset_id` TEXT PRIMARY KEY
- `dataset_code` TEXT
- `name` TEXT NOT NULL
- `description` TEXT
- `unit` TEXT NOT NULL
- `frequency` TEXT NOT NULL
- `timezone` TEXT NOT NULL
- `value_kind` TEXT NOT NULL
- `source_url` TEXT NOT NULL
- `enabled` INTEGER NOT NULL DEFAULT 1
- `metadata_json` TEXT NOT NULL DEFAULT '{}'
- `updated_at` TEXT NOT NULL

对 dataset `317`：

- `dataset_id = '317'`
- `name = 'FCR-N hourly market prices'`
- `unit = 'EUR/MW'`
- `frequency = '1h'`
- `timezone = 'Europe/Helsinki'`
- `value_kind = 'reserve_capacity_price'`
- `source_url = 'https://data.fingrid.fi/en/datasets/317'`

### 5.2 `fingrid_timeseries`

统一存储所有 Fingrid dataset 的标准化时序值。

建议字段：

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `dataset_id` TEXT NOT NULL
- `series_key` TEXT NOT NULL
- `timestamp_utc` TEXT NOT NULL
- `timestamp_local` TEXT NOT NULL
- `value` REAL
- `unit` TEXT NOT NULL
- `quality_flag` TEXT
- `source_updated_at` TEXT
- `ingested_at` TEXT NOT NULL
- `extra_json` TEXT NOT NULL DEFAULT '{}'

唯一键：

- `UNIQUE(dataset_id, series_key, timestamp_utc)`

索引：

- `idx_fingrid_timeseries_dataset_time(dataset_id, timestamp_utc)`
- `idx_fingrid_timeseries_dataset_series_time(dataset_id, series_key, timestamp_utc)`

对 dataset `317` 的标准映射：

- `dataset_id = '317'`
- `series_key = 'fcrn_hourly_market_price'`
- `timestamp_utc` 存 UTC 时间
- `timestamp_local` 存 `Europe/Helsinki` 本地时间
- `value` 存小时价格值
- `unit = 'EUR/MW'`

### 5.3 `fingrid_sync_state`

保存同步水位和状态。

建议字段：

- `dataset_id` TEXT PRIMARY KEY
- `last_success_at` TEXT
- `last_attempt_at` TEXT
- `last_cursor` TEXT
- `last_synced_timestamp_utc` TEXT
- `sync_status` TEXT NOT NULL
- `last_error` TEXT
- `backfill_started_at` TEXT
- `backfill_completed_at` TEXT

## 6. Dataset Catalog 机制

Fingrid 框架必须由 dataset catalog 驱动，而不是在 service 里写死 `317`。

首版至少支持在 catalog 中定义以下信息：

- dataset id
- 显示名称
- 官方 URL
- 单位
- 粒度
- 时区
- 标准化 `series_key`
- 默认 backfill 起点
- 默认增量 lookback 天数
- 默认支持的 aggregation 列表

这样后续接入新的 Fingrid dataset 时，新增工作应主要落在：

- 增加 catalog 配置
- 增加该 dataset 的响应映射器
- 增加页面上的轻量显示适配

而不是重写整条接入链路。

## 7. 同步与抓取设计

### 7.1 基本原则

Fingrid 接入按“受限 API 同步”设计，不按“目录抓取 ZIP”设计。

### 7.2 API Client 责任

`backend/fingrid/client.py` 负责：

- 注入 `x-api-key`
- 统一 base URL
- timeout
- retry
- 速率限制
- 原始响应解析

### 7.3 限流与配额

根据官方说明，必须显式遵守：

- 每两秒最多一请求
- 每天 10,000 次请求上限

因此 client 层必须内建请求间隔控制，不能把限流散落在 scraper 或 service 层。

### 7.4 同步模式

支持两种模式：

- `backfill`
  - 首次回填历史数据
  - `317` 默认从 `2014-01-01` 起

- `incremental`
  - 日常同步最近窗口
  - 默认拉取最近 `7d` 或 `30d`
  - 使用唯一键幂等 upsert

### 7.5 时间窗分块

回填不做一次性全量请求，必须分块。

推荐策略：

- 按月请求
- 每块成功后立即落库
- 每块之间遵守限流
- 任一块失败时写入 `fingrid_sync_state.last_error`

这样失败可恢复，也不会因为单次长请求导致整次回填失败。

### 7.6 同步入口

提供 CLI：

```powershell
python scrapers/fingrid_sync.py --dataset 317 --mode backfill
python scrapers/fingrid_sync.py --dataset 317 --mode incremental
```

首版保留手动同步与 CLI 同步，不并入当前 AEMO nightly scheduler。

## 8. 配置设计

配置通过环境变量提供，不写死在代码里。

建议至少包含：

- `FINGRID_API_KEY`
- `FINGRID_BASE_URL`
- `FINGRID_REQUEST_INTERVAL_SECONDS`
- `FINGRID_TIMEOUT_SECONDS`
- `FINGRID_DEFAULT_BACKFILL_START`
- `FINGRID_DEFAULT_INCREMENTAL_LOOKBACK_DAYS`

首版不引入新的复杂配置系统。

## 9. 后端 API 设计

Fingrid API 采用 dataset-centric 设计，而不是沿用现有 `year + region` 模式。

建议接口如下：

- `GET /api/fingrid/datasets`
  - 返回本地已启用的数据集列表

- `GET /api/fingrid/datasets/{dataset_id}/status`
  - 返回同步状态、最近更新时间、覆盖区间、记录数

- `POST /api/fingrid/datasets/{dataset_id}/sync`
  - 触发手动同步

- `GET /api/fingrid/datasets/{dataset_id}/series`
  - 查询时序数据
  - 参数：
    - `start`
    - `end`
    - `tz`
    - `limit`
    - `aggregation=raw|hour|day|week|month`

- `GET /api/fingrid/datasets/{dataset_id}/summary`
  - 返回轻量分析卡片数据

- `GET /api/fingrid/datasets/{dataset_id}/export`
  - 导出 CSV

## 10. 前端页面设计

### 10.1 路由

新增独立路由：

- `/fingrid`

页面默认展示 dataset `317`，但顶部保留 dataset selector，为后续多 dataset 扩展留位。

### 10.2 页面结构

建议页面拆分为五块：

1. `Header / Dataset Context`
   - 数据集名称
   - dataset id
   - 单位
   - 粒度
   - 官方链接
   - 最近同步时间
   - 覆盖区间
   - 同步按钮

2. `Summary Cards`
   - latest
   - 24h avg
   - 7d avg
   - 30d avg
   - range min
   - range max

3. `Main Time Series`
   - 主折线图
   - 时间范围切换
   - aggregation 切换
   - UTC / Europe-Helsinki 时区切换

4. `Distribution / Seasonality`
   - 月均值柱状图
   - 年均值趋势
   - 小时分布
   - weekday / weekend 对比（可选）

5. `Status / Export`
   - 当前同步状态
   - 最近错误
   - 当前记录数
   - 导出按钮

### 10.3 页面交互

首版推荐的筛选控件：

- dataset selector
- `7d / 30d / 90d / 1y / all`
- `raw / day / week / month`
- `Europe/Helsinki / UTC`
- `sync`
- `export`

## 11. 317 的首版轻量分析

由于 `317` 是 FCR-N 小时价格，不是能量现货价格，所以首版只做轻量分析，不做能源套利或投资模型。

建议 summary 指标包括：

- 最新值
- 最近 24h 均值
- 最近 7d 均值
- 最近 30d 均值
- 区间最小值
- 区间最大值
- 月度均值序列
- 年度均值序列

不做：

- BESS 套利
- 投资分析
- 风险评分
- 跨市场基准比较

## 12. 错误处理

同步与 API 层至少区分以下错误类型：

- `auth_error`
  - API key 缺失或无效

- `rate_limited`
  - 触发官方限流或本地限流保护

- `upstream_unavailable`
  - Fingrid 上游接口不可用

- `mapping_error`
  - 上游返回结构变化或字段映射失败

这些错误需要：

- 写日志
- 写入 `fingrid_sync_state.last_error`
- 在前端状态区可见

## 13. 实施顺序

建议按四阶段实施：

### 阶段 1：后端基础设施

- 建立 `backend/fingrid/`
- 建表
- 建 catalog
- 建 client
- 建同步 CLI
- 落地 dataset `317` 映射

完成标准：

- 可稳定把 `317` 数据落库
- 可查询 sync state

### 阶段 2：只读 API

- `datasets`
- `status`
- `series`
- `summary`
- `export`

完成标准：

- 不依赖前端即可通过 API 验证数据域

### 阶段 3：独立页面

- `/fingrid`
- dataset selector
- summary cards
- time series chart
- status + sync + export

### 阶段 4：扩展准备

- 检查 catalog 是否仍写死 317
- 检查 `series_key` 与 summary adapter 是否支持多 dataset
- 确认页面 selector 已可扩展

## 14. 测试策略

### 14.1 单元测试

覆盖：

- dataset `317` 的字段映射
- 时间戳转换
- UTC / Europe-Helsinki 转换
- aggregation 逻辑
- summary 指标计算
- sync state 更新

### 14.2 集成测试

覆盖：

- API client 解析官方响应
- backfill 分块写库
- incremental 幂等 upsert
- `series / summary / status` 接口返回

测试应使用 mocked response，不依赖真实 Fingrid API。

### 14.3 前端测试

覆盖：

- dataset selector
- 时间范围切换
- aggregation 切换
- 时区切换
- 空数据状态
- 同步失败状态
- 导出与手动同步行为

## 15. 风险与约束

首版最主要的风险有：

- API key 管理不当
- 上游限流处理不当
- DST 时区转换出错
- 未来 dataset 的字段结构差异高于预期
- 页面后续被错误地拉回现有 `NEM/WEM` 主模型

对应的控制策略是：

- 所有认证配置走环境变量
- 限流放到 client 层统一处理
- UTC 与本地时间双存
- 通过 catalog + `series_key` 保持扩展边界
- 明确不复用 `trading_price_*`

## 16. 最终设计结论

本次 Fingrid 接入采用以下定案：

- 作为独立数据域接入
- 使用可扩展的 dataset catalog + timeseries + sync state 模型
- 后端采用独立 `/api/fingrid/...` 接口组
- 前端采用独立 `/fingrid` 页面
- 首次只落地 dataset `317`
- 页面能力达到“可同步、可查询、可导出、可展示、可做轻量统计”
- 不进入现有 `NEM/WEM` 套利、FCAS、投资分析主链路

这保证了首版可以快速落地，同时为后续继续接入更多 Fingrid dataset 保留了稳定边界。
