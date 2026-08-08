"""Rolling pre-dispatch backtest — 闭环滚动回测试点（P0-1）。

背景（2026-08-05，任务记录-2026-08-05-算法系统性评估）:
    dispatch_optimizer.run_rolling_forecast 长期是占位符，直接回落完美前瞻
    MILP。文献一致结论：完美前瞻高估可达成收入。本脚本用 **NEMWeb 归档中
    真实发出过的 pre-dispatch 价格预测**（scrapers/aemo_predispatch_archive.py
    落库）驱动滚动再调度，量化"预测误差吃掉多少套利收入"：

        efficiency = rolling_revenue / hindsight_revenue

    方法（与文献 rolling re-dispatch 协议一致；归档实测 2026-08-05：
    pre-dispatch run 每 30 分钟一期，前向 56 个 30 分钟间隔 ≈ 28h 视野）:
    1. 每 commit_minutes（默认 30 分钟，与 run 发布节奏对齐）为一次再优化周期；
    2. 取决策时刻之前最近一期 pre-dispatch run 的前向价格序列作为预测视野
       （默认 horizon_hours=4）；
    3. 用 V1 引擎同一 LP 核（_solve_window，HiGHS）在预测价上求解，
       仅承诺前 commit 窗口的调度；
    4. 承诺的调度按 **实际结算价**（5 分钟价格聚合为 30 分钟块均价）计分，
       SoC 按承诺轨迹推进；
    5. 对照完美前瞻（window_hours<=0，全周一次求解）得 efficiency。

用法:
    cd backend && python ../scripts/backtest_rolling_predispatch.py \
        --week 2026-06-21 --region NSW1
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
INTERVAL_HOURS = 5.0 / 60.0            # 实际结算粒度（5 分钟）
INTERVAL_HOURS_FORECAST = 30.0 / 60.0  # pre-dispatch 预测粒度（30 分钟）
COMMIT_INTERVALS_DEFAULT = 6  # 30 分钟 / 5 分钟


def load_actual_prices(conn, region: str, week_start: datetime, week_end: datetime) -> dict:
    """实际 5 分钟结算价 {timestamp: price}（与 ML 同表同口径）。"""
    year_tables = sorted({f"trading_price_{week_start.year}", f"trading_price_{week_end.year}"})
    prices: dict = {}
    for table in year_tables:
        try:
            rows = conn.execute(
                f"""
                SELECT settlement_date, rrp_aud_mwh
                FROM {table}
                WHERE region_id = ? AND settlement_date >= ? AND settlement_date < ?
                ORDER BY settlement_date
                """,
                (region, week_start.isoformat(), week_end.isoformat()),
            ).fetchall()
        except Exception:
            continue
        for ts, price in rows:
            if ts is None or price is None:
                continue
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", ""))
            prices[ts] = float(price)
    return prices


def block_prices(actual_prices: dict, week_start: datetime, week_end: datetime, block_minutes: int = 30) -> dict:
    """5 分钟结算价聚合为 block_minutes 块均价 {block_start_ts: avg_price}。"""
    blocks: dict = {}
    for ts, price in actual_prices.items():
        offset = int((ts - week_start).total_seconds() // 60)
        block_start = week_start + timedelta(minutes=(offset // block_minutes) * block_minutes)
        blocks.setdefault(block_start, []).append(price)
    return {k: sum(v) / len(v) for k, v in blocks.items() if v}


def load_forecast_runs(conn, region: str, week_start: datetime, week_end: datetime) -> list:
    """pre-dispatch 预测 run 列表（按 run_datetime 升序）。

    Returns:
        [(run_dt, [(interval_ts, rrp), ...] 按时间升序), ...]
    """
    rows = conn.execute(
        """
        SELECT run_datetime, interval_time, rrp
        FROM predispatch_price_forecast
        WHERE region_id = ? AND week_start = ?
        ORDER BY run_datetime, interval_time
        """,
        (region, week_start.date().isoformat()),
    ).fetchall()

    runs: dict = {}
    for run_dt, interval_ts, rrp in rows:
        if run_dt is None or rrp is None or interval_ts is None:
            continue
        if isinstance(run_dt, str):
            run_dt = datetime.fromisoformat(run_dt.replace("Z", ""))
        if isinstance(interval_ts, str):
            interval_ts = datetime.fromisoformat(interval_ts.replace("Z", ""))
        runs.setdefault(run_dt, []).append((interval_ts, float(rrp)))
    ordered = []
    for run_dt in sorted(runs):
        series = sorted(runs[run_dt])
        if series:
            ordered.append((run_dt, series))
    return ordered


def latest_run_before(runs: list, decision_ts: datetime, max_lag_minutes: float):
    """决策时刻之前最近一期 run（超过 max_lag 视为预测过期，返回 None）。"""
    best = None
    for run_dt, series in runs:
        if run_dt <= decision_ts:
            best = (run_dt, series)
        else:
            break
    if best is None:
        return None
    lag = (decision_ts - best[0]).total_seconds() / 60.0
    if lag > max_lag_minutes:
        return None
    return best


def forecast_window(series: list, start_ts: datetime, horizon_hours: float) -> list:
    """从 run 的前向序列切出 [start_ts, start_ts+horizon) 的 (ts, price)。"""
    end_ts = start_ts + timedelta(hours=horizon_hours)
    return [(ts, p) for ts, p in series if start_ts <= ts < end_ts]


def run_rolling(
    *,
    solver,
    params,
    actual_blocks: dict,
    runs: list,
    week_start: datetime,
    week_end: datetime,
    commit_minutes: int,
    horizon_hours: float,
    max_lag_minutes: float,
    spread_gate: float = 0.0,
) -> dict:
    """滚动再调度主循环。返回承诺调度的实际收入与诊断计数。

    spread_gate: 预测窗口内 max-min 价差低于该阈值（$/MWh）时本块不交易。
        用途：低波动市场里预测误差驱动的往返交易是纯损耗
        （往返效率损失 ≈ (1/RTE-1)×价数量级），门槛能止血。
        0 = 关闭（保持旧行为）。
    """
    eta = params.round_trip_efficiency ** 0.5
    min_soc = params.energy_mwh * (params.min_soc_pct / 100.0)
    max_soc = params.energy_mwh * (params.max_soc_pct / 100.0)
    soc = params.initial_soc_mwh
    block_hours = commit_minutes / 60.0

    total_net = 0.0
    total_gross = 0.0
    commits = 0
    skipped_no_forecast = 0
    skipped_no_prices = 0
    gated_blocks = 0

    ts = week_start
    while ts < week_end:
        commit_end = ts + timedelta(minutes=commit_minutes)
        run = latest_run_before(runs, ts, max_lag_minutes)
        if run is None:
            skipped_no_forecast += 1
            ts = commit_end
            continue
        window = forecast_window(run[1], ts, horizon_hours)
        if not window:
            skipped_no_forecast += 1
            ts = commit_end
            continue

        # 价差门槛：预测窗口内价差不足时不交易（低波动市场止血）
        if spread_gate > 0.0:
            fprices = [p for _, p in window]
            if max(fprices) - min(fprices) < spread_gate:
                gated_blocks += 1
                ts = commit_end
                continue

        # 预测价序列上求解（LP 核与生产 V1 同一函数）
        forecast_rows = [
            {"timestamp": fts, "price": fp, "interval_hours": INTERVAL_HOURS_FORECAST}
            for fts, fp in window
        ]
        solved = solver(params, forecast_rows, soc, None)
        if not solved:
            skipped_no_forecast += 1
            ts = commit_end
            continue

        # 承诺前 commit 块（预测为 30 分钟粒度，逐块按实际块均价计分）
        commit_revenue = 0.0
        committed_blocks = 0
        for row in solved:
            if row["timestamp"] >= commit_end:
                break
            actual_price = actual_blocks.get(row["timestamp"])
            if actual_price is None:
                skipped_no_prices += 1
                continue
            gross = (row["discharge_mwh"] - row["charge_mwh"]) * actual_price
            fees = row["discharge_mwh"] * params.network_fee_per_mwh
            degr = row["discharge_mwh"] * params.degradation_cost_per_mwh
            vom = row["discharge_mwh"] * params.variable_om_per_mwh
            commit_revenue += gross - fees - degr - vom
            total_gross += gross
            # SoC 推进（与 LP 约束同一 sqrt-RTE 口径）
            soc += (
                row["charge_mw"] * INTERVAL_HOURS_FORECAST * eta
                - row["discharge_mw"] * INTERVAL_HOURS_FORECAST
            )
            soc = max(min_soc, min(max_soc, soc))
            committed_blocks += 1
        if committed_blocks:
            total_net += commit_revenue
            commits += 1
        else:
            skipped_no_forecast += 1
        ts = commit_end

    return {
        "net_revenue": total_net,
        "gross_revenue": total_gross,
        "commits": commits,
        "skipped_no_forecast": skipped_no_forecast,
        "skipped_no_prices": skipped_no_prices,
        "gated_blocks": gated_blocks,
        "final_soc_mwh": soc,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="闭环滚动回测试点（pre-dispatch 真实预测）")
    parser.add_argument("--week", required=True, help="周起始日 YYYY-MM-DD（须已入库）")
    parser.add_argument("--region", default="NSW1", choices=NEM_REGIONS)
    parser.add_argument("--power-mw", type=float, default=100.0)
    parser.add_argument("--duration-hours", type=float, default=2.0)
    parser.add_argument("--rte", type=float, default=0.87)
    parser.add_argument("--commit-minutes", type=int, default=30)
    parser.add_argument("--horizon-hours", type=float, default=4.0)
    parser.add_argument("--max-lag-minutes", type=float, default=45.0)
    parser.add_argument("--spread-gate", type=float, default=0.0,
                        help="预测价差门槛（$/MWh），低于则不交易；0=关闭")
    parser.add_argument("--degradation-cost", type=float, default=0.0)
    args = parser.parse_args()

    from deps import get_db
    from engines.bess_backtest_v1 import _solve_window
    from models.bess_backtest_params import BessBacktestParams

    week_start = datetime.strptime(args.week, "%Y-%m-%d")
    week_end = week_start + timedelta(days=7)
    if args.commit_minutes % 30 != 0:
        raise SystemExit("commit-minutes 须为 30 的倍数（pre-dispatch 预测为 30 分钟粒度）")

    params = BessBacktestParams(
        market="NEM",
        region=args.region,
        year=week_start.year,
        power_mw=args.power_mw,
        duration_hours=args.duration_hours,
        round_trip_efficiency=args.rte,
        initial_soc_pct=50.0,
        degradation_cost_per_mwh=args.degradation_cost,
        max_cycles_per_day=100.0,  # 试点不约束循环数
    )

    print("=" * 72)
    print(f"ROLLING PREDISPATCH BACKTEST — {args.region} 周 {args.week}")
    print(f"  电池: {args.power_mw:.0f}MW / {args.power_mw * args.duration_hours:.0f}MWh, RTE={args.rte}")
    print(f"  协议: 每 {args.commit_minutes}min 再优化, 预测视野 {args.horizon_hours}h, "
          f"run 过期阈值 {args.max_lag_minutes:.0f}min")
    print("=" * 72)

    db = get_db()
    with db.get_connection() as conn:
        actual_prices = load_actual_prices(conn, args.region, week_start, week_end)
        runs = load_forecast_runs(conn, args.region, week_start, week_end)

    if not actual_prices:
        print("无实际价格数据，退出")
        return 1
    if not runs:
        print("无 pre-dispatch 预测数据（先运行 scrapers/aemo_predispatch_archive.py）")
        return 1
    actual_blocks = block_prices(actual_prices, week_start, week_end, block_minutes=args.commit_minutes)
    print(f"数据: 实际价格 {len(actual_prices)} 个 5 分钟间隔 ({len(actual_blocks)} 个计分块), "
          f"pre-dispatch runs {len(runs)} 期")
    run_span = (runs[-1][0] - runs[0][0]).total_seconds() / 3600
    print(f"runs 覆盖 {runs[0][0]} ~ {runs[-1][0]}（{run_span:.1f}h），"
          f"平均前向间隔数 {sum(len(s) for _, s in runs) / len(runs):.0f}")

    # ---------- 完美前瞻上界（全周一次求解，实际价计分） ----------
    hindsight_rows = [
        {"timestamp": ts, "price": p, "interval_hours": INTERVAL_HOURS}
        for ts, p in sorted(actual_prices.items())
    ]
    hindsight_solved = _solve_window(params, hindsight_rows, params.initial_soc_mwh, params.initial_soc_mwh)
    hindsight_revenue = sum(r["net_revenue"] for r in hindsight_solved) if hindsight_solved else 0.0

    # ---------- 滚动再调度（pre-dispatch 预测驱动，实际价计分） ----------
    rolling = run_rolling(
        solver=_solve_window,
        params=params,
        actual_blocks=actual_blocks,
        runs=runs,
        week_start=week_start,
        week_end=week_end,
        commit_minutes=args.commit_minutes,
        horizon_hours=args.horizon_hours,
        max_lag_minutes=args.max_lag_minutes,
        spread_gate=args.spread_gate,
    )

    print()
    print(f"{'指标':30} {'值':>15}")
    print(f"{'完美前瞻收入 ($, 全周)':30} {hindsight_revenue:>15,.0f}")
    print(f"{'滚动预测收入 ($, 实际价计分)':30} {rolling['net_revenue']:>15,.0f}")
    eff = rolling["net_revenue"] / hindsight_revenue if hindsight_revenue > 0 else float("nan")
    print(f"{'预测效率 efficiency':30} {eff:>14.1%}")
    print(f"{'再优化次数 (commits)':30} {rolling['commits']:>15d}")
    print(f"{'跳过（无/过期预测）':30} {rolling['skipped_no_forecast']:>15d}")
    print(f"{'跳过间隔（缺实际价）':30} {rolling['skipped_no_prices']:>15d}")
    print(f"{'周末 SoC (MWh)':30} {rolling['final_soc_mwh']:>15.1f}")
    print()
    print("解读: efficiency = 真实预测信息下可达成收入 / 上帝视角上限。")
    print("      1 - efficiency 即预测误差 + 视野截断造成的套利损失，")
    print("      这是后视回测收入必须打折的实证依据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
