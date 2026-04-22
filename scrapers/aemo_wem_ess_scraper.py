"""
AEMO WEM ESS slim scraper.

Downloads WEM dispatch solution files, extracts only the market fields
needed for lightweight ESS analysis, and stores a rolling latest-month
window in slim tables.
"""

import argparse
import csv
import io
import json
import logging
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta

import requests
import urllib3

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from database import DatabaseManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

WEM_BASE = "https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData"
FCESS_CAPABILITY_URL = "https://data.wa.aemo.com.au/public/public-data/datafiles/fcess/fcess.csv"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

SERVICE_MAPPINGS = {
    "regulationRaise": "regulation_raise",
    "regulationLower": "regulation_lower",
    "contingencyRaise": "contingency_raise",
    "contingencyLower": "contingency_lower",
    "rocof": "rocof",
}

AVAILABILITY_MAPPINGS = {
    "regulationRaise": "available_regulation_raise",
    "regulationLower": "available_regulation_lower",
    "contingencyRaise": "available_contingency_raise",
    "contingencyLower": "available_contingency_lower",
    "rocof": "available_rocof",
}

IN_SERVICE_MAPPINGS = {
    "regulationRaise": "in_service_regulation_raise",
    "regulationLower": "in_service_regulation_lower",
    "contingencyRaise": "in_service_contingency_raise",
    "contingencyLower": "in_service_contingency_lower",
    "rocof": "in_service_rocof",
}

REQUIREMENT_MAPPINGS = {
    "regulationRaise": "requirement_regulation_raise",
    "regulationLower": "requirement_regulation_lower",
    "contingencyRaise": "requirement_contingency_raise",
    "contingencyLower": "requirement_contingency_lower",
    "rocof": "requirement_rocof",
}

SHORTFALL_MAPPINGS = {
    "regulationRaiseDeficit": "shortfall_regulation_raise",
    "regulationLowerDeficit": "shortfall_regulation_lower",
    "contingencyRaiseDeficit": "shortfall_contingency_raise",
    "contingencyLowerDeficit": "shortfall_contingency_lower",
    "rocofDeficit": "shortfall_rocof",
}

DISPATCH_TOTAL_MAPPINGS = {
    "regulationRaise": "dispatch_total_regulation_raise",
    "regulationLower": "dispatch_total_regulation_lower",
    "contingencyRaise": "dispatch_total_contingency_raise",
    "contingencyLower": "dispatch_total_contingency_lower",
    "rocof": "dispatch_total_rocof",
}

CONSTRAINT_TYPE_FIELDS = {
    "formulation": "max_formulation_shadow_price",
    "facility": "max_facility_shadow_price",
    "network": "max_network_shadow_price",
    "generic": "max_generic_shadow_price",
}


def _safe_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_dispatch_interval(raw_interval: str) -> str:
    if not raw_interval:
        return ""
    return raw_interval.replace("T", " ")[:19]


def _coerce_price_map(raw_prices):
    prices = {}
    if isinstance(raw_prices, list):
        for entry in raw_prices:
            if not isinstance(entry, dict):
                continue
            service = entry.get("marketService")
            value = _safe_float(entry.get("price"))
            if service and value is not None:
                prices[service] = value
    elif isinstance(raw_prices, dict):
        for service, value in raw_prices.items():
            parsed = _safe_float(value)
            if parsed is not None:
                prices[service] = parsed
    return prices


def extract_slim_solution_rows(raw: bytes) -> tuple[list[dict], list[dict]]:
    """Extract slim market rows plus constraint summary rows."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [], []

    wrapper = payload.get("data", payload)
    primary_dispatch_interval = _clean_dispatch_interval(wrapper.get("primaryDispatchInterval", ""))
    solution_rows = wrapper.get("solutionData", [])
    market_rows = []
    constraint_rows = []

    for solution in solution_rows:
        scenario = solution.get("scenario")
        dispatch_type = solution.get("dispatchType")
        if scenario not in (None, "", "Reference") or dispatch_type not in (None, "", "Dispatch"):
            continue

        dispatch_interval = _clean_dispatch_interval(solution.get("dispatchInterval", ""))
        if not dispatch_interval:
            continue
        if primary_dispatch_interval and dispatch_interval != primary_dispatch_interval:
            continue

        prices = _coerce_price_map(solution.get("prices", {}))
        market_row = {
            "dispatch_interval": dispatch_interval,
            "energy_price": prices.get("energy"),
        }

        for raw_key, db_key in SERVICE_MAPPINGS.items():
            market_row[f"{db_key}_price"] = prices.get(raw_key)

        for mapping, source in (
            (AVAILABILITY_MAPPINGS, solution.get("availableQuantities", {}) or {}),
            (IN_SERVICE_MAPPINGS, solution.get("inServiceQuantities", {}) or {}),
            (REQUIREMENT_MAPPINGS, solution.get("marketServiceRequirements", {}) or {}),
            (SHORTFALL_MAPPINGS, solution.get("marketShortfalls", {}) or {}),
            (DISPATCH_TOTAL_MAPPINGS, solution.get("dispatchTotal", {}) or {}),
        ):
            for raw_key, db_key in mapping.items():
                market_row[db_key] = _safe_float(source.get(raw_key))

        capped_flags = {}
        for entry in solution.get("priceSetting", []) or []:
            if not isinstance(entry, dict):
                continue
            service = entry.get("marketService")
            if service in SERVICE_MAPPINGS:
                capped_flags[service] = 1 if entry.get("isMarketServiceCapped") else 0
        for raw_key, db_key in SERVICE_MAPPINGS.items():
            market_row[f"capped_{db_key}"] = capped_flags.get(raw_key, 0)

        if any(market_row.get(f"{db_key}_price") is not None for db_key in SERVICE_MAPPINGS.values()):
            market_rows.append(market_row)

        binding_count = 0
        near_binding_count = 0
        binding_max_shadow = 0.0
        near_binding_max_shadow = 0.0
        constraint_summary = {
            "dispatch_interval": dispatch_interval,
            "binding_count": 0,
            "near_binding_count": 0,
            "binding_max_shadow_price": 0.0,
            "near_binding_max_shadow_price": 0.0,
            "max_formulation_shadow_price": 0.0,
            "max_facility_shadow_price": 0.0,
            "max_network_shadow_price": 0.0,
            "max_generic_shadow_price": 0.0,
        }

        for constraint in solution.get("constraints", []) or []:
            if not isinstance(constraint, dict):
                continue
            shadow_price = abs(_safe_float(constraint.get("shadowPrice")) or 0.0)
            if constraint.get("bindingConstraintFlag"):
                binding_count += 1
                binding_max_shadow = max(binding_max_shadow, shadow_price)
                type_key = (constraint.get("constraintType") or "").lower()
                field_name = CONSTRAINT_TYPE_FIELDS.get(type_key)
                if field_name:
                    constraint_summary[field_name] = max(constraint_summary[field_name], shadow_price)
            if constraint.get("nearBindingConstraintFlag"):
                near_binding_count += 1
                near_binding_max_shadow = max(near_binding_max_shadow, shadow_price)

        constraint_summary["binding_count"] = binding_count
        constraint_summary["near_binding_count"] = near_binding_count
        constraint_summary["binding_max_shadow_price"] = binding_max_shadow
        constraint_summary["near_binding_max_shadow_price"] = near_binding_max_shadow
        constraint_rows.append(constraint_summary)

    return market_rows, constraint_rows


def parse_fcess_capabilities(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    records = []
    for row in reader:
        facility_code = (row.get("Facility Code") or "").strip()
        if not facility_code:
            continue
        records.append(
            {
                "facility_code": facility_code,
                "participant_code": (row.get("Participant Code") or "").strip() or None,
                "participant_name": (row.get("Participant Name") or "").strip() or None,
                "facility_class": (row.get("Facility Class") or "").strip() or None,
                "max_accredited_regulation_raise": _safe_float(row.get("Max Accredited Regulation Raise")),
                "max_accredited_regulation_lower": _safe_float(row.get("Max Accredited Regulation Lower")),
                "max_accredited_contingency_raise": _safe_float(row.get("Max Accredited Contingency Raise")),
                "max_accredited_contingency_lower": _safe_float(row.get("Max Accredited Contingency Lower")),
                "max_accredited_rocof": _safe_float(row.get("Max Accredited ROCOF")),
                "facility_speed_factor": _safe_float(row.get("Facility Speed Factor")),
                "rocof_ride_through_capability": _safe_float(row.get("RoCoF Ride-Through Capability")),
                "extracted_at": (row.get("Extracted At") or "").strip() or None,
            }
        )
    return records


def download_bytes(url: str, label: str, *, stream: bool = False, max_retries: int = 3) -> bytes | None:
    def emit_progress(message: str):
        try:
            sys.stdout.write(message)
            sys.stdout.flush()
        except OSError:
            # Some non-interactive runners expose stdout handles that reject flush/write.
            pass

    if not stream:
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=120,
                    verify=False,
                    stream=False,
                )
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    logger.warning(f"{label}: HTTP {response.status_code} (attempt {attempt})")
                    time.sleep(attempt * 3)
                    continue
                return response.content
            except requests.RequestException as exc:
                logger.warning(f"{label}: download failed on attempt {attempt}: {exc}")
                if attempt < max_retries:
                    time.sleep(attempt * 5)
        return None

    downloaded = bytearray()
    total = 0
    for attempt in range(1, max_retries + 1):
        request_headers = dict(HEADERS)
        if downloaded:
            request_headers["Range"] = f"bytes={len(downloaded)}-"

        try:
            response = requests.get(
                url,
                headers=request_headers,
                timeout=600,
                verify=False,
                stream=True,
            )
            if response.status_code == 404:
                return None
            if response.status_code not in (200, 206):
                logger.warning(f"{label}: HTTP {response.status_code} (attempt {attempt})")
                time.sleep(attempt * 3)
                continue
            if downloaded and response.status_code == 200:
                logger.warning(f"{label}: range request ignored, restarting full download")
                downloaded = bytearray()
                total = 0

            content_range = response.headers.get("Content-Range") or ""
            if content_range:
                match = re.search(r"/(\d+)$", content_range)
                if match:
                    total = int(match.group(1))
            elif response.headers.get("Content-Length"):
                content_length = int(response.headers["Content-Length"])
                total = max(total, len(downloaded) + content_length if response.status_code == 206 else content_length)

            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                downloaded.extend(chunk)
                if total > 0:
                    pct = len(downloaded) / total * 100
                    mb_dl = len(downloaded) / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    emit_progress(f"\r  {label}: {mb_dl:.1f}/{mb_total:.1f} MB ({pct:.0f}%)")

            if total and len(downloaded) < total:
                raise requests.exceptions.ChunkedEncodingError(
                    f"incomplete download: {len(downloaded)} of {total} bytes"
                )

            if total > 0:
                emit_progress("\n")
            return bytes(downloaded)
        except requests.RequestException as exc:
            logger.warning(f"{label}: download failed on attempt {attempt}: {exc}")
            if attempt < max_retries:
                if downloaded:
                    logger.info(
                        f"{label}: resuming from {len(downloaded) / 1024 / 1024:.1f} MB"
                    )
                time.sleep(attempt * 5)
    return None


def list_current_json_urls(target_date: datetime) -> list[str]:
    date_compact = target_date.strftime("%Y%m%d")
    listing_url = f"{WEM_BASE}/current/"
    raw = download_bytes(listing_url, f"{date_compact} listing", stream=False, max_retries=1)
    if not raw:
        return []
    html = raw.decode("utf-8", errors="ignore")
    matches = sorted(set(re.findall(rf"ReferenceDispatchSolution_{date_compact}\d{{4}}\.json", html)))
    return [f"{listing_url}{name}" for name in matches]


def sync_fcess_capabilities(db: DatabaseManager) -> int:
    raw = download_bytes(FCESS_CAPABILITY_URL, "fcess.csv", stream=False, max_retries=2)
    if not raw:
        return 0
    records = parse_fcess_capabilities(raw.decode("utf-8", errors="ignore"))
    return db.replace_wem_ess_capabilities(records)


def _merge_rows_by_interval(records: list[dict]) -> list[dict]:
    merged = {}
    for record in records:
        merged[record["dispatch_interval"]] = record
    return [merged[key] for key in sorted(merged)]


def scrape_day(target_date: datetime, db: DatabaseManager) -> tuple[int, int]:
    date_label = target_date.strftime("%Y-%m-%d")
    date_compact = target_date.strftime("%Y%m%d")
    market_rows = []
    constraint_rows = []

    zip_url = f"{WEM_BASE}/previous/DispatchSolutionReference_{date_compact}.zip"
    raw_zip = download_bytes(zip_url, date_label, stream=True, max_retries=2)
    if raw_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(raw_zip)) as zipped:
                for name in sorted(n for n in zipped.namelist() if n.endswith(".json")):
                    with zipped.open(name) as handle:
                        rows, constraints = extract_slim_solution_rows(handle.read())
                        market_rows.extend(rows)
                        constraint_rows.extend(constraints)
        except zipfile.BadZipFile:
            logger.warning(f"{date_label}: bad zip file")
    else:
        for url in list_current_json_urls(target_date):
            raw_json = download_bytes(url, url.rsplit("/", 1)[-1], stream=False, max_retries=1)
            if not raw_json:
                continue
            rows, constraints = extract_slim_solution_rows(raw_json)
            market_rows.extend(rows)
            constraint_rows.extend(constraints)

    market_rows = _merge_rows_by_interval(market_rows)
    constraint_rows = _merge_rows_by_interval(constraint_rows)

    market_count = db.batch_upsert_wem_ess_market(market_rows)
    constraint_count = db.batch_upsert_wem_ess_constraints(constraint_rows)
    return market_count, constraint_count


def sync_wem_ess_range(start_dt: datetime, end_dt: datetime, db_path: str, *, prune_before_start: bool = False) -> dict:
    db = DatabaseManager(db_path)
    capability_rows = sync_fcess_capabilities(db)

    total_market = 0
    total_constraints = 0
    scanned_days = 0
    current = start_dt
    while current <= end_dt:
        scanned_days += 1
        market_count, constraint_count = scrape_day(current, db)
        total_market += market_count
        total_constraints += constraint_count
        logger.info(
            f"[{scanned_days}] {current.strftime('%Y-%m-%d')} -> market {market_count}, constraints {constraint_count}"
        )
        current += timedelta(days=1)
        time.sleep(1)

    if prune_before_start:
        db.prune_wem_ess_history(start_dt.strftime("%Y-%m-%d 00:00:00"))

    stats = db.get_wem_ess_stats()
    stats.update(
        {
            "inserted_market_rows": total_market,
            "inserted_constraint_rows": total_constraints,
            "capability_rows": capability_rows,
        }
    )
    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="Sync slim WEM ESS data")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument("--days", type=int, help="Rolling latest N days, inclusive")
    parser.add_argument("--db", default="../data/aemo_data.db", help="SQLite database path")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.days:
        end_dt = datetime.now() - timedelta(days=1)
        start_dt = end_dt - timedelta(days=max(args.days - 1, 0))
        prune_before_start = True
    elif args.start and args.end:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d")
        prune_before_start = False
    else:
        raise SystemExit("Use either --days N or both --start YYYY-MM-DD --end YYYY-MM-DD")

    logger.info("=" * 60)
    logger.info("WEM ESS slim sync")
    logger.info(f"Range: {start_dt.strftime('%Y-%m-%d')} -> {end_dt.strftime('%Y-%m-%d')}")
    logger.info("Mode: slim market + constraint summary + capability table")
    logger.info("=" * 60)

    stats = sync_wem_ess_range(start_dt, end_dt, args.db, prune_before_start=prune_before_start)
    logger.info("=" * 60)
    logger.info(f"Market rows stored: {stats['market_rows']}")
    logger.info(f"Constraint rows stored: {stats['constraint_rows']}")
    logger.info(f"Capability rows stored: {stats['capability_rows']}")
    logger.info(f"Coverage: {stats['min_interval']} -> {stats['max_interval']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
