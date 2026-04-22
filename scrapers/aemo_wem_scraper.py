"""
AEMO WEM 西澳电力市场 - 交易电价爬取工具
=================================================
数据来源: https://data.wa.aemo.com.au
数据内容: WEM (西澳) 的30分钟交易结算电价 (Reference Trading Price)
时区说明: 所有时间戳为 AWST (UTC+8), 与 NEM 的 AEST (UTC+10) 相差 2 小时
         数据存入数据库时保持原始 AWST 时间, 由下游分析层负责对齐
"""

import requests
import zipfile
import io
import json
import time
import argparse
import logging
from datetime import datetime, timedelta, timezone

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from database import DatabaseManager

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# 请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_url(url: str, max_retries: int = 8) -> requests.Response | None:
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=45)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 404:
                return None  # No data for this date, ignore silently mostly
            else:
                time.sleep(1)
        except requests.RequestException as e:
            if attempt == max_retries:
                logger.error(f"[!] Request error: {e} - {url}")
            else:
                logger.debug(f"Retrying ({attempt}/{max_retries}) after error: {e}")
                time.sleep(attempt * 1.5)
    return None

# AWST = UTC+8 (Australian Western Standard Time)
AWST = timezone(timedelta(hours=8))


def _parse_wem_timestamp(raw_interval: str) -> str:
    """
    Parse WEM ISO-8601 timestamp and normalize to AWST.

    WEM API returns timestamps like "2023-10-01T08:00:00+08:00".
    We validate the timezone is AWST, convert if needed, then store
    as "YYYY-MM-DD HH:MM:SS" in AWST for consistency.

    This is critical: NEM timestamps are AEST (UTC+10). If we blindly
    strip the timezone, a 2-hour error creeps into any cross-market
    analysis.
    """
    if not raw_interval:
        return raw_interval

    try:
        # Python 3.11+ handles the colon in +08:00 natively
        dt = datetime.fromisoformat(raw_interval)
    except ValueError:
        # Fallback: strip timezone suffix and treat as AWST
        clean = raw_interval.replace("T", " ")[:19]
        return clean

    # If the timestamp has timezone info, convert to AWST
    if dt.tzinfo is not None:
        dt = dt.astimezone(AWST)

    # Store as naive string in AWST
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def process_wem_json(json_data: dict | list, db: DatabaseManager):
    """Parse JSON payload and batch insert to DB.

    All WEM timestamps are normalized to AWST before storage.
    The 30-minute settlement interval is preserved as-is;
    any upsampling to 5-min is handled in the analysis layer.
    """
    if isinstance(json_data, list):
        prices = json_data
    else:
        prices = json_data.get('data', {}).get('referenceTradingPrices', [])

    if not prices:
        return 0

    records_to_insert = []
    for item in prices:
        raw_interval = item.get("tradingInterval", "")
        clean_date = _parse_wem_timestamp(raw_interval)

        price = item.get("referenceTradingPrice")
        if price is None:
            continue

        try:
            price_val = round(float(price), 2)
        except (ValueError, TypeError):
            logger.warning(f"Skipping invalid price value: {price}")
            continue

        records_to_insert.append({
            "settlement_date": clean_date,
            "region_id": "WEM",
            "rrp_aud_mwh": price_val,
        })

    if records_to_insert:
        db.batch_insert(records_to_insert)

    return len(records_to_insert)

def scrape_wem_date(target_date: datetime, db: DatabaseManager):
    """Scape data for a specific date (tries previous/ ZIP first, then current/ JSON)."""
    date_str_zip = target_date.strftime("%Y%m%d")
    url_zip = f"https://data.wa.aemo.com.au/public/market-data/wemde/referenceTradingPrice/previous/ReferenceTradingPrice_{date_str_zip}.zip"
    
    total_inserted = 0
    
    # Try Historical ZIP
    resp = fetch_url(url_zip, max_retries=2)
    if resp and resp.status_code == 200:
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                # WEM API packs json into zip
                for name in z.namelist():
                    if name.endswith('.json'):
                        with z.open(name) as f:
                            data = json.loads(f.read().decode('utf-8'))
                            total_inserted += process_wem_json(data, db)
            return total_inserted
        except zipfile.BadZipFile:
            logger.warning(f"Bad zip file for {date_str_zip}")
    
    # If historical ZIP not available, try current JSON
    date_str_json = target_date.strftime("%Y-%m-%d")
    url_json = f"https://data.wa.aemo.com.au/public/market-data/wemde/referenceTradingPrice/current/ReferenceTradingPrice_{date_str_json}.json"
    
    resp_current = fetch_url(url_json, max_retries=1)
    if resp_current and resp_current.status_code == 200:
        try:
            data = resp_current.json()
            total_inserted += process_wem_json(data, db)
            return total_inserted
        except json.JSONDecodeError:
            pass
            
    return total_inserted

def scrape_wem_range(start_date: str, end_date: str, db: DatabaseManager):
    """Scrape WEM data from start_date to end_date."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    curr_dt = start_dt
    total_records = 0
    
    logger.info(f"Starting WEM scrape from {start_date} to {end_date}")
    
    while curr_dt <= end_dt:
        count = scrape_wem_date(curr_dt, db)
        if count > 0:
            logger.info(f"  [+] {curr_dt.strftime('%Y-%m-%d')} - {count} records saved.")
            total_records += count
        else:
            logger.debug(f"  [-] {curr_dt.strftime('%Y-%m-%d')} - No data found.")
        curr_dt += timedelta(days=1)
        
    logger.info(f"WEM Scrape Complete! Total records inserted: {total_records}")
    return total_records

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEMO WEM Data Scraper")
    parser.add_argument("--start", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--db", type=str, default="../data/aemo_data.db", help="SQLite database file")
    
    args = parser.parse_args()
    
    db_manager = DatabaseManager(args.db)
    scrape_wem_range(args.start, args.end, db_manager)
