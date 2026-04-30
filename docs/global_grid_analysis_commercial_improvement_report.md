# 全球电网数据分析系统商业级改进建议报告

> 基于当前项目文档《项目全面解析总册》整理。  
> 适用对象：产品负责人、技术负责人、算法工程师、能源市场分析师、投资分析团队、交付团队。  
> 文档日期：2026-04-27  
> 当前覆盖市场：澳洲 NEM / WEM，芬兰 Fingrid。  
> 建议目标：从“电力市场数据分析工作台”升级为“全球电力市场与储能收益智能平台”。

---

## 0. 一句话结论

当前系统已经具备较完整的工程雏形：后端 FastAPI、SQLite 存储、Redis 缓存、React 前端、AEMO / WEM / Fingrid 数据采集、价格趋势、峰谷价差、FCAS / ESS 分析、规则型预测、BESS 收益和投资分析等模块已经形成闭环。

但如果目标是做到专业商业级，下一阶段的重点不应只是继续增加图表，而应围绕以下四个方向升级：

1. **算法层**：从规则统计和价差识别，升级为真实 BESS 调度回测、概率预测、FCAS / ESS 联合优化、P50 / P90 投资风险模型。
2. **功能层**：从工程分析面板，升级为企业客户可付费的市场筛选、收益栈、告警、自动报告、API、团队协作和投资备忘录能力。
3. **数据层**：从澳洲与 Fingrid 两条相对独立的数据线，升级为全球统一 canonical schema、数据质量评分、数据血缘和跨市场标准化模型。
4. **技术层**：从 SQLite + 内置调度的轻量部署，升级为分层数据湖 / 数仓、任务队列、调度编排、可观测性、多租户、安全和 SLA 级运维体系。

推荐产品定位：

> **Global Power Market Intelligence & BESS Revenue Analytics Platform**  
> 全球电力市场数据与储能收益智能分析平台

---

## 1. 当前系统基线判断

### 1.1 当前项目已经具备的能力

根据当前总册，系统已经不是简单脚本项目，而是一个有前后端、有数据采集、有模型、有部署方案的能源市场分析工作区。当前主要能力包括：

- 澳洲 NEM / WEM 市场价格数据采集与展示。
- NEM FCAS 字段分析。
- WEM ESS slim 数据表、约束摘要和能力表。
- Fingrid 独立数据页，包括数据集同步、状态、时序、摘要和导出。
- 价格趋势、负价分布、小时分布、峰谷套利窗口分析。
- 电网事件归一化与事件 overlay。
- 规则型 grid forecast。
- BESS 模拟、收入栈、投资分析、财务参数、IRR / NPV / DSCR / Monte Carlo 等雏形。
- Redis 响应缓存、SQLite 分析缓存、APScheduler 内置调度。
- Docker / Compose / 宝塔部署方案。
- 后端 unittest 与前端 node:test 基础测试。

### 1.2 当前真实边界

当前系统不应被过度包装为：

- 自动交易系统。
- 多市场联合最优调度系统。
- 经审计的投资决策引擎。
- 高置信度机器学习价格预测系统。
- 完整全球电力市场数据仓库。

当前更准确的定位是：

> **市场分析与解释平台雏形**，用于把原始电力市场数据转化为业务可读的信号、图表、摘要和初步投资测算。

### 1.3 最大商业化差距

当前系统的最大差距不是“没有功能”，而是很多能力还停留在分析辅助层，尚未达到客户可直接用于付费决策的可信等级。

| 维度 | 当前状态 | 商业级要求 |
|---|---|---|
| 价格分析 | 历史展示、统计、下采样 | 多市场标准化、异常解释、事件归因 |
| BESS 分析 | 价差、代表性循环、粗粒度收益 | 真实调度回测、收益栈、SoC、衰减、P50/P90 |
| FCAS / ESS | 历史价格 / slim preview | 联合优化、机会成本、可用容量、约束影响 |
| 预测 | 规则型信号 | 概率预测、置信区间、校准、可解释驱动因子 |
| 投资分析 | 情景财务模型 | Bankable-style case、P90 debt case、报告化输出 |
| 数据可信度 | 部分 coverage / state | 数据质量评分、血缘、版本、审计链 |
| 工程架构 | 单机 SQLite + Redis | 多租户、任务编排、数仓、观测、安全、SLA |

---

## 2. 外部市场调研启发

### 2.1 澳洲 NEM：必须围绕 5 分钟市场和 FCAS 收益重构模型

AEMO 已在 2021-10-01 将 NEM 切换到五分钟结算机制。对于储能资产而言，这意味着套利、充放电窗口、价格尖峰捕获、负价充电和 FCAS 机会都应以 5 分钟 interval 作为基本决策单元，而不是以小时级平均作为核心收益口径。[^aemo-5ms]

同时，NEM 的 FCAS 市场已经包含 raise / lower、regulation、1s、6s、60s、5min 等多个服务类别。AEMO 的 FCAS in NEMDE 文档强调，FCAS availability 不仅取决于报价，还取决于 energy dispatch target、enablement、trapezium scaling、technical constraints 和 unit FCAS constraints。[^aemo-fcas-model]

因此，NEM 商业级 BESS 模型必须从“看 FCAS 历史价格”升级为：

- energy + FCAS 联合优化；
- SoC 与 FCAS enablement 约束；
- raise / lower 服务与充放电功率冲突；
- opportunity cost 计算；
- capacity reservation 与 energy arbitrage 的权衡；
- very fast FCAS 对电池响应价值的单独建模。[^aemo-vfcas]

### 2.2 澳洲 WEM：WEM ESS slim 适合 preview，但不适合 investment-grade

AEMO WEM Dispatch API v2 提供 WEMDE 输出的 dispatch case、dispatch solution、dispatch instructions、dispatch summary、trading day report 等数据。AEMO 的开发者文档说明，solution file 包含 WEMDE 产生的完整数据集，而 WEM Dispatch APIs Overview 也明确覆盖 dispatch case / solution 等完整 WEMDE 数据范围。[^aemo-wem-solution][^aemo-wem-overview]

当前系统中的 WEM ESS slim 表设计合理，适合快速构建 WEM FCAS / ESS preview，但如果要支持投资级判断，应补齐：

- WEMDE solution 原始文件归档；
- WEMDE case 原始文件归档；
- original / latest / replacement 状态；
- affected / missing dispatch intervals；
- constraint、facility、requirement、enablement、shortfall、capped price；
- 数据版本与数据血缘。

结论：

> WEM 当前应明确标注为 preview / analytical-grade。只有在接入完整 WEMDE case + solution + constraint 链路后，才适合逐步提升为 investment-grade。

### 2.3 芬兰：Fingrid 不应孤立，应扩展为 Nordic / Europe 数据入口

Fingrid Open Data 提供 REST API、API key、数据集目录、下载、时序数据等能力。官方说明中，API 需要注册和 key，并且存在请求频率与节流限制。[^fingrid-api]

Fingrid 还提供 imbalance price 等关键市场数据。其 imbalance price dataset 319 说明，2025-03-19 之前为小时分辨率，之后进入更细粒度数据口径。[^fingrid-319]

但如果要做芬兰 BESS、工业柔性负荷或平衡市场分析，只接 Fingrid 还不够。应组合：

- Fingrid：实时系统、负荷、发电、跨境、平衡相关数据；
- Nord Pool：day-ahead / intraday price；
- ENTSO-E：负荷、发电、传输、平衡、跨境容量等欧洲统一透明平台数据；[^entsoe]
- 天气数据：温度、风、太阳辐照、降水、水文等；
- 市场规则元数据：bidding zone、market time unit、currency、settlement interval。

欧洲 Single Day-Ahead Coupling 已在 2025-10-01 交付日实施 15 分钟 Market Time Unit。这意味着系统不能默认欧洲市场都是小时级数据，必须把 interval duration 作为市场元数据处理。[^nordpool-15]

### 2.4 BESS 是平台商业化核心，不应只是辅助模块

IEA 的电池报告指出，2023 年电力部门电池储能新增约 42 GW，电池储能在公用事业、表后、微电网和分布式场景均快速增长。[^iea-batteries]

这对本项目的商业化启发是：

> 客户不会只为“看电价图”付高价，但会为“哪里适合投储能、收益栈如何拆、P50/P90 怎么算、FCAS 与套利如何共存、风险如何解释、投资委员会报告如何生成”付费。

因此，BESS Revenue Analytics 应成为产品主线，而不是附属卡片。

---

## 3. 算法层商业级改进建议

## 3.1 从峰谷价差升级为真实 BESS 调度回测引擎

### 当前问题

当前 `/api/peak-analysis` 主要计算 1h / 2h / 4h / 6h 价差窗口，输出 gross spread / net spread。这适合发现理论机会，但不能代表真实储能收益。

原因包括：

- 没有完整 SoC 轨迹。
- 没有同时考虑 charge / discharge 功率约束。
- 没有考虑循环次数限制。
- 没有考虑 degradation cost。
- 没有考虑 FCAS / ESS 与 energy arbitrage 的容量冲突。
- 没有滚动预测误差。
- 没有 bid / dispatch / settlement 差异。

### 建议目标

建立 `BESS Dispatch Backtest Engine v1`，支持以下输入：

```yaml
market: NEM | WEM | Finland | Europe
region_or_zone: SA1 | NSW1 | WEM | FI
asset:
  power_mw: 100
  duration_hours: 2
  energy_mwh: 200
  round_trip_efficiency: 0.88
  min_soc_pct: 5
  max_soc_pct: 95
  initial_soc_pct: 50
  availability_pct: 97
  max_cycles_per_day: 1.5
costs:
  variable_om_per_mwh: 2
  degradation_cost_per_mwh: 8
  network_fee_per_mwh: 5
strategy:
  mode: perfect_foresight | rolling_forecast | rule_based | stochastic
  products:
    - energy_arbitrage
    - fcas
    - ess
    - imbalance
```

### 核心优化模型

目标函数：

```text
Maximize:
  Energy arbitrage revenue
+ FCAS / ESS enablement revenue
+ Balancing / imbalance revenue
+ Capacity / availability revenue
- Charging cost
- Network and market fees
- Variable O&M
- Degradation cost
- Non-delivery / penalty proxy
```

基础约束：

```text
0 <= SoC_t <= E_max
0 <= charge_t <= P_charge_max
0 <= discharge_t <= P_discharge_max
SoC_t = SoC_t-1 + charge_t * eta_charge * dt - discharge_t / eta_discharge * dt
charge_t * discharge_t = 0 或用二进制变量近似避免同时充放
cycle_count_day <= max_cycles_per_day
availability_t in {0, 1} 或连续 derating factor
```

FCAS / ESS 约束：

```text
reserved_raise_t + discharge_t <= P_discharge_max
reserved_lower_t + charge_t <= P_charge_max
SoC_t >= minimum_soc_for_raise_service
SoC_t <= maximum_soc_for_lower_service
reserved_service_t <= accredited_capacity_t
reserved_service_t <= market_requirement_t 或可用出清上限
```

### 输出结果

商业级回测不应只输出一个年收益，而应输出：

```json
{
  "annual_revenue": 12400000,
  "energy_arbitrage_revenue": 6800000,
  "fcas_revenue": 4100000,
  "imbalance_revenue": 900000,
  "costs": {
    "charging_cost": 3200000,
    "network_fee": 600000,
    "degradation_cost": 750000,
    "variable_om": 180000
  },
  "net_revenue": 8860000,
  "cycles_equivalent": 312,
  "average_daily_cycles": 0.85,
  "availability_adjusted_revenue": 8590000,
  "top_5_percent_intervals_revenue_share": 0.37,
  "soc_min": 0.08,
  "soc_max": 0.94,
  "warnings": [
    "Revenue concentrated in extreme intervals",
    "FCAS opportunity cost materially reduces arbitrage capture"
  ]
}
```

### 实施优先级

| 阶段 | 能力 | 建议工具 |
|---|---|---|
| v1 | deterministic perfect-foresight LP / MILP | scipy.optimize / PuLP / OR-Tools |
| v2 | rolling forecast dispatch | LightGBM + rolling horizon optimizer |
| v3 | stochastic scenarios | scenario tree / Monte Carlo |
| v4 | bid strategy simulation | market-specific bidding model |

---

## 3.2 FCAS / ESS 从价格展示升级为联合机会成本模型

### 当前问题

当前 FCAS / ESS 分析更多偏向服务价格、分布和 preview 指标。对储能而言，真正难点不是“FCAS 价格高不高”，而是：

- 预留 FCAS 容量会不会牺牲 energy arbitrage？
- Raise 服务需要 SoC 留足电量，是否会错过高价放电？
- Lower 服务需要留出充电空间，是否会错过负价充电机会？
- FCAS enablement 与实际 activation 如何影响电池能量状态？
- 不同服务是否可叠加？是否互斥？是否受技术 accreditation 限制？

### NEM 建议模型

NEM FCAS 应至少拆成：

- raise_reg
- lower_reg
- raise_1s
- lower_1s
- raise_6s
- lower_6s
- raise_60s
- lower_60s
- raise_5min
- lower_5min

每个服务输出：

| 字段 | 说明 |
|---|---|
| price | 服务价格 |
| enabled_mw | 模拟 enablement MW |
| reserved_mw | 电池预留容量 |
| opportunity_cost | 相对 energy arbitrage 的机会成本 |
| soc_constraint_binding | SoC 是否成为限制 |
| power_constraint_binding | 功率是否成为限制 |
| net_incremental_revenue | 扣除机会成本后的增量收益 |
| revenue_confidence | 收益可信度 |

### WEM 建议模型

WEM ESS 应至少拆成：

- energy_price
- regulation_raise_price
- regulation_lower_price
- contingency_raise_price
- contingency_lower_price
- rocof_price
- requirement
- available
- in_service
- shortfall
- capped
- dispatch_total
- constraint signal

建议新增指标：

```text
ESS scarcity score
= weighted(shortfall, capped_price, requirement / available, binding_constraint_count)

ESS opportunity score
= price_level * scarcity_score * battery_technical_fit * data_quality_score
```

### 产品输出

在前端不要只展示价格曲线，应给出“业务解释”：

```text
今日 WEM Regulation Raise 收益机会偏高，主要因为：
1. requirement / available 比例上升；
2. shortfall interval 增加；
3. near-binding constraint 数量上升；
4. energy arbitrage opportunity cost 较低。

但当前数据等级为 preview，尚不建议直接用于 investment-grade 收益定价。
```

---

## 3.3 预测模块升级为概率预测和可解释驱动因子

### 当前问题

当前 `grid_forecast.py` 是规则型信号引擎，输出风险和机会信号，而不是 ML 点预测。这是合理的早期设计，但商业级产品需要：

- 预测未来价格分布，而不是只给方向标签。
- 给出置信区间，而不是单点判断。
- 能解释为什么风险上升。
- 能回测模型表现。
- 能提示模型何时不可信。

### 建议三层预测架构

#### 第一层：统计基线模型

用途：快速建立可校验 baseline。

模型包括：

- seasonal naive；
- weekday / weekend / hour profile；
- rolling quantile；
- recent volatility regime；
- negative price frequency；
- spike frequency；
- month / season effects。

#### 第二层：机器学习概率预测

模型候选：

- LightGBM；
- XGBoost；
- CatBoost；
- quantile regression；
- conformal prediction。

特征建议：

| 特征类别 | 示例 |
|---|---|
| 价格滞后 | last 5min, 30min, 1h, 24h, 7d |
| 负荷 | demand forecast, operational demand |
| 可再生 | wind forecast, solar forecast, rooftop PV |
| 天气 | temperature, wind speed, solar irradiance |
| 市场结构 | interconnector flow, constraints, outages |
| 时间 | hour, weekday, holiday, month, DST |
| 事件 | market notice, forced outage, islanding risk |
| FCAS / ESS | requirement, shortfall, capped, service prices |

输出：

```json
{
  "price_p10": -35,
  "price_p50": 42,
  "price_p90": 185,
  "negative_price_probability": 0.34,
  "spike_probability": 0.08,
  "volatility_regime": "high",
  "confidence_score": 0.71
}
```

#### 第三层：可解释预测层

输出 top drivers：

```json
{
  "top_drivers": [
    {"name": "high rooftop solar", "direction": "down", "impact": -28},
    {"name": "low operational demand", "direction": "down", "impact": -16},
    {"name": "interconnector constraint", "direction": "up", "impact": 42},
    {"name": "recent FCAS scarcity", "direction": "up", "impact": 18}
  ]
}
```

### 模型治理要求

每个预测结果必须带：

```json
{
  "model_name": "nem_price_quantile_lgbm",
  "model_version": "0.3.1",
  "trained_until": "2026-03-31",
  "feature_snapshot_id": "fs_20260427_001",
  "calibration": {
    "p90_coverage_last_90d": 0.88,
    "pinball_loss_p50": 13.2,
    "negative_price_precision": 0.74,
    "negative_price_recall": 0.68
  },
  "data_quality_score": 0.93
}
```

---

## 3.4 投资模型升级为 P50 / P90 / debt case 风险模型

### 当前问题

当前投资分析已有 IRR、NPV、DSCR、Monte Carlo 等基础能力，但商业级客户需要的不只是“一个 IRR 数字”，而是：

- P50 收益；
- P75 / P90 downside；
- 债务 sizing case；
- DSCR breach probability；
- merchant tail risk；
- revenue concentration；
- contract vs merchant split；
- augmentation plan；
- downside narrative。

### 建议新增指标

| 指标 | 说明 |
|---|---|
| P50 annual net revenue | 中位数年净收入 |
| P90 annual net revenue | 保守情景年净收入 |
| P50 / P90 equity IRR | 投资收益风险区间 |
| DSCR min / average | 偿债能力 |
| DSCR breach probability | 低于目标 DSCR 的概率 |
| Revenue concentration | 前 5% interval 贡献收入比例 |
| Merchant tail exposure | 合约期后 merchant 风险 |
| FCAS cannibalisation sensitivity | FCAS 收益压缩敏感性 |
| Augmentation cost schedule | 增容和更换成本 |
| Debt capacity | 按 P90 cashflow 可支撑债务 |

### 建议输出结构

```text
Base Case:
- Project IRR: 10.8%
- Equity IRR: 13.6%
- NPV: AUD 18.4m
- Payback: 7.2 years

Downside P90 Case:
- Project IRR: 5.1%
- Equity IRR: 6.4%
- Minimum DSCR: 1.08x
- DSCR breach probability: 22%

Main Risk Drivers:
1. FCAS price compression after additional BESS entry
2. High revenue dependence on top 5% intervals
3. Battery augmentation cost in year 9
4. WEM data is preview-grade, not investment-grade
```

### 投资报告化输出

建议自动生成：

- Executive summary；
- Market overview；
- Revenue stack；
- Dispatch simulation；
- Financial assumptions；
- Sensitivity tables；
- P50 / P90 cases；
- Key risks；
- Data quality and methodology caveats；
- Appendix。

---

## 3.5 数据质量评分和模型可信等级

### 当前问题

系统已有 coverage / confidence 类元数据，但尚未形成统一的数据质量产品能力。

### 建议数据质量评分

每个数据源、每个市场、每个接口、每个模型输出都应带：

| 指标 | 含义 |
|---|---|
| completeness | 是否缺 interval |
| freshness | 最新数据延迟 |
| duplicate_rate | 重复行比例 |
| anomaly_count | 极值、负值、单位异常 |
| schema_validity | schema 是否符合预期 |
| timezone_integrity | 时区和 DST 是否正确 |
| unit_consistency | MW / MWh / AUD/MWh / EUR/MWh 是否一致 |
| source_version | 来源版本 / 文件名 / API version |
| backfill_status | 历史回填是否完整 |
| transformation_hash | 转换链路 hash |

### 可信等级

建议定义四级：

| 等级 | 含义 | 可用于 |
|---|---|---|
| raw | 原始数据刚入库，未完整校验 | 内部排查 |
| preview | 部分字段、部分覆盖，适合方向判断 | demo / 初筛 |
| analytical | 数据质量可接受，适合分析报告 | 专业分析 |
| investment-grade | 有完整血缘、回测、审计、假设披露 | 投资决策支持 |

WEM ESS slim 当前建议标注为：

```text
preview / analytical-preview
```

NEM 历史价格 + FCAS 如果补齐质量评分和数据血缘，可逐步提升为：

```text
analytical
```

---

# 4. 功能层商业级改进建议

## 4.1 统一全球市场工作台

### 当前问题

当前澳洲主工作台和 Fingrid 独立页是两条产品线。这个结构适合早期开发，但不利于全球化商业产品。

### 建议产品结构

```text
Global Dashboard
├── Market Explorer
│   ├── Australia NEM
│   ├── Australia WEM
│   ├── Finland
│   ├── Nordic / Europe
│   ├── UK
│   ├── USA
│   └── Future Markets
├── BESS Revenue Lab
├── Forecast & Alerts
├── Grid Events & Constraints
├── Investment Analysis
├── Data Quality Center
├── Reports
├── API & Export
└── Admin / Workspace
```

### 核心交互

用户进入系统后不应先选择“澳洲页面还是 Fingrid 页面”，而应选择：

```text
Market -> Region / Bidding Zone -> Product -> Time Range -> Analysis Type
```

示例：

```text
Australia NEM -> SA1 -> Energy + FCAS -> 2025 -> BESS Revenue
Finland -> FI -> Day-ahead + Imbalance -> 2025 -> Market Screening
WEM -> WEM -> Energy + ESS -> last 90 days -> Alert Monitoring
```

---

## 4.2 Market Screening：站点和市场筛选功能

### 商业价值

这是最容易收费的核心功能之一。客户真正关心的是：

- 哪个市场值得进入？
- 哪个区域适合投储能？
- 哪个 bidding zone 价差最好？
- FCAS / ESS 收益是否可持续？
- 风险在哪里？
- 现在进入是否已经晚了？

### 建议筛选指标

| 模块 | 指标 |
|---|---|
| 价格机会 | average spread, top decile spread, negative price frequency, price spike frequency |
| 波动性 | standard deviation, tail price contribution, volatility regime |
| 储能适配度 | duration fit, cycle opportunity, charge/discharge window stability |
| FCAS / ESS | service price, scarcity, shortfall, capped events, requirement / available |
| 电网风险 | constraint count, outage density, interconnector congestion |
| 收益质量 | revenue concentration, seasonality, dependence on extreme intervals |
| 投资可行性 | indicative capex, grid fee, connection risk, P50 / P90 revenue |
| 数据可信度 | quality score, coverage, freshness, model grade |

### 输出示例

```text
Market Screening Result - BESS 2h Asset

1. SA1 / NEM
   Score: 86 / 100
   Strength: high volatility, FCAS depth, negative price charging
   Risk: revenue concentration, competition from new BESS
   Data grade: analytical

2. WEM
   Score: 78 / 100
   Strength: ESS scarcity signals, strong regulation opportunity
   Risk: current data is preview-grade, WEMDE full integration required
   Data grade: preview

3. Finland
   Score: 72 / 100
   Strength: 15-min market transition, imbalance opportunity, cross-border dynamics
   Risk: requires Fingrid + Nord Pool + ENTSO-E integration
   Data grade: partial
```

---

## 4.3 Revenue Stack 收益栈拆解

### 当前问题

当前已有 `RevenueStacking.jsx`，但商业级收益栈需要更强的解释能力。

### 建议拆解结构

```text
Total Annual Gross Revenue
├── Energy Arbitrage
│   ├── Negative price charging
│   ├── Daily spread capture
│   ├── Evening peak discharge
│   └── Extreme spike capture
├── FCAS / ESS
│   ├── Regulation raise
│   ├── Regulation lower
│   ├── Contingency raise
│   ├── Contingency lower
│   ├── Very fast FCAS / FFR
│   └── RoCoF
├── Balancing / Imbalance
├── Capacity / Reserve
├── Contracted Revenue
└── Other Revenue

Net Revenue
= Gross Revenue
- Charging Cost
- Network Fee
- Market Fee
- Variable O&M
- Degradation Cost
- Availability Loss
```

### 必须回答的问题

每个收益来源都要能回答：

- 来自哪些月份？
- 来自哪些小时？
- 是否依赖少数极端事件？
- 和其他收益是否冲突？
- 对 SoC / efficiency / degradation / network fee 是否敏感？
- 是否可持续？
- 数据等级是什么？

---

## 4.4 企业级告警系统

### 建议告警类型

| 告警 | 示例 |
|---|---|
| 价格告警 | price > AUD 500/MWh, price < 0 |
| 概率告警 | negative price probability > 40% |
| FCAS / ESS 告警 | Raise Reg price spike, ESS shortfall |
| 约束告警 | binding constraint count increased |
| 数据告警 | source freshness delayed, missing intervals |
| 模型告警 | forecast confidence dropped |
| 投资告警 | P90 revenue below debt case threshold |

### 告警渠道

- 邮件；
- Slack / Teams；
- Webhook；
- 前端 notification center；
- API polling；
- 企业版短信 / PagerDuty。

### 告警对象设计

```json
{
  "alert_id": "al_20260427_001",
  "market": "NEM",
  "region": "SA1",
  "severity": "high",
  "type": "negative_price_probability",
  "condition": "probability > 0.4",
  "observed_value": 0.52,
  "window": "2026-04-27T12:00:00+10:00/PT4H",
  "recommended_action": "preserve charging capacity for midday negative price window",
  "data_quality_score": 0.94,
  "created_at": "2026-04-27T02:00:00Z"
}
```

---

## 4.5 自动报告与投资备忘录

### 建议报告类型

1. Weekly Market Brief；
2. Monthly BESS Revenue Report；
3. Market Entry Screening Report；
4. Investment Committee Memo；
5. Data Quality Report；
6. Forecast Performance Report；
7. Project Scenario Report。

### 标准报告结构

```text
1. Executive Summary
2. Market Overview
3. Price Dynamics
4. FCAS / ESS Dynamics
5. Grid Events and Constraints
6. BESS Revenue Opportunity
7. Dispatch Backtest Result
8. Investment Sensitivity
9. P50 / P90 Case
10. Key Risks
11. Data Quality and Caveats
12. Methodology Appendix
```

### 商业价值

自动报告比单纯 dashboard 更容易商业化，因为它直接满足：

- 投资委员会材料；
- 客户月报；
- 项目筛选交付物；
- 咨询报告；
- 内部风控归档；
- 尽调附件。

---

## 4.6 外部 API 产品化

### 建议 API 分层

```text
/api/v1/markets
/api/v1/regions
/api/v1/prices
/api/v1/fcas
/api/v1/ess
/api/v1/constraints
/api/v1/events
/api/v1/forecasts
/api/v1/bess/backtests
/api/v1/investment/scenarios
/api/v1/reports
/api/v1/data-quality
```

### API 必须具备

- API key；
- organization / workspace；
- rate limit；
- usage metering；
- OpenAPI docs；
- versioning；
- webhook；
- pagination；
- export jobs；
- SLA status；
- audit log。

### 响应必须包含的专业字段

```json
{
  "data": [],
  "metadata": {
    "market": "NEM",
    "region": "SA1",
    "timezone": "Australia/Adelaide",
    "currency": "AUD",
    "unit": "AUD/MWh",
    "interval_minutes": 5,
    "source": "AEMO",
    "source_version": "...",
    "ingested_at": "...",
    "data_quality_score": 0.96,
    "methodology_version": "price_api_v1.2.0"
  }
}
```

---

# 5. 数据层与市场扩展建议

## 5.1 建立全球统一 canonical schema

### 当前问题

当前系统中，澳洲主价格表、WEM ESS 表和 Fingrid timeseries 表是不同结构。早期这样做开发效率高，但全球扩展会带来问题：

- 每加一个市场都要新增一套业务逻辑；
- 不同市场无法统一比较；
- 投资模型难以跨市场复用；
- 前端组件难以通用；
- API 无法产品化。

### 建议 canonical market data model

```text
market_code             NEM | WEM | FI | GB | ERCOT | CAISO
country_code            AU | FI | GB | US
region_code             SA1 | NSW1 | WEM | FI
bidding_zone            FI | SE1 | DK1 | ...
product_type            energy | fcas | ess | imbalance | reserve | capacity
service_type            raise_reg | lower_reg | mFRR_up | aFRR_down | ...
interval_start_utc      timestamp
interval_end_utc        timestamp
local_time              timestamp
timezone                IANA timezone
interval_minutes        5 | 15 | 30 | 60
price                   decimal
currency                AUD | EUR | GBP | USD
unit                    AUD/MWh | EUR/MWh | MW | MWh
volume_mw               decimal
energy_mwh              decimal
requirement_mw          decimal
available_mw            decimal
enabled_mw              decimal
shortfall_mw            decimal
constraint_id           string
source_name             AEMO | Fingrid | ENTSO-E | Nord Pool
source_url              string
source_file             string
source_version          string
published_at            timestamp
ingested_at             timestamp
data_status             raw | validated | corrected | replaced
quality_score           0-1
transformation_version  string
```

### service_type 标准化

```text
NEM:
- raise_reg
- lower_reg
- raise_1s
- lower_1s
- raise_6s
- lower_6s
- raise_60s
- lower_60s
- raise_5min
- lower_5min

WEM:
- regulation_raise
- regulation_lower
- contingency_raise
- contingency_lower
- rocof

Europe:
- aFRR_up
- aFRR_down
- mFRR_up
- mFRR_down
- FFR
- imbalance_up
- imbalance_down
```

---

## 5.2 澳洲数据补齐路线

### NEM 优先补齐

| 数据 | 用途 |
|---|---|
| DISPATCHPRICE | 5 分钟 energy + FCAS price |
| DISPATCHREGIONSUM | 区域负荷、可用容量、dispatch summary |
| PREDISPATCH | 预测价格和负荷 |
| STPASA / MTPASA | 短中期供需风险 |
| INTERCONNECTORRES | 跨区传输与约束影响 |
| CONSTRAINT / GENCONDATA | 约束解释 |
| BIDPEROFFER / BIDDAYOFFER | 出价和 bidding behaviour |
| Unit SCADA | 机组实际出力 |
| Market Notices | 事件和风险 |
| Rooftop PV / Operational Demand | 负价和中午谷值解释 |

### WEM 优先补齐

| 数据 | 用途 |
|---|---|
| WEM Dispatch Solution v2 | 完整 WEMDE 结果 |
| WEM Dispatch Case v2 | 输入和约束基础 |
| Dispatch Instructions | 设施调度目标 |
| Dispatch Summary | 市场汇总 |
| ESS requirement / availability | ESS 稀缺程度 |
| Facility dispatch target | 资产行为分析 |
| Constraint data | 约束解释 |
| Original / replacement schedules | 数据版本和审计 |
| Affected / missing intervals | 数据质量 |

---

## 5.3 芬兰和欧洲扩展路线

### Fingrid 优先数据

| 数据 | 用途 |
|---|---|
| imbalance price | 平衡 / imbalance 收益 |
| aFRR capacity price | 辅助服务收益 |
| mFRR activation / price | 调节收益 |
| FFR procured volume | 快速频率响应机会 |
| consumption / production | 基本供需 |
| wind / nuclear / hydro | 价格驱动因子 |
| cross-border flow | 跨境约束和价格分化 |
| transmission capacity | 区域联动 |
| consumption forecast | 预测特征 |

### ENTSO-E / Nord Pool 补齐

| 数据源 | 用途 |
|---|---|
| Nord Pool day-ahead price | 芬兰和北欧基础电价 |
| Nord Pool intraday | 短期交易机会 |
| ENTSO-E load forecast | 预测特征 |
| ENTSO-E generation forecast | 预测特征 |
| ENTSO-E cross-border capacity | 区域价格解释 |
| ENTSO-E balancing data | 平衡市场分析 |
| ENTSO-E outages | 事件和供给风险 |

---

## 5.4 全球市场扩展优先级

建议扩展顺序：

| 阶段 | 市场 | 理由 |
|---|---|---|
| 1 | Australia NEM / WEM 深化 | 已有基础，能快速形成商业深度 |
| 2 | Finland -> Nordic / Europe | Fingrid 已接入，天然扩展 ENTSO-E / Nord Pool |
| 3 | UK Elexon / BMRS | API 完整，平衡市场成熟，适合 BESS 分析 |
| 4 | US EIA + CAISO / ERCOT / PJM / NYISO | 市场大，储能客户多，但 ISO 数据差异大 |
| 5 | New Zealand / Japan / Singapore | 区域机会，但规则差异需单独建模 |

---

# 6. 技术架构商业级改进建议

## 6.1 从 SQLite 升级为分层数据架构

### 当前问题

SQLite 适合单机部署和轻量分析，但商业 SaaS 或企业版会遇到：

- 多写竞争；
- 大规模时序查询性能瓶颈；
- 多市场历史数据膨胀；
- 多租户隔离困难；
- 长任务与 API 查询互相影响；
- 审计和数据血缘不足。

### 建议目标架构

```text
Bronze Raw Layer
- 原始 CSV / JSON / ZIP / API response
- source_url / source_file / hash
- downloaded_at / published_at
- immutable archive

Silver Standardized Layer
- canonical schema
- timezone normalized
- currency / unit normalized
- deduplicated
- validated
- quality scored

Gold Product Layer
- dashboard aggregates
- BESS backtest outputs
- forecast features
- investment scenarios
- report-ready tables
```

### 推荐存储组合

| 场景 | 推荐技术 |
|---|---|
| 用户、权限、项目、配置 | PostgreSQL |
| 时序和中等规模分析 | TimescaleDB / PostgreSQL partitioning |
| 本地分析和 Parquet 查询 | DuckDB |
| 高性能 dashboard / 聚合 | ClickHouse |
| 原始数据湖 | Object Storage + Parquet |
| 大规模表格式 | Apache Iceberg |
| 缓存 | Redis |

DuckDB 适合直接查询 Parquet 等文件型数据，ClickHouse 适合实时 OLAP 分析，Iceberg 适合大规模数据湖表格式和 schema evolution。[^duckdb][^clickhouse][^iceberg]

---

## 6.2 Connector framework 替代脚本堆叠

### 当前问题

当前 `scrapers/` 是脚本集合。后续每加一个市场，如果继续堆脚本，会导致：

- 错误处理不统一；
- rate limit 不统一；
- 数据质量检查不统一；
- schema 映射重复；
- 回填和增量逻辑混乱；
- 难以监控和审计。

### 建议抽象

```python
class MarketConnector:
    market_code: str
    source_name: str
    supported_products: list[str]

    def discover(self):
        """发现可用文件、API endpoint、数据集。"""

    def backfill(self, start, end):
        """历史回填。"""

    def incremental(self):
        """增量同步。"""

    def normalize(self, raw_records):
        """映射到 canonical schema。"""

    def validate(self, normalized_records):
        """数据质量检查。"""

    def publish(self, records):
        """写入 silver / gold 层。"""
```

### 每个 connector 必备元数据

```yaml
source_name: AEMO_NEM_DISPATCHPRICE
market: NEM
country: AU
api_type: file_archive
rate_limit: null
timezone: Australia/Sydney
interval_minutes: 5
currency: AUD
unit: AUD/MWh
dedup_key:
  - market
  - region
  - interval_start_utc
  - product_type
  - service_type
quality_checks:
  - interval_continuity
  - unit_range
  - duplicate_check
  - schema_check
  - freshness_check
```

---

## 6.3 任务队列和调度编排

### 当前问题

APScheduler 内置调度适合轻量任务，但商业级多市场系统需要：

- 多 worker；
- 长回填任务；
- 失败重试；
- 任务状态；
- 进度展示；
- cancel / retry；
- per-source rate limit；
- 任务审计。

### 建议架构

```text
FastAPI API Service
  - 接收请求
  - 查询任务状态
  - 返回结果

Worker Service
  - 执行 backfill
  - 执行 incremental sync
  - 执行 forecast
  - 执行 BESS backtest
  - 执行 report generation

Queue
  - Celery / Dramatiq / RQ
  - Redis / RabbitMQ / Kafka

Scheduler / Orchestrator
  - 定时任务
  - 依赖编排
  - 重试策略
  - 失败恢复
```

### Job 状态模型

```text
queued -> running -> succeeded
                 -> failed
                 -> cancelled
                 -> retrying
                 -> partial_success
```

每个 job 必须记录：

```json
{
  "job_id": "job_20260427_001",
  "type": "fingrid_incremental_sync",
  "status": "running",
  "progress_pct": 62,
  "market": "FI",
  "dataset_id": "319",
  "created_by": "system",
  "started_at": "...",
  "updated_at": "...",
  "error": null,
  "records_processed": 18432
}
```

---

## 6.4 数据血缘和可观测性

### 数据血缘

商业级系统必须能回答：

- 图表来自哪个源文件？
- 这次收益结果用了哪个算法版本？
- 哪个数据集缺失导致预测置信度下降？
- 某个字段什么时候开始变化？
- 某个报告能否重算复现？

建议引入 OpenLineage 思路。OpenLineage 是用于数据血缘采集和分析的开放平台，追踪 datasets、jobs、runs 等元数据。[^openlineage]

### 可观测性

建议使用 OpenTelemetry 统一 traces、metrics、logs。OpenTelemetry 支持跨组件关联 traces、metrics 和 logs，便于排查服务行为和性能问题。[^opentelemetry]

### 核心监控指标

```text
ingestion_lag_seconds
source_api_error_rate
missing_interval_count
duplicate_row_count
data_quality_score
api_p95_latency
api_error_rate
cache_hit_rate
forecast_job_duration
backtest_job_duration
worker_queue_depth
db_lock_wait_seconds
report_generation_duration
```

---

## 6.5 API 合约、版本和安全

### API 治理

建议拆分：

```text
/api/internal/*  前端内部接口
/api/v1/*        对外商业 API
```

要求：

- OpenAPI 文档；
- request / response schema；
- 契约测试；
- semantic versioning；
- deprecated 字段保留窗口；
- 所有数值带 unit；
- 所有时间带 timezone；
- 所有模型输出带 methodology version。

### 安全与多租户

必须补齐：

- 登录认证；
- organization / workspace；
- RBAC；
- API key；
- rate limit；
- audit log；
- secrets management；
- export permission；
- project isolation；
- SSO / OIDC / SAML，企业版可选。

权限建议：

```text
Owner
Admin
Analyst
Viewer
API-only
Billing
```

资源模型：

```text
Organization
Workspace
Project
Market
SavedView
Report
Scenario
APIKey
Job
Dataset
Alert
```

---

# 7. 测试、质量和模型治理

## 7.1 数据质量测试

每个数据源应有自动化检查：

```text
schema test
not-null test
unique key test
interval continuity test
timezone / DST test
unit range test
negative / zero anomaly test
source freshness test
cross-source reconciliation test
```

示例：

- NEM 5 分钟数据通常每天应有 288 个 interval。
- 欧洲 15 分钟数据通常每天应有 96 个 interval，但 DST 日要特殊处理。
- Fingrid 不同 dataset 有不同分辨率，不能统一用小时级校验。
- WEM replacement / original 数据不能静默覆盖。

## 7.2 BESS 回测测试

必须覆盖：

```text
SoC boundary test
energy conservation test
round-trip efficiency test
no simultaneous charge/discharge test
cycle count sanity test
FCAS reservation conflict test
known toy-case optimality test
degradation cost calculation test
network fee application test
```

## 7.3 预测模型测试

必须记录：

```text
MAE / RMSE
pinball loss
P10 / P50 / P90 coverage
negative price precision / recall
spike detection precision / recall
calibration plot
walk-forward validation
regime-specific performance
```

## 7.4 前端 E2E 测试

建议用 Playwright 覆盖：

- 市场 / 区域 / 年份切换；
- price chart 加载；
- FCAS / ESS 图表加载；
- Fingrid 数据集同步状态；
- 投资分析提交；
- 报告导出；
- 空数据状态；
- 错误状态；
- 中英文切换；
- API 错误时 UI 降级。

---

# 8. 商业化建议

## 8.1 目标客户

| 客户类型 | 付费点 |
|---|---|
| 储能开发商 | 哪些市场值得投、收益和风险如何 |
| 投资基金 | P50 / P90、IC memo、尽调报告 |
| 电力交易团队 | 价格 / FCAS / ESS 告警、事件解释 |
| 咨询公司 | 快速生成市场报告 |
| 工商业用户 | 电价波动、储能和柔性负荷收益 |
| 政策 / 学术机构 | 标准化数据、图表和 API |

## 8.2 产品套餐

```text
Free / Demo
- 少量市场
- 延迟数据
- 基础图表
- 不含完整导出

Professional
- 全历史数据
- 高级图表
- BESS Revenue Lab
- CSV / Excel export
- 基础报告

Enterprise
- API access
- team workspace
- alerts
- scheduled reports
- custom connectors
- private deployment
- SSO / audit log

Investment-grade Add-on
- P50 / P90 cases
- methodology appendix
- custom assumptions
- investor memo
- data quality pack
```

## 8.3 商业主张

不要主打“电价可视化”，应主打：

- 全球电力市场数据标准化；
- 储能收益栈分析；
- FCAS / ESS 机会识别；
- 市场事件与约束解释；
- 投资情景与风险分布；
- 可审计数据和模型方法论；
- 自动生成投资报告。

---

# 9. 优先级路线图

## 9.1 P0：1-2 个月

| 优先级 | 事项 | 产出 |
|---|---|---|
| P0 | 定义 global canonical schema | 数据模型设计文档 + migration plan |
| P0 | 数据质量评分 | Data Quality Center v1 |
| P0 | WEM preview 标注 | UI / API 显式 data_grade |
| P0 | BESS dispatch backtest v1 | perfect-foresight 回测 |
| P0 | API unit / timezone / currency 标准化 | response metadata contract |
| P0 | 模型和数据版本号 | model_version / source_version |

## 9.2 P1：3-6 个月

| 优先级 | 事项 | 产出 |
|---|---|---|
| P1 | WEM Dispatch Solution v2 接入 | WEMDE raw + parsed tables |
| P1 | Fingrid + ENTSO-E + Nord Pool | Finland / Nordic market model |
| P1 | FCAS / ESS 联合收益模型 | opportunity cost model |
| P1 | 概率预测 P10 / P50 / P90 | quantile forecast API |
| P1 | Market Screening | 市场和区域评分 |
| P1 | 告警系统 | alert rules + webhook |
| P1 | 自动报告 | monthly / IC memo template |

## 9.3 P2：6-12 个月

| 优先级 | 事项 | 产出 |
|---|---|---|
| P2 | PostgreSQL / ClickHouse / Parquet 架构 | 商业级数据层 |
| P2 | Worker + queue + scheduler | 长任务与多市场调度 |
| P2 | 多租户 / RBAC / API key | SaaS 基础 |
| P2 | OpenTelemetry / lineage | 可观测和可审计 |
| P2 | UK / US 市场扩展 | 全球化能力 |
| P2 | Investment-grade methodology pack | 高价值交付物 |

---

# 10. 建议避免的方向

1. **不要急着宣称 AI 能准确预测电价。**  更专业的说法是概率预测、风险区间和驱动因子解释。

2. **不要把 WEM ESS slim 当成投资级结论。**  在接入完整 WEMDE case / solution 之前，WEM 应明确标注为 preview 或 analytical-preview。

3. **不要继续为每个市场单独写一套表和一套前端逻辑。**  全球化必须依赖 canonical schema。

4. **不要只做漂亮 dashboard。**  客户真正愿意付费的是收益、风险、报告、告警、API 和可审计方法论。

5. **不要在多副本生产环境依赖 SQLite 写入和内置 APScheduler。**  商业部署应拆分 worker、queue、orchestrator 和数据层。

6. **不要输出没有数据质量标签的投资结论。**  每个结果都应带 data grade、coverage、freshness、methodology version。

---

# 11. 推荐最终产品形态

建议将系统升级为：

> **全球电力市场与储能收益智能平台**

核心模块：

```text
1. Global Market Data Hub
   全球电力市场标准化数据中心

2. BESS Revenue Lab
   储能收益栈与调度回测

3. Market Screening
   市场和区域投资机会评分

4. Forecast & Risk Signals
   概率预测、负价、尖峰、FCAS / ESS 风险

5. Grid Events & Constraints
   电网事件、约束、停运、跨区解释

6. Investment Analysis
   P50 / P90、IRR、NPV、DSCR、债务 sizing

7. Reports & Memo Generator
   自动月报、投资备忘录、尽调附件

8. Data Quality & Lineage
   数据质量、来源、版本、血缘、审计

9. Enterprise API
   商业 API、webhook、导出和集成
```

最终商业定位：

```text
不是“电价图表工具”，
而是“帮助储能开发商、投资方和交易团队判断市场机会、收益风险和投资可行性的专业分析平台”。
```

---

# 12. 附录 A：推荐 API 响应规范

```json
{
  "data": [],
  "metadata": {
    "market_code": "NEM",
    "region_code": "SA1",
    "country_code": "AU",
    "timezone": "Australia/Adelaide",
    "interval_minutes": 5,
    "currency": "AUD",
    "unit": "AUD/MWh",
    "source_name": "AEMO",
    "source_version": "2026-04-27",
    "published_at": "2026-04-27T00:00:00Z",
    "ingested_at": "2026-04-27T00:05:00Z",
    "data_quality_score": 0.96,
    "data_grade": "analytical",
    "methodology_version": "price_trend_v1.1.0",
    "warnings": []
  }
}
```

---

# 13. 附录 B：推荐数据库分层

```text
Object Storage / local lake
└── bronze/
    ├── aemo/nem/dispatchprice/raw/
    ├── aemo/wem/dispatch_solution/raw/
    ├── fingrid/raw/
    └── entsoe/raw/

Warehouse
└── silver_market_interval
└── silver_market_service_price
└── silver_constraints
└── silver_events
└── silver_forecasts

Product marts
└── gold_price_dashboard
└── gold_bess_backtest
└── gold_revenue_stack
└── gold_investment_case
└── gold_data_quality
└── gold_reports
```

---

# 14. 附录 C：参考资料

[^aemo-5ms]: AEMO, Five Minute Settlements. https://aemo.com.au/initiatives/trials-and-initiatives/past-trials-and-initiatives/nem-five-minute-settlement--program-and-global-settlement/five-minute-settlements

[^aemo-fcas-model]: AEMO, FCAS Model in NEMDE. https://aemo.com.au/-/media/files/electricity/nem/security_and_reliability/dispatch/policy_and_process/fcas-model-in-nemde.pdf

[^aemo-vfcas]: AEMO, Very Fast FCAS Market Transition. https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/system-operations/ancillary-services/very-fast-fcas-market-transition

[^aemo-wem-solution]: AEMO Developer Portal, WEM Dispatch Solution v2 API. https://dev.aemo.com.au/WEM-Dispatch-Solution-v2-API

[^aemo-wem-overview]: AEMO Developer Portal, WEM Dispatch APIs Overview. https://dev.aemo.com.au/WEM-Dispatch-API-%20Overview

[^fingrid-api]: Fingrid Open Data, API instructions. https://data.fingrid.fi/en/instructions

[^fingrid-319]: Fingrid Open Data, Imbalance price dataset 319. https://data.fingrid.fi/en/datasets/319

[^nordpool-15]: Nord Pool, 15 Minute MTU Implemented in SDAC. https://www.nordpoolgroup.com/en/message-center-container/newsroom/exchange-message-list/2025/q4/15-minute-mtu-in-sdac-was-implemented/

[^entsoe]: ENTSO-E, Electricity Market Transparency. https://www.entsoe.eu/data/transparency-platform/

[^iea-batteries]: IEA, Batteries and Secure Energy Transitions. https://www.iea.org/reports/batteries-and-secure-energy-transitions

[^elexon]: Elexon Insights Solution API Documentation. https://bmrs.elexon.co.uk/api-documentation/introduction

[^eia]: U.S. Energy Information Administration, Open Data. https://www.eia.gov/opendata/

[^duckdb]: DuckDB, Querying Parquet Files. https://duckdb.org/docs/current/guides/file_formats/query_parquet

[^clickhouse]: ClickHouse official site. https://clickhouse.com/

[^iceberg]: Apache Iceberg, Evolution. https://iceberg.apache.org/docs/latest/evolution/

[^openlineage]: OpenLineage official site. https://openlineage.io/

[^opentelemetry]: OpenTelemetry official site. https://opentelemetry.io/
