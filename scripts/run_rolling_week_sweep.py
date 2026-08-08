"""多周 × 多区滚动回测扫描（efficiency 扩周验证）。

用法:
    cd backend && python ../scripts/run_rolling_week_sweep.py \
        --weeks 2026-06-21,2025-12-21,2026-03-15 --regions NSW1,QLD1,VIC1,SA1,TAS1

要求: 各周归档已通过 scrapers/aemo_predispatch_archive.py 入库。
输出: 每 (周, 区域) 的后视/滚动收入与 efficiency 汇总表。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

from backtest_rolling_predispatch import (  # noqa: E402
    INTERVAL_HOURS,
    block_prices,
    load_actual_prices,
    load_forecast_runs,
    run_rolling,
)


def run_one(db, region: str, week_start: datetime, params_factory, horizon_hours: float, max_lag_minutes: float, spread_gate: float = 0.0) -> dict | None:
    week_end = week_start + timedelta(days=7)
    with db.get_connection() as conn:
        actual_prices = load_actual_prices(conn, region, week_start, week_end)
        runs = load_forecast_runs(conn, region, week_start, week_end)
    if not actual_prices or not runs:
        return None

    params = params_factory(week_start.year)
    actual_blocks = block_prices(actual_prices, week_start, week_end, block_minutes=30)

    from engines.bess_backtest_v1 import _solve_window

    hindsight_rows = [
        {"timestamp": ts, "price": p, "interval_hours": INTERVAL_HOURS}
        for ts, p in sorted(actual_prices.items())
    ]
    hindsight_solved = _solve_window(params, hindsight_rows, params.initial_soc_mwh, params.initial_soc_mwh)
    hindsight_revenue = sum(r["net_revenue"] for r in hindsight_solved) if hindsight_solved else 0.0

    rolling = run_rolling(
        solver=_solve_window,
        params=params,
        actual_blocks=actual_blocks,
        runs=runs,
        week_start=week_start,
        week_end=week_end,
        commit_minutes=30,
        horizon_hours=horizon_hours,
        max_lag_minutes=max_lag_minutes,
        spread_gate=spread_gate,
    )
    eff = rolling["net_revenue"] / hindsight_revenue if hindsight_revenue > 0 else float("nan")
    return {
        "region": region,
        "week": week_start.date().isoformat(),
        "hindsight": hindsight_revenue,
        "rolling": rolling["net_revenue"],
        "efficiency": eff,
        "commits": rolling["commits"],
        "skipped": rolling["skipped_no_forecast"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="多周×多区滚动回测扫描")
    parser.add_argument("--weeks", required=True, help="逗号分隔的周起始日 YYYY-MM-DD")
    parser.add_argument("--regions", default="NSW1,QLD1,VIC1,SA1,TAS1")
    parser.add_argument("--power-mw", type=float, default=100.0)
    parser.add_argument("--duration-hours", type=float, default=2.0)
    parser.add_argument("--rte", type=float, default=0.87)
    parser.add_argument("--horizon-hours", type=float, default=4.0)
    parser.add_argument("--max-lag-minutes", type=float, default=45.0)
    parser.add_argument("--spread-gate", type=float, default=0.0,
                        help="预测价差门槛（$/MWh），低于则不交易；0=关闭")
    args = parser.parse_args()

    from deps import get_db
    from models.bess_backtest_params import BessBacktestParams

    weeks = [datetime.strptime(w.strip(), "%Y-%m-%d") for w in args.weeks.split(",")]
    regions = [r.strip() for r in args.regions.split(",")]

    def params_factory(year: int) -> BessBacktestParams:
        return BessBacktestParams(
            market="NEM",
            region="",  # 占位：引擎不使用该字段求解
            year=year,
            power_mw=args.power_mw,
            duration_hours=args.duration_hours,
            round_trip_efficiency=args.rte,
            initial_soc_pct=50.0,
            max_cycles_per_day=100.0,
        )

    db = get_db()
    results: list[dict] = []
    for week in weeks:
        for region in regions:
            p = params_factory(week.year)
            p.region = region
            res = run_one(db, region, week, lambda _y, _p=p: _p, args.horizon_hours, args.max_lag_minutes, args.spread_gate)
            if res is None:
                print(f"[skip] {week.date()} {region}: 无数据（实际价或 pre-dispatch）")
                continue
            results.append(res)
            print(f"[done] {res['week']} {res['region']:5} hindsight={res['hindsight']:>12,.0f} "
                  f"rolling={res['rolling']:>12,.0f} eff={res['efficiency']:.1%} "
                  f"(commits={res['commits']}, skipped={res['skipped']})")

    # ---------- 汇总 ----------
    print()
    print("=" * 72)
    print("EFFICIENCY 汇总（滚动收入 / 后视收入）")
    print("=" * 72)
    header = f"{'region':6}" + "".join(f" {w.date().isoformat():>12}" for w in weeks)
    print(header)
    by_region: dict[str, dict[str, float]] = {}
    for res in results:
        by_region.setdefault(res["region"], {})[res["week"]] = res["efficiency"]
    for region in regions:
        row = by_region.get(region, {})
        cells = []
        for w in weeks:
            key = w.date().isoformat()
            cells.append(f" {row[key]:>11.1%}" if key in row else f" {'--':>12}")
        print(f"{region:6}" + "".join(cells))
    # 全表均值与每区域均值
    all_eff = [r["efficiency"] for r in results]
    if all_eff:
        print(f"\n全表均值 = {sum(all_eff)/len(all_eff):.1%}（n={len(all_eff)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
