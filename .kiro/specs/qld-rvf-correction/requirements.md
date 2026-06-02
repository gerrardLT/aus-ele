# Requirements Document

## Introduction

本 spec 用于校正 Forward_Price_Engine 中 QLD1 的 Regional_Volatility_Factor(以下简称 QLD_RVF)取值。当前 QLD_RVF=0.55 与外部市场证据严重相悖:Modo Energy 多份月度报告反复指出 QLD 是 NEM 套利机会最丰富的州(2025-01 QLD 单月 BESS 收益约 277k AUD/MW、NEM 平均仅 105k AUD/MW;Q3 2025 QLD 主要靠 Lower Contingency FCAS 撑住),配套学术文献给出 QLD 现货价格标准差约 200(NSW 约 163)。在这种波动结构下,QLD_RVF 不可能低于 NSW_RVF=1.20。

回测基线(修复前)进一步印证此偏差:QLD1 三个时段 2024_full、2025_H1_calendar、2025_H2_calendar 的偏差分别为 -39.2%、-63.1%、-42.0%,系统性低估;同时 NSW/VIC/SA 全部时段保持在 ±30% 以内,全局 MAPE 20.61、Hit Rate 81.2% 已达标,仅 Bias 16.27 略高于 ≤15 的目标。

本次修复严格限定为单一常量值修改:仅通过网格搜索校准 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 一个值,不触碰 SATURATION_SENSITIVITY、COMPRESSION_STEEPNESS、PSF_WEIGHT、PSF_*、BASE_CAPTURE_RATE 等其他任何常量,并通过完整回测和属性测试验证不引入回归。

## Glossary

- **Forward_Price_Engine**: 位于 `backend/engines/forward_price_engine.py` 的远期价格预测引擎模块。
- **QLD_RVF**: `Forward_Price_Engine` 中常量 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 的取值,用于刻画 QLD1 相对 NEM 平均的价格波动强度。
- **Calibration_Script**: 临时校准脚本 `scripts/calibrate_qld_rvf.py`,用于网格搜索 QLD_RVF 候选值并产出验证摘要,任务完成后由开发者删除。
- **Backtest_Runner**: 完整回测脚本 `scripts/run_full_backtest.py`,产出 QLD1/NSW1/VIC1/SA1 各时段偏差、全局 MAPE/Bias/Hit_Rate 与属性测试结果。
- **Time_Window_Set**: QLD1 三个目标校验时段的集合 `{2024_full, 2025_H1_calendar, 2025_H2_calendar}`(2025_26_summer 已通过,作为参考)。
- **Bias_Tolerance**: QLD1 单时段偏差合格阈值,绝对值 ≤30%(2024_full 与 2025_H2_calendar);**特例**:`2025_H1_calendar` 阈值放宽为 ≤35%,因 2025-06 NEM 单月 $403k 极端事件污染 H1 算术均值,规则模型不可能学习。
- **Regression_Tolerance**: NSW1/VIC1/SA1 任一时段单点偏差变动阈值,绝对值 ≤3 个百分点(pp)。
- **Property_Test_Suite**: 现有 17 个 Hypothesis 属性测试构成的测试集合,本次修复后必须全部继续通过。

## Requirements

### Requirement 1: QLD_RVF 校准取值与外部证据一致

**User Story:** 作为远期模型维护者,我想让 QLD_RVF 取值反映 QLD 实际高于 NSW 的价格波动结构,以便回测偏差不再系统性低估 QLD1。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 将 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 设为通过 Calibration_Script 校准得到的取值,且该取值大于 `REGIONAL_VOLATILITY_FACTOR["NSW1"]`(即 >1.20)。
2. THE Forward_Price_Engine SHALL 仅修改 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 这一项常量,SATURATION_SENSITIVITY、COMPRESSION_STEEPNESS、PSF_WEIGHT、PSF_* 系列与 BASE_CAPTURE_RATE 的取值保持与修复前完全一致。
3. THE Forward_Price_Engine SHALL 在 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` 上方保留一段"解决记录"中文注释,内容包含修复日期、Modo Energy 数据来源摘要(月度套利收益对比、Q3 2025 FCAS 占比、价格标准差对比)以及最终选定的 QLD_RVF 值。

### Requirement 2: 网格搜索校准与候选筛选

**User Story:** 作为模型校准负责人,我想用可复现的网格搜索从候选集中挑出最优 QLD_RVF,以便取值有据可查而非拍脑袋。

#### Acceptance Criteria

1. THE Calibration_Script SHALL 以候选集 `[0.95, 1.05, 1.15, 1.25, 1.35]` 进行网格搜索;IF 该集合内无任何候选满足下列合格条件,THEN THE Calibration_Script SHALL 将候选集扩展至 `[0.95, 1.05, 1.15, 1.25, 1.35, 1.45, 1.55]` 并重新评估。
2. THE Calibration_Script SHALL 将一个候选 QLD_RVF 判定为合格当且仅当同时满足:
   - QLD1 在 `2024_full` 与 `2025_H2_calendar` 两时段 |dev| ≤ 30(强约束)
   - QLD1 在 `2025_H1_calendar` 时段 |dev| ≤ 35(放宽阈值,因为 2025-06 NEM 单月 $403k 极端价格事件把 H1 算术均值拉到 $165k,该基准被一次性事件污染,规则模型不可能学习)
   - 相对修复前基线,NSW1/VIC1/SA1 任一时段单点偏差变动 |Δpp| ≤ 3
   - 全局 Bias 绝对值 ≤ 15 且全局 Hit_Rate ≥ 75%
3. WHERE 多个候选同时合格,THE Calibration_Script SHALL 选择全局 Bias 绝对值最低的候选作为最终 QLD_RVF。
4. WHEN 校准任务完成,THE 开发者 SHALL 从仓库删除 `scripts/calibrate_qld_rvf.py`,不向主分支保留临时脚本。

### Requirement 3: 回测验证与摘要归档

**User Story:** 作为评审人,我想看到修复前后基于同一回测脚本的对比数据,以便确认偏差收敛且未引入回归。

#### Acceptance Criteria

1. THE 开发者 SHALL 在 QLD_RVF 修改前后各执行一次 Backtest_Runner(`python scripts/run_full_backtest.py`),并在本 spec 的 design 文档中以表格形式记录两次运行的 QLD1/NSW1/VIC1/SA1 各时段偏差、全局 MAPE、全局 Bias、全局 Hit_Rate 与属性测试通过数。
2. WHEN 修复后的 Backtest_Runner 运行完成,THE 修复结果 SHALL 同时满足:
   - QLD1 在 `2024_full` 与 `2025_H2_calendar` 两时段 |dev| ≤ 30%
   - QLD1 在 `2025_H1_calendar` 时段 |dev| ≤ 35%(放宽阈值,见 Req 2.2)
   - NSW1/VIC1/SA1 所有时段相对基线偏差变动 ≤±3pp
   - 全局 Bias 绝对值 ≤ 15
   - 全局 Hit_Rate ≥ 75%
3. IF 修复后任一上述指标未达标,THEN THE 开发者 SHALL 撤回常量改动并重新进入网格搜索,不得提交未达标的 QLD_RVF。

### Requirement 4: 属性测试覆盖 RVF 单调性与 compression 边界

**User Story:** 作为 QA,我想在属性测试层固化 RVF 与 compression 的关系,以便后续任何对 RVF 的改动都能立即被测试发现。

#### Acceptance Criteria

1. THE Property_Test_Suite SHALL 新增一条 Hypothesis 属性测试,验证当其他输入保持一致时,任意两组 RVF 取值满足 `RVF_a < RVF_b` 的情况下,Forward_Price_Engine 计算出的 compression 满足 `compression(RVF_a) ≤ compression(RVF_b)`。
2. THE Property_Test_Suite SHALL 新增一条 Hypothesis 属性测试,验证 Forward_Price_Engine 输出的 compression 取值始终落在区间 `(0, 1]` 内。
3. WHEN 修复后的回测执行属性测试,THE Property_Test_Suite SHALL 在原有 17 条用例基础上扩展至包含上述两条新增用例,且所有用例全部通过。

### Requirement 5: 向后兼容与外部接口稳定

**User Story:** 作为下游调用方,我想 QLD_RVF 修改不影响任何已有 API 与调用契约,以便不需要同步改动其他模块或前端。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 保持 `REGIONAL_VOLATILITY_FACTOR` 的字典结构、键名 `QLD1/NSW1/VIC1/SA1` 与值类型(`float`)不变,仅 `QLD1` 对应数值发生变化。
2. THE Forward_Price_Engine SHALL 保持所有公开函数签名、返回结构和异常类型与修复前一致,不新增、不重命名、不删除任何公开符号。
3. WHEN 任务全部完成,THE 开发者 SHALL 同步更新本 spec 的 tasks 文档,将相关任务条目状态标记为完成,并清理本次修复期间产生的所有临时脚本与中间产物。
