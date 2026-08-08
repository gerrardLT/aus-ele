"""AEMO NEM pre-dispatch 历史归档抓取器（P0-1 闭环滚动回测的数据基础）。

背景（2026-08-05，任务记录-2026-08-05-算法系统性评估）:
    dispatch_optimizer.run_rolling_forecast 长期是占位符（回落完美前瞻），
    而完美前瞻系统性高估可达成收入（price-maker/forecast-error 文献一致结论）。
    闭环需要**历史上真实发出过的 pre-dispatch 价格预测**——NEMWeb Archive
    保存了 2025-07-13 起每周一个 PUBLIC_PREDISPATCHIS 压缩包（~300MB/周）：
    https://www.nemweb.com.au/Reports/Archive/PredispatchIS_Reports/

    本脚本下载指定周的归档，流式解析其中每个 30 分钟窗口的内层 zip（zip 套
    zip）的 REGION_PRICES 段（5 区域 × 56 个 30 分钟前向间隔 ≈ 28h 视野），
    落入 PostgreSQL 表 ``predispatch_price_forecast``。每周 336 个窗口 ×
    280 行 ≈ 9.4 万行（紧凑）。

    归档实测结构（2026-08-05 探测）：外层 zip 每 30 分钟一个内层 zip，
    内层单个 CSV，C 头行含 run 时刻；REGION_PRICES 表含 DATETIME
    （目标间隔时间戳）与 RRP，无需由 PERIODID 推算。

用法:
    cd backend && python ../scrapers/aemo_predispatch_archive.py --list
    cd backend && python ../scrapers/aemo_predispatch_archive.py --week 2026-06-21
    cd backend && python ../scrapers/aemo_predispatch_archive.py --week 2026-06-21 --parse-only
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import requests  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("predispatch_archive")

ARCHIVE_LISTING_URL = "https://www.nemweb.com.au/Reports/Archive/PredispatchIS_Reports/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
DOWNLOAD_DIR = REPO / "data" / "predispatch_archive"
TABLE_NAME = "predispatch_price_forecast"
NEM_REGIONS = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")


# ---------------------------------------------------------------------------
# Archive listing / download
# ---------------------------------------------------------------------------


def list_archive_files() -> list[dict]:
    """枚举归档目录中的所有周归档文件。"""
    res = requests.get(ARCHIVE_LISTING_URL, headers=HEADERS, timeout=30)
    res.raise_for_status()
    entries = []
    for href, size in re.findall(
        r'href=["\']([^"\']+PUBLIC_PREDISPATCHIS_\d{8}_\d{8}\.zip)["\'][^>]*>\s*</a></td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*>\s*([\d,]+)',
        res.text,
        flags=re.IGNORECASE,
    ):
        match = re.search(r"PUBLIC_PREDISPATCHIS_(\d{8})_(\d{8})\.zip", href, re.IGNORECASE)
        if not match:
            continue
        entries.append(
            {
                "filename": Path(href).name,
                "href": href,
                "week_start": match.group(1),
                "week_end": match.group(2),
                "size_bytes": int(size.replace(",", "")) if size else 0,
            }
        )
    # 宽松回退：仅匹配 href（不同目录页 HTML 结构时）
    if not entries:
        for href in re.findall(r'href=["\']([^"\']+PUBLIC_PREDISPATCHIS_\d{8}_\d{8}\.zip)', res.text, flags=re.IGNORECASE):
            match = re.search(r"PUBLIC_PREDISPATCHIS_(\d{8})_(\d{8})\.zip", href, re.IGNORECASE)
            entries.append(
                {
                    "filename": Path(href).name,
                    "href": href,
                    "week_start": match.group(1),
                    "week_end": match.group(2),
                    "size_bytes": 0,
                }
            )
    entries.sort(key=lambda e: e["week_start"])
    return entries


def find_archive_for_week(week_start: str) -> dict:
    """按周起始日（YYYY-MM-DD）定位归档文件。"""
    target = datetime.strptime(week_start, "%Y-%m-%d").strftime("%Y%m%d")
    for entry in list_archive_files():
        if entry["week_start"] == target:
            return entry
    raise SystemExit(f"未找到周起始日为 {target} 的归档文件（用 --list 查看可用周）")


def download_archive(entry: dict) -> Path:
    """下载周归档 zip 到 data/predispatch_archive/（断点跳过已存在文件）。"""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOAD_DIR / entry["filename"]
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("归档已存在，跳过下载: %s (%.0f MB)", dest.name, dest.stat().st_size / 1e6)
        return dest

    url = urljoin(ARCHIVE_LISTING_URL, entry["href"])
    logger.info("开始下载: %s", url)
    start = datetime.now()
    with requests.get(url, headers=HEADERS, stream=True, timeout=60) as res:
        res.raise_for_status()
        total = int(res.headers.get("Content-Length", 0))
        done = 0
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for chunk in res.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    elapsed = (datetime.now() - start).total_seconds()
                    speed = done / elapsed / 1e6 if elapsed > 0 else 0
                    print(
                        f"\r  {done/1e6:.0f}/{total/1e6:.0f} MB "
                        f"({done*100//total}%) {speed:.2f} MB/s",
                        end="",
                        flush=True,
                    )
        tmp.rename(dest)
    elapsed = (datetime.now() - start).total_seconds()
    logger.info("下载完成: %s（%.0f MB，%.0f 秒）", dest.name, dest.stat().st_size / 1e6, elapsed)
    return dest


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def _parse_run_csv(text: str) -> tuple[str, list[tuple]]:
    """解析单个内层 CSV（一个 pre-dispatch 窗口）。

    Returns:
        (run_datetime, [(region_id, interval_datetime, rrp), ...])
        run_datetime 取自 C 头行（格式 2026/06/21,00:01:51）。
    """
    lines = text.splitlines()

    # C 头行: C,NEMP.WORLD,PREDISPATCHIS,AEMO,PUBLIC,2026/06/21,00:01:51,...
    run_dt = ""
    for line in lines:
        if line.startswith("C,"):
            parts = line.split(",")
            if len(parts) >= 7:
                run_dt = f"{parts[5].strip()} {parts[6].strip()}".replace("/", "-")
            break

    header_cols: list[str] | None = None
    rows: list[tuple] = []
    for idx, line in enumerate(lines):
        if not line.startswith("I,"):
            continue
        upper = line.upper()
        if "REGION_PRICES" in upper and "REGIONID" in upper and "RRP" in upper:
            header_cols = [c.strip().strip('"') for c in line.split(",")]
            for data_line in lines[idx + 1:]:
                if data_line.startswith("I,") or data_line.startswith("100,"):
                    break
                if not data_line.startswith("D,") or "REGION_PRICES" not in data_line:
                    continue
                rec = dict(zip(header_cols, data_line.split(",")))
                region = rec.get("REGIONID", "").strip().strip('"').upper()
                if region not in NEM_REGIONS:
                    continue
                try:
                    interval_dt = rec.get("DATETIME", "").strip().strip('"').replace("/", "-")
                    rrp = float(rec.get("RRP", ""))
                except (ValueError, TypeError):
                    continue
                rows.append((region, interval_dt, rrp))
            break
    return run_dt, rows


def parse_week_zip(zip_path: Path, db) -> dict:
    """流式解析周归档并批量落库（幂等：按 (run_datetime, region_id, period_id) 去重）。"""
    week_start = re.search(r"(\d{8})_", zip_path.name).group(1)
    week_date = datetime.strptime(week_start, "%Y%m%d").date()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                run_datetime  TIMESTAMP NOT NULL,
                region_id     VARCHAR(8) NOT NULL,
                interval_time TIMESTAMP NOT NULL,
                rrp           DOUBLE PRECISION NOT NULL,
                week_start    DATE NOT NULL,
                PRIMARY KEY (run_datetime, region_id, interval_time)
            )
            """
        )
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_week ON {TABLE_NAME} (week_start, region_id)")
        conn.commit()

        inserted = 0
        files_parsed = 0
        buffer: list[tuple] = []
        with zipfile.ZipFile(zip_path) as archive:
            members = [m for m in archive.namelist() if m.lower().endswith(".zip")]
            logger.info("归档包含 %d 个内层窗口 zip", len(members))
            for member in members:
                try:
                    inner_bytes = archive.open(member).read()
                    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zip:
                        csv_names = [n for n in inner_zip.namelist() if n.lower().endswith(".csv")]
                        if not csv_names:
                            continue
                        text = inner_zip.open(csv_names[0]).read().decode("utf-8-sig", errors="replace")
                except Exception as exc:
                    logger.warning("跳过损坏的窗口文件 %s: %s", member, exc)
                    continue
                run_dt, rows = _parse_run_csv(text)
                files_parsed += 1
                if not run_dt:
                    continue
                for region, interval_dt, rrp in rows:
                    buffer.append((run_dt, region, interval_dt, rrp, week_date))
                if len(buffer) >= 20000:
                    inserted += _flush(cursor, buffer)
                    buffer = []
                if files_parsed % 50 == 0:
                    logger.info("进度: %d/%d 窗口, 累计落库 %d 行", files_parsed, len(members), inserted)
        if buffer:
            inserted += _flush(cursor, buffer)
        conn.commit()

        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE week_start = %s", (week_date,))
        week_rows = cursor.fetchone()[0]

    return {"files_parsed": files_parsed, "inserted_rows": inserted, "week_rows_total": week_rows}


def _flush(cursor, buffer: list[tuple]) -> int:
    cursor.executemany(
        f"""
        INSERT INTO {TABLE_NAME} (run_datetime, region_id, interval_time, rrp, week_start)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (run_datetime, region_id, interval_time) DO NOTHING
        """,
        buffer,
    )
    return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="AEMO NEM pre-dispatch 历史归档抓取")
    parser.add_argument("--list", action="store_true", help="列出可用周归档")
    parser.add_argument("--week", help="周起始日（YYYY-MM-DD，须为归档中的周日）")
    parser.add_argument("--parse-only", action="store_true", help="跳过下载，直接解析已有 zip")
    args = parser.parse_args()

    if args.list or not args.week:
        for entry in list_archive_files():
            size = f"{entry['size_bytes']/1e6:.0f} MB" if entry["size_bytes"] else "?"
            print(f"{entry['week_start']} ~ {entry['week_end']}  {size}  {entry['filename']}")
        return 0

    entry = find_archive_for_week(args.week)
    if args.parse_only:
        zip_path = DOWNLOAD_DIR / entry["filename"]
        if not zip_path.exists():
            raise SystemExit(f"本地不存在 {zip_path}，请先下载（去掉 --parse-only）")
    else:
        zip_path = download_archive(entry)

    from deps import get_db

    stats = parse_week_zip(zip_path, get_db())
    logger.info("完成: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
