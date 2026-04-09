"""
AEMO WEM ESS (Essential System Services) 辅助服务价格爬取工具
=============================================================
数据来源: https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/
服务类型: energy, regulationRaise, regulationLower, contingencyRaise, contingencyLower, rocof
历史范围: 2023-10-01 ~ 至今 (WEM改革后)

注意: 每天ZIP约230MB，下载约需3-5分钟/天(取决于网速)
     建议分批运行，每次爬取一周或一个月的数据

使用方法:
    python aemo_wem_ess_scraper.py --start 2025-01-01 --end 2025-01-07
    python aemo_wem_ess_scraper.py --start 2025-01-01 --end 2025-01-31
"""

import sys
import requests
import zipfile
import io
import json
import time
import argparse
import sqlite3
import logging
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================
WEM_BASE = "https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
ESS_SERVICES = ["energy", "regulationRaise", "regulationLower",
                "contingencyRaise", "contingencyLower", "rocof"]


# ============================================================
# 数据库
# ============================================================
class WemEssDB:
    TABLE = "wem_ess_price"

    def __init__(self, db_path="aemo_data.db"):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dispatch_interval TEXT NOT NULL,
                    energy_price REAL,
                    regulation_raise_price REAL,
                    regulation_lower_price REAL,
                    contingency_raise_price REAL,
                    contingency_lower_price REAL,
                    rocof_price REAL,
                    UNIQUE(dispatch_interval)
                )
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_interval
                ON {self.TABLE} (dispatch_interval)
            """)
            conn.commit()

    def has_date(self, date_str: str) -> bool:
        """检查某天是否已有足够数据（至少200条=可用的一天）"""
        with sqlite3.connect(self.db_path) as conn:
            r = conn.execute(
                f"SELECT COUNT(*) FROM {self.TABLE} WHERE dispatch_interval LIKE ?",
                (f"{date_str}%",)
            ).fetchone()
            return (r[0] or 0) >= 200

    def batch_insert(self, records: list[dict]) -> int:
        if not records:
            return 0
        rows = [(
            r["dispatch_interval"],
            r.get("energy_price"),
            r.get("regulation_raise_price"),
            r.get("regulation_lower_price"),
            r.get("contingency_raise_price"),
            r.get("contingency_lower_price"),
            r.get("rocof_price"),
        ) for r in records]

        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.executemany(f"""
                    INSERT OR IGNORE INTO {self.TABLE}
                    (dispatch_interval, energy_price,
                     regulation_raise_price, regulation_lower_price,
                     contingency_raise_price, contingency_lower_price,
                     rocof_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                return len(rows)
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"DB error: {e}")
                return 0

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(f"SELECT COUNT(*) FROM {self.TABLE}").fetchone()[0]
            mm = conn.execute(
                f"SELECT MIN(dispatch_interval), MAX(dispatch_interval) FROM {self.TABLE}"
            ).fetchone()
            return {"count": count, "min": mm[0], "max": mm[1]}


# ============================================================
# 解析
# ============================================================
def parse_ess_prices(raw: bytes) -> list[dict]:
    """从dispatch JSON 提取 Reference+Dispatch 的 ESS 价格"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    wrapper = data.get("data", data)
    sd_list = wrapper.get("solutionData", [])
    results = []

    for sd in sd_list:
        if sd.get("scenario") != "Reference" or sd.get("dispatchType") != "Dispatch":
            continue

        interval = sd.get("dispatchInterval", "")
        if not interval:
            continue

        # "2026-04-08T15:50:00+08:00" -> "2026-04-08 15:50:00"
        clean = interval.replace("T", " ")[:19]

        prices_raw = sd.get("prices", [])
        pm = {}

        # prices 可能是 list[dict] 或 dict
        if isinstance(prices_raw, list):
            for p in prices_raw:
                if isinstance(p, dict):
                    svc = p.get("marketService", "")
                    val = p.get("price")
                    if svc and val is not None:
                        pm[svc] = float(val)
        elif isinstance(prices_raw, dict):
            for svc, val in prices_raw.items():
                if val is not None:
                    pm[svc] = float(val) if isinstance(val, (int, float)) else val

        if pm:
            results.append({
                "dispatch_interval": clean,
                "energy_price": pm.get("energy"),
                "regulation_raise_price": pm.get("regulationRaise"),
                "regulation_lower_price": pm.get("regulationLower"),
                "contingency_raise_price": pm.get("contingencyRaise"),
                "contingency_lower_price": pm.get("contingencyLower"),
                "rocof_price": pm.get("rocof"),
            })

    return results


# ============================================================
# 下载
# ============================================================
def download_zip(url: str, label: str, max_retries: int = 3) -> bytes | None:
    """流式下载带进度，含重试"""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=600,
                                verify=False, stream=True)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning(f"  HTTP {resp.status_code} (attempt {attempt})")
                time.sleep(attempt * 5)
                continue

            total = int(resp.headers.get('Content-Length', 0))
            chunks = []
            downloaded = 0

            for chunk in resp.iter_content(chunk_size=256 * 1024):
                chunks.append(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    mb_dl = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    sys.stdout.write(f"\r  {label}: {mb_dl:.1f}/{mb_total:.1f} MB ({pct:.0f}%)")
                    sys.stdout.flush()

            if total > 0:
                sys.stdout.write("\n")
                sys.stdout.flush()

            return b"".join(chunks)

        except requests.RequestException as e:
            logger.warning(f"  下载失败 (attempt {attempt}): {e}")
            if attempt < max_retries:
                wait = attempt * 10
                logger.info(f"  等待 {wait}秒 后重试...")
                time.sleep(wait)

    return None


# ============================================================
# 主逻辑
# ============================================================
def scrape_day(target_date: datetime, db: WemEssDB) -> int:
    """爬取某天 ESS 价格, 返回记录数或 -1(已存在)"""
    date_str = target_date.strftime("%Y-%m-%d")
    date_compact = target_date.strftime("%Y%m%d")

    if db.has_date(date_str):
        return -1

    zip_url = f"{WEM_BASE}/previous/DispatchSolutionReference_{date_compact}.zip"
    raw = download_zip(zip_url, date_str)
    if not raw:
        return 0

    all_records = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            json_names = sorted([n for n in z.namelist() if n.endswith('.json')])
            for name in json_names:
                with z.open(name) as f:
                    records = parse_ess_prices(f.read())
                    all_records.extend(records)
    except zipfile.BadZipFile:
        logger.warning(f"  ZIP损坏: {date_compact}")
        return 0

    if all_records:
        db.batch_insert(all_records)
    return len(all_records)


def main():
    parser = argparse.ArgumentParser(description="WEM ESS 辅助服务价格爬取")
    parser.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--db", default="aemo_data.db", help="数据库路径")
    args = parser.parse_args()

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    except ValueError:
        print("错误: 日期格式应为 YYYY-MM-DD")
        sys.exit(1)

    db = WemEssDB(args.db)
    total_days = (end_dt - start_dt).days + 1
    total_records = 0
    skipped = 0

    logger.info("=" * 55)
    logger.info("  WEM ESS 辅助服务价格爬取")
    logger.info(f"  范围: {args.start} ~ {args.end} ({total_days} 天)")
    logger.info(f"  服务: {', '.join(ESS_SERVICES)}")
    logger.info("  提示: 每天ZIP约230MB，下载约3-5分钟")
    logger.info("=" * 55)

    curr = start_dt
    day_n = 0

    while curr <= end_dt:
        day_n += 1
        label = curr.strftime("%Y-%m-%d")

        count = scrape_day(curr, db)

        if count == -1:
            skipped += 1
            logger.info(f"  [{day_n}/{total_days}] {label} - 跳过(已有)")
        elif count > 0:
            total_records += count
            logger.info(f"  [{day_n}/{total_days}] {label} - {count} 条 ✓")
        else:
            logger.info(f"  [{day_n}/{total_days}] {label} - 无数据")

        curr += timedelta(days=1)
        if count != -1:
            time.sleep(2)

    stats = db.get_stats()
    logger.info("=" * 55)
    logger.info("  爬取完成!")
    logger.info(f"  新增: {total_records} 条 | 跳过: {skipped} 天")
    logger.info(f"  数据库: {stats['count']} 条")
    if stats["min"]:
        logger.info(f"  范围: {stats['min']} ~ {stats['max']}")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
