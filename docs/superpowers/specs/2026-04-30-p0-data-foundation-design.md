# P0 数据底座设计

**日期**: 2026-04-30  
**上位文档**: [全球电网数据分析与预测模型深度调研.md](/g:/project/aus-ele/docs/全球电网数据分析与预测模型深度调研.md)  
**关联路线图**: [2026-04-30-global-grid-model-roadmap-design.md](/g:/project/aus-ele/docs/superpowers/specs/2026-04-30-global-grid-model-roadmap-design.md)  
**设计口径**: 先以澳洲/AEMO 为主落地，但按全球统一底座的目标设计；同时覆盖后端数据层、对外 API 契约、前端消费约束。

---

## 1. 背景

当前仓库已经具备：

- NEM/WEM 历史价格分析能力
- `grid_forecast` 规则型前瞻信号层
- FCAS/ESS 机会分析
- standardized BESS backtest 与投资分析链路
- metadata / coverage / freshness 的初步表达

但当前数据层仍然存在明显局限：

1. 主要围绕价格、FCAS、事件、WEM slim ESS 数据展开；
2. 基本面数据域尚不完整；
3. 多市场统一 schema 还没有成型；
4. API 层虽已有 metadata 基础，但还没有一套面向 P0 的 canonical dataset contract；
5. 前端消费更多依赖页面级语义，而不是统一数据域语义。

因此，P0 的职责不是“继续加几个表”，而是建立一层能稳定支撑：

- P1 regime layer
- P2 forecast layer
- P3 BESS decision layer
- P4 governance layer

的统一数据底座。

---

## 2. 设计目标

P0 的目标是建立一套：

> **AEMO 优先落地、但面向全球扩展的统一电网数据底座**

并满足以下条件：

1. 首批能贴合当前仓库现实，优先服务 NEM/WEM；
2. 不把 AEMO 私有字段和市场语义硬编码成全球标准；
3. 后端数据层、API 契约、前端消费约束三层口径一致；
4. 后续接入 ENTSO-E、US ISO/RTO、Japan、Southeast Asia 时，不需要推翻整体结构；
5. 每个数据域都能清楚表达：
   - source
   - coverage
   - freshness
   - forecast vs actual
   - preview / analytical / investment-grade 边界

---

## 3. 非目标

本 spec 不直接完成以下工作：

- 具体 scraper / connector 的逐个实现
- 单个国家所有数据域的一次性接通
- P1 regime 逻辑定义
- P2 模型训练与评估实现
- P3 dispatch optimizer 实现
- 前端具体页面样式改造

这些内容会在后续 phase spec 与 implementation plan 中展开。

---

## 4. 首批范围

### 4.1 首批落地区域

首批实施以 AEMO 为主，覆盖：

- NEM
- WEM

### 4.2 首批数据域

P0 首批必须纳入统一设计范围的数据域：

- load forecast
- load actual
- wind forecast
- wind actual
- solar forecast
- solar actual
- rooftop PV
- outage / unit availability
- interconnector flow
- reserve / shortfall
- weather
- constraint
- settlement

### 4.3 扩展预留市场

不要求首批接通，但 schema 和 adapter 边界必须预留：

- ENTSO-E / Europe
- CAISO / ERCOT / PJM / ISO-NE / US ISO-RTO
- Japan / OCCTO / JEPX / JPX
- Singapore / Philippines / Malaysia / Thailand / Indonesia / Vietnam

---

## 5. 设计原则

### 5.1 AEMO 优先，但不 AEMO 锁死

首批落地优先围绕现有仓库的澳洲链路展开，但 canonical schema 不能直接等同于：

- `region_id`
- `settlement_date`
- `rrp_aud_mwh`
- AEMO 私有 reserve / FCAS naming

这些字段可以存在于 raw layer，但不能直接成为跨市场 contract。

### 5.2 原始数据语义必须保留

P0 不能只保留清洗后的指标结果。必须保留：

- 原始 source identity
- 原始时间戳
- 原始粒度
- 原始字段映射关系
- source-specific warnings

否则后续无法做：

- lineage
- reprocessing
- source audit
- market-specific troubleshooting

### 5.3 Canonical contract 优先于页面语义

前端和 API 不应围绕“某个页面现在怎么展示”来定义数据。  
应先定义：

- dataset family
- observation type
- market scope
- region scope
- temporal scope
- quality / freshness / lineage

页面只是消费这些 contract。

### 5.4 预测与实际必须成对建模

像 `load forecast` / `load actual`、`wind forecast` / `wind actual` 这类数据域，必须在 contract 中天然支持 pairing，而不是后续页面再手动拼接。

### 5.5 输入层和解释层必须分离

P0 只负责输入层，不负责解释结论。

例如：

- `constraint` 是输入层
- `interconnector flow` 是输入层
- `reserve / shortfall` 是输入层

而：

- `congestion`
- `transmission separation`
- `reserve stress`

属于 P1 regime layer，不属于 P0 schema。

---

## 6. 总体架构

P0 分为三层：

1. **Raw Source Layer**
2. **Canonical Data Layer**
3. **Serving Contract Layer**

### 6.1 Raw Source Layer

职责：

- 存储原始采集结果
- 保留 source-specific 字段
- 保留原始时间与粒度
- 保留采集状态与错误

这一层允许强市场特征，不追求统一。

### 6.2 Canonical Data Layer

职责：

- 把 raw source 映射成统一 dataset family
- 统一 market / region / zone / node scope
- 统一 forecast / actual / event / settlement observation type
- 统一 coverage / freshness / lineage metadata

这一层是 P0 的核心。

### 6.3 Serving Contract Layer

职责：

- 向 API 暴露稳定 contract
- 向前端暴露清晰的质量与适用性边界
- 让 P1/P2/P3 能稳定消费数据，而不直接依赖 raw tables

---

## 7. Canonical Schema

### 7.1 核心实体

P0 统一定义以下核心实体。

#### `market_scope`

用于表达数据属于哪个市场及其上下文：

- `market_code`
- `market_type`
- `country`
- `operator`
- `currency`
- `timezone`

示例：

- `NEM`
- `WEM`
- `ENTSOE`
- `CAISO`
- `ERCOT`
- `JEPX`
- `NEMS`

#### `location_scope`

用于表达区域粒度，但不强制所有市场用同一层级。

统一字段：

- `scope_type`: `market` | `region` | `zone` | `node` | `interconnector`
- `scope_code`
- `scope_label`
- `parent_scope_code`

这允许：

- AEMO 用 region
- 欧洲用 bidding zone
- 美国用 node / hub / zone

#### `dataset_family`

统一的数据族，不依赖单一市场命名。

首批 family：

- `load_forecast`
- `load_actual`
- `wind_forecast`
- `wind_actual`
- `solar_forecast`
- `solar_actual`
- `rooftop_pv`
- `outage`
- `unit_availability`
- `interconnector_flow`
- `reserve_requirement`
- `reserve_shortfall`
- `weather`
- `constraint`
- `settlement`

#### `observation_kind`

统一表达该数据是什么类型：

- `forecast`
- `actual`
- `event`
- `state`
- `settlement`
- `derived`

#### `series_contract`

统一的时序数据表达：

- `series_id`
- `dataset_family`
- `observation_kind`
- `market_scope`
- `location_scope`
- `interval_minutes`
- `unit`
- `value_type`
- `points`
- `coverage`
- `freshness`
- `lineage`
- `quality`
- `warnings`

### 7.2 Forecast / Actual Pairing

P0 必须显式支持 forecast 与 actual 的配对关系。

建议统一字段：

- `counterpart_series_id`
- `forecast_issue_time`
- `forecast_target_time`
- `actual_observed_time`

这样可以支撑后续：

- forecast error calculation
- walk-forward backtest
- calibration
- regime attribution

### 7.3 Constraint 数据表达

`constraint` 在 P0 中属于输入数据域，不直接输出 P1 结论。

建议 canonical 字段支持：

- `constraint_id`
- `constraint_type`
- `binding_flag`
- `near_binding_flag`
- `shadow_price`
- `affected_scope`
- `effective_start`
- `effective_end`

### 7.4 Settlement 数据表达

`settlement` 在 P0 中是基础商业数据域，但不等于最终 valuation 结论。

应支持：

- settlement interval
- settlement price / component
- realized settlement status
- revision / finality state
- source lag

它后续会被 P2/P3 用于：

- realized revenue comparison
- forecast value attribution
- decision quality evaluation

---

## 8. Source Adapter 设计

### 8.1 目标

每个市场都通过 adapter 进入 canonical layer，而不是把 source-specific 逻辑散在业务接口中。

### 8.2 AEMO Adapter

首批必须实现的 adapter 家族：

- AEMO fundamentals adapter
- AEMO weather/context adapter
- AEMO constraint adapter
- AEMO settlement adapter

它们的职责：

- 拉取 raw source
- 记录 source metadata
- 映射成 canonical family
- 产出 coverage / freshness / lineage

### 8.3 扩展 Adapter 预留

后续市场按同一接口模式接入：

- ENTSO-E adapter
- ISO/RTO adapter
- OCCTO / JEPX adapter
- EMA / IEMOP / Single Buyer 等 adapter

### 8.4 Adapter Contract

每个 adapter 至少必须产出：

- source identifier
- dataset family mapping
- market scope mapping
- location scope mapping
- interval mapping
- quality / completeness summary
- fetch timestamp
- source coverage window
- warnings / caveats

### 8.5 失败与缺失表达

adapter 失败不能只返回空数据。

必须区分：

- source unavailable
- source delayed
- source partial
- mapping failed
- normalization failed

并进入 serving metadata。

---

## 9. 存储设计

### 9.1 Raw Source Storage

保存：

- source payload
- fetch metadata
- raw coverage
- source status

目标是支持：

- replay
- audit
- remapping
- source debugging

### 9.2 Canonical Storage

保存统一后的：

- canonical series
- market/location scopes
- forecast/actual pairings
- quality/freshness/coverage metadata

### 9.3 Serving Storage / Cache

为 API 和前端提供：

- 快速查询
- 稳定 schema
- metadata 附带返回

但 serving cache 不应成为唯一真实来源。  
真实来源仍应可回溯到 canonical 与 raw layers。

---

## 10. API 契约设计

### 10.1 目标

P0 需要一套面向数据域的统一 API contract，而不是继续让每个业务接口各自表达数据质量和来源。

### 10.2 API 设计原则

1. API 返回必须包含 dataset metadata
2. API 返回必须包含 coverage / freshness / lineage
3. API 返回必须明确 preview / analytical / investment-grade 边界
4. API 返回必须支持 forecast / actual pairing
5. API 不允许让前端靠隐式字段猜语义

### 10.3 核心 contract 字段

建议所有 P0 相关 API 统一包含：

- `dataset_family`
- `market`
- `scope`
- `observation_kind`
- `unit`
- `interval_minutes`
- `coverage`
- `freshness`
- `quality`
- `lineage`
- `warnings`
- `grade`

### 10.4 内部 API 与前端消费 API

P0 应区分两类接口：

1. **内部数据服务接口**
   - 面向 P1/P2/P3
   - 结构更完整
   - 可包含更多 mapping / diagnostic 字段
2. **前端消费接口**
   - 结构稳定
   - 更强调 metadata completeness
   - 不暴露不稳定 raw source 结构

### 10.5 与现有 API 的兼容策略

不要求一次性重写所有现有 endpoint。  
首版应采用：

- 保留现有业务分析接口
- 新增或内化 P0 contract 层
- 逐步让现有接口改为消费 canonical datasets

---

## 11. 前端消费约束

### 11.1 必须消费 metadata

前端不能只读 `value` 和 `points`。必须消费：

- coverage
- freshness
- quality
- lineage
- warnings
- grade

否则页面会把不完整或 preview 数据伪装成稳定能力。

### 11.2 Grade 展示约束

前端必须区分至少三类：

- `preview`
- `analytical`
- `investment-grade` 或明确 `not investment-grade`

并按 grade 约束展示方式：

- preview 不允许伪装为精确结论
- analytical 可以用于研究分析
- investment-grade 需要后续更严格治理支持

### 11.3 Forecast / Actual 对齐约束

前端不允许自行用页面逻辑随意拼接 forecast 与 actual。  
必须使用 API / contract 提供的 canonical pairing。

### 11.4 Constraint / Reserve / Settlement 的消费约束

前端不允许把：

- constraint
- reserve / shortfall
- settlement

直接混成单一“风险值”或“收益值”，除非该聚合来自后端明确 contract。  
这三类数据在 P0 中是基础输入，不是最终结论。

### 11.5 国际化与默认文案约束

根据当前仓库要求，前端展示的文案必须尊重：

- 已有国际化机制
- 默认文字体系

P0 相关的 grade / warning / freshness / coverage message key 应优先采用可国际化的 key，而不是把英文或中文提示硬编码到组件里。

---

## 12. Rollout 顺序

建议按以下顺序推进。

### Phase 1：AEMO fundamentals

优先打通：

- load forecast / actual
- wind / solar forecast / actual
- rooftop PV
- weather

### Phase 2：AEMO grid state

继续打通：

- outage / unit availability
- interconnector flow
- reserve / shortfall
- constraint

### Phase 3：AEMO settlement / commercial inputs

接入：

- settlement
- realized revenue relevant inputs
- revision/finality context

### Phase 4：Canonical API layer

建立：

- dataset family contract
- metadata contract
- forecast/actual pairing contract

### Phase 5：Frontend contract alignment

让前端页面统一消费：

- grade
- freshness
- coverage
- lineage
- warnings

### Phase 6：Non-AEMO adapter expansion

按同一 contract 逐步扩到：

- ENTSO-E
- US ISO/RTO
- Japan
- Southeast Asia

---

## 13. 风险与约束

### 13.1 主要风险

- 把 AEMO 原始字段直接变成全球标准
- 只做 raw ingestion，不做 canonical pairing
- API 返回数据点，但不返回质量语义
- 前端继续把 preview 数据包装成成熟结论
- settlement 过晚进入设计，导致 P2/P3 缺少 realized comparison 基础

### 13.2 关键约束

- P0 不能越界去定义 P1 regime 结论
- P0 不能只为现有页面服务，必须为 P1/P2/P3 服务
- P0 不能把 raw source schema 直接暴露给前端
- P0 的 contract 必须允许国际化和多市场扩展

---

## 14. 完成标准

P0 设计完成并进入实施后，验收应满足：

1. AEMO 首批数据域已进入 canonical schema
2. forecast / actual pairing contract 已建立
3. coverage / freshness / lineage / warnings / grade 已成为统一 contract
4. 现有至少一组核心 API 已从 canonical layer 提供数据
5. 前端已开始按 metadata / grade 约束展示结果
6. P1/P2 后续实现不需要直接依赖 raw source table 命名

---

## 15. 后续拆分建议

P0 spec 确认后，下一步 implementation plan 建议进一步拆成几个子实施块：

1. `P0-01 canonical schema 与 dataset family`
2. `P0-02 AEMO fundamentals adapters`
3. `P0-03 AEMO grid state adapters`
4. `P0-04 settlement adapters`
5. `P0-05 API contract 与 frontend metadata alignment`

这样既能保持统一路线，又能控制单次实施范围。

