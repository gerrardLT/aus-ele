#!/usr/bin/env python3
"""
WEM CSV bulk import script — designed for 32GB+ historical data.

Key design decisions:
- Streaming CSV parsing (line-by-line, never loads full file)
- PostgreSQL COPY protocol for bulk insert (100x faster than INSERT)
- Automatic CSV type detection from headers
- Supports single files, directories (recursive), and ZIP archives
- Progress reporting with ETA
- Resumable: tracks completed files to skip on re-run

Usage:
    # Import a single CSV
    python scripts/wem_bulk_import.py --input data/wem_csv/ReferenceTradingPrice_20240101.csv

    # Import all CSVs in a directory
    python scripts/wem_bulk_import.py --input data/wem_csv/

    # Import with custom PG connection
    python scripts/wem_bulk_import.py --input data/wem_csv/ --dsn "postgresql://aemo:pass@localhost:5432/aemo_data"

    # Dry run (show plan without writing)
    python scripts/wem_bulk_import.py --input data/wem_csv/ --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

AWST = timezone(timedelta(hours=8))
COPY_BATCH_SIZE = 50_000  # Rows per COPY operation
PROGRESS_FILE = ".wem_import_progress.json"

# ---------------------------------------------------------------------------
# Column detection heuristics
# ---------------------------------------------------------------------------

# Trading price CSV headers (AEMO various formats)
_TRADING_PRICE_PATTERNS = {
    "tradinginterval", "trading_interval", "settlement_date",
    "referencetradingprice", "reference_trading_price", "rrp", "rrp_aud_mwh",
}

# ESS market CSV headers
_ESS_PATTERNS = {
    "dispatchinterval", "dispatch_interval",
    "energyprice", "energy_price",
    "regulationraiseprice", "regulation_raise_price",
}


def _detect_csv_type(headers: list[str]) -> str | None:
    """Detect CSV type from header row. Returns 'trading_price', 'ess_market', or None."""
    normalized = {h.strip().lower().replace(" ", "_") for h in headers}

    if normalized & {"tradinginterval", "trading_interval", "settlement_date"}:
        if normalized & {"referencetradingprice", "reference_trading_price", "rrp", "rrp_aud_mwh", "price"}:
            return "trading_price"

    if normalized & {"dispatchinterval", "dispatch_interval"}:
        if normalized & {"energyprice", "energy_price"}:
            return "ess_market"

    return None


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------

def _normalize_interval(raw: str) -> str:
    """Normalize a WEM timestamp to 'YYYY-MM-DD HH:MM:SS' in AWST."""
    if not raw:
        return ""
    raw = raw.strip()
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(AWST)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw.replace("T", " ")[:19]


def _safe_float(value: str | None) -> float | None:
    if value in (None, "", "null", "NULL", "-", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

_TRADING_PRICE_COL_MAP = {
    "tradinginterval": "interval",
    "trading_interval": "interval",
    "settlement_date": "interval",
    "referencetradingprice": "price",
    "reference_trading_price": "price",
    "rrp": "price",
    "rrp_aud_mwh": "price",
    "price": "price",
}

_ESS_COL_MAP = {
    "dispatchinterval": "dispatch_interval",
    "dispatch_interval": "dispatch_interval",
    "energyprice": "energy_price",
    "energy_price": "energy_price",
    "regulationraiseprice": "regulation_raise_price",
    "regulation_raise_price": "regulation_raise_price",
    "regulationlowerprice": "regulation_lower_price",
    "regulation_lower_price": "regulation_lower_price",
    "contingencyraiseprice": "contingency_raise_price",
    "contingency_raise_price": "contingency_raise_price",
    "contingencylowerprice": "contingency_lower_price",
    "contingency_lower_price": "contingency_lower_price",
    "rocofprice": "rocof_price",
    "rocof_price": "rocof_price",
}


def _build_col_map(headers: list[str], pattern: dict[str, str]) -> dict[str, str]:
    """Map normalized header names to canonical field names."""
    result: dict[str, str] = {}
    for h in headers:
        key = h.strip().lower().replace(" ", "_")
        mapped = pattern.get(key)
        if mapped and mapped not in result:
            result[mapped] = h
    return result


# ---------------------------------------------------------------------------
# Streaming CSV parser — yields rows one at a time
# ---------------------------------------------------------------------------

def _stream_trading_prices(csv_path: str, col_map: dict[str, str]):
    """Stream trading price rows from CSV. Yields (settlement_date, region_id, rrp)."""
    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_interval = row.get(col_map["interval"], "")
            interval = _normalize_interval(raw_interval)
            if not interval:
                continue
            price = _safe_float(row.get(col_map["price"]))
            if price is None:
                continue
            yield (interval, "WEM", round(price, 2))


def _stream_ess_market(csv_path: str, col_map: dict[str, str]):
    """Stream ESS market rows from CSV. Yields tuples matching table columns."""
    fields = [
        "dispatch_interval", "energy_price",
        "regulation_raise_price", "regulation_lower_price",
        "contingency_raise_price", "contingency_lower_price",
        "rocof_price",
    ]
    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_interval = row.get(col_map.get("dispatch_interval", ""), "")
            interval = _normalize_interval(raw_interval)
            if not interval:
                continue
            values = [interval]
            for field in fields[1:]:
                src = col_map.get(field)
                values.append(_safe_float(row.get(src, "")) if src else None)
            yield tuple(values)


# ---------------------------------------------------------------------------
# PostgreSQL COPY writer
# ---------------------------------------------------------------------------

def _ensure_trading_price_table(pg_conn, year: int):
    """Create sharded trading price table for a given year."""
    table = f"trading_price_{year}"
    cur = pg_conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id BIGSERIAL PRIMARY KEY,
            settlement_date TEXT NOT NULL,
            region_id TEXT NOT NULL,
            rrp_aud_mwh DOUBLE PRECISION NOT NULL,
            raise1sec_rrp DOUBLE PRECISION,
            raise6sec_rrp DOUBLE PRECISION,
            raise60sec_rrp DOUBLE PRECISION,
            raise5min_rrp DOUBLE PRECISION,
            raisereg_rrp DOUBLE PRECISION,
            lower1sec_rrp DOUBLE PRECISION,
            lower6sec_rrp DOUBLE PRECISION,
            lower60sec_rrp DOUBLE PRECISION,
            lower5min_rrp DOUBLE PRECISION,
            lowerreg_rrp DOUBLE PRECISION,
            UNIQUE(settlement_date, region_id)
        )
    """)
    cur.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table}_search
        ON {table} (region_id, settlement_date)
    """)
    pg_conn.commit()


def _ensure_ess_table(pg_conn):
    """Create WEM ESS market price table."""
    cur = pg_conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_market_price (
            dispatch_interval TEXT PRIMARY KEY,
            energy_price DOUBLE PRECISION,
            regulation_raise_price DOUBLE PRECISION,
            regulation_lower_price DOUBLE PRECISION,
            contingency_raise_price DOUBLE PRECISION,
            contingency_lower_price DOUBLE PRECISION,
            rocof_price DOUBLE PRECISION,
            available_regulation_raise DOUBLE PRECISION,
            available_regulation_lower DOUBLE PRECISION,
            available_contingency_raise DOUBLE PRECISION,
            available_contingency_lower DOUBLE PRECISION,
            available_rocof DOUBLE PRECISION,
            in_service_regulation_raise DOUBLE PRECISION,
            in_service_regulation_lower DOUBLE PRECISION,
            in_service_contingency_raise DOUBLE PRECISION,
            in_service_contingency_lower DOUBLE PRECISION,
            in_service_rocof DOUBLE PRECISION,
            requirement_regulation_raise DOUBLE PRECISION,
            requirement_regulation_lower DOUBLE PRECISION,
            requirement_contingency_raise DOUBLE PRECISION,
            requirement_contingency_lower DOUBLE PRECISION,
            requirement_rocof DOUBLE PRECISION,
            shortfall_regulation_raise DOUBLE PRECISION,
            shortfall_regulation_lower DOUBLE PRECISION,
            shortfall_contingency_raise DOUBLE PRECISION,
            shortfall_contingency_lower DOUBLE PRECISION,
            shortfall_rocof DOUBLE PRECISION,
            dispatch_total_regulation_raise DOUBLE PRECISION,
            dispatch_total_regulation_lower DOUBLE PRECISION,
            dispatch_total_contingency_raise DOUBLE PRECISION,
            dispatch_total_contingency_lower DOUBLE PRECISION,
            dispatch_total_rocof DOUBLE PRECISION,
            capped_regulation_raise INTEGER DEFAULT 0,
            capped_regulation_lower INTEGER DEFAULT 0,
            capped_contingency_raise INTEGER DEFAULT 0,
            capped_contingency_lower INTEGER DEFAULT 0,
            capped_rocof INTEGER DEFAULT 0
        )
    """)
    pg_conn.commit()


def _copy_trading_prices(pg_conn, csv_path: str, col_map: dict[str, str], dry_run: bool) -> dict:
    """Stream trading price CSV into PG using COPY. Returns stats dict."""
    import psycopg2  # noqa: imported here to allow --dry-run without psycopg2

    stats = {"rows_read": 0, "rows_written": 0, "years": set(), "min_interval": None, "max_interval": None}
    buf: list[tuple] = []
    current_year: int | None = None

    for row in _stream_trading_prices(csv_path, col_map):
        stats["rows_read"] += 1
        settlement_date, region_id, rrp = row
        year = int(settlement_date[:4])
        stats["years"].add(year)

        if stats["min_interval"] is None or settlement_date < stats["min_interval"]:
            stats["min_interval"] = settlement_date
        if stats["max_interval"] is None or settlement_date > stats["max_interval"]:
            stats["max_interval"] = settlement_date

        if dry_run:
            continue

        # Ensure table exists when year changes
        if year != current_year:
            _ensure_trading_price_table(pg_conn, year)
            current_year = year

        buf.append(row)

        if len(buf) >= COPY_BATCH_SIZE:
            _flush_copy_trading(pg_conn, buf, year)
            stats["rows_written"] += len(buf)
            buf.clear()

    # Flush remaining
    if buf and not dry_run:
        _flush_copy_trading(pg_conn, buf, int(buf[-1][0][:4]))
        stats["rows_written"] += len(buf)
        buf.clear()

    return stats


def _flush_copy_trading(pg_conn, buf: list[tuple], year: int):
    """Use COPY to bulk insert trading price rows."""
    table = f"trading_price_{year}"
    cur = pg_conn.cursor()
    sio = io.StringIO()
    for settlement_date, region_id, rrp in buf:
        sio.write(f"{settlement_date}\t{region_id}\t{rrp}\n")
    sio.seek(0)
    try:
        cur.copy_expert(
            f"COPY {table} (settlement_date, region_id, rrp_aud_mwh) FROM STDIN WITH (FORMAT text, DELIMITER E'\\t')",
            sio,
        )
        pg_conn.commit()
    except Exception:
        # Fallback: use ON CONFLICT upsert for rows that already exist
        pg_conn.rollback()
        for settlement_date, region_id, rrp in buf:
            cur.execute(
                f"""INSERT INTO {table} (settlement_date, region_id, rrp_aud_mwh)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (settlement_date, region_id)
                    DO UPDATE SET rrp_aud_mwh = EXCLUDED.rrp_aud_mwh""",
                (settlement_date, region_id, rrp),
            )
        pg_conn.commit()


def _copy_ess_market(pg_conn, csv_path: str, col_map: dict[str, str], dry_run: bool) -> dict:
    """Stream ESS market CSV into PG using COPY."""
    stats = {"rows_read": 0, "rows_written": 0, "min_interval": None, "max_interval": None}
    buf: list[tuple] = []

    if not dry_run:
        _ensure_ess_table(pg_conn)

    for row in _stream_ess_market(csv_path, col_map):
        stats["rows_read"] += 1
        dispatch_interval = row[0]

        if stats["min_interval"] is None or dispatch_interval < stats["min_interval"]:
            stats["min_interval"] = dispatch_interval
        if stats["max_interval"] is None or dispatch_interval > stats["max_interval"]:
            stats["max_interval"] = dispatch_interval

        if dry_run:
            continue

        buf.append(row)
        if len(buf) >= COPY_BATCH_SIZE:
            _flush_copy_ess(pg_conn, buf)
            stats["rows_written"] += len(buf)
            buf.clear()

    if buf and not dry_run:
        _flush_copy_ess(pg_conn, buf)
        stats["rows_written"] += len(buf)

    return stats


def _flush_copy_ess(pg_conn, buf: list[tuple]):
    """Use COPY to bulk insert ESS market rows."""
    cols = "dispatch_interval,energy_price,regulation_raise_price,regulation_lower_price,contingency_raise_price,contingency_lower_price,rocof_price"
    cur = pg_conn.cursor()
    sio = io.StringIO()
    for row in buf:
        parts = []
        for v in row:
            if v is None:
                parts.append("\\N")
            else:
                parts.append(str(v))
        sio.write("\t".join(parts) + "\n")
    sio.seek(0)
    try:
        cur.copy_expert(
            f"COPY wem_ess_market_price ({cols}) FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\\\N')",
            sio,
        )
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        placeholders = ",".join(["%s"] * 7)
        sql = f"""INSERT INTO wem_ess_market_price ({cols}) VALUES ({placeholders})
                  ON CONFLICT (dispatch_interval) DO UPDATE SET
                    energy_price = EXCLUDED.energy_price,
                    regulation_raise_price = EXCLUDED.regulation_raise_price,
                    regulation_lower_price = EXCLUDED.regulation_lower_price,
                    contingency_raise_price = EXCLUDED.contingency_raise_price,
                    contingency_lower_price = EXCLUDED.contingency_lower_price,
                    rocof_price = EXCLUDED.rocof_price"""
        for row in buf:
            cur.execute(sql, row)
        pg_conn.commit()


# ---------------------------------------------------------------------------
# File discovery & progress tracking
# ---------------------------------------------------------------------------

def _discover_csv_files(input_path: str) -> list[str]:
    """Find all CSV files from a path (file, directory, or ZIP)."""
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() == ".csv":
            return [str(p)]
        elif p.suffix.lower() == ".zip":
            return _extract_zip_csvs(str(p))
        else:
            return []
    elif p.is_dir():
        files = []
        for ext in ("*.csv", "*.CSV"):
            files.extend(str(f) for f in p.rglob(ext))
        # Also check for ZIPs in the directory
        for zf in p.rglob("*.zip"):
            files.extend(_extract_zip_csvs(str(zf)))
        return sorted(files)
    return []


def _extract_zip_csvs(zip_path: str) -> list[str]:
    """Extract CSV files from a ZIP archive to a temp directory. Returns list of paths."""
    import tempfile
    tmp_dir = os.path.join(tempfile.gettempdir(), "wem_bulk_import_zip")
    os.makedirs(tmp_dir, exist_ok=True)
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    # Extract to temp dir
                    out_path = os.path.join(tmp_dir, os.path.basename(name))
                    with zf.open(name) as src, open(out_path, "wb") as dst:
                        while True:
                            chunk = src.read(65536)
                            if not chunk:
                                break
                            dst.write(chunk)
                    extracted.append(out_path)
    except zipfile.BadZipFile:
        logger.warning(f"Bad ZIP file: {zip_path}")
    return extracted


def _load_progress(progress_path: str) -> set[str]:
    """Load set of completed file paths from progress file."""
    if os.path.exists(progress_path):
        try:
            with open(progress_path) as f:
                data = json.load(f)
            return set(data.get("completed", []))
        except (json.JSONDecodeError, KeyError):
            pass
    return set()


def _save_progress(progress_path: str, completed: set[str]):
    """Save progress to file."""
    with open(progress_path, "w") as f:
        json.dump({"completed": sorted(completed)}, f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.environ.get("AUS_ELE_PG_HOST", "localhost")
    port = os.environ.get("AUS_ELE_PG_PORT", "5432")
    db = os.environ.get("AUS_ELE_PG_DATABASE", "aemo_data")
    user = os.environ.get("AUS_ELE_PG_USER", "aemo")
    password = os.environ.get("AUS_ELE_PG_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WEM CSV bulk import — streaming parser + PostgreSQL COPY for 32GB+ data",
    )
    parser.add_argument("--input", "-i", required=True, help="CSV file, directory, or ZIP to import")
    parser.add_argument("--dsn", help="PostgreSQL DSN (default: from env vars)")
    parser.add_argument("--dry-run", action="store_true", help="Scan files and show plan without writing")
    parser.add_argument("--no-resume", action="store_true", help="Ignore progress file, re-import all")
    parser.add_argument("--type", choices=["trading_price", "ess_market"], help="Force CSV type (auto-detect by default)")
    parser.add_argument("--progress-dir", help="Directory for progress tracking file (default: input dir)")
    args = parser.parse_args()

    # Load .env if present
    repo_root = Path(__file__).resolve().parent.parent
    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    dsn = args.dsn or _build_dsn()

    # Discover files
    logger.info(f"Scanning: {args.input}")
    files = _discover_csv_files(args.input)
    if not files:
        logger.error(f"No CSV files found at: {args.input}")
        return 1
    logger.info(f"Found {len(files)} CSV file(s)")

    # Progress tracking
    progress_dir = args.progress_dir or (args.input if os.path.isdir(args.input) else str(Path(args.input).parent))
    progress_path = os.path.join(progress_dir, PROGRESS_FILE)
    completed = set() if args.no_resume else _load_progress(progress_path)
    if completed:
        logger.info(f"Resuming: {len(completed)} files already imported, will skip them")

    # Pre-scan to detect types
    file_types: list[tuple[str, str, dict[str, str]]] = []
    for f in files:
        fname = os.path.basename(f)
        if f in completed:
            logger.info(f"  [SKIP] {fname} (already imported)")
            continue
        try:
            with open(f, "r", encoding="utf-8-sig", errors="replace") as fh:
                header_line = fh.readline()
        except Exception as e:
            logger.warning(f"  [ERROR] Cannot read {fname}: {e}")
            continue

        headers = next(csv.reader(io.StringIO(header_line)))
        csv_type = args.type or _detect_csv_type(headers)
        if not csv_type:
            logger.warning(f"  [SKIP] {fname}: cannot detect CSV type from headers: {headers[:5]}")
            continue

        col_map = _build_col_map(headers, _TRADING_PRICE_COL_MAP if csv_type == "trading_price" else _ESS_COL_MAP)
        file_types.append((f, csv_type, col_map))

    if not file_types:
        logger.error("No importable CSV files found")
        return 1

    # Summary
    tp_count = sum(1 for _, t, _ in file_types if t == "trading_price")
    ess_count = sum(1 for _, t, _ in file_types if t == "ess_market")
    logger.info(f"Import plan: {tp_count} trading price + {ess_count} ESS market files")
    if args.dry_run:
        logger.info("[DRY RUN] No changes will be made")
        return 0

    # Connect to PostgreSQL
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 is required. Install: pip install psycopg2-binary")
        return 1

    try:
        pg_conn = psycopg2.connect(dsn)
        pg_conn.autocommit = False
    except Exception as e:
        logger.error(f"Cannot connect to PostgreSQL: {e}")
        logger.error(f"DSN: {dsn.split('@')[0]}@...")
        return 1

    # Import files
    total_start = time.time()
    total_rows = 0

    for idx, (filepath, csv_type, col_map) in enumerate(file_types, 1):
        fname = os.path.basename(filepath)
        fsize = os.path.getsize(filepath) / 1024 / 1024
        logger.info(f"[{idx}/{len(file_types)}] {fname} ({fsize:.1f} MB, type={csv_type})")

        file_start = time.time()
        try:
            if csv_type == "trading_price":
                stats = _copy_trading_prices(pg_conn, filepath, col_map, dry_run=False)
            else:
                stats = _copy_ess_market(pg_conn, filepath, col_map, dry_run=False)

            elapsed = time.time() - file_start
            rate = stats["rows_written"] / elapsed if elapsed > 0 else 0
            total_rows += stats["rows_written"]
            years_str = f", years={sorted(stats.get('years', []))}" if stats.get("years") else ""
            logger.info(
                f"  Done: {stats['rows_written']:,} rows in {elapsed:.1f}s "
                f"({rate:,.0f} rows/s){years_str} "
                f"[{stats['min_interval']} → {stats['max_interval']}]"
            )

            # Mark as completed
            completed.add(filepath)
            _save_progress(progress_path, completed)

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            continue

    pg_conn.close()
    total_elapsed = time.time() - total_start
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Import complete: {total_rows:,} rows in {total_elapsed:.1f}s ({total_rows / total_elapsed:,.0f} rows/s)")
    logger.info(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
