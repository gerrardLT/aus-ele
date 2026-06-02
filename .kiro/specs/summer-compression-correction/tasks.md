# Implementation Plan: Summer Compression Correction

## Status: SUPERSEDED (2026-05-29) — 由数据修正 + 时间粒度修复部分覆盖

**关闭原因:** spec 设计阶段的根因诊断("BESS 高渗透率非线性压缩 → 单乘子 _high_penetration_decay")在落地时被否决,因为:

1. **数据层证伪**: `data/capacity_data.json` 里 QLD1 BESS 严重缺失(只有 280MW 加权,实际 2025 Q4 末 1.86GW per Modo)。补全数据后,QLD summer 偏差从 +148% 降到 +104%,但**根因不是公式**而是**输入数据**。
2. **时间粒度证伪**: `_get_existing_bess_capacity` 用年级粒度,导致 2025 Q4 投运的项目被错误算进 H1。改为月级精度后,QLD H1 从 -43% 恢复到 baseline 的 -34%,QLD summer 反弹到 +104%(因为 summer 截止 Feb 时,Broadsound/Woolooga 实际还没投运,bess_ratio 反而更低)。
3. **设计前提失效**: 月级精度下 QLD summer 的 bess_ratio = 0.20,比 QLD H2 (0.27) 还低。`_high_penetration_decay(ratio)` 在 summer 时段不会触发,**无法解决该时段偏差**。
4. **真正根因**: Modo summer review "QLD -73% YoY" 是**季节性现象**(高太阳能 + 低净需求 + autobidder 同质化竞争),不能用 bess_ratio 单变量描述。需要的是**季节性乘子**或**regime-aware capture rate**,与本 spec 的"单乘子 _high_penetration_decay"完全不同。

## Overview

> 本 spec 已 SUPERSEDED,本节仅作历史记录保留。

原计划:针对 qld-rvf-correction(QLD_RVF=1.35)落地后,QLD1 的 `2025_26_summer` 时段从 -3.6% 反弹到 +148.2% 的回归问题,在 `_compute_capture_rate` 末尾追加单乘子 `_high_penetration_decay(bess_capacity_ratio)` 解决。

实际落地路径见 `seasonal-capture-rate-correction` spec(2026-05-31 完成,采用区域差异化季节乘子方案,QLD summer +104% → +84%,全局 MAPE 20.01 → 17.66,|Bias| 2.62 → 0.01)。

## 已完成 (跨 spec 实际改动,2026-05-29)

- ✅ `data/capacity_data.json` v3 → v4: 修正 Bouldercombe 50MW(原 200MW),补 6 个已确认 QLD 项目 + 1 个聚合条目(对齐 Modo 1.86GW 锚点) + 4 个 2027+ 管道项目
- ✅ `backend/engines/forward_price_engine.py`: `_get_existing_bess_capacity` 和 `_get_cumulative_bess_capacity` 加 `reference_date: Optional[date]` 参数,支持月级精度;`validate_against_benchmarks` 为每个时段(2024_full/2025_H1_calendar/2025_H2_calendar/2025_26_summer)传入对应的截止日期(分别为 12-31/06-30/12-31/02-28)
- ✅ 全量回测 33/33 通过率维持; MAPE 23.29 → 20.01; Bias 0.01 → 2.62; Hit Rate 87.5% 不变;19 PBT 全过

## 已知遗留 (已由 seasonal-capture-rate-correction 处理)

- QLD1 `2025_26_summer` 偏差 +104%,QLD1 `2025_H2_calendar` 偏差 -10.7% — **根因为季节性 capture rate 差异未建模**,不在本 spec 覆盖范围
- ✅ 后续 spec `seasonal-capture-rate-correction` 已于 2026-05-31 完成,用区域差异化季节乘子修复;QLD summer +104% → +84%(单超阈点,在 Req 6.1 允许范围内),全局 MAPE 20.01 → 17.66

## Tasks

> 以下 7 个任务在 spec 关闭时被废弃,**未执行**也**不会执行**。统一勾选 `[x]` 以避免任务追踪工具误判为待办。spec 实际产物在上方"已完成 (跨 spec 实际改动)"区段。

- [x] 1. 基线冻结 Checkpoint — ~~不执行(spec 关闭)~~
- [x] 2. 实现临时校准脚本 — ~~不执行(spec 关闭)~~
- [x] 3. 加 2 个新模块级常量 — ~~不执行(spec 关闭)~~
- [x] 4. 执行校准、写回常量 — ~~不执行(spec 关闭)~~
- [x] 5. 实现 `_high_penetration_decay` + 集成 — ~~不执行(spec 关闭)~~
- [x] 6. 加 `TestHighPenetrationDecayProperties` PBT — ~~不执行(spec 关闭)~~
- [x] 7. 修复后回测 + 清理 — ~~不执行(spec 关闭)~~

## Notes

- 本 spec 状态为 SUPERSEDED,**不再执行任何任务**
- 实际产物记录在 `## 已完成` 与 `## 已知遗留` 段落,以及继任 spec `seasonal-capture-rate-correction`
- `forward-model-accuracy-upgrade/tasks.md` 的 `## Post-Implementation Changelog` 已记录:
  - 2026-05-29 数据修正 + 时间粒度修复(本 spec 关闭时落地的实际产物)
  - 2026-05-31 seasonal-capture-rate-correction 完成(继任 spec 处理已知遗留)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": [] }
  ]
}
```

> 空 wave:本 spec 已 SUPERSEDED,无任何待执行任务(全部 7 个原任务已统一标记 `[x]` 关闭)。
