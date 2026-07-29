"""Holdout spread validation — 真样本外价差验证（v2 双层检验）。

背景（2026-07）:
    项目此前的 validate_against_benchmarks 存在循环验证问题：季节乘子 /
    QLD RVF 在 Modo 基准上网格搜索调参，又用同一份基准"验收"。本脚本
    提供不依赖 Modo 的独立验证路径。

v1 → v2 演进:
    v1（绝对压缩旧代码）实测：五区 × 两窗口 10 点全部低估，平均 |dev|≈41%。
    诊断：ML 校准 base 是"当前已实现"价差（已含历史压缩），再乘绝对压缩
    因子把历史压缩重放一遍（双重计数）。同时同比数据显示市场真实 YoY
    压缩高达 -38%~-63%（Q2 2025 → Q2 2026），即旧代码"水平"砍过头，
    但"斜率"未必够狠。v2 因此拆成两层检验：

    - LEVEL 层：修正后（增量压缩）的 2026 预测 vs 最近 12 个月实际
      （2025-07~2026-06，全季节覆盖，消除季节错位）。
    - TREND 层：模型隐含的年度压缩斜率（pred_2027/pred_2026）vs 市场
      实际同比压缩（Q2 2026/Q2 2025）。

污染状态（诚实声明）:
    双重计数修正是由 v1 holdout 结果**驱动发现**的结构性 bug fix，未向
    holdout 窗口做任何数值参数拟合——对"参数"干净，但对"模型结构选择"
    存在一次反馈。下一批完全零污染检验 = 2026-07 数据（AEMO 月末发布）。

用法:
    cd backend && python ../scripts/validate_holdout_spread.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# 与 MLCalibrationEngine 的 winsorize 口径一致
CLIP_LOW, CLIP_HIGH = -100.0, 500.0

# 冻结校准快照（2026-07-28，补抓 NEM 2026-03~06 数据之前训练产出，
# 训练集 2020~2024；MAE=31.7, R²=0.57, CI覆盖率=0.83）。
# 这组参数在 holdout 窗口数据入库前就已定死。
FROZEN_CALIBRATION: dict[str, dict[str, float]] = {
    "NSW1": {"mean_spread": 192.02, "spike_frequency": 0.006134},
    "QLD1": {"mean_spread": 193.86, "spike_frequency": 0.000810},
    "VIC1": {"mean_spread": 164.65, "spike_frequency": 0.000231},
    "SA1": {"mean_spread": 271.03, "spike_frequency": 0.007060},
    "TAS1": {"mean_spread": 153.80, "spike_frequency": 0.000810},
}
FROZEN_ANCHOR_YEAR = 2026  # 快照 base 所处年份（"最近30天"→2026）

# 每日有效 interval 下限：低于此数的残缺天不参与统计
MIN_INTERVALS_PER_DAY = 24


def realized_spread(conn, region: str, spans: list[tuple[str, str, str]]) -> tuple[float, int]:
    """跨表窗口的实际 winsorized daily spread 均值。

    Args:
        spans: [(table, start, end), ...]，start/end 为 ISO 日期（end 不含）。

    Returns:
        (窗口内日 spread 均值, 有效天数)；无数据时 (nan, 0)。
    """
    all_spreads: list[float] = []
    for table, start, end in spans:
        rows = conn.execute(
            f"""
            SELECT DATE(settlement_date) AS day,
                   MAX(LEAST(GREATEST(rrp_aud_mwh, ?), ?)) -
                   MIN(LEAST(GREATEST(rrp_aud_mwh, ?), ?)) AS spread,
                   COUNT(*) AS n
            FROM {table}
            WHERE region_id = ? AND settlement_date >= ? AND settlement_date < ?
            GROUP BY DATE(settlement_date)
            """,
            (CLIP_LOW, CLIP_HIGH, CLIP_LOW, CLIP_HIGH, region, start, end),
        ).fetchall()
        all_spreads.extend(float(r[1]) for r in rows if r[2] >= MIN_INTERVALS_PER_DAY)
    if not all_spreads:
        return float("nan"), 0
    return sum(all_spreads) / len(all_spreads), len(all_spreads)


def main() -> int:
    from deps import get_db
    from engines.forward_price_engine import ForwardPriceEngine
    from models.forward_price_models import ScenarioType

    print("=" * 78)
    print("HOLDOUT SPREAD VALIDATION v2 — 双层检验（不依赖 Modo）")
    print("=" * 78)

    engine = ForwardPriceEngine()
    # 强制注入冻结快照与锚点年：当前进程重新跑的校准已"见过"补抓数据，
    # 直接使用即非样本外验证。
    engine._calibrated_spreads = {k: dict(v) for k, v in FROZEN_CALIBRATION.items()}
    engine._calibration_anchor_year = FROZEN_ANCHOR_YEAR
    print(f"calibration source: FROZEN snapshot (anchor={FROZEN_ANCHOR_YEAR}, pre-backfill)")

    def predict(region: str, year: int) -> float:
        capacity = engine._get_cumulative_bess_capacity(
            region, ScenarioType.CENTRAL, year, reference_date=date(year, 12, 31)
        )
        peak = engine._get_dynamic_peak_demand(region, year)
        ratio = capacity / peak if peak else 0.0
        dist = engine.calculate_price_distribution(
            region=region, scenario=ScenarioType.CENTRAL, year=year,
            bess_capacity_ratio=ratio,
        )
        return float(dist.mean_spread)

    pred_2026 = {r: predict(r, 2026) for r in NEM_REGIONS}
    pred_2027 = {r: predict(r, 2027) for r in NEM_REGIONS}

    db = get_db()
    with db.get_connection() as conn:
        # ---------- LEVEL 层 ----------
        print()
        print("--- LEVEL: 2026 预测（增量压缩修正后） vs 最近12个月实际 (2025-07~2026-06) ---")
        print(f"{'region':6} {'pred26':>8} {'actual':>8} {'dev%':>8} {'days':>5}")
        level_devs = []
        for region in NEM_REGIONS:
            actual, days = realized_spread(conn, region, [
                ("trading_price_2025", "2025-07-01", "2026-01-01"),
                ("trading_price_2026", "2026-01-01", "2026-07-01"),
            ])
            if days == 0:
                print(f"{region:6} {'--':>8} {'no data':>8}")
                continue
            dev = (pred_2026[region] - actual) / actual * 100
            level_devs.append(abs(dev))
            print(f"{region:6} {pred_2026[region]:8.1f} {actual:8.1f} {dev:+8.1f} {days:5d}")
        if level_devs:
            print(f"LEVEL mean |dev| = {sum(level_devs)/len(level_devs):.1f}%  |  "
                  f"worst = {max(level_devs):.1f}%")

        # ---------- TREND 层 ----------
        print()
        print("--- TREND: 模型隐含年压缩 (pred27/pred26) vs 实际同比 (Q2'26/Q2'25) ---")
        print(f"{'region':6} {'model_yoy%':>10} {'actual_yoy%':>11} {'gap_pp':>8}")
        trend_gaps = []
        for region in NEM_REGIONS:
            q2_25, d25 = realized_spread(conn, region, [
                ("trading_price_2025", "2025-04-01", "2025-07-01"),
            ])
            q2_26, d26 = realized_spread(conn, region, [
                ("trading_price_2026", "2026-04-01", "2026-07-01"),
            ])
            if d25 == 0 or d26 == 0:
                print(f"{region:6} {'--':>10} {'no data':>11}")
                continue
            model_yoy = (pred_2027[region] / pred_2026[region] - 1.0) * 100
            actual_yoy = (q2_26 / q2_25 - 1.0) * 100
            gap = model_yoy - actual_yoy
            trend_gaps.append(gap)
            print(f"{region:6} {model_yoy:+10.1f} {actual_yoy:+11.1f} {gap:+8.1f}")
        if trend_gaps:
            avg_gap = sum(trend_gaps) / len(trend_gaps)
            print(f"TREND mean gap = {avg_gap:+.1f}pp "
                  f"(正值 = 模型压缩斜率比市场实际温和/乐观)")

    print()
    print("解读提示:")
    print("  LEVEL 检验修正后的水平锚定是否合理（跨全季节 12 个月，无季节错位）。")
    print("  TREND 检验模型的年度压缩斜率是否跟得上市场真实蚕食速度。")
    print("  注意实际 YoY 同时含饱和压缩与年际气候/事件差异，gap 解读需保留余量。")
    print("  2026-07 数据发布后 = 下一批对结构选择也零污染的检验窗口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
