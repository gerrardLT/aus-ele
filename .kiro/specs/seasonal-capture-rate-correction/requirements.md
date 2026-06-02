# Requirements Document

## Introduction

`backend/engines/forward_price_engine.py` 中的 `_compute_capture_rate` 在所有日历月份返回同一个 capture_rate,无法表达 NEM 实测中显著的季节性差异。前序诊断(参见 `.kiro/specs/summer-compression-correction/tasks.md` 的 Status 区段)与 Modo Energy 公开数据(2025-26 Summer Review NEM-wide -38% YoY、QLD -73% YoY;2025-01 单月极端价格事件 QLD 单月达 277k AUD/MW)一致表明:

- 澳洲夏季(Dec-Feb)BESS capture rate 受高太阳能 + 低净需求 + autobidder 同质化竞争压制,模型对该窗口系统性高估。
- H1 与 full-year 时段因为包含 Dec-Feb 高 capture 月与 January 偶发极端事件,模型用单一年度均值表达时系统性低估。
- 修正后剩余偏差(QLD 2025_26_summer +104.4%、QLD 2025_H1_calendar -33.9%、NSW1 2024_full -22.1%、VIC1 2024_full -29.0% 等共 4 个超阈时段)无法通过当前的 RVF/容量/月级精度三个维度继续收敛。

本 spec 为 `_compute_capture_rate` 引入**月份维度 + 区域差异化季节乘子**,目标是把 16 个回测时段的偏差全部收敛到 ±30% 以内(QLD1 2025_H1_calendar 单时段允许 ≤±35% 的 January 极端事件放宽),同时保持 19 条现有 PBT 全过、新增 ≥1 条覆盖季节因子代数性质的 PBT,且**不**修改 RVF、`capacity_data.json`、`_get_existing_bess_capacity`、`_get_cumulative_bess_capacity`。

### 架构集成 Flag(留待 design 阶段决策)

`validate_against_benchmarks` 当前使用硬编码 `MODO_CAPTURE_RATE = 0.65`(经 `REVENUE_FACTOR = 365 × DURATION × CAPTURE × RTE` 计算 model_revenue),**不**调用 `_compute_capture_rate`。这意味着如果季节修正只放在 `_compute_capture_rate` 里,回测验证不会生效。Design 阶段必须在以下三条路径中选定一条:

- 路径 A:让 `validate_against_benchmarks` 改用动态 `_compute_capture_rate(region, month=representative_month)` 替代硬编码 0.65,与 Req 5 配合;
- 路径 B:把季节修正应用到 `dist.mean_spread`(给 `calculate_price_distribution` 加 month 参数),影响价差而非 capture_rate;
- 路径 C:在 `validate_against_benchmarks` 内部单独叠加一层 seasonal modifier,保持 `_compute_capture_rate` 与 `MODO_CAPTURE_RATE` 互不干涉。

设计选择会反过来约束 Req 3、5、6 的最终断言形式;requirements 阶段把"集成点开放"作为一个显式 flag,不在此处锁死实现路径。

## Glossary

- **Forward_Price_Engine**: `backend/engines/forward_price_engine.py` 中的 `ForwardPriceEngine` 类,负责生成区域价格分布与 BESS 收入预测。
- **Capture_Rate_Calculator**: `Forward_Price_Engine` 内 `_compute_capture_rate` 方法及其辅助子例程的统称,职责是把 `compression_factor / year / bess_capacity_ratio / fleet_size` 计算为 capture_rate。
- **Seasonal_Capture_Module**: 本 spec 新增的内部子模块(限定在 `forward_price_engine.py` 文件内),职责是在给定 `region` 与 `month` 时返回一个区域+季节乘子,对 `Capture_Rate_Calculator` 的输出进行修正。
- **Season**: 取值集合为 `{"summer", "shoulder", "winter"}` 的离散标签,定义为:
  - `summer` = 月份 ∈ {12, 1, 2}
  - `winter` = 月份 ∈ {6, 7, 8}
  - `shoulder` = 月份 ∈ {3, 4, 5, 9, 10, 11}
- **Seasonal_Multiplier**: 浮点数,索引为 `(region, season)`,默认 1.0;由 `Seasonal_Capture_Module` 加载的常量字典 `SEASONAL_CAPTURE_MULTIPLIER` 提供。允许范围 [0.30, 1.50](见 Req 4)。
- **Reference_Month**: 整数 ∈ {1, ..., 12},由调用方传入 `Capture_Rate_Calculator`,表示该 capture_rate 评估对应的代表月份。
- **Backtest_Validator**: `Forward_Price_Engine.validate_against_benchmarks` 方法,负责把模型输出与 `data/financial_evidence.json` 中的 Modo 基准对比。
- **Backtest_Window**: 16 个 (region, period) 数据点构成的集合,region ∈ {NSW1, QLD1, VIC1, SA1},period ∈ {2024_full, 2025_H1_calendar, 2025_H2_calendar, 2025_26_summer}。
- **Period_Representative_Month**: 每个 period 在调用 `Capture_Rate_Calculator` 时使用的代表月份;具体映射见 Req 5。
- **PBT**: Property-Based Test,使用 Hypothesis 生成的代数性质测试,位于 `tests/test_forward_model_properties.py`。
- **Zero_Season_Mode**: 安全回退状态,定义为 `SEASONAL_CAPTURE_MULTIPLIER` 字典中所有条目均为 1.0 的状态。
- **Pre_Spec_Capture_Rate**: 本 spec 启动前(即 `summer-compression-correction` 关闭、capacity_data v4 + reference_date 月级精度落地后)`_compute_capture_rate(compression_factor, year, bess_capacity_ratio, fleet_size)` 的返回值。

## Requirements

### Requirement 1: 季节分类函数

**User Story:** 作为 Forward_Price_Engine 维护者,我需要一个把月份映射到季节标签的函数,以便后续按季节查表获取乘子。

#### Acceptance Criteria

1. THE Seasonal_Capture_Module SHALL 暴露一个内部函数,该函数接受一个名为 month 的 int 类型参数(合法取值范围为 1 至 12 的整数,含两端端点),并返回一个字符串,返回值仅限于集合 {"summer", "shoulder", "winter"}(全小写,无前后空白字符,无其他字符)。

2. WHEN month 取值为 12、1 或 2, THE Seasonal_Capture_Module SHALL 返回字符串 "summer"(此处 month=1 视为南半球澳洲夏季,与北半球月份-季节对应不一致是预期行为)。

3. WHEN month 取值为 6、7 或 8, THE Seasonal_Capture_Module SHALL 返回字符串 "winter"。

4. WHEN month 取值为 3、4、5、9、10 或 11, THE Seasonal_Capture_Module SHALL 返回字符串 "shoulder"。

5. IF month 为 int 类型但取值不在集合 {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12} 内, THEN THE Seasonal_Capture_Module SHALL 抛出 `ValueError` 异常,且错误消息同时包含传入的 month 实际数值与合法取值范围标识 "1-12",并且不返回任何季节字符串。

6. IF month 参数不是 int 类型(例如 float、str、None、list、dict 等任意非 int 类型), THEN THE Seasonal_Capture_Module SHALL 抛出 `TypeError` 异常,且错误消息包含传入参数的实际类型名称,并且不返回任何季节字符串。

### Requirement 2: 季节乘子查表

**User Story:** 作为 Forward_Price_Engine 维护者,我需要一个按 region + season 索引乘子的查表机制,以便不同区域使用差异化的季节修正强度。

#### Acceptance Criteria

1. THE Seasonal_Capture_Module SHALL 暴露一个模块级常量字典 `SEASONAL_CAPTURE_MULTIPLIER`,其结构为 `Dict[str, Dict[str, float]]`,外层键为区域字符串字面量(必须包含 "NSW1"、"QLD1"、"VIC1"、"SA1"),内层键为 Season 字符串字面量("summer"、"shoulder"、"winter")。

2. THE Seasonal_Capture_Module SHALL 为 NSW1、QLD1、VIC1、SA1 四个区域(本 spec 必需配置区域,不允许任一缺失)各定义 summer、shoulder、winter 三个 Season 的乘子,且每个乘子的浮点值落在闭区间 [0.30, 1.50] 内。

3. THE Seasonal_Capture_Module SHALL 暴露一个查询函数,接受 region (str) 与 month (int) 两个参数,按 NEM 季节划分(summer = {12, 1, 2}、shoulder = {3, 4, 5, 9, 10, 11}、winter = {6, 7, 8})将 month 解析为 Season 标签,并返回 `SEASONAL_CAPTURE_MULTIPLIER[region][season]` 对应的浮点值。

4. IF region 不在 `SEASONAL_CAPTURE_MULTIPLIER` 字典中且 region 不在必需配置区域集合 {NSW1, QLD1, VIC1, SA1} 内, THEN THE Seasonal_Capture_Module SHALL 返回 1.0 浮点值且不抛出异常。

5. THE Seasonal_Capture_Module SHALL 在源文件注释中为每个非 1.0 乘子记录 Modo 数据来源,包含报告标题或发布日期,以及该 region/season 对应的关键指标值。

6. IF month 不在闭区间 [1, 12] 的整数范围内, THEN THE Seasonal_Capture_Module SHALL 返回 1.0 浮点值且不抛出异常,且无论 region 参数取值如何,均优先按月份越界处理(短路返回 1.0)。

7. IF 必需配置区域集合 {NSW1, QLD1, VIC1, SA1} 中任一区域未在 `SEASONAL_CAPTURE_MULTIPLIER` 字典中定义 summer、shoulder、winter 三个 Season 的全部条目, THEN THE Seasonal_Capture_Module SHALL 在模块导入阶段抛出 `ValueError`,且错误消息列出全部缺失的 (region, season) 二元组。

### Requirement 3: capture_rate 集成季节修正

**User Story:** 作为 Forward_Price_Engine 用户,我需要 `_compute_capture_rate` 在已知月份的情况下应用季节乘子,以便不同时段窗口得到差异化的 capture_rate。

#### Acceptance Criteria

1. THE Capture_Rate_Calculator SHALL 接受可选参数 `region: Optional[str]` 与 `month: Optional[int]`,二者默认值均为 `None`,其中 `month` 的有效取值为闭区间 [1, 12] 内的整数;并要求两参数同时提供或同时省略(不允许只提供其一)。

2. IF `region` 与 `month` 同时为非 `None` 值且 `month` 在闭区间 [1, 12] 内, THEN THE Capture_Rate_Calculator SHALL 先将基础公式输出乘以 Seasonal_Multiplier(region, month),再依次执行基础 clamp 与高饱和 clamp。

3. IF `region` 与 `month` 同时为 `None`, THEN THE Capture_Rate_Calculator SHALL 跳过季节修正,并返回与 Pre_Spec_Capture_Rate 在浮点容差 1e-9 范围内一致的数值。

4. THE Capture_Rate_Calculator SHALL 在乘以 Seasonal_Multiplier 之后,先通过基础 clamp 将结果限定在闭区间 [0.10, 0.55],随后当且仅当 `bess_capacity_ratio > 0.30` 时再通过高饱和 clamp 将结果上限限定为 0.40。

5. WHILE Zero_Season_Mode 处于激活状态(即 SEASONAL_CAPTURE_MULTIPLIER 中所有条目均等于 1.0), THE Capture_Rate_Calculator SHALL 完全跳过 Seasonal_Multiplier 查表与乘子应用步骤(短路优化),并对任意相同输入返回与 Pre_Spec_Capture_Rate 在浮点容差 1e-9 范围内一致的数值。

6. IF `month` 非 `None` 但不在闭区间 [1, 12] 内,或 `region` 非 `None` 但未在 SEASONAL_CAPTURE_MULTIPLIER 中定义,或仅 `region` 与 `month` 之一被提供, THEN THE Capture_Rate_Calculator SHALL 按"两参数均为 None"的语义跳过季节修正并返回 Pre_Spec_Capture_Rate(浮点容差 1e-9),且不抛出异常。

### Requirement 4: 季节乘子的有界性

**User Story:** 作为模型审计者,我需要季节乘子被限定在合理范围内,以便防止配置错误把 capture_rate 推到非物理区域。

#### Acceptance Criteria

1. THE Seasonal_Capture_Module SHALL 要求 `SEASONAL_CAPTURE_MULTIPLIER` 字典中每个 (region, season) 条目对应的 Seasonal_Multiplier 为满足 0.30 ≤ value ≤ 1.50 的有限实数(闭区间,不允许 NaN、±Inf、None 或非数值类型)。

2. IF `SEASONAL_CAPTURE_MULTIPLIER` 字典中存在不满足 0.30 ≤ value ≤ 1.50 的条目,或存在 NaN、±Inf、None、非数值类型(例如字符串、列表)的值, THEN THE Seasonal_Capture_Module SHALL 在模块导入阶段(eager validation,且必须先于首次 capture_rate 计算调用完成)抛出 `ValueError`,且错误消息列出全部越界条目的 (region, season, value) 三元组。

3. WHEN Capture_Rate_Calculator 对基础 capture_rate 应用 Seasonal_Multiplier 并执行最终 clamp 后返回结果时, THE Capture_Rate_Calculator SHALL 使返回的 capture_rate 满足 0.10 ≤ capture_rate ≤ 0.55(闭区间)。

4. IF SEASONAL_CAPTURE_MULTIPLIER 字典在模块导入时被检测到任意非法条目(见条 2 中所列情形), THEN THE Forward_Price_Engine SHALL 不允许 capture_rate 计算流程在该字典通过校验之前完成,即 `_compute_capture_rate` 在该状态下被调用时 SHALL 抛出与导入期同样的 `ValueError` 而非降级处理。

### Requirement 5: Backtest_Validator 传递月份

**User Story:** 作为回测脚本运行者,我需要 `validate_against_benchmarks` 在调用模型计算 capture_rate 时传入与 period 对应的代表月份,以便季节修正能够在回测时段生效。

> **集成点说明**: 本 Req 假设 design 阶段选定路径 A(`validate_against_benchmarks` 改用动态 `_compute_capture_rate` 替代硬编码 `MODO_CAPTURE_RATE = 0.65`)。如果 design 阶段选路径 B 或 C,本 Req 的 AC 6 中"调用 `_compute_capture_rate`"将相应替换为"调用承载季节修正的实际函数",其余条款保持不变。
>
> **2026-05-30 更新**: design 阶段最终选定**变体路径 C**(详见 design.md *Architecture / 集成点路径决策* 区段),不采用路径 A。原因:Task 2 校准脚本验证表明路径 A 让 `model_revenue` 中的隐式 capture 假设从 Modo 0.65 推到 ~0.40,等价于整体缩水 38%,4 区域 × (summer, winter) 网格搜索全部不合格。变体路径 C 让 `model_revenue` 仍用 `MODO_CAPTURE_RATE = 0.65`(沿用 Task 1 锁定的 33/33 通过 baseline 与该公式可比),但额外乘上 `_lookup_seasonal_multiplier(region, representative_month)`;`_compute_capture_rate(...,region,month)` 在回测中仅作为输出诊断列 `dynamic_capture_rate`,**不**参与 model_revenue 主公式。本 Req 的 AC 6 中"调用承载季节修正的实际函数"在变体路径 C 下解释为"调用 `_lookup_seasonal_multiplier(region, representative_month)`",其余 AC 条款逐字保持。

#### Acceptance Criteria

1. THE Backtest_Validator SHALL 维护一个 `PERIOD_TO_REPRESENTATIVE_MONTH: Dict[str, int]` 映射,为下列 4 个回测 period 字符串各定义一个取值范围为 [1, 12] 的 Period_Representative_Month 整数:`2024_full`、`2025_H1_calendar`、`2025_H2_calendar`、`2025_26_summer`。

2. THE Backtest_Validator SHALL 为 `2024_full` 配置 Period_Representative_Month = 7(年中)。

3. THE Backtest_Validator SHALL 为 `2025_H1_calendar` 配置 Period_Representative_Month = 3(H1 中点)。

4. THE Backtest_Validator SHALL 为 `2025_H2_calendar` 配置 Period_Representative_Month = 9(H2 中点)。

5. THE Backtest_Validator SHALL 为 `2025_26_summer` 配置 Period_Representative_Month = 1(summer 窗口中位月)。

6. WHEN `validate_against_benchmarks` 在某 period 的迭代中调用承载季节修正的函数计算该回测窗口的 capture_rate, THE Backtest_Validator SHALL 同时传入与本次迭代当前 region 一致的 region 实参(且 region 必须属于 SUPPORTED_REGIONS,否则按 Req 3.6 短路返回 Pre_Spec_Capture_Rate),以及通过 `PERIOD_TO_REPRESENTATIVE_MONTH[period]` 查表得到的 Period_Representative_Month 实参(必须满足 1 ≤ month ≤ 12)。

7. IF 当前 period 不在 `PERIOD_TO_REPRESENTATIVE_MONTH` 字典中, THEN THE Backtest_Validator SHALL 在调用承载季节修正的函数时传入 month=None,使该回测窗口的 capture_rate 与未启用季节修正时的输出在数值上相等。

8. IF 当前 period 不在 `PERIOD_TO_REPRESENTATIVE_MONTH` 字典中, THEN THE Backtest_Validator SHALL 以 warning 级别日志记录该未映射 period 字符串。

9. IF 当前 period 不在 `PERIOD_TO_REPRESENTATIVE_MONTH` 字典中, THEN THE Backtest_Validator SHALL 继续迭代处理 benchmark 数据中的其余 period,不中断 `validate_against_benchmarks` 的整体执行流程。

### Requirement 6: 回测达标判据

**User Story:** 作为模型 owner,我需要本 spec 的最终落地版本满足明确的回测达标线,以便确认季节修正方案有效。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 在全部 16 个 Backtest_Window 数据点(4 个 region × 4 个 period)中,使至少 15 个数据点满足 `|deviation_pct| ≤ 30`(单位:百分点)。

2. WHERE 数据点 region = QLD1 且 period = 2025_H1_calendar, THE Forward_Price_Engine SHALL 使该数据点满足 `|deviation_pct| ≤ 35`(单位:百分点;因 January 极端价格事件污染该窗口算术均值,该单点放宽,与 `qld-rvf-correction` 一致;此放宽仅作用于本条的单点判据,该数据点仍按原值计入条 3-5 的全局指标)。

3. THE Forward_Price_Engine SHALL 使全局 MAPE(对全部 16 个 Backtest_Window 数据点 `|deviation_pct|` 取算术均值,单位:百分点)≤ 30。

4. THE Forward_Price_Engine SHALL 使全局 Bias 的绝对值 `|Bias|`(对全部 16 个 Backtest_Window 数据点带符号 deviation_pct 取算术均值后取绝对值,单位:百分点)≤ 15。

5. THE Forward_Price_Engine SHALL 使全局 Hit Rate(全部 16 个 Backtest_Window 数据点中满足 `|deviation_pct| ≤ 30` 的数据点占比,单位:%)≥ 75。

6. WHEN 季节修正落地后回测重跑, THE Backtest_Validator SHALL 在终端标准输出和 `reports/backtest_report.txt` 中记录全部 16 个 Backtest_Window 数据点的 (region, period, model, benchmark, deviation_pct) 五元组,以及条 3-5 的 MAPE、Bias、Hit Rate 三项全局指标的实际值;若两个输出目标之一失败但另一个成功记录全部内容,本条仍视为满足。

7. IF 回测重跑后 Backtest_Window 有效数据点数量 ≠ 16,或 条 1-5 中任一判据未满足, THEN THE Backtest_Validator SHALL 在终端标准输出和 `reports/backtest_report.txt` 中明确标记"未达标"状态并列出每一项未达标的判据编号及对应实际值,使本次回测结果不被采纳为达标。

8. THE Forward_Price_Engine SHALL 同时满足"Backtest_Window 有效数据点数量 = 16"与"条 1-5 全部判据成立"两组条件,二者缺一不可,任一不满足即判定本 Req 整体未达标。

### Requirement 7: 季节因子的代数性质 PBT

**User Story:** 作为模型质量负责人,我需要至少一条新增 PBT 覆盖季节修正的代数不变量,以便在未来重构中保护核心性质。

#### Acceptance Criteria

1. THE 新增 PBT SHALL 以新增测试函数形式追加于 `tests/test_forward_model_properties.py` 文件中现有最后一条测试函数之后,且 SHALL 不修改、不删除任何现有测试类与现有测试用例的代码。

2. WHILE Zero_Season_Mode 激活(即 SEASONAL_CAPTURE_MULTIPLIER 中全部条目数值等于 1.0),THE 新增 PBT SHALL 对任意满足 compression_factor ∈ [0.05, 1.0]、year ∈ [2024, 2050]、bess_capacity_ratio ∈ [0, 2]、fleet_size ∈ [0, 50]、region ∈ {NSW1, QLD1, VIC1, SA1}、month ∈ [1, 12] 的输入,断言带 (region, month) 参数调用 capture_rate 的返回值与不带 (region, month) 参数调用 capture_rate 的返回值之间的绝对差 ≤ 1e-9。

3. THE 新增 PBT SHALL 对任意满足上述 6 个参数合法范围的输入,断言带 (region, month) 参数调用 capture_rate 的返回值 rate 满足 0.10 ≤ rate ≤ 0.55(含两端);为保证下界 0.10 不被破坏,Capture_Rate_Calculator 实现 SHALL 通过 clamp 确保返回值不低于 0.10(即不允许返回 0.0 等小于 0.10 的数值)。

4. THE 新增 PBT SHALL 使用 `@settings(max_examples=100)` 装饰器,且 SHALL 通过 `@given` 策略覆盖上述 6 个输入参数(compression_factor、year、bess_capacity_ratio、fleet_size、region、month)的全部合法取值范围。

5. THE 新增 PBT SHALL 在 docstring 首行写入字符串,且该字符串 SHALL 同时包含字面前缀 `Feature: seasonal-capture-rate-correction` 与 `Property 20:` 后接属性名称,以与现有 19 条 PBT 的 docstring 首行格式一致。

6. WHEN 季节修正实现落地后执行 `tests/test_forward_model_properties.py` 完整 PBT 测试套件,THE Forward_Price_Engine SHALL 通过现有 19 条 PBT 与新增 1 条 PBT 的全部断言,且测试运行结果为 20 通过、0 失败、0 错误。

### Requirement 8: 改动边界

**User Story:** 作为前序 spec(`qld-rvf-correction`、`summer-compression-correction`)结果的守护者,我需要明确禁止本 spec 触碰已经稳定的常量与函数,以便保留前序工作的成果。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 保留 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 的浮点数值与 1.35 的绝对差 ≤ 1e-9(由 `qld-rvf-correction` 校准)。

2. THE Forward_Price_Engine SHALL 保留 `REGIONAL_VOLATILITY_FACTOR` 字典的键名集合不变,且每个键对应的浮点数值与本 spec 启动前对应数值的绝对差 ≤ 1e-9。

3. THE Forward_Price_Engine SHALL 使本 spec 落地后的 `data/capacity_data.json` 文件与本 spec 启动前的同名文件逐字节相同(SHA-256 哈希值完全一致)。

4. THE Forward_Price_Engine SHALL 保留 `_get_existing_bess_capacity` 与 `_get_cumulative_bess_capacity` 的函数名、参数名、参数顺序、参数默认值、返回值类型注解不变,且对任意合法输入调用,返回值与本 spec 启动前的返回值绝对差 ≤ 1e-9。

5. THE Forward_Price_Engine SHALL 把本 spec 的代码改动(新增、修改、删除的代码行)限定在以下三个范围:(a) `_compute_capture_rate` 方法体及其签名;(b) `_compute_capture_rate` 的调用点(`validate_against_benchmarks`、`estimate_annual_revenue`、`generate_20year_projection`);(c) 新增的 Seasonal_Capture_Module 内部辅助函数与常量。范围之外的代码差异行数应为零。

6. THE Forward_Price_Engine SHALL 保留所有不以下划线开头的方法名(公开方法)与所有全大写+下划线的模块级常量名(模块级常量)不被删除、不被重命名(键名集合的前后差集为空)。

### Requirement 9: 向后兼容性

**User Story:** 作为 `Forward_Price_Engine` 的下游调用者,我需要现有调用点在不传 region/month 的情况下行为不变,以便其他 spec(投资模型、ML 校准等)不被本次改动打破。

#### Acceptance Criteria

1. WHEN `_compute_capture_rate` 被以原签名调用(即 region 参数与 month 参数均省略,或两者显式传入 None), THE Capture_Rate_Calculator SHALL 在其余输入参数完全相同的条件下,返回与 Pre_Spec_Capture_Rate 数值等价的结果(返回值与 Pre_Spec_Capture_Rate 的绝对差 ≤ 1e-9)。

2. WHEN 在本 spec 落地后执行现有 PBT 测试套件, THE Forward_Price_Engine SHALL 使全部 19 条 PBT 用例的断言通过(失败用例数 = 0,错误用例数 = 0)。

3. WHEN 在本 spec 落地后执行 `scripts/run_full_backtest.py`, THE Forward_Price_Engine SHALL 使 A-H 八个章节合计 33 个验证数据点全部判定为通过(被标记为失败的数据点数 = 0)。

4. IF `scripts/run_full_backtest.py` 在执行过程中以非零退出码终止、抛出未捕获异常,或未完成全部 33 个数据点的写入, THEN THE Forward_Price_Engine SHALL 视为本 Req 未通过(脚本崩溃即等同于回归)。

### Requirement 10: 来源记录

**User Story:** 作为审计者,我需要每个非 1.0 的 Seasonal_Multiplier 条目都附有可追溯的数据出处,以便后续调参时不会盲改。

#### Acceptance Criteria

1. THE Seasonal_Capture_Module SHALL 在 `SEASONAL_CAPTURE_MULTIPLIER` 字典定义语句的紧邻上方(中间不夹杂其他代码或空行)追加一段独立的中文注释块,以 `# ===== 解决记录:seasonal-capture-rate-correction =====` 作为起始标记行,以 `# ============================================` 作为结束标记行。

2. THE Seasonal_Capture_Module SHALL 在该注释块中,为 `SEASONAL_CAPTURE_MULTIPLIER` 字典中所有 summer 或 winter 乘子取值不等于 1.0 的条目逐项登记以下五个字段:(a) 区域名称(NEM/QLD/NSW/VIC/SA 之一)、(b) 季节标识(summer 或 winter)、(c) 乘子数值(保留两位小数)、(d) 来源 Modo 报告完整标题、(e) 对应的实测 YoY 数值(以百分比表示,带百分号)。

3. IF `SEASONAL_CAPTURE_MULTIPLIER` 字典中存在 summer 或 winter 乘子取值不等于 1.0 但该注释块中未同时登记其区域名称、季节标识、乘子数值、Modo 报告标题与实测 YoY 数值,THEN THE Seasonal_Capture_Module SHALL 视为来源记录校验不通过。

4. WHERE 某条目对应的 Modo 报告标题在公开渠道暂无法获取,THE Seasonal_Capture_Module SHALL 在"来源 Modo 报告完整标题"字段以 ISO 8601 日期格式(YYYY-MM-DD)填写报告发布日期,并在该字段后追加 "(标题缺失,以发布日期代替)" 文字标注。

5. THE Seasonal_Capture_Module SHALL 在该注释块中以 `修复日期: YYYY-MM-DD`(YYYY-MM-DD 为 ISO 8601 日期格式)与 `关联 spec: seasonal-capture-rate-correction` 两个独立行,分别标识本次修复完成日期与关联 spec 名称。

6. THE Seasonal_Capture_Module SHALL 在该注释块中以一个独立段落说明 shoulder 季节乘子固定为 1.0 的依据,该段落必须显式包含以下三点要素:(a) shoulder 季节作为基线值 1.0、(b) summer 与 winter 乘子表示相对 shoulder 基线的偏移倍数、(c) shoulder 基线不引用任何 Modo 报告数据;该段落 SHALL 独立存在,不依赖于条 2/3/4 关于 summer、winter 来源记录的校验状态(即使来源记录校验失败,该段落仍必须存在并完整)。
