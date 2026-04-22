"""
BESS arbitrage backtest utilities.

This module keeps the original CLI entrypoints, but the core backtest now
returns a conservative physical upper bound:
- optimized hindsight dispatch
- fixed 50% initial SoC each month
- terminal SoC forced back to 50%
- monthly charge-throughput limited by cycles-per-day
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import pulp

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_PATH = "aemo_data.db"

STORAGE_CONFIGS = {
    "2h": {"duration_hours": 2, "capacity_mwh": 200, "power_mw": 100},
    "4h": {"duration_hours": 4, "capacity_mwh": 400, "power_mw": 100},
    "6h": {"duration_hours": 6, "capacity_mwh": 600, "power_mw": 100},
}

ROUND_TRIP_EFFICIENCY = 0.87
CYCLES_PER_DAY = 1


def get_available_tables(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'"
    ).fetchall()
    return sorted([row[0] for row in tables])


def get_available_regions(conn, table):
    regions = conn.execute(
        f"SELECT DISTINCT region_id FROM {table} ORDER BY region_id"
    ).fetchall()
    return [row[0] for row in regions]


def analyze_daily_spreads(conn, region, year):
    table = f"trading_price_{year}"
    try:
        rows = conn.execute(
            f"""
            SELECT
                DATE(settlement_date) as day,
                MIN(rrp_aud_mwh) as min_price,
                MAX(rrp_aud_mwh) as max_price,
                AVG(rrp_aud_mwh) as avg_price,
                COUNT(*) as intervals,
                SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count
            FROM {table}
            WHERE region_id = ?
            GROUP BY DATE(settlement_date)
            ORDER BY day
            """,
            (region,),
        ).fetchall()
    except Exception:
        return []

    results = []
    for day, min_price, max_price, avg_price, intervals, neg_count in rows:
        spread = max_price - min_price
        neg_pct = (neg_count / intervals * 100) if intervals > 0 else 0
        results.append(
            {
                "date": day,
                "min_price": round(min_price, 2),
                "max_price": round(max_price, 2),
                "avg_price": round(avg_price, 2),
                "spread": round(spread, 2),
                "intervals": intervals,
                "neg_count": neg_count,
                "neg_pct": round(neg_pct, 1),
            }
        )
    return results


def backtest_arbitrage(conn, region, year, storage_config):
    table = f"trading_price_{year}"
    duration_h = storage_config["duration_hours"]
    capacity_mwh = storage_config["capacity_mwh"]
    power_mw = storage_config["power_mw"]
    initial_soc_mwh = capacity_mwh * 0.5

    try:
        months_res = conn.execute(
            f"SELECT DISTINCT substr(settlement_date, 1, 7) FROM {table} WHERE region_id = ?",
            (region,),
        ).fetchall()
        months = sorted([row[0] for row in months_res])
    except Exception:
        return {}

    monthly_revenue = defaultdict(float)
    trading_days_total = 0
    total_spread_val = 0.0
    total_charge_mwh = 0.0
    total_discharge_mwh = 0.0
    throughput_limit_total = 0.0
    terminal_soc_mwh = initial_soc_mwh

    eta = ROUND_TRIP_EFFICIENCY ** 0.5

    for month in months:
        rows = conn.execute(
            f"""
            SELECT settlement_date, rrp_aud_mwh
            FROM {table}
            WHERE region_id = ? AND settlement_date LIKE ?
            ORDER BY settlement_date
            """,
            (region, f"{month}-%"),
        ).fetchall()

        n = len(rows)
        if n < 2:
            continue

        dt_hours = 5.0 / 60.0
        try:
            t1 = datetime.fromisoformat(rows[0][0])
            t2 = datetime.fromisoformat(rows[1][0])
            delta_min = (t2 - t1).total_seconds() / 60.0
            if 0 < delta_min <= 60:
                dt_hours = delta_min / 60.0
        except Exception:
            pass

        prices = [row[1] for row in rows]
        prob = pulp.LpProblem(f"BESS_{region}_{month}", pulp.LpMaximize)

        charge = [pulp.LpVariable(f"Pc_{t}", lowBound=0, upBound=power_mw) for t in range(n)]
        discharge = [pulp.LpVariable(f"Pd_{t}", lowBound=0, upBound=power_mw) for t in range(n)]
        soc = [pulp.LpVariable(f"E_{t}", lowBound=0, upBound=capacity_mwh) for t in range(n)]
        charge_on = [pulp.LpVariable(f"Bc_{t}", cat="Binary") for t in range(n)]
        discharge_on = [pulp.LpVariable(f"Bd_{t}", cat="Binary") for t in range(n)]

        for t in range(n):
            if t == 0:
                prob += soc[t] == initial_soc_mwh + charge[t] * dt_hours * eta - discharge[t] * dt_hours / eta
            else:
                prob += soc[t] == soc[t - 1] + charge[t] * dt_hours * eta - discharge[t] * dt_hours / eta

            prob += charge_on[t] + discharge_on[t] <= 1
            prob += charge[t] <= power_mw * charge_on[t]
            prob += discharge[t] <= power_mw * discharge_on[t]

        month_days = n * dt_hours / 24.0
        throughput_limit_mwh = CYCLES_PER_DAY * month_days * capacity_mwh
        throughput_limit_total += throughput_limit_mwh
        prob += pulp.lpSum(charge[t] * dt_hours for t in range(n)) <= throughput_limit_mwh
        prob += soc[n - 1] == initial_soc_mwh

        profit = pulp.lpSum((discharge[t] - charge[t]) * prices[t] * dt_hours for t in range(n))
        prob += profit

        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=20)
        prob.solve(solver)

        if pulp.LpStatus[prob.status] != "Optimal":
            continue

        net_revenue = pulp.value(profit) or 0.0
        month_charge = sum((charge[t].varValue or 0.0) * dt_hours for t in range(n))
        month_discharge = sum((discharge[t].varValue or 0.0) * dt_hours for t in range(n))
        terminal_soc_mwh = soc[n - 1].varValue if soc[n - 1].varValue is not None else terminal_soc_mwh

        total_charge_mwh += month_charge
        total_discharge_mwh += month_discharge

        if net_revenue > 0:
            monthly_revenue[month] += net_revenue
            active_days = set()
            for idx in range(n):
                if (charge[idx].varValue or 0.0) > 0.1 or (discharge[idx].varValue or 0.0) > 0.1:
                    active_days.add(rows[idx][0][:10])
            trading_days_total += len(active_days)
            total_spread_val += net_revenue / max(len(active_days), 1) / capacity_mwh

    total_annual = sum(monthly_revenue.values())
    revenue_per_mw = total_annual / power_mw if power_mw else 0.0
    avg_daily = total_annual / max(trading_days_total, 1)

    return {
        "region": region,
        "year": year,
        "duration": f"{duration_h}h",
        "capacity_mwh": capacity_mwh,
        "power_mw": power_mw,
        "backtest_mode": "optimized_hindsight",
        "revenue_scope": "physical_upper_bound",
        "total_revenue_aud": round(total_annual, 0),
        "revenue_per_mw_year": round(revenue_per_mw, 0),
        "monthly": {key: round(value, 0) for key, value in sorted(monthly_revenue.items())},
        "trading_days": trading_days_total,
        "avg_daily_revenue": round(avg_daily, 0),
        "avg_spread": round(total_spread_val / max(len(monthly_revenue), 1), 2),
        "annual_charge_mwh": round(total_charge_mwh, 2),
        "annual_discharge_mwh": round(total_discharge_mwh, 2),
        "throughput_limit_mwh": round(throughput_limit_total, 2),
        "initial_soc_mwh": round(initial_soc_mwh, 2),
        "terminal_soc_mwh": round(terminal_soc_mwh, 2),
    }


def run_full_analysis(regions=None, years=None):
    conn = sqlite3.connect(DB_PATH)
    tables = get_available_tables(conn)

    if not tables:
        logger.error("No trading_price tables found in the database.")
        return

    available_years = [int(table.split("_")[-1]) for table in tables]
    target_years = [year for year in years if year in available_years] if years else available_years

    if not regions:
        discovered_regions = set()
        for table in tables:
            discovered_regions.update(get_available_regions(conn, table))
        regions = sorted(discovered_regions)

    logger.info("=" * 60)
    logger.info("  BESS arbitrage backtest")
    logger.info(f"  Regions: {', '.join(regions)}")
    logger.info(f"  Years: {', '.join(str(year) for year in target_years)}")
    logger.info(f"  Storage configs: {', '.join(STORAGE_CONFIGS.keys())}")
    logger.info(f"  Round-trip efficiency: {ROUND_TRIP_EFFICIENCY * 100:.0f}%")
    logger.info("=" * 60)

    all_results = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "round_trip_efficiency": ROUND_TRIP_EFFICIENCY,
            "cycles_per_day": CYCLES_PER_DAY,
        },
        "spread_analysis": {},
        "arbitrage_backtest": {},
        "negative_price_trend": {},
    }

    logger.info("\n1/3 Daily spread analysis...")
    for region in regions:
        all_results["spread_analysis"][region] = {}
        for year in target_years:
            spreads = analyze_daily_spreads(conn, region, year)
            if not spreads:
                continue
            avg_spread = sum(item["spread"] for item in spreads) / len(spreads)
            max_spread = max(item["spread"] for item in spreads)
            avg_neg_pct = sum(item["neg_pct"] for item in spreads) / len(spreads)
            all_results["spread_analysis"][region][year] = {
                "days": len(spreads),
                "avg_daily_spread": round(avg_spread, 2),
                "max_daily_spread": round(max_spread, 2),
                "median_spread": round(sorted(item["spread"] for item in spreads)[len(spreads) // 2], 2),
                "avg_neg_price_pct": round(avg_neg_pct, 1),
            }
            logger.info(
                f"  {region} {year}: avg spread=${avg_spread:.0f}, "
                f"max=${max_spread:.0f}, neg price share={avg_neg_pct:.1f}%"
            )

    logger.info("\n2/3 Negative price trend...")
    for region in regions:
        trend = {}
        for year in target_years:
            spreads = analyze_daily_spreads(conn, region, year)
            if not spreads:
                continue
            monthly_neg = defaultdict(list)
            for item in spreads:
                monthly_neg[item["date"][:7]].append(item["neg_pct"])
            for month, values in sorted(monthly_neg.items()):
                trend[month] = round(sum(values) / len(values), 1)
        all_results["negative_price_trend"][region] = trend

    logger.info("\n3/3 Arbitrage backtest...")
    for region in regions:
        all_results["arbitrage_backtest"][region] = {}
        for year in target_years:
            year_results = {}
            for config_name, config in STORAGE_CONFIGS.items():
                result = backtest_arbitrage(conn, region, year, config)
                if result and result.get("trading_days", 0) > 0:
                    year_results[config_name] = result
                    logger.info(
                        f"  {region} {year} {config_name}: "
                        f"${result['revenue_per_mw_year']:,.0f}/MW/year "
                        f"(avg spread=${result['avg_spread']:.0f})"
                    )
            if year_results:
                all_results["arbitrage_backtest"][region][year] = year_results

    conn.close()

    output_file = "bess_backtest_results.json"
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(all_results, handle, indent=2, ensure_ascii=False)

    logger.info(f"\nSaved results to {output_file}")
    print_summary(all_results)
    return all_results


def print_summary(results):
    print("\n" + "=" * 80)
    print("  BESS arbitrage backtest summary - annual revenue/MW ($AUD)")
    print("=" * 80)

    backtests = results.get("arbitrage_backtest", {})
    header = f"{'Region':>8} {'Year':>6}"
    for config in STORAGE_CONFIGS:
        header += f" {config + ' $/MW':>12}"
    header += f" {'AvgSpread':>12}"
    print(header)
    print("-" * 80)

    for region in sorted(backtests.keys()):
        for year in sorted(backtests[region].keys()):
            line = f"{region:>8} {year:>6}"
            spread_val = 0
            for config in STORAGE_CONFIGS:
                if config in backtests[region][year]:
                    revenue = backtests[region][year][config]["revenue_per_mw_year"]
                    line += f" ${revenue:>10,.0f}"
                    if config == "4h":
                        spread_val = backtests[region][year][config]["avg_spread"]
                else:
                    line += f" {'N/A':>11}"
            line += f" ${spread_val:>10,.0f}"
            print(line)

    print("=" * 80)
    print(
        f"  Note: {ROUND_TRIP_EFFICIENCY * 100:.0f}% round-trip efficiency, "
        f"{CYCLES_PER_DAY} cycle/day limit, optimized hindsight physical upper bound."
    )
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="BESS arbitrage backtest")
    parser.add_argument("--region", type=str, help="Region (NSW1/QLD1/SA1/TAS1/VIC1/WEM)")
    parser.add_argument("--year", type=int, help="Year")
    parser.add_argument("--all", action="store_true", help="Analyze all regions and years")
    args = parser.parse_args()

    if args.all:
        run_full_analysis()
    elif args.region and args.year:
        run_full_analysis(regions=[args.region], years=[args.year])
    elif args.region:
        run_full_analysis(regions=[args.region])
    elif args.year:
        run_full_analysis(years=[args.year])
    else:
        run_full_analysis(
            regions=["NSW1", "SA1", "VIC1", "QLD1", "WEM"],
            years=[2024, 2025, 2026],
        )


if __name__ == "__main__":
    main()
