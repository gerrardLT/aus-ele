"""
下载 WEM 全量历史数据（从 WEMDE 上线日 2023-10-01 至今）。

数据源：data.wa.aemo.com.au 公开文件服务器
包含：
  - DispatchSolution ZIP（ESS 价格 + 容量 + 约束）
  - ReferenceTradingPrice ZIP（RTP 30 分钟价格）
  - FCESS 设施能力 CSV

用法：
  # 下载全部（2023-10-01 至今）
  python scripts/download_wem_all.py

  # 指定日期范围
  python scripts/download_wem_all.py --start 2024-01-01 --end 2024-12-31

  # 只下载 RTP（小文件，快速）
  python scripts/download_wem_all.py --rtp-only

  # 只下载 Dispatch Solution（大文件）
  python scripts/download_wem_all.py --dispatch-only

  # 跳过已存在的文件（断点续传）
  python scripts/download_wem_all.py --skip-existing

  # 指定下载目录
  python scripts/download_wem_all.py --output-dir G:\\wem_data

注意：
  - Dispatch Solution 每天约 285 MB，全量约 260 GB
  - RTP 每天约 50 KB，全量约 50 MB
  - 支持断点续传（Range 请求）
  - 默认 1 秒间隔避免被限流
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────

WEM_BASE = "https://data.wa.aemo.com.au/public/market-data/wemde"
DISPATCH_BASE = f"{WEM_BASE}/dispatchSolution/dispatchData/previous"
RTP_BASE = f"{WEM_BASE}/referenceTradingPrice/previous"
FCESS_URL = "https://data.wa.aemo.com.au/public/public-data/datafiles/fcess/fcess.csv"

# WEMDE 上线日期
WEMDE_START = datetime(2023, 10, 1)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 下载配置
CHUNK_SIZE = 512 * 1024  # 512 KB
MAX_RETRIES = 3
RETRY_DELAY = 5
REQUEST_INTERVAL = 1.0  # 请求间隔（秒）


# ─────────────────────────────────────────────
# 下载函数
# ─────────────────────────────────────────────


def download_file(url: str, output_path: Path, *, skip_existing: bool = False) -> bool:
    """下载文件，支持断点续传。

    Returns:
        True 如果下载成功或文件已存在，False 如果失败。
    """
    if skip_existing and output_path.exists() and output_path.stat().st_size > 0:
        logger.debug(f"  跳过（已存在）: {output_path.name}")
        return True

    # 检查已下载的部分（断点续传）
    downloaded = 0
    if output_path.exists():
        downloaded = output_path.stat().st_size

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request_headers = dict(HEADERS)
            if downloaded > 0:
                request_headers["Range"] = f"bytes={downloaded}-"

            response = requests.get(
                url,
                headers=request_headers,
                verify=False,
                timeout=600,
                stream=True,
            )

            if response.status_code == 404:
                logger.warning(f"  404 Not Found: {url}")
                return False

            if response.status_code == 416:
                # Range not satisfiable — file already complete
                logger.info(f"  已完成: {output_path.name}")
                return True

            if response.status_code not in (200, 206):
                logger.warning(
                    f"  HTTP {response.status_code} (attempt {attempt}): {url}"
                )
                time.sleep(RETRY_DELAY * attempt)
                continue

            # 如果服务器不支持 Range，重新开始
            if downloaded > 0 and response.status_code == 200:
                downloaded = 0

            # 获取总大小
            total = None
            content_range = response.headers.get("Content-Range", "")
            if content_range:
                import re
                match = re.search(r"/(\d+)$", content_range)
                if match:
                    total = int(match.group(1))
            elif response.headers.get("Content-Length"):
                cl = int(response.headers["Content-Length"])
                total = downloaded + cl if response.status_code == 206 else cl

            # 写入文件
            mode = "ab" if downloaded > 0 and response.status_code == 206 else "wb"
            with open(output_path, mode) as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 进度显示
                        if total and total > 10 * 1024 * 1024:  # 只对 >10MB 文件显示进度
                            pct = downloaded / total * 100
                            mb_dl = downloaded / 1024 / 1024
                            mb_total = total / 1024 / 1024
                            sys.stdout.write(
                                f"\r  {output_path.name}: {mb_dl:.1f}/{mb_total:.1f} MB ({pct:.0f}%)"
                            )
                            sys.stdout.flush()

            if total and total > 10 * 1024 * 1024:
                sys.stdout.write("\n")
                sys.stdout.flush()

            logger.info(
                f"  ✓ {output_path.name} ({downloaded / 1024 / 1024:.1f} MB)"
            )
            return True

        except (requests.RequestException, IOError) as exc:
            logger.warning(f"  下载失败 (attempt {attempt}): {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    logger.error(f"  ✗ 下载失败（已重试 {MAX_RETRIES} 次）: {output_path.name}")
    return False


# ─────────────────────────────────────────────
# 主逻辑
# ─────────────────────────────────────────────


def download_dispatch_solutions(
    start: datetime, end: datetime, output_dir: Path, *, skip_existing: bool = False
) -> dict:
    """下载 Dispatch Solution ZIP 文件。"""
    dispatch_dir = output_dir / "dispatch_solution"
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0}
    current = start

    while current <= end:
        stats["total"] += 1
        date_str = current.strftime("%Y%m%d")
        filename = f"DispatchSolutionReference_{date_str}.zip"
        url = f"{DISPATCH_BASE}/{filename}"
        output_path = dispatch_dir / filename

        if skip_existing and output_path.exists() and output_path.stat().st_size > 0:
            stats["skipped"] += 1
            logger.debug(f"  跳过: {filename}")
        else:
            logger.info(f"[{stats['total']}] 下载 Dispatch Solution: {date_str}")
            if download_file(url, output_path, skip_existing=skip_existing):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        current += timedelta(days=1)
        time.sleep(REQUEST_INTERVAL)

    return stats


def download_rtp_prices(
    start: datetime, end: datetime, output_dir: Path, *, skip_existing: bool = False
) -> dict:
    """下载 Reference Trading Price ZIP 文件。"""
    rtp_dir = output_dir / "reference_trading_price"
    rtp_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0}
    current = start

    while current <= end:
        stats["total"] += 1
        date_str = current.strftime("%Y%m%d")
        filename = f"ReferenceTradingPrice_{date_str}.zip"
        url = f"{RTP_BASE}/{filename}"
        output_path = rtp_dir / filename

        if skip_existing and output_path.exists() and output_path.stat().st_size > 0:
            stats["skipped"] += 1
        else:
            logger.info(f"[{stats['total']}] 下载 RTP: {date_str}")
            if download_file(url, output_path, skip_existing=skip_existing):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        current += timedelta(days=1)
        time.sleep(0.5)  # RTP 文件小，间隔短一些

    return stats


def download_fcess_capabilities(output_dir: Path) -> bool:
    """下载 FCESS 设施能力 CSV。"""
    output_path = output_dir / "fcess_capabilities.csv"
    logger.info("下载 FCESS 设施能力...")
    return download_file(FCESS_URL, output_path)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(
        description="下载 WEM 全量历史数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载全部（2023-10-01 至今）
  python scripts/download_wem_all.py

  # 指定范围
  python scripts/download_wem_all.py --start 2024-06-01 --end 2024-12-31

  # 只下载 RTP（快速，每天约 50KB）
  python scripts/download_wem_all.py --rtp-only

  # 断点续传（跳过已下载的文件）
  python scripts/download_wem_all.py --skip-existing
        """,
    )
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD（默认 2023-10-01）")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD（默认昨天）")
    parser.add_argument("--output-dir", default="./wem_raw_data", help="输出目录（默认 ./wem_raw_data）")
    parser.add_argument("--dispatch-only", action="store_true", help="只下载 Dispatch Solution")
    parser.add_argument("--rtp-only", action="store_true", help="只下载 RTP 价格")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的文件")
    parser.add_argument("--interval", type=float, default=1.0, help="请求间隔秒数（默认 1.0）")
    return parser.parse_args()


def main():
    args = parse_args()

    global REQUEST_INTERVAL
    REQUEST_INTERVAL = args.interval

    # 日期范围
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start = WEMDE_START

    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end = datetime.now() - timedelta(days=1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_days = (end - start).days + 1

    logger.info("=" * 60)
    logger.info("WEM 全量数据下载")
    logger.info("=" * 60)
    logger.info(f"日期范围: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')} ({total_days} 天)")
    logger.info(f"输出目录: {output_dir.resolve()}")
    logger.info(f"请求间隔: {REQUEST_INTERVAL}s")
    logger.info(f"跳过已存在: {args.skip_existing}")

    if not args.rtp_only:
        estimated_gb = total_days * 285 / 1024
        logger.info(f"Dispatch Solution 预估: {estimated_gb:.1f} GB")
    if not args.dispatch_only:
        estimated_mb = total_days * 0.05
        logger.info(f"RTP 价格预估: {estimated_mb:.1f} MB")

    logger.info("=" * 60)

    # 下载 FCESS 能力
    download_fcess_capabilities(output_dir)

    # 下载 RTP
    if not args.dispatch_only:
        logger.info("\n--- RTP 价格下载 ---")
        rtp_stats = download_rtp_prices(start, end, output_dir, skip_existing=args.skip_existing)
        logger.info(
            f"RTP 完成: {rtp_stats['success']} 成功, "
            f"{rtp_stats['skipped']} 跳过, {rtp_stats['failed']} 失败"
        )

    # 下载 Dispatch Solution
    if not args.rtp_only:
        logger.info("\n--- Dispatch Solution 下载 ---")
        dispatch_stats = download_dispatch_solutions(
            start, end, output_dir, skip_existing=args.skip_existing
        )
        logger.info(
            f"Dispatch 完成: {dispatch_stats['success']} 成功, "
            f"{dispatch_stats['skipped']} 跳过, {dispatch_stats['failed']} 失败"
        )

    logger.info("\n" + "=" * 60)
    logger.info("全部完成！")
    logger.info(f"数据保存在: {output_dir.resolve()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
