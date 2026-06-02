# Requirements Document

## Introduction

本规约定义 Forward_Price_Engine 的 summer 时段单点修复方案。在 qld-rvf-correction(QLD_RVF=1.35)落地后,QLD1 的 2024_full、2025_H1、2025_H2 三个时段全部进入 ±35% 合格带,但 2025_26_summer 时段从 -3.6% 反弹到 +148.2%(模型 $84,387 vs 基准 $34,000),成为剩余的 1 个未达标数据点。Modo Energy《2025-26 Summer Review》披露 NEM-wide BESS 收益同比下跌 38% 至 $73k/MW/yr(为 October–March 窗口史上最弱),其中 QLD 同比下跌 73%,主因 BESS 渗透率达饱和阈值后压缩效应非线性放大。

修复策略为在 `_compute_capture_rate` 末尾追加 1 个新乘数 `_high_penetration_decay(bess_capacity_ratio)`:当 BESS 渗透率超过激活阈值时按 Decay_Rate 速率额外压低 capture,渗透率越高、压低越多,从而把"BESS 大量入市的极端压缩窗口"模拟出来。函数普适所有区域,通过临时网格搜索脚本扫描 `(threshold, decay_rate)` 二维参数空间确定最优组合,跑完即从仓库删除。

合格目标承认 summer 是特殊压缩窗口,把 QLD summer 偏差从 +148.2% 收敛到 ≤±50%;其他 15 个数据点相对 qld-rvf-correction 修完后的基线变动不超过 ±5pp;全局回测维持 33/33 通过、|Bias|≤15%、Hit_Rate≥75%;现有 19 条 Hypothesis 属性测试全部通过,并新增 1 条 `_high_penetration_decay` 单调性属性。

## Glossary

- **Forward_Price_Engine**: `backend/engines/forward_price_engine.py` 中的 `ForwardPriceEngine` 类,本次修复涉及的唯一被改动后端引擎。
- **High_Penetration_Decay**: 新增的私有方法 `_high_penetration_decay(bess_capacity_ratio: float) -> float`,作为乘数衔接到 `_compute_capture_rate` 公式末尾,刻画 BESS 渗透率超阈值后对 capture rate 的额外压制。
- **BESS_Capacity_Ratio**: `_compute_capture_rate` 已有入参,表示当前年份某区域 BESS 装机占可压缩负荷的比例,取值范围 `[0.0, 1.0]`,数值越大代表渗透率越高。
- **Activation_Threshold**: 新增模块级常量(取值候选集 `[0.10, 0.15, 0.20]`),BESS_Capacity_Ratio 低于此阈值时 High_Penetration_Decay 返回 `1.0`(不产生影响)。
- **Decay_Rate**: 新增模块级常量(取值候选集 `[0.5, 0.7, 1.0, 1.5]`),控制 BESS_Capacity_Ratio 超过 Activation_Threshold 后衰减因子下降的速率,数值越大则同等渗透率下衰减越激烈。
- **Capture_Rate**: `_compute_capture_rate` 的输出,已有公式 `BASE_CAPTURE_RATE * compression^0.5 * autobidder_decay(year) * fleet_size_factor(fleet)`,clamp 到 `[0.10, 0.55]`,且 `bess_ratio > 0.30` 时进一步限制 `≤ 0.40`。本次在该公式末尾追加 High_Penetration_Decay 乘子。
- **Summer_Window**: 回测时段标识 `2025_26_summer`,覆盖 October 2025 – March 2026,Modo 数据中 BESS 套利压缩最为剧烈的"压缩极端"窗口。
- **Baseline_Backtest**: qld-rvf-correction 落地后的回测结果(`reports/backtest_report.txt`),作为本次修复的对比基线,16 个 (region, window) 数据点 dev 值见 qld-rvf-correction design.md "修复前基线"表的"修复后 dev%"列。
- **Calibration_Script**: 临时脚本 `scripts/calibrate_high_penetration_decay.py`,任务完成后从仓库删除(`git rm`),不进入主分支。
- **Property_Test_Suite**: `tests/test_forward_model_properties.py`,qld-rvf-correction 完成后规模为 19 条;本次扩展至 20 条。
- **Bias**: 全局回测指标,16 个数据点 dev% 的算术平均的绝对值,合格阈值 `|Bias| ≤ 15`。
- **Hit_Rate**: 全局回测指标,`|dev| ≤ 30%` 的数据点占比,合格阈值 `≥ 75%`。

## Requirements

### Requirement 1: High_Penetration_Decay 函数定义与单调有界

**User Story:** 作为 Forward_Price_Engine 的维护者,我希望新增 `_high_penetration_decay` 函数提供一个数学上单调、有界的衰减因子,以便建模 BESS 渗透率超阈值后的非线性压缩。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 在 `forward_price_engine.py` 中新增私有方法 `_high_penetration_decay(bess_capacity_ratio: float) -> float`,其行为完全由模块级常量 Activation_Threshold 与 Decay_Rate 决定。
2. WHEN BESS_Capacity_Ratio 小于等于 Activation_Threshold,THE Forward_Price_Engine SHALL 使 `_high_penetration_decay` 返回 `1.0`,确保低渗透率区域不被影响。
3. WHEN BESS_Capacity_Ratio 大于 Activation_Threshold,THE Forward_Price_Engine SHALL 使 `_high_penetration_decay` 返回值随 BESS_Capacity_Ratio 单调不增,且在浮点容差 `1e-9` 范围内严格小于 `1.0`。
4. THE Forward_Price_Engine SHALL 使 `_high_penetration_decay` 的输出落在闭区间 `[0.3, 1.0]` 内,下界 `0.3` 用于防止极端渗透率下衰减失控。
5. IF Activation_Threshold 或 Decay_Rate 在 `forward_price_engine.py` 模块加载时不可解析为正数,THEN THE Forward_Price_Engine SHALL 使该模块导入失败并抛出 `ValueError`,避免使用未校准参数静默运行。

### Requirement 2: 把 High_Penetration_Decay 集成到 _compute_capture_rate

**User Story:** 作为 Forward_Price_Engine 的维护者,我希望把 `_high_penetration_decay` 作为乘数衔接到 `_compute_capture_rate` 末尾,以便在不重构既有公式的前提下把渗透率敏感度纳入 capture rate 计算。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 在 `_compute_capture_rate` 中,把 `_high_penetration_decay(bess_capacity_ratio)` 作为最末一个乘子追加到现有公式 `BASE_CAPTURE_RATE * compression^0.5 * autobidder_decay(year) * fleet_size_factor(fleet)` 之后。
2. THE Forward_Price_Engine SHALL 保留 `_compute_capture_rate` 现有的 `clamp` 到 `[0.10, 0.55]` 与 `bess_capacity_ratio > 0.30` 时进一步限制 `≤ 0.40` 的两条约束,新乘子在 clamp 之前应用。
3. THE Forward_Price_Engine SHALL 保持 `BASE_CAPTURE_RATE`、`SATURATION_SENSITIVITY`、`COMPRESSION_STEEPNESS`、`PSF_WEIGHT`、`PSF_*` 系列常量与 `REGIONAL_VOLATILITY_FACTOR` 字典(包含 `QLD1: 1.35`)的取值与原值完全一致。
4. THE Forward_Price_Engine SHALL 保持 `_compute_capture_rate` 的函数签名、`validate_against_benchmarks()` 与 `predict_*` 系列方法的入参与返回结构与现有版本完全一致,以保证 API 契约向后兼容。
5. WHERE 调用方传入的 `bess_capacity_ratio` 等于 `0.0`,THE Forward_Price_Engine SHALL 使 `_compute_capture_rate` 的输出与未追加新乘子前的版本相对偏差小于 `1e-9`,以保证零渗透率场景行为不变。

### Requirement 3: 网格搜索校准与合格判据

**User Story:** 作为 Forward_Price_Engine 的维护者,我希望通过临时网格搜索脚本扫描 `(Activation_Threshold, Decay_Rate)` 二维参数空间确定最优组合,以便校准过程完全可复现且不污染主分支历史。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 通过新增临时脚本 `scripts/calibrate_high_penetration_decay.py` 扫描 Activation_Threshold ∈ `[0.10, 0.15, 0.20]` 与 Decay_Rate ∈ `[0.5, 0.7, 1.0, 1.5]` 共 12 组候选,每组运行 `engine.validate_against_benchmarks()` 并聚合 16 个 (region, window) 数据点。
2. WHEN 网格搜索完成,THE Forward_Price_Engine SHALL 在 Calibration_Script 标准输出中生成包含每组候选的 QLD summer dev%、其他 15 个数据点相对 Baseline_Backtest 的最大 ±pp 变动、全局 Bias、Hit_Rate 与合格标记的评估表。
3. THE Forward_Price_Engine SHALL 把"合格组合"定义为同时满足以下四条:QLD summer `|dev| ≤ 50%`,其他 15 个数据点相对 Baseline_Backtest 任一时段 `|Δpp| ≤ 5pp`,全局 `|Bias| ≤ 15`,全局 `Hit_Rate ≥ 75%`。
4. WHEN 12 组候选中存在合格组合,THE Forward_Price_Engine SHALL 在合格组合中按全局 `|Bias|` 升序选出最优组合,并将选定的 Activation_Threshold 与 Decay_Rate 写回 `forward_price_engine.py` 模块级常量。
5. IF 12 组候选中无合格组合,THEN THE Forward_Price_Engine SHALL 把候选集扩展为 Activation_Threshold ∈ `[0.10, 0.15, 0.20, 0.25]` 与 Decay_Rate ∈ `[0.3, 0.5, 0.7, 1.0, 1.5, 2.0]` 共 24 组重新评估,并在评估表中明确标注扩展原因。
6. WHEN 最优组合写回常量并通过修复后回测,THE Forward_Price_Engine SHALL 使开发者从仓库删除 `scripts/calibrate_high_penetration_decay.py` 与所有由该脚本产生的中间文件,且不在主分支留下脚本痕迹。

### Requirement 4: 修复后回测验证目标

**User Story:** 作为 Forward_Price_Engine 的维护者,我希望通过修复后回测验证 summer 偏差收敛、其他时段不恶化、全局指标维持达标,以便确认修复方案不引入新的回归风险。

#### Acceptance Criteria

1. WHEN 校准后的 Activation_Threshold 与 Decay_Rate 写回 `forward_price_engine.py` 后,THE Forward_Price_Engine SHALL 使 `python scripts/run_full_backtest.py` 报告 QLD1 在 Summer_Window 的 `|dev|` 收敛到 `≤ 50%`(基线 +148.2% → 修复后落入 ±50% 带)。
2. WHEN 修复后回测完成,THE Forward_Price_Engine SHALL 使 NSW1、VIC1、SA1 各自在 `2024_full`、`2025_H1_calendar`、`2025_H2_calendar`、`2025_26_summer` 共 12 个时段的 dev%,以及 QLD1 在 `2024_full`、`2025_H1_calendar`、`2025_H2_calendar` 共 3 个时段的 dev%,相对 Baseline_Backtest 同时段 dev% 的差值绝对值 `|Δpp| ≤ 5pp`。
3. WHEN 修复后回测完成,THE Forward_Price_Engine SHALL 使全局 `|Bias| ≤ 15`、`Hit_Rate ≥ 75%`、`MAPE ≤ 30`,与 Baseline_Backtest 全部达标项保持一致。
4. WHEN 修复后回测完成,THE Forward_Price_Engine SHALL 使 `scripts/run_full_backtest.py` 末尾的"通过 / 失败"统计维持 `33 / 0`,通过率 `100%`。
5. IF 修复后回测任一项不达标,THEN THE Forward_Price_Engine SHALL 使开发者撤回 Activation_Threshold 与 Decay_Rate 的常量改动,回到 Baseline_Backtest 状态,并在 `tasks.md` 标注失败原因。

### Requirement 5: 新增单调性属性测试并维持原 19 条 PBT 通过

**User Story:** 作为 Forward_Price_Engine 的维护者,我希望新增 1 条 Hypothesis 属性测试覆盖 `_high_penetration_decay` 单调性,并维持现有 19 条属性测试全部通过,以便代数行为受机器验证保护。

#### Acceptance Criteria

1. THE Forward_Price_Engine SHALL 在 `tests/test_forward_model_properties.py` 末尾新增类 `TestHighPenetrationDecayProperties`,包含至少 1 条标注 `Feature: summer-compression-correction, Property: High penetration decay monotonicity` 的 Hypothesis 属性测试,使 Property_Test_Suite 规模从 `19` 扩展到 `20`。
2. THE Forward_Price_Engine SHALL 使新增属性测试以 `bess_capacity_ratio_a`、`bess_capacity_ratio_b` 为输入(Hypothesis 策略 `floats(min_value=0.0, max_value=1.0)`),断言当 `bess_capacity_ratio_a ≤ bess_capacity_ratio_b` 时 `_high_penetration_decay(a) >= _high_penetration_decay(b) - 1e-9` 成立(单调不增)。
3. THE Forward_Price_Engine SHALL 使新增属性测试同时断言 `_high_penetration_decay(bess_capacity_ratio)` 落在闭区间 `[0.3, 1.0]` 内,与 Requirement 1.4 的边界约束一一对应。
4. THE Forward_Price_Engine SHALL 使新增属性测试每条至少运行 100 次 Hypothesis 迭代(`@settings(max_examples=100)`),与文件中现有属性测试的强度保持一致。
5. WHEN 修复完成后运行 `pytest tests/test_forward_model_properties.py`,THE Forward_Price_Engine SHALL 使 Property_Test_Suite 全部 `20` 条用例通过,无 Hypothesis shrink 失败例,无 deprecation warning 触发硬失败。
