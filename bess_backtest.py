"""
BESS 储能套利回测分析工具
==========================
功能:
  1. 每日最大价差统计（日内最高价 - 最低价）
  2. 负电价频率趋势
  3. 不同储能时长 (2h/4h/6h) 的理论套利收入回测
  4. 按月/季度/年度汇总

使用方法:
  python bess_backtest.py --region SA1 --year 2025
  python bess_backtest.py --region WEM --year 2024
  python bess_backtest.py --all
"""

import sqlite3
import json
import sys
import argparse
import logging
from datetime import datetime, timedelta
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

DB_PATH = "aemo_data.db"

# 储能参数
STORAGE_CONFIGS = {
    "2h": {"duration_hours": 2, "capacity_mwh": 200, "power_mw": 100},
    "4h": {"duration_hours": 4, "capacity_mwh": 400, "power_mw": 100},
    "6h": {"duration_hours": 6, "capacity_mwh": 600, "power_mw": 100},
}
ROUND_TRIP_EFFICIENCY = 0.87  # 87%
CYCLES_PER_DAY = 1  # 保守假设每天 1 个完整循环


def get_available_tables(conn):
    """获取所有交易价格表"""
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'"
    ).fetchall()
    return sorted([t[0] for t in tables])


def get_available_regions(conn, table):
    """获取表中的区域列表"""
    regions = conn.execute(
        f"SELECT DISTINCT region_id FROM {table} ORDER BY region_id"
    ).fetchall()
    return [r[0] for r in regions]


def analyze_daily_spreads(conn, region, year):
    """分析某区域某年的每日价差"""
    table = f"trading_price_{year}"
    
    try:
        rows = conn.execute(f"""
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
        """, (region,)).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        day, min_p, max_p, avg_p, intervals, neg_count = row
        spread = max_p - min_p
        neg_pct = (neg_count / intervals * 100) if intervals > 0 else 0
        results.append({
            "date": day,
            "min_price": round(min_p, 2),
            "max_price": round(max_p, 2),
            "avg_price": round(avg_p, 2),
            "spread": round(spread, 2),
            "intervals": intervals,
            "neg_count": neg_count,
            "neg_pct": round(neg_pct, 1),
        })
    return results


def backtest_arbitrage(conn, region, year, storage_config):
    """回测套利收入：每天找最优充/放电窗口"""
    table = f"trading_price_{year}"
    duration_h = storage_config["duration_hours"]
    capacity_mwh = storage_config["capacity_mwh"]
    power_mw = storage_config["power_mw"]
    
    # 获取每天的所有价格数据
    try:
        rows = conn.execute(f"""
            SELECT settlement_date, rrp_aud_mwh
            FROM {table}
            WHERE region_id = ?
            ORDER BY settlement_date
        """, (region,)).fetchall()
    except Exception:
        return {}
    
    # 按天分组
    daily_prices = defaultdict(list)
    for ts, price in rows:
        day = ts[:10]  # YYYY-MM-DD
        daily_prices[day].append((ts, price))
    
    # NEM 是 5 分钟间隔 (12 intervals/hour), WEM 也是 5 分钟
    intervals_per_hour = 12
    charge_intervals = duration_h * intervals_per_hour
    
    monthly_revenue = defaultdict(float)
    daily_results = []
    
    for day in sorted(daily_prices.keys()):
        prices = daily_prices[day]
        n = len(prices)
        
        if n < charge_intervals * 2:
            continue
        
        price_values = [p[1] for p in prices]
        
        # 滑动窗口找最低价充电窗口和最高价放电窗口
        best_charge_avg = float('inf')
        best_discharge_avg = float('-inf')
        
        # 充电窗口（连续 charge_intervals 个最低均价）
        for i in range(n - charge_intervals + 1):
            window = price_values[i:i + charge_intervals]
            avg = sum(window) / len(window)
            if avg < best_charge_avg:
                best_charge_avg = avg
                best_charge_start = i
        
        # 放电窗口（连续 charge_intervals 个最高均价，不能与充电重叠）
        for i in range(n - charge_intervals + 1):
            # 检查是否与充电窗口重叠
            charge_end = best_charge_start + charge_intervals
            if i < charge_end and i + charge_intervals > best_charge_start:
                continue
            window = price_values[i:i + charge_intervals]
            avg = sum(window) / len(window)
            if avg > best_discharge_avg:
                best_discharge_avg = avg
                best_discharge_start = i
        
        if best_discharge_avg == float('-inf'):
            continue
        
        # 计算单次循环收入
        charge_cost = best_charge_avg * capacity_mwh  # 充电成本
        discharge_income = best_discharge_avg * capacity_mwh * ROUND_TRIP_EFFICIENCY  # 放电收入(扣效率)
        net_revenue = discharge_income - charge_cost
        
        month = day[:7]  # YYYY-MM
        monthly_revenue[month] += max(0, net_revenue)  # 只有正收益才交易
        
        daily_results.append({
            "date": day,
            "charge_price": round(best_charge_avg, 2),
            "discharge_price": round(best_discharge_avg, 2),
            "spread": round(best_discharge_avg - best_charge_avg, 2),
            "net_revenue": round(net_revenue, 2),
        })
    
    # 年度统计
    total_annual = sum(monthly_revenue.values())
    revenue_per_mw = total_annual / power_mw if power_mw else 0
    
    return {
        "region": region,
        "year": year,
        "duration": f"{duration_h}h",
        "capacity_mwh": capacity_mwh,
        "power_mw": power_mw,
        "total_revenue_aud": round(total_annual, 0),
        "revenue_per_mw_year": round(revenue_per_mw, 0),
        "monthly": {k: round(v, 0) for k, v in sorted(monthly_revenue.items())},
        "trading_days": len(daily_results),
        "avg_daily_revenue": round(total_annual / max(len(daily_results), 1), 0),
        "avg_spread": round(
            sum(d["spread"] for d in daily_results) / max(len(daily_results), 1), 2
        ),
    }


def run_full_analysis(regions=None, years=None):
    """运行完整分析"""
    conn = sqlite3.connect(DB_PATH)
    tables = get_available_tables(conn)
    
    if not tables:
        logger.error("数据库中没有找到交易价格表")
        return
    
    available_years = [int(t.split('_')[-1]) for t in tables]
    
    if years:
        target_years = [y for y in years if y in available_years]
    else:
        target_years = available_years
    
    if not regions:
        # 默认分析所有区域
        regions = set()
        for t in tables:
            regions.update(get_available_regions(conn, t))
        regions = sorted(regions)
    
    logger.info("=" * 60)
    logger.info("  BESS 储能套利回测分析")
    logger.info(f"  区域: {', '.join(regions)}")
    logger.info(f"  年份: {', '.join(str(y) for y in target_years)}")
    logger.info(f"  储能配置: {', '.join(STORAGE_CONFIGS.keys())}")
    logger.info(f"  往返效率: {ROUND_TRIP_EFFICIENCY*100}%")
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
    
    # 1. 价差分析
    logger.info("\n📊 1/3 每日价差分析...")
    for region in regions:
        all_results["spread_analysis"][region] = {}
        for year in target_years:
            spreads = analyze_daily_spreads(conn, region, year)
            if spreads:
                avg_spread = sum(d["spread"] for d in spreads) / len(spreads)
                max_spread = max(d["spread"] for d in spreads)
                avg_neg_pct = sum(d["neg_pct"] for d in spreads) / len(spreads)
                
                summary = {
                    "days": len(spreads),
                    "avg_daily_spread": round(avg_spread, 2),
                    "max_daily_spread": round(max_spread, 2),
                    "median_spread": round(
                        sorted([d["spread"] for d in spreads])[len(spreads)//2], 2
                    ),
                    "avg_neg_price_pct": round(avg_neg_pct, 1),
                }
                all_results["spread_analysis"][region][year] = summary
                logger.info(f"  {region} {year}: 均价差=${avg_spread:.0f}, "
                          f"最大=${max_spread:.0f}, 负价占比={avg_neg_pct:.1f}%")
    
    # 2. 负电价趋势
    logger.info("\n📉 2/3 负电价频率趋势...")
    for region in regions:
        trend = {}
        for year in target_years:
            spreads = analyze_daily_spreads(conn, region, year)
            if spreads:
                # 按月汇总
                monthly_neg = defaultdict(list)
                for d in spreads:
                    month = d["date"][:7]
                    monthly_neg[month].append(d["neg_pct"])
                for month, pcts in sorted(monthly_neg.items()):
                    trend[month] = round(sum(pcts) / len(pcts), 1)
        all_results["negative_price_trend"][region] = trend
    
    # 3. 套利回测
    logger.info("\n💰 3/3 套利收入回测...")
    for region in regions:
        all_results["arbitrage_backtest"][region] = {}
        for year in target_years:
            year_results = {}
            for config_name, config in STORAGE_CONFIGS.items():
                result = backtest_arbitrage(conn, region, year, config)
                if result and result.get("trading_days", 0) > 0:
                    year_results[config_name] = result
                    rev = result["revenue_per_mw_year"]
                    logger.info(f"  {region} {year} {config_name}: "
                              f"${rev:,.0f}/MW/年 "
                              f"(均价差=${result['avg_spread']:.0f})")
            if year_results:
                all_results["arbitrage_backtest"][region][year] = year_results
    
    conn.close()
    
    # 输出 JSON
    output_file = "bess_backtest_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✅ 结果已保存至 {output_file}")
    
    # 打印摘要表
    print_summary(all_results)
    
    return all_results


def print_summary(results):
    """打印汇总表"""
    print("\n" + "=" * 80)
    print("  BESS 套利回测摘要 - 年化收入/MW ($AUD)")
    print("=" * 80)
    
    bt = results.get("arbitrage_backtest", {})
    
    # 表头
    header = f"{'区域':>6} {'年份':>6}"
    for cfg in STORAGE_CONFIGS:
        header += f" {cfg+' $/MW':>12}"
    header += f" {'均价差':>10}"
    print(header)
    print("-" * 80)
    
    for region in sorted(bt.keys()):
        for year in sorted(bt[region].keys()):
            line = f"{region:>6} {year:>6}"
            spread_val = 0
            for cfg in STORAGE_CONFIGS:
                if cfg in bt[region][year]:
                    rev = bt[region][year][cfg]["revenue_per_mw_year"]
                    line += f" ${rev:>10,.0f}"
                    if cfg == "4h":
                        spread_val = bt[region][year][cfg]["avg_spread"]
                else:
                    line += f" {'N/A':>11}"
            line += f" ${spread_val:>8,.0f}"
            print(line)
    
    print("=" * 80)
    print(f"  注: 基于 {ROUND_TRIP_EFFICIENCY*100}% 往返效率, {CYCLES_PER_DAY} 次/天循环")
    print(f"  注: 这是理论最优(完美预见)收入上限，实际约为 60-70%")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="BESS 储能套利回测")
    parser.add_argument("--region", type=str, help="区域 (NSW1/QLD1/SA1/TAS1/VIC1/WEM)")
    parser.add_argument("--year", type=int, help="年份")
    parser.add_argument("--all", action="store_true", help="分析所有区域和年份")
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
        # 默认: 分析最近 3 年的关键区域
        run_full_analysis(
            regions=["NSW1", "SA1", "VIC1", "QLD1", "WEM"],
            years=[2024, 2025, 2026]
        )


if __name__ == "__main__":
    main()
