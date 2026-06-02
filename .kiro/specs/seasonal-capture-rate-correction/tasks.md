# Implementation Plan: Seasonal Capture Rate Correction

## Overview

针对 `backend/engines/forward_price_engine.py` 中 `_compute_capture_rate` 在所有日历月份返回同一 capture_rate、导致 QLD1 2025_26_summer 偏高 +104.4% 与 QLD1 2025_H1_calendar 偏低 -33.9% 的问题,引入**月份维度 + 区域差异化季节乘子**(`SEASONAL_CAPTURE_MULTIPLIER`)。设计阶段最终选定**变体路径 C**(`validate_against_benchmarks` 内 `model_revenue = mean_spread × MODO_REVENUE_FACTOR × seasonal_multiplier`,保留 `MODO_CAPTURE_RATE = 0.65` 不变,新增 `dynamic_capture_rate` 诊断列;详见 `design.md` *Revision History* 与 *Architecture / 集成点路径决策* 区段)。

工作流程为 8 步:基线冻结 → 字典占位 + 4 私有函数 + eager validation(让校准脚本可 monkeypatch)→ 校准脚本 ‖ Property 20 PBT 并行写 → 执行校准 + 写回乘子值 → 改 `_compute_capture_rate` ‖ 改 `validate_against_benchmarks` 并行 → 修复后回测 + 清理临时脚本 + 收尾。

预计总耗时 4–6 小时(任务 1/4/8 各 ~0.5h 等回测;任务 2 ~1.5h 写脚本 + 0.5h 网格搜索;任务 3/5/6 各 ~0.5h;任务 7 ~0.5h)。

## Tasks

- [x] 1. 基线冻结 Checkpoint:确认 design.md 对比表"修复前"列与最新回测一致
  - 执行 `python scripts/run_full_backtest.py`,捕获终端输出与 `reports/backtest_report.txt`
  - 把 16 个 Backtest_Window 数据点(QLD1/NSW1/VIC1/SA1 × 4 个 period)的 dev% 与全局 MAPE/Bias/Hit_Rate/PBT 通过数核对到 `design.md` "Data Models / 修复前 → 修复后回测对比表",确认"修复前 dev%"列已与最新回测一致(已预填:QLD summer +104.4 / QLD H1 -33.9 / NSW1 2024_full -22.1 / VIC1 2024_full -29.0 等;MAPE 20.01 / |Bias| 2.62 / Hit Rate 87.5%);如有偏差需改写
  - **关键**:本步必须在任何常量改动之前完成,作为后续 Req 9.2/9.3 回归检测的对照基线(19 PBT 全过 + 33/33 回测全过)
  - **不修改**任何源码、字典、数据文件
  - 验证:`reports/backtest_report.txt` A 段表与 `design.md` 对比表"修复前 dev%"列逐行一致(16 行 + 全局 4 项)
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 9.2, 9.3_

- [x] 2. 实现临时校准脚本 `scripts/calibrate_seasonal_multiplier.py`(网格搜索)
  - 按 design.md "Components and Interfaces / 1. SEASONAL_CAPTURE_MULTIPLIER 字典 / 网格搜索空间(变体路径 C 适用,tasks 阶段使用)" 实现 4 区域独立网格搜索;脚本是**自包含模拟器**:在脚本内按**变体路径 C** 公式手动计算 `model_revenue = mean_spread × MODO_REVENUE_FACTOR(沿用 0.65)× seasonal_multiplier(region, representative_month)`,**不**像之前路径 A 那样调用动态 `_compute_capture_rate`(避免 0.65 → ~0.40 的 38% 缩水基底问题,详见 design.md "Revision History")
  - 脚本内常量沿用 `MODO_DURATION = 4`、`MODO_CAPTURE_RATE = 0.65`、`MODO_RTE = 0.87`、`MODO_REVENUE_FACTOR = 365 × 4 × 0.65 × 0.87`,与改造前 baseline 公式完全一致(Zero_Season_Mode 下回测结果数值 ≡ Pre_Spec)
  - 候选空间(每区域独立,共 4 区域串行):
    - **QLD1 / NSW1 / VIC1**(偏差较大区域)各做 11×8 = 88 候选:summer ∈ {0.30, 0.40, ..., 1.00}(11 候选)× winter ∈ {0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20}(8 候选)
    - **SA1**(已达标 ±15.3% 内,缩小空间)做 5×5 = 25 候选:summer ∈ {0.90, 0.95, 1.00, 1.05, 1.10} × winter ∈ {0.90, 0.95, 1.00, 1.05, 1.10}
    - 总 88×3 + 25 = 289 组合,4 区域串行,合计 ~289 次评估调用(变体路径 C 下评估比路径 A 简单 — 无需调用 `_compute_capture_rate`,只需查 `_lookup_seasonal_multiplier` 直接乘到 model_revenue)
  - **shoulder 全部锁 1.00**(Req 10.6 设计契约,不参与搜索)
  - 候选评估通过 monkeypatch 字典 + 模拟变体路径 C 公式,**不**写回 `forward_price_engine.py` 主文件
  - 合格判据(全部 AND):
    1. 16 个 Backtest_Window 中至少 15 个满足 `|dev| ≤ 30`(QLD1 2025_H1_calendar 单点放宽到 ≤35,Req 6.1, 6.2)
    2. 全局 MAPE ≤ 30(Req 6.3)
    3. 全局 `|Bias|` ≤ 15(Req 6.4)
    4. 全局 Hit Rate(`|dev| ≤ 30` 占比)≥ 75%(Req 6.5)
  - 多组合格按 `min(|global_bias|)` 选优,平局按 `min(MAPE)` 二选优(Req 6.4 优先于 6.3)
  - **不允许**任何候选乘子超过 [0.30, 1.50](Req 4.1 硬上下界,在脚本进入主循环前用 `assert` 守卫,违规直接拒绝该候选)
  - 控制台按 design.md 给出的"候选评估表"格式输出,明确标注每候选 ✓ / ✗、每个达标判据(MAPE/|Bias|/Hit Rate/超阈数)的实际值,以及每区域最终选定的 (summer, winter) 二元组
  - **预期合格率显著高于路径 A**(因为公式无 38% 缩水偏移),直觉测算的乘子(QLD summer 0.49 / VIC1 winter 1.41 等)落在搜索空间内
  - 验证:脚本运行结束后,控制台与 `scripts/calibrate_seasonal_multiplier.log`(临时日志)同时记录 4 区域的候选评估表与最终选定值;若所有候选不合格,脚本以非零退出码终止并打印"候选空间扩展建议"
  - _Requirements: 2.2, 4.1, 4.2, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 3. 在 `forward_price_engine.py` 加 `SEASONAL_CAPTURE_MULTIPLIER` 字典(Zero_Season_Mode 占位 = 全 1.0)+ 4 个新私有函数 + eager validation 调用
  - 按 design.md "Components and Interfaces / 1-4" 顺序在 `backend/engines/forward_price_engine.py` 模块顶部追加 5 段代码,**位置紧跟 `MODO_RTE` 与 `REGIONAL_VOLATILITY_FACTOR` 等已有模块级常量之后**(避免与字典内值产生 import 顺序问题):
    1. 模块级常量 `_VALID_MONTHS: frozenset[int]`、`_SEASON_BY_MONTH: Dict[int, str]`、`_REQUIRED_REGIONS: frozenset[str]`、`_REQUIRED_SEASONS: frozenset[str]`、`_MULTIPLIER_LOWER_BOUND: float = 0.30`、`_MULTIPLIER_UPPER_BOUND: float = 1.50`(design.md "2. _classify_season" + "4. _validate_seasonal_multiplier_table" 中预定义)
    2. **`SEASONAL_CAPTURE_MULTIPLIER` 字典定义占位版**(本任务先写 Zero_Season_Mode = 全 1.0,任务 4 写真值):
       ```python
       SEASONAL_CAPTURE_MULTIPLIER: Dict[str, Dict[str, float]] = {
           "NSW1": {"summer": 1.00, "shoulder": 1.00, "winter": 1.00},
           "QLD1": {"summer": 1.00, "shoulder": 1.00, "winter": 1.00},
           "VIC1": {"summer": 1.00, "shoulder": 1.00, "winter": 1.00},
           "SA1":  {"summer": 1.00, "shoulder": 1.00, "winter": 1.00},
       }
       ```
       本任务**先不**写中文解决记录注释块(Req 10.1-10.6 的注释由任务 4 与真值一并落入)
    3. `_classify_season(month: int) -> str`,实现严格类型契约(`type(month) is not int` 抛 TypeError、月份越界抛 ValueError),按 design.md 提供的实现照抄(关键:用 `type(month) is not int` 排除 bool 子类,而非 `isinstance`)
    4. `_lookup_seasonal_multiplier(region: str, month: int) -> float`,三层防御(month 越界 → 1.0 短路、region 不在表 → 1.0 短路、正常查 `_SEASON_BY_MONTH` 反向表),按 design.md 实现照抄
    5. `_validate_seasonal_multiplier_table() -> None`,完整列出 missing/invalid 三元组后一次性抛 `ValueError`,按 design.md 实现照抄(包含 NaN/Inf 与 bool 子类排除)
  - **在 `SEASONAL_CAPTURE_MULTIPLIER` 字典定义之后立即调用** `_validate_seasonal_multiplier_table()`(模块加载期 eager validation,Req 4.2 / 4.4)
  - 追加 `_compute_zero_season_mode_flag()` 函数与 `_ZERO_SEASON_MODE: bool = _compute_zero_season_mode_flag()` 模块级缓存标志(design.md "5. _compute_capture_rate 改造的 1 行集成点 / Zero_Season_Mode 短路标志")
  - **本任务结束时全字典都是 1.0,`_ZERO_SEASON_MODE` 被算成 True**;这正是任务 2 校准脚本的 monkeypatch baseline(任务 2 把字典改成候选乘子 + `_ZERO_SEASON_MODE` 改 False 即可触发集成点)
  - **不修改** `_compute_capture_rate` 或 `validate_against_benchmarks`(留给任务 5/6)
  - **不修改** `REGIONAL_VOLATILITY_FACTOR`、`BASE_CAPTURE_RATE`、`BASE_SPREAD_PARAMS`、`MODO_CAPTURE_RATE` 等已有常量(Req 8.1, 8.2, 8.6)
  - 验证:`python -c "from backend.engines.forward_price_engine import SEASONAL_CAPTURE_MULTIPLIER, _classify_season, _lookup_seasonal_multiplier, _ZERO_SEASON_MODE; print(_ZERO_SEASON_MODE, _classify_season(1), _lookup_seasonal_multiplier('QLD1', 1))"` 输出 `True summer 1.0`;运行完整 19 PBT 测试套件全过(Req 9.2);运行 `run_full_backtest.py` 33/33 全过(因为字典是 Zero_Season_Mode,产品行为完全等价 Pre_Spec)
  - _Requirements: 1.1-1.6, 2.1, 2.4, 2.6, 2.7, 4.1, 4.2, 4.4, 8.1-8.6_

- [x] 4. 执行任务 2 校准、记录候选评估表、把选定值写回 `SEASONAL_CAPTURE_MULTIPLIER` + Modo 数据来源注释块
  - 手工运行 `python scripts/calibrate_seasonal_multiplier.py`,把控制台输出的 4 区域候选评估表完整保存(可贴入本任务下方的执行日志,或临时记到 commit message)
  - 确认脚本自动选出的 4 区域 (summer, winter) 二元组满足任务 2 的合格判据;若所有候选不合格(脚本退出码非零),停下来检查 design.md "Data Models / 直觉性方向" 段并扩展候选空间;**严禁**在不合格情况下硬选某组值修改主常量
  - 把 4 区域 × 2 季节(summer / winter)的选定乘子值写回 `forward_price_engine.py` 的 `SEASONAL_CAPTURE_MULTIPLIER` 字典,**shoulder 保持 1.00 不变**(Req 10.6)
  - 在 `SEASONAL_CAPTURE_MULTIPLIER` 字典定义**紧邻上方**(中间不夹杂其他代码或空行,Req 10.1)追加中文解决记录注释块,严格按 design.md "Components and Interfaces / 1. 占位结构" 模板填写,必须包含:
    - 起始标记行 `# ===== 解决记录:seasonal-capture-rate-correction =====`(Req 10.1)
    - 结束标记行 `# ============================================`(Req 10.1)
    - `# 修复日期: YYYY-MM-DD`(Req 10.5,本任务执行当日)
    - `# 关联 spec: seasonal-capture-rate-correction`(Req 10.5)
    - shoulder 基线说明独立段落(Req 10.6),显式包含三要素:(a) shoulder 作为基线值 1.0、(b) summer/winter 乘子表示相对 shoulder 基线的偏移倍数、(c) shoulder 基线不引用任何 Modo 报告数据
    - 对每个 summer / winter 乘子值 ≠ 1.0 的条目,逐项登记 5 字段(Req 10.2):区域名称、季节标识、乘子数值(两位小数)、来源 Modo 报告完整标题、对应实测 YoY 数值(带百分号)
    - 若某条目对应 Modo 报告标题在公开渠道暂无法获取,以 ISO 8601 日期格式 `YYYY-MM-DD` 填报告发布日期,并追加 `(标题缺失,以发布日期代替)` 标注(Req 10.4)
  - **写回后 `_ZERO_SEASON_MODE` 应被刷新为 False**(因为字典不再全是 1.0)— 由模块顶部 `_ZERO_SEASON_MODE = _compute_zero_season_mode_flag()` 在下次 import 时自动重算,无需手动改
  - **不修改** `_compute_capture_rate` 或 `validate_against_benchmarks`(留给任务 5/6 — 此时主链路尚未应用季节乘子,因此本任务写回字典后回测指标**仍**与任务 1 baseline 等价)
  - **不修改** RVF、capacity 函数等(Req 8.1-8.4)
  - 验证:`python -c "from backend.engines.forward_price_engine import SEASONAL_CAPTURE_MULTIPLIER, _ZERO_SEASON_MODE; print(_ZERO_SEASON_MODE); print(SEASONAL_CAPTURE_MULTIPLIER)"` 输出 `False` + 4 区域字典值;`python scripts/run_full_backtest.py` **33/33 仍全过**(因为任务 5/6 还没改主链路);19 PBT 全过(Req 9.2)
  - _Requirements: 2.2, 2.5, 4.1, 6.4, 10.1-10.6_

- [x] 5. 改造 `_compute_capture_rate`(签名扩展 + Zero_Season_Mode 短路 + 季节乘子集成点)
  - 按 design.md "Components and Interfaces / 5. _compute_capture_rate 改造的 1 行集成点" 修改 `backend/engines/forward_price_engine.py` 的 `ForwardPriceEngine._compute_capture_rate`:
    1. **签名扩展**:在现有 4 个位置参数(`compression_factor`, `year`, `bess_capacity_ratio`, `fleet_size`)之后追加 2 个 `Optional` 关键字参数,默认 `None`:
       ```python
       region: Optional[str] = None,   # NEW(Req 3.1)
       month: Optional[int] = None,    # NEW(Req 3.1)
       ```
       **不**改原有 4 个参数的名称、顺序、类型(Req 8.4 / 9.1)
    2. **函数体**:严格按 design.md "函数体改造(对应 Req 3.2-3.6)" 给出的结构插入季节修正集成点 — 三守卫(`region is not None and month is not None and not _ZERO_SEASON_MODE`)同时成立时,在 `raw` 上乘以 `_lookup_seasonal_multiplier(region, month)`,然后**保留原有** clamp [0.10, 0.55] 与 `bess_capacity_ratio > 0.30 → ≤ 0.40` 二次 clamp 不动(Req 3.4 / 4.3)
    3. **不**改 `BASE_CAPTURE_RATE * (compression_factor ** 0.5) * self._autobidder_decay(year) * self._fleet_size_factor(fleet_size)` 这一原始公式(Req 8.5)
  - 在 docstring 中补充三段说明,对应 Req 3.1 / 3.5 / 9.1(参考 design.md docstring 模板)
  - **关键不变量**(由实现自然保证,无需额外断言代码):
    - `_compute_capture_rate(...)`(无 region/month)≡ Pre_Spec_Capture_Rate(Req 3.3, 9.1)
    - 混合(只一个非 None)走 `not (region is not None and month is not None)` 守卫 → 等价 Pre_Spec(Req 3.6)
    - month 越界 / region 不在表 → `_lookup_seasonal_multiplier` 返回 1.0 → 乘 1.0 等价跳过(Req 3.6)
    - Zero_Season_Mode 激活 → `not _ZERO_SEASON_MODE` 守卫 → 短路绕过查表(Req 3.5)
  - **不**修改 `estimate_annual_revenue` 与 `generate_20year_projection` 对 `_compute_capture_rate` 的调用方式(暂不传 region/month,行为不变,Req 9.1)— 这两处的季节修正改造不在本 spec 范围
  - **不**新增/重命名/删除任何公开符号或模块级常量(Req 8.6)
  - 验证:运行 19 PBT 全过(Req 9.2);手动跑 `python -c "from backend.engines.forward_price_engine import ForwardPriceEngine; e = ForwardPriceEngine(); print(e._compute_capture_rate(0.5, 2025, 0.2, 10), e._compute_capture_rate(0.5, 2025, 0.2, 10, region='QLD1', month=1))"` 两个返回值都 ∈ [0.10, 0.55],且后者(若 QLD1 summer 乘子 < 1.0)< 前者
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.3, 4.4, 8.4, 8.5, 8.6, 9.1_

- [x] 6. 改造 `validate_against_benchmarks`(`PERIOD_TO_REPRESENTATIVE_MONTH` + 季节乘子叠层 + `dynamic_capture_rate` 诊断列)
  - 按 design.md "Components and Interfaces / 6. validate_against_benchmarks 改造(变体路径 C 核心)" 修改 `backend/engines/forward_price_engine.py` 的 `ForwardPriceEngine.validate_against_benchmarks` 方法:
    1. **新增 `PERIOD_TO_REPRESENTATIVE_MONTH: Dict[str, int]` 局部 dict**(Req 5.1-5.5),包含 4 个本 spec 必需 key + 2 个 legacy key:
       ```python
       PERIOD_TO_REPRESENTATIVE_MONTH = {
           "2024_full": 7,             # 年中(Req 5.2)
           "2025_H1_calendar": 3,      # H1 中点(Req 5.3)
           "2025_H2_calendar": 9,      # H2 中点(Req 5.4)
           "2025_26_summer": 1,        # summer 中位月(Req 5.5)
           "2025_H1": 3,               # legacy 兼容
           "2025_H2": 9,               # legacy 兼容
       }
       ```
    2. **重命名局部** `REVENUE_FACTOR` → `MODO_REVENUE_FACTOR`(语义化为"Modo 0.65 capture 假设的收入因子",但**仍是函数内局部变量**,公式不变:`365 * MODO_DURATION * MODO_CAPTURE_RATE * MODO_RTE`),保留 `MODO_CAPTURE_RATE = 0.65` 模块级常量本身不变(Req 8.6)
    3. 在 `for period, region` 嵌套循环内,**先查 `PERIOD_TO_REPRESENTATIVE_MONTH.get(period)`**:
       - 命中 → `representative_month = <int>`,然后 `seasonal_multiplier = _lookup_seasonal_multiplier(region, representative_month)`
       - 未命中 → `representative_month = None`,`seasonal_multiplier = 1.0` + `logger.warning(...)`(Req 5.7-5.8)+ **不中断循环**(Req 5.9)
    4. **`model_revenue` 公式(变体路径 C 核心)**:`model_revenue = dist.mean_spread * MODO_REVENUE_FACTOR * seasonal_multiplier`(Req 5.6)。**不**调用 `_compute_capture_rate(region, month)` 计算主公式(避免路径 A 的 0.65→0.40 缩水陷阱);Modo 0.65 + 季节乘子叠层让回测主公式与 Task 1 锁定的 33/33 baseline 在 Zero_Season_Mode 下数值等价
    5. **诊断列 `dynamic_capture_rate`** = `self._compute_capture_rate(compression_factor=dist.compression_factor, year=target_year, bess_capacity_ratio=bess_ratio, fleet_size=fleet_size, region=region, month=representative_month)`,`fleet_size` 取本循环内同区域 + 截止 `target_year` 的 BESS_COMMISSIONING 事件计数(沿用 design.md §6 给出的写法)。**该返回值仅作输出诊断列,不参与 model_revenue 计算**
    6. **`results` dict 新增 3 字段**:
       - `seasonal_multiplier`(round 到 4 位):本 region+representative_month 对应的乘子值,直接来自 `_lookup_seasonal_multiplier`
       - `dynamic_capture_rate`(round 到 4 位):业务代码视角下的动态 capture rate(诊断用,不参与 model_revenue)
       - `representative_month`(int 或 None):该 period 的代表月
  - **`benchmark_revenue` 与 `deviation_pct` 计算不变**(后者仍为 `(model_revenue - benchmark_revenue) / benchmark_revenue × 100`)
  - **Zero_Season_Mode 下 model_revenue ≡ Pre_Spec**:当 `SEASONAL_CAPTURE_MULTIPLIER` 全 1.0 时,`_lookup_seasonal_multiplier` 始终返回 1.0,`model_revenue = mean_spread × MODO_REVENUE_FACTOR × 1.0` ≡ Pre_Spec 公式 `mean_spread × REVENUE_FACTOR`(Req 9.3 自然保持 33/33)
  - 同步更新 `scripts/run_full_backtest.py` A 段输出格式,在每行末尾追加 `seasonal=<seasonal_multiplier>` 与 `capRate=<dynamic_capture_rate>` 列(可选;若列宽超限,则只保留 `seasonal` 列即可,Req 6.6 容忍"两输出之一记录全部内容"即视为满足)
  - **不**修改 `data/financial_evidence.json`、`data/capacity_data.json`(Req 8.3 SHA-256 一致)
  - **不**修改 `_get_existing_bess_capacity` / `_get_cumulative_bess_capacity`(Req 8.4)
  - **不**新增/重命名 `MODO_CAPTURE_RATE` / `MODO_DURATION` / `MODO_RTE` 等公开符号(Req 8.6)— 仅函数内局部 `REVENUE_FACTOR` → `MODO_REVENUE_FACTOR` 重命名属于私有改造,公开符号集合不变
  - 验证:`python scripts/run_full_backtest.py` 不抛异常;A 段每行多出 `seasonal=<value>` 与 `capRate=<value>` 列;`reports/backtest_report.txt` 末尾追加"季节修正:已启用(变体路径 C 集成方式)PERIOD_TO_REPRESENTATIVE_MONTH"标记;Zero_Season_Mode(任务 4 写真值前字典仍全 1.0)下 33/33 仍全过
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.6, 8.3, 8.4, 8.6_

- [x] 7. 在 `tests/test_forward_model_properties.py` 末尾追加 `TestSeasonalCaptureProperties` + Property 20 PBT
  - 按 design.md "Testing Strategy / Zero_Season_Mode 测试 fixture"(完整代码)与 "Correctness Properties / Property 20" 实现规范追加测试代码:
    1. **新增 `zero_season_mode` pytest fixture**(`@pytest.fixture` 装饰):同时 `monkeypatch.setattr(fpe_module, "SEASONAL_CAPTURE_MULTIPLIER", zeroed_table)` 与 `monkeypatch.setattr(fpe_module, "_ZERO_SEASON_MODE", True)`,严格按 design.md 给出的实现照抄 — **不允许只 monkeypatch 字典而不改 `_ZERO_SEASON_MODE` 标志**(否则 `_compute_capture_rate` 不走 short-circuit 路径,数值上仍等价但断言含义不准)
    2. **新增类 `TestSeasonalCaptureProperties`**,包含 1 个测试方法 `test_property_20_zero_season_mode_equivalence_and_bounds`,使用 fixture `zero_season_mode`
    3. **方法 docstring 首行**:`Feature: seasonal-capture-rate-correction, Property 20: Zero_Season_Mode 等价性 + 边界`(Req 7.5,与现有 19 条 PBT 风格一致)
    4. **Hypothesis 策略**(Req 7.4):`compression ∈ [0.05, 1.0]`、`year ∈ [2024, 2050]`、`bess_ratio ∈ [0.0, 2.0]`、`fleet_size ∈ [0, 50]`、`region = sampled_from(["NSW1", "QLD1", "VIC1", "SA1"])`、`month ∈ [1, 12]`,全部排除 NaN/Inf
    5. **`@settings(max_examples=100)`**(Req 7.4)
    6. **两条断言**(同一测试方法内,Req 7.2 + 7.3):
       - (a) 等价性:`abs(rate_with - rate_without) <= 1e-9`
       - (b) 边界:`0.10 <= rate_with <= 0.55` 且 `0.10 <= rate_without <= 0.55`
  - **不**修改、删除任何现有 19 条 PBT 与 10 个测试类(Req 7.1)
  - **不**新增 Property C(月份周期性)— design.md "Property C 设计决策" 已论证:`_classify_season(13)` 抛 ValueError 而 `_classify_season(1)` 返回 "summer",二者不等价,纳入会与 Req 1.5 / 2.6 严格区间契约冲突
  - 注:Req 7 把 Property 20 列为强制要求,因此本任务**不带 `*` 标记**(与 `qld-rvf-correction` 任务 5 同理)
  - 验证:`pytest tests/test_forward_model_properties.py -v` 输出 20 passed / 0 failed / 0 errors(Req 7.6 / 9.2)
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 9.2_

- [x] 8. 修复后回测 + 清理 + 收尾(填表 + 删除临时脚本 + 同步 changelog)
  - **Step 1 — 修复后回测**:执行 `python scripts/run_full_backtest.py`,这次会同时跑 19 + 1 = 20 条 PBT + 16 数据点回测 + B-H 章节
  - **Step 2 — 填回测对比表**:把 16 数据点的 dev% 与全局 MAPE/`|Bias|`/Hit Rate 填入 `design.md` "Data Models / 修复前 → 修复后回测对比表" 的"修复后 dev%"列与"Δpp(后-前)"列;把"全局指标对比"表的"修复后(目标)"列填入实际值
  - **Step 3 — 达标判据**(Req 6 / Req 9 全部,任一不满足直接 FAIL → 撤回任务 4 字典写回与任务 5/6 改动并回到任务 2 重选):
    1. 16 数据点中至少 15 个 `|dev| ≤ 30`(QLD1 2025_H1_calendar 单点放宽 ≤35,Req 6.1, 6.2)
    2. 全局 MAPE ≤ 30(Req 6.3)
    3. 全局 `|Bias|` ≤ 15(Req 6.4)
    4. 全局 Hit Rate ≥ 75%(Req 6.5)
    5. Backtest_Window 有效数据点数量 = 16(Req 6.7, 6.8)
    6. 19 + 1 = 20 条 PBT 全过(Req 7.6 / 9.2)
    7. `run_full_backtest.py` 33/33 通过、退出码 0、不抛未捕获异常(Req 9.3, 9.4)
    8. `data/capacity_data.json` SHA-256 与本 spec 启动前一致(Req 8.3,可用 `git diff data/capacity_data.json` 验证为空)
    9. `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 浮点值与 1.35 绝对差 ≤ 1e-9(Req 8.1)
  - **Step 4 — 清理临时产物**:
    - `git rm scripts/calibrate_seasonal_multiplier.py`(Req 8.5 边界,沿用 qld-rvf-correction / summer-compression-correction 一次性脚本不进主分支惯例)
    - 清理校准脚本运行期间产生的中间产物:`scripts/calibrate_seasonal_multiplier.log` 与任何临时 CSV/JSON
    - 验证:`git status` 工作树干净,`scripts/` 目录无 `calibrate_seasonal_multiplier.*` 文件
  - **Step 5 — 同步 forward-model-accuracy-upgrade changelog**:在 `.kiro/specs/forward-model-accuracy-upgrade/tasks.md` 的 `## Post-Implementation Changelog` 段下方追加一段(沿用 qld-rvf-correction 与 summer-compression-correction 段落格式):
    ```
    ### YYYY-MM-DD — seasonal-capture-rate-correction 完成
    seasonal-capture-rate-correction 完成,新增 SEASONAL_CAPTURE_MULTIPLIER 字典 +
    _classify_season / _lookup_seasonal_multiplier / _validate_seasonal_multiplier_table /
    _compute_zero_season_mode_flag 4 个私有函数 + 1 条 PBT(Property 20)。
    QLD summer +104.4% → <填实际值>%,QLD H1 -33.9% → <填实际值>%。
    全局 MAPE <fill>、|Bias| <fill>、Hit Rate <fill>%,通过率 33/33。
    详见 .kiro/specs/seasonal-capture-rate-correction/。
    ```
    YYYY-MM-DD 替换为本任务执行当日 ISO 8601 日期
  - **Step 6 — 同步 spec 任务状态**:把本 `tasks.md` 全部 8 个任务的 `[ ]` 改为 `[x]`(沿用 qld-rvf-correction 收尾惯例)
  - **Step 7 — Checkpoint**:Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 6.1-6.8, 7.6, 8.1, 8.3, 8.5, 9.2, 9.3, 9.4_

## Notes

- 本 spec 是**单乘子追加 + 字典查表**的 **fast-task** 性质改动,不改架构、不动 RVF / `capacity_data.json` / capacity 函数 / 公开符号集合;改动严格限定在 `forward_price_engine.py`(`_compute_capture_rate` + `validate_against_benchmarks` 周边 + 模块顶部新增 Seasonal_Capture_Module 区段)与 `tests/test_forward_model_properties.py`(末尾追加 1 类 1 用例)两个文件。

- **任务 3 与任务 4 的拆分理由(避免循环依赖)**:任务 2 的校准脚本需要 `forward_price_engine.SEASONAL_CAPTURE_MULTIPLIER` 字典存在(才能 monkeypatch),但脚本内的网格搜索结果决定字典的真值。如果一步到位"加字典 + 写真值",就会循环依赖(脚本依赖字典存在,字典内容依赖脚本结果)。拆分后:**任务 3 写 Zero_Season_Mode 占位字典**(全 1.0,产品行为 ≡ Pre_Spec,既满足 eager validation 又让任务 2 脚本可正常 monkeypatch),**任务 4 把任务 2 搜索结果写回字典**(此时主链路尚未应用季节乘子 — 因为任务 5/6 还没改,所以任务 4 写回字典后回测指标**仍**与任务 1 baseline 等价,这是**预期行为**而非异常)。

- **任务 8 是质量门**:任一指标不达标(MAPE/|Bias|/Hit Rate/Hit 数/PBT/SHA-256/RVF 一致性)直接 FAIL,必须撤回任务 4 的字典写回与任务 5/6 的改动,回到任务 2 重新调整候选空间或合格判据。**严禁**带着 |Bias| > 15 或 Hit Rate < 75 或 Backtest_Window ≠ 16 的版本提交主分支。

- **任务 7(PBT)未带 `*` 标记**,因为 Req 7 把 Property 20 列为强制要求,与项目既有 19 条 PBT 同等地位,不属于"可选 MVP 跳过"范围。

- **临时脚本生命周期(任务 8 强制清理)**:`scripts/calibrate_seasonal_multiplier.py` 与运行产生的任何中间 CSV / JSON / log 文件,在任务 8 必须 `git rm` 删除,沿用 qld-rvf-correction / summer-compression-correction 一次性脚本不进主分支的项目惯例。

- **预计总耗时 4–6 小时**:任务 1/4/8 各 ~0.5h(主要是等回测脚本跑完 + 填表),任务 2 ~2h(写脚本 + 网格搜索 ~289 次回测调用),任务 3/5/6 各 ~0.5h(机械改造 + docstring + 验证),任务 7 ~0.5h(照抄 design.md fixture + 1 条 PBT)。串行总计 ~4h 编码 + ~1.5h 等回测。

- **shoulder 时段不被直接修正**(代表月 3 月 / 9 月落在 shoulder,乘子固定 1.0,Req 10.6),H1 与 H2 时段的 dev% 改善只能通过"summer/winter 乘子调整后,反向网格搜索让其他时段微调以保持 |Bias| 最小"间接得到。这是设计阶段已论证的工程妥协(详见 design.md "Data Models / shoulder 时段不被直接修正的影响"),tasks 阶段网格搜索会同时观察 16 时段的 Δpp 而非只盯 summer。

- **变体路径 C 对 `MODO_CAPTURE_RATE = 0.65` 的处理**:模块级常量本身保留(Req 8.6),仅在 `validate_against_benchmarks` 内部把局部 `REVENUE_FACTOR` 重命名为 `MODO_REVENUE_FACTOR`(语义化为"Modo 0.65 capture 假设的收入因子")。`model_revenue` 公式从 `mean_spread × MODO_REVENUE_FACTOR` 扩展为 `mean_spread × MODO_REVENUE_FACTOR × seasonal_multiplier`,Zero_Season_Mode 下数值 ≡ Pre_Spec(Task 1 锁定的 33/33 baseline)。同时新增 `dynamic_capture_rate` 诊断列(由 `_compute_capture_rate(region, month)` 计算,仅作业务视角参考,不参与 model_revenue);`seasonal_multiplier` / `representative_month` 也作为 results 字段输出。详见 design.md *Architecture / 集成点路径决策* 区段。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["3"] },
    { "id": 2, "tasks": ["2", "7"] },
    { "id": 3, "tasks": ["4"] },
    { "id": 4, "tasks": ["5", "6"] },
    { "id": 5, "tasks": ["8"] }
  ]
}
```
