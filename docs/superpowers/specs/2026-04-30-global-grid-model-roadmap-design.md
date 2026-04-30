# 全球电网数据分析与预测模型总路线图 Spec

**日期**: 2026-04-30  
**关联文档**: [全球电网数据分析与预测模型深度调研.md](/g:/project/aus-ele/docs/全球电网数据分析与预测模型深度调研.md)  
**目标**: 为当前仓库建立一条从研究型分析平台走向预测与决策平台的统一演进总纲，作为后续拆分 P0-P4 独立 specs 与实施计划的上位文档。

---

## 1. 背景

当前仓库已经具备以下能力：

- 历史价格、负价、FCAS/ESS 机会分析
- 规则型 `grid_forecast`
- 结构化 explanation / metadata / coverage 表达
- standardized BESS backtest 与投资分析链路

但它的本质仍是：

> **研究型电力市场分析工作台 + 规则型前瞻信号层**

而不是：

> **具备基本面数据、显式状态层、可评估预测层、BESS 决策层和治理层的预测与决策平台**

因此需要一条明确的顶层路线，避免后续进入“接口零散增加、模型零散增加、治理滞后”的状态。

---

## 2. 设计目标

本路线图的目标不是直接定义每一行实现代码，而是明确：

1. 后续模型平台应由哪些层组成
2. 各层的边界是什么
3. 当前仓库先做什么、后做什么
4. 什么属于阶段完成，什么只是增强项
5. 哪些能力必须贯穿全链路，而不是后置收尾

本 spec 用于：

- 后续拆分 `P0 / P1 / P2 / P3 / P4` 子 spec
- 为每个 phase 写实现 plan
- 约束前后端、数据、模型和治理口径一致

---

## 3. 非目标

本 spec 不直接定义：

- 单个数据源接入的字段级 schema
- 单个预测模型的具体算法实现
- 单个 API endpoint 的最终 response 细节
- 单个前端页面的交互设计
- 单次迭代中的具体 task 拆分

这些内容应在后续 phase spec 和 implementation plan 中展开。

---

## 4. 总体架构

统一路线划分为五层：

1. **P0 数据底座**
2. **P1 regime layer**
3. **P2 可评估预测层**
4. **P3 BESS 决策层**
5. **P4 模型治理层**

它们的依赖关系如下：

- `P0` 为全平台输入基础
- `P1` 建立统一状态语义
- `P2` 在 `P0 + P1` 上输出可评估预测
- `P3` 使用 `P1 + P2` 驱动资产决策
- `P4` 横切 `P0-P3`，负责可信度、审计与可用性声明

这个结构要求：

- 不允许先跳过 `P0` 直接堆复杂模型
- 不允许预测层脱离 regime 与评估闭环
- 不允许决策层脱离 uncertainty 与 degradation
- 不允许治理层只在产品末期补文案

---

## 5. P0：数据底座

### 5.1 目标

建立支撑后续 forecast / regime / dispatch / valuation 的统一基础数据层。

### 5.2 范围

首批必须覆盖的数据域：

- load forecast / actual
- wind forecast / actual
- solar forecast / actual
- rooftop PV
- outage / unit availability
- interconnector flow
- reserve / shortfall
- weather
- constraint
- settlement

### 5.3 结构原则

P0 必须同时包含两层能力：

1. **原始采集层**
   - 保留官方字段与时间戳语义
   - 保留 source identity
   - 保留 coverage / freshness
2. **统一建模层**
   - 统一市场/区域标识
   - 统一时间粒度表达
   - 统一 forecast vs actual 对照关系
   - 统一质量与 lineage metadata

### 5.4 关键边界

- `constraint` 是输入层，不是结论层
- `interconnector flow` 是输入层，不是 transmission separation 本身
- `settlement` 既是 P0 数据域，也是后续 P2/P3 收益评估的重要依赖

### 5.5 完成标准

P0 完成不意味着所有国家和所有数据一次性接完，而意味着：

- 已建立统一 ingestion contract
- 已有首批高价值数据域贯通
- 已能支撑 P1/P2 的最小可用输入
- 已能输出 coverage / freshness / source traceability

---

## 6. P1：Regime Layer

### 6.1 目标

把当前项目中散落的 score / driver / heuristic 结果升级为统一的显式状态层。

### 6.2 统一 regime 集合

首版统一状态：

- oversupply
- scarcity
- negative price
- reserve stress
- congestion
- transmission separation

### 6.3 输入来源

P1 不直接创造原始数据，而是消费：

- P0 fundamentals
- 现有 price / FCAS / event / constraint signals
- interconnector / reserve / shortfall / weather context

### 6.4 输出形态

regime layer 必须支持：

- current regime
- regime confidence
- regime drivers
- regime transition hints
- regime-to-score mapping

### 6.5 与现有系统的兼容策略

首版不应推翻现有 score 系统，而应采用：

- 保留 score
- 新增 regime
- 用 regime 统一解释 score / windows / drivers

这样可以避免：

- API 语义大改
- 前端全部重写
- 现有分析能力失稳

### 6.6 完成标准

P1 完成意味着：

- 现有核心分析接口具备统一 regime 输出
- regime 定义在跨市场口径上可复用
- 分析结果能从“单点分数”升级为“状态 + 分数 + 驱动”的结构

---

## 7. P2：可评估预测层

### 7.1 目标

建立一条可验证、可比较、可解释的预测生产线，而不是单次模型实验。

### 7.2 范围

建议预测能力按顺序建设：

1. baseline point forecast
2. quantile forecast
3. spike probability
4. negative price duration

### 7.3 Benchmark Hierarchy

P2 必须明确基线层级：

- naive baseline
- seasonal baseline
- fundamental baseline
- ML baseline
- probabilistic model

没有这条层级，不允许宣称“模型提升”。

### 7.4 必需评估能力

P2 的定义里必须内建：

- walk-forward backtest
- calibration
- regime error attribution

其中：

- `walk-forward backtest` 用于避免 hindsight leakage
- `calibration` 用于验证 quantile / probability 是否可靠
- `regime error attribution` 用于回答“模型在什么状态下失效”

### 7.5 完成标准

P2 完成意味着：

- 至少一条主预测链路可持续运行
- baseline 与模型对比是自动化的
- calibration 与 attribution 已进入输出契约
- 预测结果可被 P3 消费，而不是仅供图表展示

---

## 8. P3：BESS 决策层

### 8.1 目标

把当前 hindsight upper-bound backtest 推进到可用于真实决策研究的调度层。

### 8.2 核心能力

- rolling horizon dispatch
- energy + FCAS/ESS co-optimization
- degradation-aware dispatch
- scenario / stochastic dispatch
- revenue attribution

### 8.3 与当前能力的区别

当前系统更擅长回答：

- 历史上限是多少
- 哪个市场更有研究价值

P3 需要开始回答：

- forecast 引入后实际 dispatch 是否改善
- ancillary stacking 是否提高收益质量
- uncertainty 是否改变最优 SoC 策略
- degradation / risk reserve 是否改变长期价值

### 8.4 输出形态

P3 应输出的不只是 total revenue，还应包括：

- revenue stack decomposition
- realized vs forecast-driven gap
- cycle / throughput / SoC risk
- degradation impact
- scenario spread

### 8.5 完成标准

P3 完成意味着：

- 决策层不再依赖纯 hindsight 逻辑
- 预测结果已能进入 dispatch engine
- 收益输出具备 attribution 能力
- 投资分析可区分 upper bound、rule-based、forecast-driven、stochastic 口径

---

## 9. P4：模型治理层

### 9.1 目标

建立贯穿 P0-P3 的可信度、适用性和审计能力。

### 9.2 范围

- data lineage
- source freshness
- drift detection
- forecast value attribution
- investment-grade disclaimer

### 9.3 原则

`investment-grade disclaimer` 不是 P4 才第一次出现的能力。  
它应当从现在开始贯穿所有输出；P4 要做的是把它：

- 标准化
- 可追溯
- 与 coverage / freshness / confidence 绑定
- 可被 API / UI / report 统一消费

### 9.4 完成标准

P4 完成意味着：

- 关键结果都能追到 source 与 version
- freshness / drift / applicability 有统一表达
- forecast value attribution 能说明模型提升是否真正带来决策价值
- “可用于研究”与“不可用于投资级判断”的边界可系统化表达

---

## 10. 执行顺序

推荐执行顺序：

1. **Phase 1: P0 最小可用底座**
2. **Phase 2: P1 regime layer**
3. **Phase 3: P2 可评估预测**
4. **Phase 4: P3 BESS 决策层**
5. **Phase 5: P4 治理层系统化**

原因：

- `P0` 决定输入是否稳
- `P1` 决定语义是否统一
- `P2` 决定预测是否可信
- `P3` 决定模型是否能转化为决策价值
- `P4` 决定整套系统是否适合商业化

---

## 11. 与当前仓库的接口关系

后续各 phase 都应尽量围绕现有能力增量演进，而不是推翻重做。

重点接口与模块：

- `backend/grid_forecast.py`
- `backend/server.py`
- `backend/bess_backtest.py`
- `backend/engines/bess_backtest_v1.py`
- `backend/market_screening.py`
- `backend/finland_market_model.py`

优先演进原则：

1. 先扩充统一 metadata / lineage / coverage 表达
2. 再引入 P0 数据域
3. 再把 regime 挂进现有 API
4. 再逐步增加 forecast / dispatch 新链路

---

## 12. 风险与约束

### 12.1 最大风险

- 先做复杂模型，后补数据底座
- forecast 做出来但无法解释在哪些 regime 失效
- dispatch 层过早复杂化，脱离可验证输入
- disclaimer 只停留在文案，未与模型治理绑定

### 12.2 关键约束

- 不应让 WEM preview-grade 能力伪装成 investment-grade
- 不应让 point forecast 替代 probabilistic understanding
- 不应让前端先消费不稳定 schema
- 不应让 phase 边界混乱，导致“每层都做一点但没有一层做完整”

---

## 13. 验收方式

本总路线图 spec 的验收标准不是代码完成，而是：

1. 路线已按 P0-P4 明确定义
2. phase 边界和依赖关系清楚
3. 当前仓库的现实起点被正确纳入
4. 后续可以直接按本 spec 拆分子 specs

---

## 14. 后续拆分建议

下一步应从本总纲继续拆出以下独立 specs：

1. `P0 数据底座设计`
2. `P1 regime layer 设计`
3. `P2 forecast layer 设计`
4. `P3 BESS decision layer 设计`
5. `P4 governance layer 设计`

拆分原则：

- 每份 spec 只覆盖一个 phase
- 每份 spec 都要给出边界、数据契约、API 影响、测试策略、验收标准
- 每份 spec 后再单独写 implementation plan

