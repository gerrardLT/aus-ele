# Implementation Plan: QLD RVF Correction

## Overview

针对 `backend/engines/forward_price_engine.py` 中 `REGIONAL_VOLATILITY_FACTOR["QLD1"]=0.55` 与 Modo Energy 实测证据严重相悖、导致 QLD1 三个时段偏差 -39%/-63%/-42% 的问题,执行一次性单常量校正。流程为 5 步:基线冻结 → 临时网格搜索脚本校准 → 选定 QLD_RVF → 改主常量 → 双重测试验证(完整回测 + 新增 2 条属性测试) → 清理临时产物。预计总耗时 1–2 个工作日。

## Tasks

- [x] 1. 基线冻结 Checkpoint:运行修复前完整回测并填入对比表"修复前"列
  - 执行 `python scripts/run_full_backtest.py`,捕获终端输出与 `reports/backtest_report.txt`
  - 把 16 个数据点(QLD1/NSW1/VIC1/SA1 × 4 个时段)的 dev% 与全局 MAPE/Bias/Hit_Rate/属性测试通过数核对到 `design.md` 对比表"修复前"一列(已预填,确认即可,如有偏差需改写)
  - **关键**:本步必须在任何常量改动之前完成,作为后续 Regression_Tolerance(NSW/VIC/SA 各时段 ≤±3pp)的对照基线
  - 不修改任何源码
  - _Requirements: 3.1_

- [x] 2. 实现临时校准脚本 `scripts/calibrate_qld_rvf.py`
  - 按 `design.md` "Components and Interfaces / 3. scripts/calibrate_qld_rvf.py" 接口草图实现 `evaluate_candidate(rvf_value, baseline) -> CandidateReport`、`main()`、`print_table(reports)` 三个函数
  - 候选集硬编码为 `[0.95, 1.05, 1.15, 1.25, 1.35]`;若全部不合格则扩展为 `[0.95, 1.05, 1.15, 1.25, 1.35, 1.45, 1.55]` 重新评估
  - **Req 1.1 硬约束**:任何候选 RVF ≤ 1.20(NSW1)直接淘汰(`is_eligible=False`),不进入"全局 |Bias| 最小"比较
  - 合格判据(全部 AND):QLD1 三时段 \|dev\| ≤ 30、NSW/VIC/SA 各时段相对 baseline \|Δpp\| ≤ 3、全局 \|Bias\| ≤ 15、全局 Hit_Rate ≥ 75
  - 多候选合格时按 `min(|global_bias|)` 选优(Req 2.3)
  - 通过 monkeypatch 或字典原地替换覆盖 `REGIONAL_VOLATILITY_FACTOR["QLD1"]`,**不**写回源文件
  - 控制台按 `design.md` 给出的"候选评估表"格式输出,明确标注每个候选 ✓ / ✗ 与最终选定 RVF 值
  - _Requirements: 1.1, 2.1, 2.2, 2.3_

- [x] 3. 执行校准、记录候选评估表、选定 QLD_RVF
  - 手工运行 `python scripts/calibrate_qld_rvf.py`,把控制台输出的候选评估表(5 候选或 7 候选)完整保存到本任务的执行日志(可贴入 `tasks.md` 的本任务下方,或临时记到 commit message)
  - 确认脚本自动选出的候选满足:RVF > 1.20 且 \|global_bias\| 在合格候选中最低
  - 若所有候选不合格(脚本会触发扩展集后仍找不到),停下来检查 `design.md` 的"候选选择直觉"段是否需要修订;**严禁**在不合格情况下硬选某个值修改主常量(Req 3.3)
  - 输出:确认的最终 QLD_RVF 数值(用于任务 4)
  - _Requirements: 2.1, 2.2, 2.3, 3.3_

- [x] 4. 修改主常量 `REGIONAL_VOLATILITY_FACTOR["QLD1"]` + 中文解决记录注释
  - 在 `backend/engines/forward_price_engine.py` 第 80–89 行 `REGIONAL_VOLATILITY_FACTOR` 字典上方追加一段中文注释,内容包含:
    - 修复日期:`2026-05-29`
    - Modo Energy 数据来源摘要(2025-01 QLD BESS ~277k AUD/MW、Q3 2025 Lower Contingency FCAS、QLD/NSW 价格标准差 200/163)
    - 修复前回测偏差(-39.2 / -63.1 / -42.0)
    - 网格搜索结论与最终 RVF 值
  - 注释模板严格按 `design.md` "Components and Interfaces / 1. forward_price_engine.py 常量段 / 修改后" 段提供的样式(把 `YYYY-MM-DD` 替换为 `2026-05-29`、`X.XX` 替换为任务 3 选定的实际值)
  - 把字典内 `"QLD1": 0.55, # TODO: 与实际市场数据矛盾,待系统校准` 改为 `"QLD1": <calibrated>,  # 见上方解决记录`
  - **不**修改 `SATURATION_SENSITIVITY`、`COMPRESSION_STEEPNESS`、`PSF_WEIGHT`、`PSF_*`、`BASE_CAPTURE_RATE` 与字典中其他 5 项区域的 RVF 值(Req 1.2)
  - **不**新增/重命名/删除任何公开符号(Req 5.2)
  - _Requirements: 1.1, 1.2, 1.3, 5.1, 5.2_

- [x] 5. 在 `tests/test_forward_model_properties.py` 末尾追加 `TestCompressionFactorProperties`
  - 沿用文件顶部现有 `from hypothesis import given, settings, strategies as st` 与 `from backend.engines.forward_price_engine import ForwardPriceEngine` 导入风格,无需新增 import 行
  - 新增类不动现有 8 个测试类与 17 条用例,仅追加,目标 17 → 19
  - **Property A: Compression monotonicity in RVF**
    - 方法名 `test_property_a_compression_monotone_in_rvf`,docstring 首行 `Feature: qld-rvf-correction, Property A: Compression monotonicity in RVF`
    - Hypothesis 策略与断言体严格按 `design.md` "Correctness Properties / Property 1" 草图实现
    - **Validates: Requirements 4.1, 4.3**
  - **Property B: Compression bounded in (0, 1]**
    - 方法名 `test_property_b_compression_bounded`,docstring 首行 `Feature: qld-rvf-correction, Property B: Compression bounded in (0, 1]`
    - Hypothesis 策略与断言体严格按 `design.md` "Correctness Properties / Property 2" 草图实现(实现 clamp 下界为 0.05,因此断言用 `0.05 <= c <= 1.0`)
    - **Validates: Requirements 4.2, 4.3**
  - 两条用例均使用 `@settings(max_examples=100)` 与现有文件保持一致
  - 注:Req 4 强制要求新增属性测试,故本任务**不带 `*` 标记**
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 6. 修复后回测:重跑 `run_full_backtest.py`,填入对比表"修复后"列并校验全部达标
  - 执行 `python scripts/run_full_backtest.py`,这次会同时跑 17 + 2 = 19 条属性测试 + 16 数据点回测
  - 把 16 数据点的 dev% 与全局指标填入 `design.md` 对比表"修复后"一列,把每行的"变动 pp"列也算出来
  - **达标判据**(Req 3.2,任一不满足直接 FAIL → 撤回任务 4 改动并回到任务 3 重选):
    - QLD1 在 `2024_full / 2025_H1_calendar / 2025_H2_calendar` 三时段 \|dev\| ≤ 30
    - NSW1/VIC1/SA1 全部 16 个数据点中 4 个区域 × 4 时段相对修复前 \|Δpp\| ≤ 3
    - 全局 \|Bias\| ≤ 15、全局 Hit_Rate ≥ 75
    - 19 条属性测试全部通过
  - 在 `design.md` 对比表"全局指标"段把 `✗` 标记从 Bias 行移除(若已达标)
  - _Requirements: 3.1, 3.2, 3.3, 4.3_

- [x] 7. 清理临时产物 + 收尾
  - 删除 `scripts/calibrate_qld_rvf.py`(Req 2.4):`git rm scripts/calibrate_qld_rvf.py`
  - 清理校准脚本运行期间产生的任何临时 CSV / JSON / log 文件(Req 5.3)
  - 在 `.kiro/specs/forward-model-accuracy-upgrade/tasks.md` 的 changelog / Notes 区追加一行:`- 2026-05-29 QLD_RVF 校正完成,详见 .kiro/specs/qld-rvf-correction/(0.55 → <calibrated>),三时段偏差全部回到 ±30% 以内`
  - 把本 `tasks.md` 全部 7 个任务的 `[ ]` 改为 `[x]`(Req 5.3)
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 2.4, 5.3_

## Execution Summary (2026-05-29)

**实际执行结果与原计划差异:**

1. **Task 3 — H1 达标阈值放宽**
   - 原计划:QLD 三时段全部 \|dev\| ≤ 30%
   - 实际:网格搜索表明,即使 RVF 拉到 1.55(扩展集上限),QLD 2025_H1 仍卡在 -30.7%
   - 根因:Modo 公开数据显示 2025-06 NEM 单月 $403k 极端价格事件污染 H1 算术均值($165k 中包含 6 月单月接近 $277k QLD 单月数据);规则模型不可能学习一次性极端事件
   - 修订:Req 2.2 与 Req 3.2 已同步更新——`2025_H1_calendar` 阈值放宽到 ≤35%(其他两时段保持 30%);取得用户确认后执行

2. **选定 RVF = 1.35**
   - 全局 |Bias| 最低(0.01%),Hit Rate 87.5%
   - QLD 偏差:2024_full -4.9% / 2025_H1_calendar -34.2%(放宽阈值内) / 2025_H2_calendar +3.5%
   - NSW/VIC/SA 任一时段 Δpp = 0.00(零副作用,符合 Req 3.2 ≤±3pp)

3. **全部 33 项回测达标** — 通过率 31/33 → 33/33 = 100%

4. **遗留问题(已记录,非本 spec 范围):**
   - QLD 2025_26_summer 修复后偏差 +148.2%(模型 $84k vs Modo $34k)
   - 该时段不在 Time_Window_Set 强约束集中(只是参考)
   - 根因:RVF=1.35 让所有 QLD 时段保留更多价差,在 H1/H2 校准成功,但 summer 这种"BESS 渗透率最高、煤电故障最少、温和需求"的极端压缩窗口反而显得偏高
   - 需要后续 spec 引入"季节性压缩"或"BESS 渗透率敏感度"参数

5. **临时产物清理** — `scripts/calibrate_qld_rvf.py` 已 `delete_file` 删除,工作树干净

6. **forward-model-accuracy-upgrade tasks.md changelog** 已同步追加 RVF 校正记录

## Notes

- 这是一次性参数校正型 **fast-task** spec,目标是把 QLD1 三时段系统性偏差(-39 / -63 / -42)收敛到 ±30% 以内,**不**新增公式、**不**改架构、**不**碰其他常量。
- 任务 2 产生的 `scripts/calibrate_qld_rvf.py` 是**临时脚本**,任务 7 必须 `git rm` 删除,**不进主分支历史**;若任务 7 跳过,会留下与 Req 2.4 冲突的脏产物。
- 任务 5(属性测试)未带 `*` 标记,因为 Req 4 把这两条 PBT 列为强制要求,与项目既有 17 条 PBT 同等地位,不属于"可选 MVP 跳过"范围。
- 任务 6 是质量门:任一指标不达标直接 FAIL,必须撤回任务 4 的常量改动并回到任务 3 重新选 RVF;**严禁**带着 \|Bias\| > 15 或 Hit_Rate < 75 的版本提交主分支。
- 全部任务建议在 1–2 个工作日内串行完成,任务 1/3/6 各约 0.5h(主要是等回测脚本跑完),任务 2 约 1.5h,任务 4/5 各约 0.5h,任务 7 约 0.5h,总计 ~4h 编码 + ~1h 等回测。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4", "5"] },
    { "id": 4, "tasks": ["6"] },
    { "id": 5, "tasks": ["7"] }
  ]
}
```
