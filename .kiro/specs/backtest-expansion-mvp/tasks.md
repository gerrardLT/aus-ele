# Implementation Plan: Backtest Expansion MVP

## Overview

将 Forward Price Engine 的回测框架从 16 个 Modo Energy 基准时段扩展到 96+ 个月度数据点，数据源为本地 `data/aemo_data.db`（247 万行 AEMO 5 分钟级实测数据）。实现语言为 **Python**（与既有 `backend/engines/forward_price_engine.py`、`tests/test_forward_model_properties.py` 一致）。

核心交付物：

- **新增模块** `backend/engines/backtest_expansion.py`，封装 `MonthlyBenchmarkCalculator`、`CaptureRateCalculator`、`validate_against_monthly_benchmarks_impl`、`run_monthly_reconciliation` 及四个 `@dataclass` 数据模型。
- **薄委托方法** `ForwardPriceEngine.validate_against_monthly_benchmarks`（延迟 import，零硬依赖，不触碰受保护成员）。
- **APScheduler cron job**（每月 1 日，env-gated）接入 `backend/app.py`。
- **回测脚本扩展** `scripts/run_full_backtest.py` 新增 "I. 月度 AEMO 基准验证" section。
- **测试** `tests/test_backtest_expansion_properties.py`（12 条 Hypothesis 属性测试，对应 design 的 12 条 Correctness Properties）+ 单元 / 集成 / 非回归测试。

设计原则为"零侵入既有引擎、补充而非替换、优雅降级"。所有改动严格保证既有 33/33 回测与 20 条 PBT 不回归（Req 8）。

> 实现指令：Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Make sure that each prompt builds on the previous prompts, and ends with wiring things together. There should be no hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on tasks that involve writing, modifying, or testing code.

## Tasks

- [x] 1. 创建模块骨架与数据模型
  - [x] 1.1 创建 `backend/engines/backtest_expansion.py` 并定义四个 dataclass
    - 新建模块文件，写入模块 docstring、`logging` logger、`from __future__ import annotations`
    - 定义 `@dataclass(frozen=True) MonthlyBenchmark`（region, year_month, mean_spread_aud_mwh, sample_days, data_quality_flag）
    - 定义 `@dataclass(frozen=True) CaptureRateResult`（region, year_month, monthly_actual_revenue, perfect_foresight_capture_rate, capped, sample_days）
    - 定义 `@dataclass(frozen=True) CaptureRateComparison`（region, year_month, model_capture_rate, perfect_foresight_capture_rate, efficiency_ratio, violation, low_efficiency_warning）
    - 定义 `@dataclass(frozen=True) MonthlyValidationResult`（region, year_month, model_mean_spread, benchmark_mean_spread, deviation_pct）
    - _Requirements: 1.6, 2.5, 8.5_

  - [x]* 1.2 编写 dataclass schema 与模块存在性单元测试
    - 断言四个 dataclass 字段齐全且类型正确，`backtest_expansion.py` 模块可被 import
    - _Requirements: 1.6, 2.5, 8.5_

- [x] 2. 实现 MonthlyBenchmarkCalculator (Req 1, 9)
  - [x] 2.1 实现 `compute_monthly_benchmark` 核心聚合逻辑
    - 定义类常量 `NEM_REGIONS`（五区域，排除 WEM）、`MIN_INTERVALS_PER_DAY=200`、`MIN_VALID_DAYS=20`、`QUERY_TIMEOUT_SECONDS=30`、`START_MONTH="2024-01"`
    - 解析 `year_month` 选择 `trading_price_{year}` 表，使用 **`region_id`** 列（非 `region`）执行 daily spread SQL：`MAX(rrp_aud_mwh)-MIN(rrp_aud_mwh)` 按 `DATE(settlement_date)` 分组并计 `COUNT(*)`
    - `mean_spread_aud_mwh = mean(spread for valid_days)`，`valid_days = [d for d in days if intervals >= 200]`
    - `sample_days < 20` 时设 `data_quality_flag="insufficient_data"`，否则 `"ok"`
    - 负电价直接进入 MIN/MAX，不过滤不截断
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 9.4_

  - [x] 2.2 实现 `compute_all_benchmarks` 与 `latest_complete_month`
    - `latest_complete_month` 探测 AEMO_Database 中数据覆盖到月末的最新完整日历月
    - `compute_all_benchmarks` 从 2024-01 连续枚举到 `end_month`（默认最新完整月）× 五区域，逐点调用 `compute_monthly_benchmark`
    - _Requirements: 1.2, 1.4_

  - [x] 2.3 实现优雅降级与 30 秒超时
    - db 文件不可达（`Path.exists()` / 连接异常）→ 返回 `[]`，记 warning，不抛异常
    - `trading_price_{year}` 表缺失 → 跳过该年，记 info
    - region-month 零行 → 排除该点，记 debug
    - 用 `sqlite3.Connection.set_progress_handler` 注册回调，比较 `time.monotonic()-start>30` 触发 `OperationalError`，捕获后记 warning 返回 None 并继续
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [x]* 2.4 编写属性测试：Property 1 月度 mean_spread 聚合正确性
    - **Property 1: 月度 mean_spread 聚合正确性** — 返回的 `mean_spread_aud_mwh` 应等于所有有效日（interval ≥ 200）每日价差 `max(rrp)-min(rrp)` 的算术平均值
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 1`，`@settings(max_examples=100)`
    - **Validates: Requirements 1.1, 1.3**

  - [x]* 2.5 编写属性测试：Property 2 负电价保留不被过滤或截断
    - **Property 2: 负电价保留不被过滤或截断** — 含负价的每日序列价差用真实 min/max 计算，负价不剔除不截断；存在负价时价差严格大于忽略负价时的价差
    - 生成器价格范围 `st.floats(min_value=-1000, max_value=16000)` 显式包含负价区间
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 2`，`@settings(max_examples=100)`
    - **Validates: Requirements 9.4**

  - [x]* 2.6 编写属性测试：Property 3 月份枚举范围连续且区域齐全
    - **Property 3: 月份枚举范围连续且区域齐全** — `compute_all_benchmarks` 枚举的 `(region, year_month)` 从 2024-01 连续覆盖到 `end_month` 无遗漏无越界，每月含全部五区域且不含 WEM
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 3`，`@settings(max_examples=100)`
    - **Validates: Requirements 1.2, 1.4**

  - [x]* 2.7 编写属性测试：Property 4 数据不足月标记与排除
    - **Property 4: 数据不足月标记与排除** — `sample_days < 20` → `data_quality_flag="insufficient_data"` 且不进入对比集合；`sample_days ≥ 20` → flag 为 `"ok"` 且进入对比
    - 生成器有效日计数 `st.integers(0, 31)` 覆盖 19/20 边界
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 4`，`@settings(max_examples=100)`
    - **Validates: Requirements 1.5**

  - [x]* 2.8 编写错误处理边界单元测试
    - 不存在的 db 路径返回 `[]`；缺表年份跳过；空 region-month 排除；注入慢查询触发超时中止并继续
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 3. Checkpoint - 确保 MonthlyBenchmarkCalculator 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 实现 CaptureRateCalculator (Req 3, 4)
  - [x] 4.1 实现 `compute_perfect_foresight` 完美预见日收入与月度封顶
    - 定义类常量 `RTE=0.87`、`BATTERY_HOURS=4`、`VIOLATION_MARGIN=0.05`、`LOW_EFFICIENCY_THRESHOLD=0.40`
    - 5 分钟价格按 `HH=substr(settlement_date,12,2)` 聚合为 24 个小时均价，选 top-4 小时放电、bottom-4 小时充电
    - `daily_revenue = Σ(discharge_price×1MW×1h) - Σ(charge_price×1MW×1h/RTE)`
    - `monthly_actual_revenue = Σ daily_revenue`；`monthly_capture_rate = monthly_actual_revenue / (monthly_mean_spread × days_in_month × 4h × RTE)`
    - `capture_rate > 1.0` → 封顶 1.0 且 `capped=True`
    - 无数据 / 表缺失 / 超时复用 §2.3 的优雅降级，返回 None
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 9.4_

  - [x] 4.2 实现 `compare_with_model` 与 `validate_all`
    - `compare_with_model`：`violation = model > perfect_foresight + 0.05`；非越界时 `efficiency_ratio = model / perfect_foresight`；`efficiency_ratio < 0.40` → `low_efficiency_warning=True` 且 `logger.warning`
    - `validate_all(self, engine, end_month=None)`：遍历五区域 × 2024-01 至 end_month 的全部 region-month（覆盖 Req 3.4 的全区域全月份迭代），逐点调用 `compute_perfect_foresight` 取完美预见值
    - 模型 capture rate 取数来源：调用引擎既有 `_compute_capture_rate`（**只读不改**，Req 8.1）获取 `model_capture_rate`，再以 `compare_with_model` 对比
    - 汇总 `violation_count` 与越界明细列表（Req 4.2）
    - _Requirements: 3.4, 3.6, 4.1, 4.2, 4.3, 4.4_

  - [x]* 4.3 编写属性测试：Property 7 完美预见日收入最优性与公式正确性
    - **Property 7: 完美预见日收入最优性与公式正确性** — 选出的 4 放电小时为最高价、4 充电小时为最低价（任一放电小时价 ≥ 任一未选小时价 ≥ 任一充电小时价），当日收入 = `Σ(top4_price) - Σ(bottom4_price)/RTE`（RTE=0.87）
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 7`，`@settings(max_examples=100)`
    - **Validates: Requirements 3.1, 3.2**

  - [x]* 4.4 编写属性测试：Property 8 monthly_capture_rate 公式正确性
    - **Property 8: monthly_capture_rate 公式正确性** — 封顶前 `monthly_capture_rate = actual / (mean_spread × days × 4 × RTE)`（`mean_spread > 0`）
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 8`，`@settings(max_examples=100)`
    - **Validates: Requirements 3.3**

  - [x]* 4.5 编写属性测试：Property 9 capture_rate 封顶有界与标记
    - **Property 9: capture_rate 封顶有界与标记** — 输出 `≤ 1.0`；原始值 > 1.0 时输出 1.0 且 `capped=True`，否则输出等于原始值且 `capped=False`；封顶操作幂等
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 9`，`@settings(max_examples=100)`
    - **Validates: Requirements 3.5**

  - [x]* 4.6 编写属性测试：Property 10 越界判定与 efficiency_ratio
    - **Property 10: 越界判定与 efficiency_ratio** — `violation` 为真当且仅当 `model > pf + 0.05`；`violation` 为假时 `efficiency_ratio = model / pf`，且 `efficiency_ratio < 0.40` 时 `low_efficiency_warning` 为真
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 10`，`@settings(max_examples=100)`
    - **Validates: Requirements 3.6, 4.1, 4.3, 4.4**

  - [x]* 4.7 编写属性测试：Property 11 violation_count 与明细一致性
    - **Property 11: violation_count 与明细一致性** — 报告的 `violation_count` 等于越界明细列表长度，明细项 `violation` 均为真、非明细项均为假
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 11`，`@settings(max_examples=100)`
    - **Validates: Requirements 4.2**

  - [x]* 4.8 编写告警边界单元测试
    - efficiency_ratio 跨 0.40 阈值时 `low_efficiency_warning` 标志与日志正确触发
    - _Requirements: 4.4_

- [x] 5. Checkpoint - 确保 CaptureRateCalculator 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现月度验证逻辑与引擎委托方法 (Req 2)
  - [x] 6.1 实现 `validate_against_monthly_benchmarks_impl`
    - 在 `backtest_expansion.py` 内实现：用 `MonthlyBenchmarkCalculator.compute_all_benchmarks()` 取基准并过滤 `insufficient_data` 月
    - 对每个有效 region-month 调用引擎既有 `calculate_price_distribution(region, ScenarioType.CENTRAL, year, bess_ratio)` 取 `mean_spread`；`bess_ratio` 由既有 `_get_cumulative_bess_capacity` / `_get_dynamic_peak_demand`（reference_date = 该月月末）计算，与 `validate_against_benchmarks` 同源
    - `deviation_pct = (model_mean_spread - benchmark_mean_spread) / benchmark_mean_spread × 100`
    - 聚合 MAPE、RMSE、Bias、Hit Rate（|deviation| ≤ 30% 占比）
    - 返回与 `validate_against_benchmarks` 兼容的结构（per-point results + summary）
    - 支持 `target_month` 参数：给定时只验证该月（供 reconciliation 复用）
    - 单点 `calculate_price_distribution` 抛错时 try/except 跳过该点继续聚合（Req 9 优雅降级）
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [x] 6.2 在 ForwardPriceEngine 追加薄委托方法 `validate_against_monthly_benchmarks`
    - 在 `backend/engines/forward_price_engine.py` 类尾部**追加**方法，签名 `(self, end_month=None, target_month=None) -> Dict`
    - 方法体内**延迟 import** `from engines.backtest_expansion import validate_against_monthly_benchmarks_impl` 并转交（`engine=self`）
    - **不触碰** `validate_against_benchmarks`、`_compute_capture_rate`、`SEASONAL_CAPTURE_MULTIPLIER`、`REGIONAL_VOLATILITY_FACTOR` 等受保护成员（只读不写）
    - _Requirements: 2.1, 2.6, 8.1, 8.5_

  - [x]* 6.3 编写属性测试：Property 5 deviation_pct 计算公式正确性
    - **Property 5: deviation_pct 计算公式正确性** — `deviation_pct = (model - benchmark) / benchmark × 100`（`benchmark ≠ 0`）；`model > benchmark` 时符号为正、`model < benchmark` 时为负
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 5`，`@settings(max_examples=100)`
    - **Validates: Requirements 2.3**

  - [x]* 6.4 编写属性测试：Property 6 聚合指标数学不变量
    - **Property 6: 聚合指标数学不变量** — `MAPE = mean(|d|) ≥ 0`、`RMSE = sqrt(mean(d²)) ≥ |Bias|`、`Bias = mean(d)`、`Hit Rate ∈ [0,100]` 且等于 `|d| ≤ 30` 元素占比百分比
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 6`，`@settings(max_examples=100)`
    - **Validates: Requirements 2.4**

  - [x]* 6.5 编写引擎委托方法接口单元测试
    - 断言引擎含 `validate_against_monthly_benchmarks` 方法、返回结构含 per-point results 与 summary（MAPE/RMSE/Bias/Hit Rate）字段
    - 断言委托为延迟 import（新模块缺失时引擎其余功能不受影响）
    - _Requirements: 2.1, 2.5, 8.5_

- [x] 7. 实现月度 Reconciliation 入口与归档 (Req 5, 6)
  - [x] 7.1 实现 `run_monthly_reconciliation` 主入口
    - `target_month` 缺省 = 上一个完整日历月
    - 流程：算上月 5 区域基准 → 调 `validate_against_monthly_benchmarks(target_month)` → 逐区域附 capture rate 对比 → 计算 summary（MAPE/max_deviation/violation_count）
    - `|deviation| > 40%` → `alert_triggered=True` 且 `logger.warning`（含 region, month, model, actual, deviation%）
    - 返回写入的 reconciliation 记录（供测试断言）
    - _Requirements: 5.2, 5.3, 5.5, 6.1, 6.3_

  - [x] 7.2 实现 JSON 归档 append 写入
    - 写 `reports/monthly_reconciliation.json`：读取既有数组 → append 新记录 → 写回，保留全部历史记录
    - 文件不存在 → 初始化为空数组 `[]` 再 append
    - JSON 损坏（`JSONDecodeError`）→ 记 warning，以空数组重建（保护性，不丢失新记录）
    - 每条记录顶层含 `run_date`、`target_month`、`results`（per-region 数组）、`summary`；per-region 含 region、model_mean_spread、actual_mean_spread、deviation_pct、capture_rate_comparison、alert_triggered
    - _Requirements: 5.4, 6.1, 6.2, 6.3, 6.4_

  - [x]* 7.3 编写属性测试：Property 12 reconciliation 归档 append 不变量
    - **Property 12: reconciliation 归档 append 不变量** — 写入后数组 = "原数组 + [新记录]"：长度恰好加一、历史记录按原顺序原值保留、新记录追加末尾
    - docstring 首行标注 `Feature: backtest-expansion-mvp, Property 12`，`@settings(max_examples=100)`
    - **Validates: Requirements 5.4, 6.2, 6.4**

  - [x]* 7.4 编写归档格式与告警边界单元测试
    - 断言记录顶层与 per-region 字段完整（Req 6.1, 6.3）；缺失归档文件初始化空数组（Req 6.4）
    - deviation 跨 40% 阈值时 `alert_triggered` 与 `logger.warning` 正确（Req 5.5）
    - _Requirements: 5.5, 6.1, 6.3, 6.4_

- [x] 8. Checkpoint - 确保验证与对账逻辑测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 接线：APScheduler cron job (Req 5)
  - [x] 9.1 在 `backend/app.py` 注册月度 reconciliation cron job
    - 新增 `_reconciliation_enabled()` 复用既有 `_env_flag("AUS_ELE_RECONCILIATION_ENABLED", True)`
    - 在既有 `if _scheduler_enabled():` 块内追加：`rh = _cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3)`，延迟 import `run_monthly_reconciliation`，`scheduler.add_job(..., "cron", day=1, hour=rh, id="monthly-reconciliation", max_instances=1, coalesce=True, misfire_grace_time=3600)`
    - 时区沿用既有 `_scheduler_timezone()`（默认 UTC，对应 Req 5.1 的 03:00 UTC）
    - _Requirements: 5.1, 5.6_

  - [x]* 9.2 编写调度接线集成测试
    - mock `MonthlyBenchmarkCalculator` 与验证方法，断言 cron job 以 `day=1, hour=cfg` 注册、时区 UTC、触发后对上月 5 区域各调一次
    - 断言 `_reconciliation_enabled` / `_cron_hour` 正确读取环境变量（默认 enabled=true, hour=3）
    - _Requirements: 5.1, 5.2, 5.3, 5.6_

- [x] 10. 接线：回测脚本扩展 Section I (Req 7)
  - [x] 10.1 在 `scripts/run_full_backtest.py` 新增 "I. 月度 AEMO 基准验证" section
    - 在 H section 之后、总结之前插入，调用 `engine.validate_against_monthly_benchmarks()`
    - 逐 region-month 打印偏差 + 复用 A section 度量风格计算并报告 MAPE/RMSE/Bias/Hit Rate
    - 报告验证点总数（目标 96+）；用与 A 相同阈值（MAPE ≤ 30, Hit Rate ≥ 75）独立累加 `pass_count`/`fail_count`
    - 注明模型年度粒度限制（同年各月返回同一 mean_spread，度量年度预测 vs 各月实测）
    - 确保对 A–H 既有 pass/fail 计数零影响
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x]* 10.2 编写脚本扩展集成测试
    - 运行 `run_full_backtest.py`，断言报告含 "I. 月度 AEMO 基准验证" 段、含 MAPE/RMSE/Bias/Hit Rate、Section I 用 MAPE ≤ 30 / Hit Rate ≥ 75 阈值累加、且 A–H 的 pass/fail 计数与扩展前一致
    - _Requirements: 7.1, 7.2, 7.4, 7.5_

- [x] 11. 集成测试与非回归验证 (Req 7, 8)
  - [x]* 11.1 编写真实 DB 集成测试
    - 对 `data/aemo_data.db` 跑 `compute_all_benchmarks`，断言有效验证点 ≥ 96；断言单日 interval 计数接近 288
    - _Requirements: 7.3, 1.3_

  - [x]* 11.2 编写非回归验证测试
    - 运行 `run_full_backtest.py` 的 A–H section，断言 33/33 通过且各点数值与扩展前完全一致
    - 运行 `tests/test_forward_model_properties.py`，断言既有 20 条 PBT 无修改通过
    - 通过 git diff / 代码审查确认 `validate_against_benchmarks`、`_compute_capture_rate`、`SEASONAL_CAPTURE_MULTIPLIER`、`REGIONAL_VOLATILITY_FACTOR` 未被改动，`data/capacity_data.json`、`data/financial_evidence.json` 未被新模块写入
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 12. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 任务标记 `*` 为可选（属性测试 / 单元测试 / 集成测试），可跳过以加速 MVP 交付；核心实现任务不带 `*` 必须实现。
- 实现语言为 Python，复用项目既有 Hypothesis（与 `tests/test_forward_model_properties.py` 一致）。
- 12 条属性测试集中在新文件 `tests/test_backtest_expansion_properties.py`，与既有 20 条 PBT 完全隔离（Req 8.4）；每条测试 docstring 首行标注 `Feature: backtest-expansion-mvp, Property {N}` 且 `@settings(max_examples=100)`。
- 纯计算函数（价差聚合、完美预见、聚合指标、封顶、append 写）从 DB I/O 解耦（接收价格 / 数值列表参数），便于无数据库随机测试。
- 检查点确保增量验证；基础设施接线（APScheduler、SQL 分组、脚本渲染）与非回归约束用集成 / 示例测试覆盖。
- 数据源勘误：统一使用 `region_id` 列（非 `region`）。
- 需求覆盖：Req 1（任务 2）、Req 2（任务 6）、Req 3/4（任务 4）、Req 5/6（任务 7、9）、Req 7（任务 10）、Req 8（任务 6.2、11.2）、Req 9（任务 2.3、4.1）。
- 12 条 Correctness Properties 覆盖：P1→2.4、P2→2.5、P3→2.6、P4→2.7、P5→6.3、P6→6.4、P7→4.3、P8→4.4、P9→4.5、P10→4.6、P11→4.7、P12→7.3。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6", "2.7", "2.8", "4.2"] },
    { "id": 4, "tasks": ["4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "7.4", "9.1", "10.1"] },
    { "id": 7, "tasks": ["9.2", "10.2", "11.1", "11.2"] }
  ]
}
```
