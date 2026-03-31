"""
AEMO NEM 澳洲国家电力市场 - 历史交易电价爬取工具
=================================================
数据来源: AEMO NEMWEB (http://nemweb.com.au)
数据内容: 各州(Region)的5分钟交易结算电价 (Trading Price / RRP)
覆盖区域: NSW1(新南威尔士), QLD1(昆士兰), VIC1(维多利亚), SA1(南澳), TAS1(塔斯马尼亚)
时区说明: 所有时间戳为 AEST (UTC+10), 不含夏令时

使用方法:
    python aemo_nem_scraper.py --start 2025-01 --end 2025-03
    python aemo_nem_scraper.py --start 2024-06 --end 2024-06 --regions NSW1,VIC1
    python aemo_nem_scraper.py --start 2025-01 --end 2025-12 --output my_data.csv
"""

import sys
import requests
import zipfile
import io
import csv
import os
import time
import argparse
import re
from datetime import datetime
from pathlib import Path

from database import DatabaseManager

# 修复 Windows 控制台 GBK 编码问题
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


# ============================================================
# 配置区
# ============================================================
NEMWEB_MMSDM_BASE = "http://www.nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM"
NEMWEB_CURRENT_TRADING = "http://www.nemweb.com.au/Reports/Current/TradingIS_Reports/"

ALL_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

REGION_NAME_MAP = {
    "NSW1": "新南威尔士州 (New South Wales)",
    "QLD1": "昆士兰州 (Queensland)",
    "VIC1": "维多利亚州 (Victoria)",
    "SA1":  "南澳大利亚州 (South Australia)",
    "TAS1": "塔斯马尼亚州 (Tasmania)",
}

# 请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 请求间延迟（秒），避免触发反爬
REQUEST_DELAY = 1.5


# ============================================================
# 核心函数
# ============================================================

def log(msg: str):
    """带时间戳的日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def fetch_url(url: str, max_retries: int = 3) -> requests.Response | None:
    """带重试机制的 HTTP GET 请求"""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200:
                return resp
            else:
                log(f"  [!] HTTP {resp.status_code} - {url} (尝试 {attempt}/{max_retries})")
        except requests.RequestException as e:
            log(f"  [!] 请求异常: {e} (尝试 {attempt}/{max_retries})")
        if attempt < max_retries:
            time.sleep(REQUEST_DELAY * attempt)
    return None


def list_mmsdm_monthly_zips(year: int) -> list[str]:
    """
    列出某年 MMSDM 归档中的月度 ZIP 文件名。
    归档路径格式: /Data_Archive/Wholesale_Electricity/MMSDM/YYYY/MMSDM_YYYY_MM/
    """
    url = f"{NEMWEB_MMSDM_BASE}/{year}/"
    resp = fetch_url(url)
    if not resp:
        log(f"  [X] 无法访问 {year} 年归档目录")
        return []

    # 从 HTML 目录列表中提取月度子目录名
    # 格式如: MMSDM_2025_01, MMSDM_2025_02 ...
    pattern = re.compile(rf'MMSDM_{year}_(\d{{2}})')
    months_found = sorted(set(pattern.findall(resp.text)))
    return months_found


def download_and_parse_tradingprice(year: int, month: int, regions: list[str]) -> list[dict]:
    """
    下载单个月份的 MMSDM TRADINGPRICE 数据并解析。

    MMSDM 归档结构 (新版使用 # 分隔符, URL编码为 %23):
      /YYYY/MMSDM_YYYY_MM/MMSDM_Historical_Data_SQLLoader/DATA/
        PUBLIC_ARCHIVE%23TRADINGPRICE%23FILE01%23YYYYMM010000.zip

    CSV 格式 (AEMO MMSDM 标准):
      - 以 'C' 开头的行: 注释/元数据
      - 以 'I' 开头的行: 列名头 (column headers)
      - 以 'D' 开头的行: 数据行
    """
    month_str = f"{month:02d}"
    data_dir_url = (
        f"{NEMWEB_MMSDM_BASE}/{year}/MMSDM_{year}_{month_str}/"
        f"MMSDM_Historical_Data_SQLLoader/DATA/"
    )

    log(f"[>>] 正在处理 {year}年{month}月 的数据...")

    # 按优先级排列的 URL 候选列表 (新版 # 格式 + 旧版 _ 格式)
    zip_candidates = [
        # 新版命名 (2020年后常见): PUBLIC_ARCHIVE#TRADINGPRICE#FILE01#YYYYMM010000.zip
        f"{data_dir_url}PUBLIC_ARCHIVE%23TRADINGPRICE%23FILE01%23{year}{month_str}010000.zip",
        # 旧版命名: PUBLIC_DVD_TRADINGPRICE_YYYYMM010000.CSV.zip
        f"{data_dir_url}PUBLIC_DVD_TRADINGPRICE_{year}{month_str}010000.CSV.zip",
        f"{data_dir_url}PUBLIC_DVD_TRADINGPRICE_{year}{month_str}010000.zip",
    ]

    actual_zip_url = None

    # 逐一尝试候选 URL
    for candidate in zip_candidates:
        resp = fetch_url(candidate, max_retries=1)
        if resp and resp.status_code == 200:
            actual_zip_url = candidate
            fname_display = candidate.split('/')[-1].replace('%23', '#')
            log(f"  [OK] 找到数据文件: {fname_display}")
            break

    # 方案 B: 如果直接猜测失败，扫描目录页查找文件名
    if not actual_zip_url:
        log(f"  [..] 扫描目录页查找 TRADINGPRICE 文件...")
        resp_dir = fetch_url(data_dir_url, max_retries=1)
        if resp_dir:
            tp_pattern = re.compile(
                r'(PUBLIC_(?:ARCHIVE|DVD)[^"<>\s]*TRADINGPRICE[^"<>\s]*\.zip)',
                re.IGNORECASE
            )
            matches = tp_pattern.findall(resp_dir.text)
            if matches:
                actual_zip_url = data_dir_url + matches[0]
                log(f"  [OK] 从目录找到: {matches[0]}")

    if not actual_zip_url:
        log(f"  [X] 未找到 {year}年{month}月 的 TRADINGPRICE 数据文件")
        return []

    # 下载 ZIP (如果前面试探阶段已经拿到了完整 resp，就复用)
    if not (resp and resp.status_code == 200 and resp.url and actual_zip_url in resp.url):
        time.sleep(REQUEST_DELAY)
        resp = fetch_url(actual_zip_url)
    if not resp:
        log(f"  [X] 下载失败: {actual_zip_url}")
        return []

    log(f"  [..] 下载完成, 大小: {len(resp.content) / 1024:.1f} KB, 正在解析...")

    # 解压并解析
    records = []
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for fname in zf.namelist():
                if "TRADINGPRICE" in fname.upper() and fname.upper().endswith('.CSV'):
                    log(f"  [..] 解析CSV: {fname}")
                    with zf.open(fname) as f:
                        text = f.read().decode('utf-8', errors='replace')
                        records.extend(parse_mmsdm_csv(text, regions))
    except zipfile.BadZipFile:
        log(f"  [i] 文件不是 ZIP 格式，尝试直接解析为 CSV...")
        text = resp.content.decode('utf-8', errors='replace')
        records.extend(parse_mmsdm_csv(text, regions))

    log(f"  [OK] 获取到 {len(records)} 条交易电价记录")
    return records


def parse_mmsdm_csv(text: str, regions: list[str]) -> list[dict]:
    """
    解析 AEMO MMSDM 标准格式的 CSV 文本。

    MMSDM CSV 格式规则:
      - 'C' 行: 文件头/注释/文件尾
      - 'I' 行: 列名定义 (紧跟在数据段之前)
      - 'D' 行: 实际数据

    TRADINGPRICE 关键字段:
      - SETTLEMENTDATE: 结算时间 (AEST, UTC+10)
      - REGIONID: 区域/州代码 (NSW1, QLD1, VIC1, SA1, TAS1)
      - RRP: 区域参考价格 (Regional Reference Price, $/MWh)
    """
    records = []
    headers = []
    regions_upper = [r.upper() for r in regions]

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(',')
        row_type = parts[0].strip('"').upper()

        if row_type == 'I':
            # 这是列名行
            headers = [h.strip().strip('"').upper() for h in parts]

        elif row_type == 'D' and headers:
            # 数据行
            if len(parts) < len(headers):
                continue

            row = {}
            for i, h in enumerate(headers):
                if i < len(parts):
                    row[h] = parts[i].strip().strip('"')

            region_id = row.get('REGIONID', '').upper()
            if region_id not in regions_upper:
                continue

            settlement_date = row.get('SETTLEMENTDATE', '')
            rrp = row.get('RRP', '')

            if settlement_date and rrp:
                try:
                    price = float(rrp)
                    records.append({
                        'settlement_date': settlement_date,
                        'region_id': region_id,
                        'rrp_aud_mwh': round(price, 2),
                    })
                except ValueError:
                    pass

    return records


def save_to_csv(records: list[dict], output_path: str):
    """将数据保存为 CSV 文件"""
    if not records:
        log("[!] 没有数据可保存")
        return

    # 按时间和区域排序
    records.sort(key=lambda r: (r['settlement_date'], r['region_id']))

    fieldnames = ['settlement_date', 'region_id', 'rrp_aud_mwh']
    header_display = ['结算时间(AEST)', '州/区域代码', '电价(AUD$/MWh)']

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        # 写入中文表头
        writer.writerow(header_display)
        for rec in records:
            writer.writerow([
                rec['settlement_date'],
                rec['region_id'],
                rec['rrp_aud_mwh'],
            ])

    log(f"[OK] 数据已保存到: {output_path}")
    log(f"     共 {len(records)} 条记录")

    # 输出摘要统计
    print_summary(records)


def print_summary(records: list[dict]):
    """打印数据摘要"""
    if not records:
        return

    print("\n" + "=" * 60)
    print("[*] 数据摘要")
    print("=" * 60)

    # 按区域统计
    region_stats = {}
    for r in records:
        rid = r['region_id']
        if rid not in region_stats:
            region_stats[rid] = {'count': 0, 'prices': []}
        region_stats[rid]['count'] += 1
        region_stats[rid]['prices'].append(r['rrp_aud_mwh'])

    print(f"\n{'Region':<8} {'State':<35} {'Count':>8} {'Avg Price':>12} {'Min':>10} {'Max':>10}")
    print("-" * 90)

    for region in sorted(region_stats.keys()):
        stats = region_stats[region]
        prices = stats['prices']
        name = REGION_NAME_MAP.get(region, region)
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        print(f"{region:<8} {name:<35} {stats['count']:>8,} {avg_price:>10.2f}  {min_price:>10.2f} {max_price:>10.2f}")

    # 时间范围
    dates = [r['settlement_date'] for r in records]
    print(f"\n时间范围: {min(dates)} -> {max(dates)}")
    print(f"总记录数: {len(records):,}")
    print("=" * 60)


def parse_month_range(start_str: str, end_str: str) -> list[tuple[int, int]]:
    """
    解析月份范围，返回 (year, month) 元组列表。
    支持格式: YYYY-MM
    """
    try:
        start_parts = start_str.split('-')
        end_parts = end_str.split('-')

        start_year, start_month = int(start_parts[0]), int(start_parts[1])
        end_year, end_month = int(end_parts[0]), int(end_parts[1])
    except (ValueError, IndexError):
        raise ValueError("日期格式错误，请使用 YYYY-MM 格式 (例: 2025-01)")

    months = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


# ============================================================
# 主程序入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="AEMO NEM 澳洲国家电力市场 - 历史交易电价爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 下载 2025年1月至3月所有州的交易电价
  python aemo_nem_scraper.py --start 2025-01 --end 2025-03

  # 仅下载新南威尔士和维多利亚的数据
  python aemo_nem_scraper.py --start 2025-01 --end 2025-01 --regions NSW1,VIC1

  # 指定输出文件
  python aemo_nem_scraper.py --start 2024-06 --end 2024-12 --output data/prices.csv

数据来源: AEMO (Australian Energy Market Operator)
声明: 使用此数据请注明来源 "AEMO"，详见其使用条款。
        """
    )
    parser.add_argument('--start', required=True, help='起始月份 (YYYY-MM)')
    parser.add_argument('--end', required=True, help='结束月份 (YYYY-MM)')
    parser.add_argument('--regions', default=','.join(ALL_REGIONS),
                        help=f'区域代码，逗号分隔 (默认: {",".join(ALL_REGIONS)})')
    parser.add_argument('--output', default=None,
                        help='输出 CSV 文件路径 (选填，若填此项则同时产生大 CSV)')
    parser.add_argument('--db-path', default="aemo_data.db",
                        help='输出 SQLite 数据库库路径 (默认: aemo_data.db)')

    args = parser.parse_args()

    # 解析参数
    regions = [r.strip().upper() for r in args.regions.split(',')]
    invalid_regions = [r for r in regions if r not in ALL_REGIONS]
    if invalid_regions:
        print(f"[X] 无效的区域代码: {invalid_regions}")
        print(f"    有效代码: {ALL_REGIONS}")
        return

    months = parse_month_range(args.start, args.end)

    output_path = args.output or f"output/aemo_trading_prices_{args.start}_{args.end}.csv"

    # 开始爬取
    print("=" * 60)
    print("AEMO NEM 历史交易电价爬取工具")
    print("=" * 60)
    print(f"时间范围: {args.start} -> {args.end} ({len(months)} 个月)")
    print(f"目标区域: {', '.join(regions)}")
    print(f"数据存储库: {args.db_path}")
    if output_path:
        print(f"同时输出 CSV: {output_path}")
    print(f"请求延迟: {REQUEST_DELAY}s")
    print("=" * 60)
    print()

    db = DatabaseManager(args.db_path)
    all_records_for_csv = [] if output_path else None

    for i, (year, month) in enumerate(months, 1):
        log(f"[{i}/{len(months)}] 正在处理 {year}-{month:02d}...")
        records = download_and_parse_tradingprice(year, month, regions)
        
        # 批量入库
        if records:
            try:
                db.batch_insert(records)
                log(f"  [DB] 该月数据已写入/更新至数据库")
            except Exception as e:
                log(f"  [DB_ERR] 写入数据库失败: {e}")

        # 内存保留以便生成最后的大 CSV（如果指定了 output_path）
        if output_path and records:
            all_records_for_csv.extend(records)

        # 礼貌延迟
        if i < len(months):
            time.sleep(REQUEST_DELAY)

    # 汇总总结
    stats = db.get_summary()
    if stats.get("tables"):
        print("\n" + "=" * 60)
        print("[*] 数据库目前状态摘要")
        print("=" * 60)
        for t in stats["tables"]:
            print(f"  表 {t['table']:<22} | 记录数: {t['count']:>9,} | {t['min_date']} -> {t['max_date']}")
        print("=" * 60)

    # 如果有选择导出 CSV
    if output_path and all_records_for_csv:
        save_to_csv(all_records_for_csv, output_path)


if __name__ == '__main__':
    main()
