# 澳洲电网预测模块设计文档

> 日期：2026-04-15
> 状态：draft
> 目的：把系统从“历史分析 + 事件解释”扩展为“独立的澳洲电网预测模块”，但坚持保守真实性，不假装给出投资级收益预测。

## 1. 这次要做的到底是什么

这次要做的不是把“事件解释层”继续挂在每个图表下面，也不是把新闻/公告做成资讯流。

这次真正要做的是一个独立模块：

- 面向未来，不是只做事后解释。
- 核心任务是预测未来 `24h / 7d / 30d` 的电网状态变化和市场机会。
- 输出的是 `风险 / 概率 / 机会窗口 / 驱动因子`，不是直接改写 NPV、IRR、payback。

用一句话概括：

`基于 AEMO/BOM 官方数据 + 本地历史市场数据，给出澳洲电网未来时段的电网紧张度、价格风险、FCAS 机会和储能充放电窗口预测。`

## 2. 研究结论与当前项目现实基础

### 2.1 官方可用输入源

基于截至 `2026-04-15` 的官方源核对，第一版预测模块最值得使用的前瞻输入不是“泛新闻”，而是这些官方结构化源：

NEM：

- AEMO `Pre-dispatch` / `5 Minute Pre-dispatch`：
  用于未来短时段的价格和需求预测。AEMO 官方页面明确说明该数据包含未来短时段的区域价格与需求预测。
- AEMO `Operational Demand data`：
  用于构造真实负荷基线和异常偏离度。
- AEMO `Market Notices`：
  用于识别 LOR、direction、intervention、system security 事件。
- AEMO `Network Outage Schedule`：
  用于识别未来计划停运和网络压力。
- AEMO `MMS / EMMS` 体系中的风光预测相关数据：
  用于后续扩展 UIGF / ASEFS / AWEFS 类输入，但第一版不要求全部打通。

WEM：

- AEMO `Market Advisories`：
  用于 reserve/security/process 类预警。
- AEMO `Data (WEM)` / Market Data：
  官方页面明确列出 demand and forecasts、dispatch、outages、prices、settlements 等数据类型。
- AEMO `Outages and Commissioning` / `Outage Intention Plan`：
  用于计划停运和未来可用性扰动。

天气：

- BOM `Weather Data Services`：
  提供 forecast / warnings / observations 等自动化数据服务。
- BOM `Fire Weather Warnings`：
  对极端天气、电网安全、线路风险和需求冲击有直接解释价值。

### 2.2 本地工程当前真实数据基础

按当前仓库和本地 `aemo_data.db` 核对，系统现在已经具备这些基础：

- `trading_price_2020` 到 `trading_price_2026`
  - NEM 五大区价格历史已在库。
  - NEM FCAS 历史价格字段也已并入同表。
  - WEM trading price 也已经通过 `region_id='WEM'` 写入同类年表，当前本地覆盖到 `2026-04-14`。
- `wem_ess_market_price`
  - 当前是最近约 30 天的 slim 表。
  - 本地区间约为 `2026-03-16` 到 `2026-04-14`。
- `wem_ess_constraint_summary`
  - 提供 binding / near-binding / max shadow price 等约束摘要。
- `grid_event_raw` / `grid_event_state`
  - 已有官方事件抓取和标准化入库基础。

这意味着：

- NEM 侧已经具备做 `历史校准 + 未来短时预测` 的基础。
- WEM 侧适合先做 `核心风险预测`，不适合一上来做“全量可实现收益预测”。

## 3. 产品定位

预测模块的定位固定为：

- `市场监控 / 调度机会识别 / 异动前瞻`
- 不是：
  - 投资收益自动改写器
  - 项目融资结论引擎
  - 自动交易执行器
  - 泛新闻中心

### 第一版明确不做

- 不自动改写 InvestmentAnalysis 的收益、NPV、IRR、payback。
- 不把事件或天气直接注入 BESS Simulator 的现金流。
- 不承诺给出“未来电价点位一定是多少”的精确单值预测。
- 不对 WEM 输出“投资级 FCAS 收益预测”。

## 4. 模块输出应该长什么样

预测模块做成独立页面或独立一级模块，而不是图表下方重复卡片。

### 4.1 预测时域

- `24h`
  - 以小时级或 30 分钟级窗口为主。
  - 偏实时、偏调度。
- `7d`
  - 以日级为主，局部高风险窗口可细化。
  - 偏运营排班和风险监控。
- `30d`
  - 做 regime / structural outlook，不做精细点位预测。
  - 偏策略和月度风险观察。

### 4.2 核心输出指标

对每个市场、区域、时域，输出以下结果：

- `grid_stress_score`
  - 电网紧张度分数，0-100。
- `price_spike_risk`
  - 高价尖峰风险，输出概率带或风险等级。
- `negative_price_risk`
  - 负价风险，输出概率带或风险等级。
- `reserve_tightness_risk`
  - 储备紧张风险。
- `fcas_opportunity_score`
  - FCAS 机会强度分数。
- `charge_window_score`
  - 储能优先充电窗口分数。
- `discharge_window_score`
  - 储能优先放电窗口分数。
- `driver_tags`
  - 驱动因子标签，例如 weather / outage / reserve / demand / constraint / interconnector / supply。
- `confidence`
  - 预测置信度，不足时必须下调。

### 4.3 页面级展示

页面只保留一个独立预测模块，建议结构：

- 顶部：
  - 市场、区域、时域切换
  - 更新时间、覆盖说明、模型模式说明
- 第一屏：
  - 5 张 summary cards
  - `grid stress / spike risk / negative price / FCAS / storage window`
- 主图：
  - 未来 `24h / 7d / 30d` 风险时间轴
- 次级区块：
  - 关键驱动因子列表
  - 官方证据链接
  - “为什么这么判断”的结构化解释
- 底部：
  - 模型假设、覆盖缺口、不可用于项目融资的声明

## 5. 三种实现路线

### 方案 A：纯规则引擎

做法：

- 基于公告、天气、停运、约束、近期价格/FCAS 行为，直接打规则分。
- 不做历史拟合，不做概率校准。

优点：

- 快，透明，可审计。
- 很适合 WEM 这种当前数据不完整场景。

缺点：

- 只能给“信号”，不能较可信地给“概率”。
- 容易在正常日和复杂叠加场景上失真。

### 方案 B：纯时间序列 / 纯 ML 预测

做法：

- 直接用历史价格、负荷、FCAS 做未来价格预测模型。

优点：

- 理论上可以输出更连续的数值预测。

缺点：

- 当前项目的数据治理、特征层、样本覆盖、回测框架都还不够。
- 极容易做成“看起来很像，但不可相信”的假精度。
- WEM 当前更不适合。

### 方案 C：混合式 MVP，推荐

做法：

- 前瞻官方源提供“未来驱动”。
- 历史市场数据提供“基线行为”和“风险校准”。
- 先做 `规则信号 + 历史分位校准 + 概率带`。

优点：

- 真实、可解释、能较快上线。
- 能和现有项目数据基础对接。
- 可逐步从 score 升级到 calibrated probability，再升级到更完整模型。

缺点：

- 第一版不是华丽的数值型价格预测器。
- 需要清楚写出哪些概率是“校准概率”，哪些只是“风险等级”。

### 推荐结论

采用 `方案 C：混合式 MVP`。

第一版先把：

- `未来风险`
- `未来机会窗口`
- `驱动因子`
- `概率带`

做可信，再考虑更激进的点位预测。

## 6. 推荐的模块架构

预测模块拆成 4 层：

### 6.1 Source Layer

职责：

- 拉取未来导向官方源。
- 规范化时区、区域、字段名。

第一版优先源：

- NEM：
  - predispatch / p5min
  - market notices
  - network outage schedule
  - operational demand
  - BOM warnings / forecasts
- WEM：
  - market advisories
  - outages / OIP
  - WEM market data 中可直接获取的 demand / forecast / price / dispatch 摘要
  - BOM warnings / forecasts

### 6.2 Feature Builder

职责：

- 把不同来源转成统一特征。

第一版核心特征：

- `recent_price_regime`
- `recent_negative_price_ratio`
- `recent_peak_price_intensity`
- `recent_fcas_level`
- `recent_fcas_dispersion`
- `predispatch_price_level`
- `predispatch_price_slope`
- `predispatch_demand_level`
- `predispatch_demand_ramp`
- `outage_severity`
- `outage_density`
- `event_severity`
- `reserve_signal`
- `weather_severity`
- `fire_weather_signal`
- `constraint_tightness`
- `interconnector_stress`
- `wem_binding_constraint_signal`
- `wem_shortfall_signal`

### 6.3 Forecast Engine

职责：

- 基于特征产出预测结果。

第一版不直接做“单值价格预测”，而是做：

- 风险分数
- 机会分数
- 方向判断
- 概率带

建议分成两个子引擎：

- `signal_engine`
  - 基于显式规则和权重输出原始分数。
- `calibration_engine`
  - 用历史样本分位数或简单逻辑回归，把分数映射成风险带。

### 6.4 Presentation Layer

职责：

- 输出稳定 API。
- 前端展示独立预测页面。

## 7. 预测口径

### 7.1 NEM 预测口径

NEM 第一版允许输出：

- `24h`
  - 较高置信度的风险/机会窗口
  - 以 predispatch / p5min 为核心
- `7d`
  - 中等置信度的日级风险 outlook
  - 更多依赖 outage + notices + weather + recent regime
- `30d`
  - 低频结构判断
  - 只做 regime，不做具体价格点位

### 7.2 WEM 预测口径

WEM 第一版只做 `core forecast mode`：

- 可以输出：
  - reserve/security/network/constraint 风险
  - FCESS/ESS 机会强弱
  - 未来 24h/7d 的核心风险标签
- 不可以输出：
  - 投资级 FCAS 收益预测
  - 高可信的全量 dispatch-feasible joint optimisation 结果

WEM 页面必须显式标注：

- `core coverage`
- `not investment-grade`
- `confidence constrained by slim history`

## 8. 推荐 API 设计

第一版只增加一组独立接口，不污染现有分析接口。

### 8.1 `GET /api/grid-forecast`

查询参数：

- `market`
- `region`
- `horizon=24h|7d|30d`
- `as_of?`
- `lang?`

响应：

- `metadata`
  - `forecast_mode`
  - `coverage_quality`
  - `issued_at`
  - `as_of`
  - `confidence_band`
  - `sources_used`
- `summary`
  - `grid_stress_score`
  - `price_spike_risk`
  - `negative_price_risk`
  - `reserve_tightness_risk`
  - `fcas_opportunity_score`
  - `charge_window_score`
  - `discharge_window_score`
- `windows`
  - `start_time`
  - `end_time`
  - `window_type`
  - `scores`
  - `probabilities`
  - `driver_tags`
  - `confidence`
- `drivers`
  - `driver_type`
  - `direction`
  - `severity`
  - `headline`
  - `summary`
  - `source`
  - `source_url`
  - `effective_start`
  - `effective_end`
- `disclaimer`

### 8.2 `GET /api/grid-forecast/coverage`

用途：

- 返回当前市场、区域、时域可以用到哪些源。
- 告诉前端当前预测为什么是 `full / partial / core_only / none`。

### 8.3 不新增的接口

第一版不新增：

- 自动改写投资模型的 forecast-adjusted revenue 接口
- 自动交易信号接口
- 告警订阅/推送接口

## 9. 数据持久化建议

第一版不需要引入复杂数据库改造，可以继续 SQLite，但要单独增加缓存/快照表。

推荐新增：

- `grid_forecast_snapshot`
  - 缓存同一 `market + region + horizon + as_of_bucket` 的结果
- `grid_forecast_feature_snapshot`
  - 可选，用于审计关键特征
- `grid_forecast_sync_state`
  - 跟踪未来导向源的同步状态

这样做的目的：

- 避免每次切换页面都重新抓/重新算导致很慢。
- 让预测结果可回放、可审计。

## 10. 与现有模块的关系

### 10.1 预测模块是独立模块

必须新增独立入口，例如：

- 顶部导航增加 `电网预测 / Grid Forecast`

而不是：

- 在 `Price Trend`
- `PeakAnalysis`
- `FcasAnalysis`
- `RevenueStacking`
- `CycleCost`

下面重复插入同一块预测/解释内容。

### 10.2 现有图表只保留“轻引用”

如果后续要和现有图表联动，最多允许：

- 图表上显示一个轻量 forecast badge
- 点击跳转到独立预测模块

不允许：

- 每个图表下面塞一个完整预测面板

## 11. 算法边界

### 11.1 第一版真正可落地的算法

可以做：

- 规则信号评分
- 历史分位校准
- 风险等级映射
- 未来窗口排序
- 驱动因子归因

### 11.2 第一版不要装作能做的算法

不要做这些虚高承诺：

- “未来 17:35 的价格一定是 xxx”
- “未来 7 天 FCAS 收益一定是多少”
- “自动把 forecast 注入 IRR/NPV 就更真实”

这些事情需要更重的数据、样本和验证框架，当前仓库还不具备。

## 12. 国际化和前端约束

这次新增模块必须从一开始就处理好中英文，不允许后补。

要求：

- 所有显示文案走 `web/src/translations.js`
- 不把中文硬编码进组件
- 不把英文官方原文直接裸露成唯一展示文本
- 对官方标题/摘要至少提供：
  - 原文
  - 中文解释文案
  - 来源链接

同时要注意：

- 时间轴上的文本不能溢出
- 卡片标题和 driver 标签要支持中英文长度差异
- 移动端不能把预测页做成横向爆宽

## 13. MVP 验收标准

### 后端

- `GET /api/grid-forecast` 能返回 NEM 结果。
- NEM `24h / 7d / 30d` 三种时域都能返回结构化结果。
- WEM 至少能返回 `core forecast mode`。
- 没有覆盖时返回 `coverage_quality` 和缺口说明，不装作有结果。
- 预测接口具备缓存，避免频繁切换导致明显卡顿。

### 前端

- 页面上存在独立的 `Grid Forecast` 模块或入口。
- 不再把预测内容重复插到每个旧图表下方。
- 中英文切换完整生效。
- 官方驱动因子有完整来源链接。
- 页面明确显示：
  - 预测模式
  - 置信度
  - 是否可用于投资判断

### 真实性

- 预测结果如果证据弱，必须降低 confidence。
- WEM 必须显式弱化。
- 不允许因为 UI 漂亮而伪造高精度结论。

## 14. 分阶段实施建议

### Phase 1：独立预测页面 + NEM 24h/7d

- 新建独立页面/模块
- 接通 `grid-forecast` 基础接口
- NEM 实现：
  - stress
  - spike risk
  - negative price risk
  - FCAS opportunity
  - storage windows

### Phase 2：NEM 30d + WEM core mode

- 增加 NEM regime outlook
- 增加 WEM 核心风险预测

### Phase 3：校准升级

- 加入更系统的历史样本校准
- 逐步从 risk band 升级到更可靠的 probability band

## 15. 本文档对应的直接结论

直接结论只有三条：

- 你要的应该是 `独立的澳洲电网预测模块`，不是“给现有图表加一堆重复的事件解释层”。
- 第一版最靠谱的做法是 `混合式 MVP：规则信号 + 历史校准 + 概率带`，而不是假装做高精度点位预测。
- NEM 可以先做完整一些，WEM 先做核心风险预测，不能装成和 NEM 同精度。

## 16. 官方来源

- AEMO Market Notices
  - https://www.aemo.com.au/market-notices
- AEMO Data (NEM)
  - https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem
- AEMO Pre-dispatch
  - https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/market-management-system-mms-data/pre-dispatch
- AEMO Operational Demand Data
  - https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/operational-demand-data
- AEMO Network Outage Schedule
  - https://aemo.com.au/en/energy-systems/electricity/national-electricity-market-nem/data-nem/network-data/network-outage-schedule
- AEMO Data (WEM)
  - https://www.aemo.com.au/energy-systems/electricity/wholesale-electricity-market-wem/data-wem
- AEMO WEM Market Advisories
  - https://aemo.com.au/energy-systems/electricity/wholesale-electricity-market-wem/data-wem/market-and-dispatch-advisories
- AEMO WEM Outages and Commissioning
  - https://aemo.com.au/energy-systems/electricity/wholesale-electricity-market-wem/system-operations/outages-and-commissioning
- AEMO WEM Outage Intention Plan
  - https://www.aemo.com.au/energy-systems/electricity/wholesale-electricity-market-wem/system-operations/outages-and-commissioning/outage-intention-plan
- BOM Weather Data Services
  - https://www.bom.gov.au/catalogue/data-feeds.shtml
- BOM Fire Weather Warnings
  - https://www.bom.gov.au/weather-services/bushfire/index.shtml
