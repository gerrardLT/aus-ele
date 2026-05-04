import csv
import datetime as dt
import io
import json
import logging
import math
import re
import zipfile
from typing import Optional
from urllib.parse import urljoin

import requests


logger = logging.getLogger(__name__)

NEM_PREDISPATCH_LISTING_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/PREDISPATCHIS_Reports/"
FCAS_COLUMNS = [
    "raise1sec_rrp", "raise6sec_rrp", "raise60sec_rrp", "raise5min_rrp", "raisereg_rrp",
    "lower1sec_rrp", "lower6sec_rrp", "lower60sec_rrp", "lower5min_rrp", "lowerreg_rrp",
]
SEVERITY_SCORES = {
    "low": 15.0,
    "medium": 30.0,
    "high": 45.0,
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def parse_timestamp(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None

    normalized = str(value).strip().replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]
    if "+" in normalized:
        normalized = normalized.split("+", 1)[0].strip()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return dt.datetime.strptime(normalized[:19], fmt)
        except ValueError:
            continue
    return None


def format_timestamp(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_as_of(as_of: Optional[str]) -> dt.datetime:
    parsed = parse_timestamp(as_of)
    return parsed or dt.datetime.now(dt.UTC).replace(tzinfo=None)


def horizon_delta(horizon: str) -> dt.timedelta:
    if horizon == "24h":
        return dt.timedelta(hours=24)
    if horizon == "7d":
        return dt.timedelta(days=7)
    return dt.timedelta(days=30)


def build_as_of_bucket(as_of: str | dt.datetime | None, horizon: str) -> str:
    as_of_dt = parse_as_of(as_of if isinstance(as_of, str) or as_of is None else format_timestamp(as_of))
    if horizon == "24h":
        bucket = as_of_dt.replace(minute=0, second=0, microsecond=0)
    else:
        bucket = as_of_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return format_timestamp(bucket)


def expiry_for_bucket(bucket: str, horizon: str) -> str:
    bucket_dt = parse_timestamp(bucket) or parse_as_of(bucket)
    if horizon == "24h":
        return format_timestamp(bucket_dt + dt.timedelta(hours=1))
    if horizon == "7d":
        return format_timestamp(bucket_dt + dt.timedelta(hours=6))
    return format_timestamp(bucket_dt + dt.timedelta(hours=12))


def _extract_listing_links(html: str) -> list[str]:
    matches = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    candidates = []
    for href in matches:
        if "PREDISPATCH" not in href.upper():
            continue
        if not href.lower().endswith((".zip", ".csv")):
            continue
        candidates.append(href)
    return sorted(set(candidates))


def _normalize_predispatch_row(row: dict) -> dict | None:
    upper_row = {str(key).strip().upper(): value for key, value in row.items()}
    region = (
        upper_row.get("REGIONID")
        or upper_row.get("REGION_ID")
        or upper_row.get("REGION")
    )
    if not region:
        return None

    time_value = (
        upper_row.get("PREDISPATCHTIME")
        or upper_row.get("PREDISPATCH_DATETIME")
        or upper_row.get("SETTLEMENTDATE")
        or upper_row.get("INTERVAL_DATETIME")
        or upper_row.get("DATETIME")
    )
    price_value = (
        upper_row.get("RRP")
        or upper_row.get("REGIONRRP")
        or upper_row.get("PRICE")
    )
    demand_value = (
        upper_row.get("TOTALDEMAND")
        or upper_row.get("DEMANDFORECAST")
        or upper_row.get("DEMAND")
    )
    parsed_time = parse_timestamp(time_value)
    if not parsed_time:
        return None

    try:
        price = float(price_value) if price_value not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    try:
        demand = float(demand_value) if demand_value not in (None, "") else None
    except (TypeError, ValueError):
        demand = None

    return {
        "region": str(region).strip().upper(),
        "time": format_timestamp(parsed_time),
        "price": price,
        "demand_mw": demand,
    }


def _parse_predispatch_csv_bytes(raw_bytes: bytes, region: str) -> list[dict]:
    try:
        text = raw_bytes.decode("utf-8-sig", errors="replace")
    except Exception:
        text = raw_bytes.decode("latin-1", errors="replace")

    lines = [line for line in text.splitlines() if line.strip()]
    header_index = None
    for index, line in enumerate(lines):
        upper = line.upper()
        if "REGIONID" in upper and ("RRP" in upper or "PRICE" in upper):
            header_index = index
            break
    if header_index is None:
        return []

    reader = csv.DictReader(lines[header_index:])
    region_key = region.strip().upper()
    records = []
    for row in reader:
        normalized = _normalize_predispatch_row(row)
        if not normalized or normalized["region"] != region_key:
            continue
        records.append(normalized)

    records.sort(key=lambda item: item["time"])
    return records


def fetch_nem_predispatch_window(region: str, as_of: str) -> list[dict]:
    try:
        listing_res = requests.get(NEM_PREDISPATCH_LISTING_URL, headers=HEADERS, timeout=20)
        listing_res.raise_for_status()
        links = _extract_listing_links(listing_res.text)
        if not links:
            return []

        latest_href = links[-1]
        latest_url = urljoin(NEM_PREDISPATCH_LISTING_URL, latest_href)
        file_res = requests.get(latest_url, headers=HEADERS, timeout=30)
        file_res.raise_for_status()
        content = file_res.content
        if latest_url.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for member in archive.namelist():
                    if not member.lower().endswith(".csv"):
                        continue
                    with archive.open(member) as handle:
                        return _parse_predispatch_csv_bytes(handle.read(), region)
        return _parse_predispatch_csv_bytes(content, region)
    except Exception as exc:
        logger.warning("Failed to fetch NEM predispatch data: %s", exc)
        return []


def _available_year_tables(conn, market: str, region: str) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'")
    tables = []
    for (name,) in cursor.fetchall():
        try:
            cursor.execute(f"SELECT 1 FROM {name} WHERE region_id = ? LIMIT 1", (region,))
            if cursor.fetchone():
                tables.append(name)
        except Exception:
            continue
    return sorted(tables)


def build_recent_market_features(db, market: str, region: str, as_of: str) -> dict:
    as_of_dt = parse_as_of(as_of)
    if market == "WEM":
        with db.get_connection() as conn:
            db.ensure_wem_ess_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    m.dispatch_interval,
                    m.energy_price,
                    m.regulation_raise_price,
                    m.regulation_lower_price,
                    m.contingency_raise_price,
                    m.contingency_lower_price,
                    m.rocof_price,
                    m.shortfall_regulation_raise,
                    m.shortfall_regulation_lower,
                    m.shortfall_contingency_raise,
                    m.shortfall_contingency_lower,
                    m.shortfall_rocof,
                    c.binding_count,
                    c.near_binding_count,
                    c.binding_max_shadow_price,
                    c.max_network_shadow_price
                FROM {db.WEM_ESS_MARKET_TABLE} m
                LEFT JOIN {db.WEM_ESS_CONSTRAINT_TABLE} c
                    ON c.dispatch_interval = m.dispatch_interval
                WHERE m.dispatch_interval <= ?
                ORDER BY m.dispatch_interval DESC
                LIMIT 96
                """,
                (format_timestamp(as_of_dt),),
            )
            rows = cursor.fetchall()

        if not rows:
            return {
                "coverage": "none",
                "recent_history_points": 0,
                "recent_avg_price": 0.0,
                "recent_max_price": 0.0,
                "binding_count_avg": 0.0,
                "binding_shadow_max": 0.0,
                "network_shadow_max": 0.0,
                "shortfall_total": 0.0,
                "recent_fcas_avg": 0.0,
            }

        energy_prices = [float(row[1] or 0.0) for row in rows]
        fcas_prices = [
            sum(float(value or 0.0) for value in row[2:7])
            for row in rows
        ]
        shortfalls = [
            sum(float(value or 0.0) for value in row[7:12])
            for row in rows
        ]
        return {
            "coverage": "core_only",
            "recent_history_points": len(rows),
            "recent_avg_price": sum(energy_prices) / len(energy_prices),
            "recent_max_price": max(energy_prices),
            "binding_count_avg": sum(float(row[12] or 0.0) for row in rows) / len(rows),
            "binding_shadow_max": max(float(row[14] or 0.0) for row in rows),
            "network_shadow_max": max(float(row[15] or 0.0) for row in rows),
            "shortfall_total": sum(shortfalls),
            "recent_fcas_avg": sum(fcas_prices) / len(fcas_prices),
        }

    empty_nem_history = {
        "coverage": "none",
        "recent_history_points": 0,
        "recent_avg_price": 0.0,
        "recent_max_price": 0.0,
        "recent_min_price": 0.0,
        "negative_ratio": 0.0,
        "recent_fcas_avg": 0.0,
    }

    with db.get_connection() as conn:
        table_name = f"trading_price_{as_of_dt.year}"
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        if not cursor.fetchone():
            tables = _available_year_tables(conn, market, region)
            if not tables:
                return empty_nem_history
            table_name = tables[-1]

        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        fcas_expr = " + ".join(f"COALESCE({col}, 0)" for col in FCAS_COLUMNS if col in existing_cols)
        if not fcas_expr:
            fcas_expr = "0"

        cursor.execute(
            f"""
            SELECT rrp_aud_mwh, {fcas_expr} as total_fcas
            FROM {table_name}
            WHERE region_id = ? AND settlement_date <= ?
            ORDER BY settlement_date DESC
            LIMIT 288
            """,
            (region, format_timestamp(as_of_dt)),
        )
        rows = cursor.fetchall()

    if not rows:
        return empty_nem_history

    prices = [float(row[0] or 0.0) for row in rows]
    total_fcas = [float(row[1] or 0.0) for row in rows]
    negative_count = sum(1 for price in prices if price < 0)
    return {
        "coverage": "full",
        "recent_history_points": len(rows),
        "recent_avg_price": sum(prices) / len(prices),
        "recent_max_price": max(prices),
        "recent_min_price": min(prices),
        "negative_ratio": negative_count / len(prices),
        "recent_fcas_avg": sum(total_fcas) / len(total_fcas),
    }


def build_event_features(db, market: str, region: str, as_of: str, horizon: str) -> dict:
    as_of_dt = parse_as_of(as_of)
    horizon_end = as_of_dt + horizon_delta(horizon)
    with db.get_connection() as conn:
        db.ensure_event_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT state_type, severity, confidence, headline, start_time, end_time
            FROM {db.GRID_EVENT_STATE_TABLE}
            WHERE market = ?
              AND region = ?
              AND end_time >= ?
              AND start_time <= ?
            ORDER BY start_time ASC
            """,
            (market, region, format_timestamp(as_of_dt), format_timestamp(horizon_end)),
        )
        rows = cursor.fetchall()

    states = [
        {
            "state_type": row[0],
            "severity": row[1],
            "confidence": float(row[2] or 0.0),
            "headline": row[3],
            "start_time": row[4],
            "end_time": row[5],
        }
        for row in rows
    ]
    return {
        "state_types": [state["state_type"] for state in states],
        "event_count": len(states),
        "severity_score": sum(SEVERITY_SCORES.get(state["severity"], 0.0) for state in states),
        "states": states,
    }


def _event_drivers(event_features: dict) -> list[dict]:
    drivers = []
    for state in event_features.get("states", []):
        drivers.append(
            {
                "driver_type": state["state_type"],
                "direction": "upside_risk" if state["state_type"] != "demand_weather_shock" else "two_way",
                "severity": state["severity"],
                "headline": state["headline"],
                "summary": state["headline"],
                "source": "event_state",
                "source_url": None,
                "effective_start": state["start_time"],
                "effective_end": state["end_time"],
            }
        )
    return drivers


def _is_current_forecast_payload(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    coverage = payload.get("coverage")
    market_context = payload.get("market_context")
    baseline_forecast = payload.get("baseline_forecast")
    if not isinstance(coverage, dict) or not isinstance(market_context, dict) or not isinstance(baseline_forecast, dict):
        return False
    return True


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fetch_forward_actual_price_rows(db, market: str, region: str, start_time: str | None, end_time: str | None) -> list[dict]:
    start_dt = parse_timestamp(start_time)
    end_dt = parse_timestamp(end_time)
    if not start_dt or not end_dt or end_dt < start_dt:
        return []

    if market == "WEM":
        with db.get_connection() as conn:
            db.ensure_wem_ess_tables(conn)
            rows = conn.execute(
                f"""
                SELECT dispatch_interval, energy_price
                FROM {db.WEM_ESS_MARKET_TABLE}
                WHERE dispatch_interval >= ? AND dispatch_interval <= ?
                ORDER BY dispatch_interval ASC
                """,
                (format_timestamp(start_dt), format_timestamp(end_dt)),
            ).fetchall()
        return [
            {"time": row[0], "price_aud_mwh": float(row[1] or 0.0)}
            for row in rows
        ]

    with db.get_connection() as conn:
        table_name = f"trading_price_{start_dt.year}"
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        if not cursor.fetchone():
            tables = _available_year_tables(conn, market, region)
            if not tables:
                return []
            table_name = tables[-1]
        rows = conn.execute(
            f"""
            SELECT settlement_date, rrp_aud_mwh
            FROM {table_name}
            WHERE region_id = ?
              AND settlement_date >= ?
              AND settlement_date <= ?
            ORDER BY settlement_date ASC
            """,
            (region, format_timestamp(start_dt), format_timestamp(end_dt)),
        ).fetchall()
    return [
        {"time": row[0], "price_aud_mwh": float(row[1] or 0.0)}
        for row in rows
    ]


def _pinball_loss(actual: float, forecast: float, quantile: float) -> float:
    error = actual - forecast
    return quantile * error if error >= 0 else (quantile - 1.0) * error


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _merge_missing_dict(target: dict, defaults: dict) -> dict:
    merged = dict(defaults)
    for key, value in (target or {}).items():
        default_value = merged.get(key)
        if isinstance(value, dict) and isinstance(default_value, dict):
            merged[key] = _merge_missing_dict(value, default_value)
        else:
            merged[key] = value
    return merged


def _classify_signed_gap(value: float | None, *, tolerance: float = 0.05, low_label: str, mid_label: str, high_label: str) -> str | None:
    if value is None:
        return None
    if value < -tolerance:
        return low_label
    if value > tolerance:
        return high_label
    return mid_label


def _classify_price_state(actual_price: float) -> str:
    if actual_price < 0.0:
        return "negative_price"
    if actual_price > 300.0:
        return "price_spike"
    if actual_price > 150.0:
        return "elevated_price"
    return "normal_price"


def _build_heuristic_quantile_scaffold(
    *,
    low_value: float,
    high_value: float,
    mid_value: float,
    band_width: float,
    horizon: str | None,
    driver_tags: list[str],
    spike_probability: float,
    negative_probability: float,
    confidence_band: str | None,
) -> dict:
    horizon_multiplier = {"24h": 1.0, "7d": 1.3, "30d": 1.6}.get(horizon or "", 1.15)
    regime_multiplier = 1.0
    if any(tag in driver_tags for tag in ("reserve_tightness", "network_stress", "market_regime_shift", "wem_constraint_tightness")):
        regime_multiplier += 0.18
    if any(tag in driver_tags for tag in ("negative_price_regime", "predispatch_negative_price")):
        regime_multiplier += 0.12
    if any(tag in driver_tags for tag in ("fcas_pressure_regime", "wem_shortfall_signal")):
        regime_multiplier += 0.08

    probability_multiplier = 1.0 + max(spike_probability, negative_probability) * 0.35
    effective_width = max(band_width, max(abs(mid_value) * 0.2, 25.0)) * horizon_multiplier * regime_multiplier * probability_multiplier
    lower_tail = effective_width * (0.55 + min(negative_probability, 0.8) * 0.35)
    upper_tail = effective_width * (0.55 + min(spike_probability, 0.8) * 0.35)
    p10_value = round(mid_value - lower_tail, 2)
    p90_value = round(mid_value + upper_tail, 2)

    return {
        "method": "heuristic_regime_quantiles_v1",
        "confidence_band": confidence_band or "unknown",
        "volatility_anchor": "forward_range" if band_width > 0 else "recent_range",
        "regime_adjustment_factor": round(regime_multiplier * probability_multiplier, 4),
        "p10_price_aud_mwh": p10_value,
        "p50_price_aud_mwh": round(mid_value, 2),
        "p90_price_aud_mwh": p90_value,
        "band_width_aud_mwh": round(max(p90_value - p10_value, 0.0), 2),
    }


def _build_regime_error_attribution(actual_prices: list[float], point_forecast: float, driver_tags: list[str]) -> dict:
    if not actual_prices:
        return {
            "status": "not_attributed",
            "primary_regime": None,
            "regime_buckets": [],
        }

    bucket_map: dict[str, list[float]] = {}
    for actual in actual_prices:
        regime = _classify_price_state(actual)
        bucket_map.setdefault(regime, []).append(actual)

    regime_buckets = []
    ordered_states = ["negative_price", "normal_price", "elevated_price", "price_spike"]
    for regime in ordered_states:
        values = bucket_map.get(regime)
        if not values:
            continue
        errors = [actual - point_forecast for actual in values]
        abs_errors = [abs(error) for error in errors]
        regime_buckets.append(
            {
                "regime": regime,
                "bucket_type": "observed_price_state",
                "sample_count": len(values),
                "mae_aud_mwh": round(_mean(abs_errors) or 0.0, 4),
                "mean_error_aud_mwh": round(_mean(errors) or 0.0, 4),
            }
        )

    for tag in driver_tags:
        errors = [actual - point_forecast for actual in actual_prices]
        abs_errors = [abs(error) for error in errors]
        regime_buckets.append(
            {
                "regime": tag,
                "bucket_type": "driver_tag",
                "sample_count": len(actual_prices),
                "mae_aud_mwh": round(_mean(abs_errors) or 0.0, 4),
                "mean_error_aud_mwh": round(_mean(errors) or 0.0, 4),
            }
        )

    primary_regime = regime_buckets[0]["regime"] if regime_buckets else (driver_tags[0] if driver_tags else None)
    return {
        "status": "attributed",
        "primary_regime": primary_regime,
        "regime_buckets": regime_buckets,
    }


def _build_walk_forward_samples(
    actual_rows: list[dict],
    *,
    p10_value: float,
    p50_value: float,
    p90_value: float,
) -> list[dict]:
    samples = []
    running_actuals: list[float] = []
    for index, row in enumerate(actual_rows, start=1):
        actual_price = float(row.get("price_aud_mwh") or 0.0)
        running_actuals.append(actual_price)
        abs_error = abs(actual_price - p50_value)
        signed_error = actual_price - p50_value
        samples.append(
            {
                "sample_index": index,
                "timestamp": row.get("time"),
                "point_forecast_aud_mwh": round(p50_value, 2),
                "p10_price_aud_mwh": round(p10_value, 2),
                "p90_price_aud_mwh": round(p90_value, 2),
                "actual_price_aud_mwh": round(actual_price, 2),
                "absolute_error_aud_mwh": round(abs_error, 4),
                "signed_error_aud_mwh": round(signed_error, 4),
                "observed_price_state": _classify_price_state(actual_price),
                "running_mae_aud_mwh": round(_mean([abs(value - p50_value) for value in running_actuals]) or 0.0, 4),
            }
        )
    return samples


def _infer_interval_minutes(horizon: str | None, market: str | None) -> int:
    if market == "WEM":
        return 5
    if horizon == "24h":
        return 30
    return 24 * 60


def _estimate_negative_duration(windows: list[dict], *, horizon: str | None, market: str | None, negative_probability: float) -> tuple[int, float]:
    negative_windows = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        probabilities = window.get("probabilities") or {}
        window_type = window.get("window_type")
        probability = _safe_float(probabilities.get("negative_price_probability"))
        if window_type == "charge" or probability > 0.0:
            negative_windows.append(probability)

    interval_minutes = _infer_interval_minutes(horizon, market)
    if negative_windows:
        expected_intervals = int(round(sum(1.0 if probability >= 0.5 else probability for probability in negative_windows)))
    else:
        expected_intervals = 1 if negative_probability >= 0.5 else int(round(max(negative_probability, 0.0)))

    expected_intervals = max(expected_intervals, 1 if negative_probability > 0 else 0)
    duration_hours = round((expected_intervals * interval_minutes) / 60.0, 4)
    return expected_intervals, duration_hours


def _build_calibration_summary(calibration: dict) -> dict:
    coverage_gap_80 = calibration.get("coverage_gap_80")
    coverage_gap_90 = calibration.get("coverage_gap_90")
    spike_gap = calibration.get("spike_probability_gap")
    negative_gap = calibration.get("negative_price_probability_gap")
    sample_count = int(calibration.get("sample_count") or 0)

    penalties = 0
    for gap, tol in ((coverage_gap_80, 0.15), (coverage_gap_90, 0.15), (spike_gap, 0.2), (negative_gap, 0.2)):
        if gap is None:
            penalties += 1
            continue
        if abs(gap) > tol:
            penalties += 1

    if sample_count <= 1 or penalties >= 3:
        summary_grade = "poor"
    elif penalties >= 1:
        summary_grade = "mixed"
    else:
        summary_grade = "good"

    return {
        "summary_grade": summary_grade,
        "signal_count": 4,
        "signals_with_material_gap": penalties,
        "sample_size_tier": "thin" if sample_count <= 2 else "usable" if sample_count <= 8 else "broad",
    }


def _build_evaluation_diagnostics(metrics: dict, calibration: dict) -> dict:
    mae = metrics.get("mae_aud_mwh")
    if mae is None:
        return {
            "status": "unavailable",
            "error_grade": None,
            "primary_gap_domain": None,
            "summary_note": "diagnostics unavailable",
        }

    if mae >= 80:
        error_grade = "high_error"
    elif mae >= 35:
        error_grade = "moderate_error"
    else:
        error_grade = "low_error"

    gap_candidates = {
        "coverage": max(
            abs(calibration.get("coverage_gap_80") or 0.0),
            abs(calibration.get("coverage_gap_90") or 0.0),
        ),
        "probability": max(
            abs(calibration.get("spike_probability_gap") or 0.0),
            abs(calibration.get("negative_price_probability_gap") or 0.0),
        ),
        "bias": abs(calibration.get("mean_error_aud_mwh") or 0.0) / 100.0,
    }
    primary_gap_domain = max(gap_candidates, key=gap_candidates.get)
    if gap_candidates[primary_gap_domain] < 0.05:
        primary_gap_domain = "balanced"

    summary_note = (
        f"{error_grade}; calibration {calibration.get('summary_grade') or 'unknown'}; "
        f"primary gap {primary_gap_domain}"
    )
    return {
        "status": "available",
        "error_grade": error_grade,
        "primary_gap_domain": primary_gap_domain,
        "summary_note": summary_note,
    }


def _build_baseline_forecast_contract(payload: dict, *, db=None) -> dict:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    market_context = payload.get("market_context") if isinstance(payload.get("market_context"), dict) else {}
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    windows = payload.get("windows") if isinstance(payload.get("windows"), list) else []

    spike_probability = 0.0
    negative_probability = 0.0
    for window in windows:
        probabilities = window.get("probabilities") if isinstance(window, dict) else {}
        if not isinstance(probabilities, dict):
            continue
        spike_probability = max(spike_probability, _safe_float(probabilities.get("price_spike_probability")))
        negative_probability = max(negative_probability, _safe_float(probabilities.get("negative_price_probability")))

    price_low = market_context.get("forward_price_min_aud_mwh")
    price_high = market_context.get("forward_price_max_aud_mwh")
    if price_low is None and price_high is None:
        price_low = market_context.get("recent_price_min_aud_mwh")
        price_high = market_context.get("recent_price_max_aud_mwh")
    low_value = _safe_float(price_low, 0.0)
    high_value = _safe_float(price_high, low_value)
    mid_value = round((low_value + high_value) / 2.0, 2)
    band_width = max(high_value - low_value, 0.0)
    driver_tags = list(summary.get("driver_tags") or [])
    confidence_band = metadata.get("confidence_band", "unknown")

    warnings = list(metadata.get("warnings") or [])
    for warning in ("not_backtested", "not_calibrated"):
        if warning not in warnings:
            warnings.append(warning)

    forecast_window_start = coverage.get("forward_window_start") or metadata.get("issued_at")
    forecast_window_end = coverage.get("forward_window_end") or metadata.get("issued_at")

    evaluation = {
        "backtest_status": "not_backtested",
        "calibration_status": "not_calibrated",
        "regime_attribution_status": "not_attributed",
        "backtest_window": {
            "policy": "walk_forward_required",
            "walk_forward_mode": "rolling_origin",
            "actuals_dataset_family": "settlement",
            "target_metric": "price_aud_mwh",
            "evaluation_window_start": forecast_window_start,
            "evaluation_window_end": forecast_window_end,
            "sample_points_evaluated": 0,
            "window_count": 0,
            "window_unit": "interval",
            "samples": [],
        },
        "metrics": {
            "mae_aud_mwh": None,
            "rmse_aud_mwh": None,
            "mape_pct": None,
            "pinball_loss_p10": None,
            "pinball_loss_p50": None,
            "pinball_loss_p90": None,
            "coverage_80": None,
            "coverage_90": None,
            "brier_score_spike": None,
            "brier_score_negative_price": None,
        },
        "calibration": {
            "status": "not_calibrated",
            "sample_count": 0,
            "mean_error_aud_mwh": None,
            "coverage_gap_80": None,
            "coverage_gap_90": None,
            "spike_probability_gap": None,
            "negative_price_probability_gap": None,
            "bias_direction": None,
            "coverage_assessment_80": None,
            "coverage_assessment_90": None,
            "spike_probability_assessment": None,
            "negative_price_probability_assessment": None,
            "summary_grade": None,
            "signal_count": 0,
            "signals_with_material_gap": 0,
            "sample_size_tier": "none",
        },
        "regime_error_attribution": {
            "status": "not_attributed",
            "primary_regime": None,
            "regime_buckets": [],
        },
        "diagnostics": {
            "status": "unavailable",
            "error_grade": None,
            "primary_gap_domain": None,
            "summary_note": "diagnostics unavailable",
        },
    }

    if db is not None:
        actual_rows = _fetch_forward_actual_price_rows(
            db,
            metadata.get("market") or "",
            metadata.get("region") or "",
            forecast_window_start,
            forecast_window_end,
        )
        if actual_rows:
            actual_prices = [float(row["price_aud_mwh"]) for row in actual_rows]
            p10_value = round(low_value, 2)
            p50_value = mid_value
            p90_value = round(high_value, 2)
            p20_value = round(p50_value - (p50_value - p10_value) * 0.75, 2)
            p80_value = round(p50_value + (p90_value - p50_value) * 0.75, 2)
            walk_forward_samples = _build_walk_forward_samples(
                actual_rows,
                p10_value=p10_value,
                p50_value=p50_value,
                p90_value=p90_value,
            )
            abs_errors = [abs(actual - p50_value) for actual in actual_prices]
            sq_errors = [(actual - p50_value) ** 2 for actual in actual_prices]
            pct_errors = [
                abs((actual - p50_value) / actual) * 100.0
                for actual in actual_prices
                if actual != 0
            ]
            spike_probability = round(spike_probability, 2)
            negative_probability = round(negative_probability, 2)
            spike_actuals = [1.0 if actual > 300.0 else 0.0 for actual in actual_prices]
            negative_actuals = [1.0 if actual < 0.0 else 0.0 for actual in actual_prices]
            coverage_80 = round(_mean([1.0 if p20_value <= actual <= p80_value else 0.0 for actual in actual_prices]) or 0.0, 4)
            coverage_90 = round(_mean([1.0 if p10_value <= actual <= p90_value else 0.0 for actual in actual_prices]) or 0.0, 4)
            mean_error = round(_mean([actual - p50_value for actual in actual_prices]) or 0.0, 4)
            spike_base_rate = round(_mean(spike_actuals) or 0.0, 4)
            negative_base_rate = round(_mean(negative_actuals) or 0.0, 4)
            evaluation["backtest_status"] = "evaluated"
            evaluation["calibration_status"] = "baseline_only"
            evaluation["backtest_window"].update(
                {
                    "sample_points_evaluated": len(actual_prices),
                    "window_count": len(actual_prices),
                    "samples": walk_forward_samples,
                }
            )
            evaluation["metrics"] = {
                "mae_aud_mwh": round(_mean(abs_errors) or 0.0, 4),
                "rmse_aud_mwh": round(math.sqrt(_mean(sq_errors) or 0.0), 4),
                "mape_pct": round(_mean(pct_errors), 4) if pct_errors else None,
                "pinball_loss_p10": round(_mean([_pinball_loss(actual, p10_value, 0.1) for actual in actual_prices]) or 0.0, 4),
                "pinball_loss_p50": round(_mean([_pinball_loss(actual, p50_value, 0.5) for actual in actual_prices]) or 0.0, 4),
                "pinball_loss_p90": round(_mean([_pinball_loss(actual, p90_value, 0.9) for actual in actual_prices]) or 0.0, 4),
                "coverage_80": coverage_80,
                "coverage_90": coverage_90,
                "brier_score_spike": round(_mean([(actual - spike_probability) ** 2 for actual in spike_actuals]) or 0.0, 4),
                "brier_score_negative_price": round(_mean([(actual - negative_probability) ** 2 for actual in negative_actuals]) or 0.0, 4),
            }
            evaluation["calibration"] = {
                "status": "baseline_only",
                "sample_count": len(actual_prices),
                "mean_error_aud_mwh": mean_error,
                "coverage_gap_80": round(coverage_80 - 0.8, 4),
                "coverage_gap_90": round(coverage_90 - 0.9, 4),
                "spike_probability_gap": round(spike_probability - spike_base_rate, 4),
                "negative_price_probability_gap": round(negative_probability - negative_base_rate, 4),
                "bias_direction": _classify_signed_gap(
                    mean_error,
                    tolerance=10.0,
                    low_label="overforecast",
                    mid_label="neutral",
                    high_label="underforecast",
                ),
                "coverage_assessment_80": _classify_signed_gap(
                    round(coverage_80 - 0.8, 4),
                    tolerance=0.05,
                    low_label="under_covered",
                    mid_label="well_calibrated",
                    high_label="over_covered",
                ),
                "coverage_assessment_90": _classify_signed_gap(
                    round(coverage_90 - 0.9, 4),
                    tolerance=0.05,
                    low_label="under_covered",
                    mid_label="well_calibrated",
                    high_label="over_covered",
                ),
                "spike_probability_assessment": _classify_signed_gap(
                    round(spike_probability - spike_base_rate, 4),
                    tolerance=0.1,
                    low_label="understated",
                    mid_label="well_calibrated",
                    high_label="overstated",
                ),
                "negative_price_probability_assessment": _classify_signed_gap(
                    round(negative_probability - negative_base_rate, 4),
                    tolerance=0.1,
                    low_label="understated",
                    mid_label="well_calibrated",
                    high_label="overstated",
                ),
            }
            evaluation["calibration"].update(_build_calibration_summary(evaluation["calibration"]))
            evaluation["regime_error_attribution"] = _build_regime_error_attribution(actual_prices, p50_value, driver_tags)
            evaluation["diagnostics"] = _build_evaluation_diagnostics(
                evaluation["metrics"],
                evaluation["calibration"],
            )
            warnings = [warning for warning in warnings if warning not in {"not_backtested", "not_calibrated"}]

    negative_duration_intervals, negative_duration_hours = _estimate_negative_duration(
        windows,
        horizon=metadata.get("horizon"),
        market=metadata.get("market"),
        negative_probability=round(negative_probability, 2),
    )

    return {
        "availability_status": "available",
        "forecast_class": "baseline_point_forecast",
        "market": metadata.get("market"),
        "region": metadata.get("region"),
        "horizon": metadata.get("horizon"),
        "issued_at": metadata.get("issued_at"),
        "coverage_mode": coverage.get("mode", metadata.get("coverage_quality", "none")),
        "regime_context": {
            "driver_tags": driver_tags,
            "primary_regime": None,
            "availability_status": "not_attached",
        },
        "forecast_horizon_summary": {
            "horizon": metadata.get("horizon"),
            "issued_at": metadata.get("issued_at"),
            "forecast_window_start": forecast_window_start,
            "forecast_window_end": forecast_window_end,
            "forward_points": int(coverage.get("forward_points") or 0),
            "event_count": int(coverage.get("event_count") or 0),
            "confidence_band": confidence_band,
        },
        "point_forecast": {
            "price_band_low_aud_mwh": round(low_value, 2),
            "price_band_mid_aud_mwh": mid_value,
            "price_band_high_aud_mwh": round(high_value, 2),
            "grid_stress_score": _safe_float(summary.get("grid_stress_score")),
        },
        "quantile_scaffold": _build_heuristic_quantile_scaffold(
            low_value=low_value,
            high_value=high_value,
            mid_value=mid_value,
            band_width=band_width,
            horizon=metadata.get("horizon"),
            driver_tags=driver_tags,
            spike_probability=round(spike_probability, 2),
            negative_probability=round(negative_probability, 2),
            confidence_band=confidence_band,
        ),
        "probabilities": {
            "price_spike": round(spike_probability, 2),
            "negative_price": round(negative_probability, 2),
            "negative_price_duration_intervals": negative_duration_intervals,
            "negative_price_duration_hours": negative_duration_hours,
            "duration_method": "window_probability_scan_v1",
        },
        "evaluation": evaluation,
        "warnings": warnings,
    }


def ensure_baseline_forecast_contract(payload: dict, *, db=None) -> dict:
    if not isinstance(payload, dict):
        return payload
    default_contract = _build_baseline_forecast_contract(payload, db=db)
    baseline = payload.get("baseline_forecast")
    if isinstance(baseline, dict):
        merged = _merge_missing_dict(baseline, default_contract)
        evaluation = merged.get("evaluation")
        if isinstance(evaluation, dict):
            calibration = evaluation.get("calibration")
            calibration_status = evaluation.get("calibration_status")
            inferred_status = calibration_status
            if inferred_status not in {"baseline_only", "calibrated"} and evaluation.get("backtest_status") == "evaluated":
                inferred_status = "baseline_only"
            if isinstance(calibration, dict) and calibration.get("status") == "not_calibrated" and inferred_status in {"baseline_only", "calibrated"}:
                calibration["status"] = inferred_status
                evaluation["calibration"] = calibration
            metrics = evaluation.get("metrics")
            diagnostics = evaluation.get("diagnostics")
            if isinstance(metrics, dict) and isinstance(calibration, dict) and (
                not isinstance(diagnostics, dict)
                or diagnostics.get("status") == "unavailable" and evaluation.get("backtest_status") == "evaluated"
            ):
                evaluation["diagnostics"] = _build_evaluation_diagnostics(metrics, calibration)
            merged["evaluation"] = evaluation
        payload["baseline_forecast"] = merged
        return payload
    payload["baseline_forecast"] = default_contract
    return payload


def build_nem_24h_forecast(db, region: str, horizon: str, as_of: str) -> dict:
    issued_at = format_timestamp(parse_as_of(as_of))
    recent = build_recent_market_features(db, "NEM", region, as_of)
    future_rows = fetch_nem_predispatch_window(region, as_of)
    as_of_dt = parse_as_of(as_of)
    window_end = as_of_dt + horizon_delta(horizon)
    forward_rows = [
        row for row in future_rows
        if parse_timestamp(row.get("time"))
        and as_of_dt <= parse_timestamp(row["time"]) <= window_end
    ]
    event_features = build_event_features(db, "NEM", region, as_of, horizon)

    max_future_price = max((float(row["price"] or 0.0) for row in forward_rows), default=recent["recent_max_price"])
    min_future_price = min((float(row["price"] or 0.0) for row in forward_rows), default=recent["recent_min_price"])
    max_future_demand = max((float(row["demand_mw"] or 0.0) for row in forward_rows), default=0.0)

    spike_score = clamp((max_future_price / 500.0) * 100.0 + min(event_features["severity_score"], 20.0))
    negative_score = clamp(max(abs(min(min_future_price, 0.0)) * 1.5, recent["negative_ratio"] * 100.0))
    reserve_score = clamp(25.0 + recent["recent_fcas_avg"] * 0.4 + event_features["severity_score"])
    fcas_score = clamp(reserve_score * 0.75 + recent["recent_fcas_avg"] * 0.6)
    charge_score = clamp(negative_score + (10.0 if min_future_price < 0 else 0.0))
    discharge_score = clamp(spike_score + (10.0 if max_future_price > 300 else 0.0))
    grid_stress = clamp(max(spike_score, reserve_score, recent["recent_avg_price"] * 0.25, max_future_demand / 180.0))

    driver_tags = sorted(
        set(event_features["state_types"])
        | ({"predispatch_price_spike"} if max_future_price > 150 else set())
        | ({"predispatch_negative_price"} if min_future_price < 0 else set())
    )

    windows = []
    for row in forward_rows:
        price = float(row["price"] or 0.0)
        if price < 0:
            windows.append(
                {
                    "start_time": row["time"],
                    "end_time": row["time"],
                    "window_type": "charge",
                    "scores": {
                        "charge_window_score": round(charge_score, 1),
                        "negative_price_risk_score": round(negative_score, 1),
                    },
                    "probabilities": {
                        "negative_price_probability": round(clamp(negative_score) / 100.0, 2),
                    },
                    "driver_tags": driver_tags,
                    "confidence": "medium" if forward_rows else "low",
                }
            )
        if price > 150:
            windows.append(
                {
                    "start_time": row["time"],
                    "end_time": row["time"],
                    "window_type": "discharge",
                    "scores": {
                        "discharge_window_score": round(discharge_score, 1),
                        "price_spike_risk_score": round(spike_score, 1),
                    },
                    "probabilities": {
                        "price_spike_probability": round(clamp(spike_score) / 100.0, 2),
                    },
                    "driver_tags": driver_tags,
                    "confidence": "medium" if forward_rows else "low",
                }
            )

    drivers = _event_drivers(event_features)
    if max_future_price > 150:
        drivers.append(
            {
                "driver_type": "predispatch_price_spike",
                "direction": "upside_risk",
                "severity": "medium" if max_future_price < 300 else "high",
                "headline": "Predispatch spike window",
                "summary": f"Predispatch price reached {round(max_future_price, 2)} AUD/MWh.",
                "source": "nem_predispatch",
                "source_url": NEM_PREDISPATCH_LISTING_URL,
                "effective_start": forward_rows[-1]["time"] if forward_rows else issued_at,
                "effective_end": forward_rows[-1]["time"] if forward_rows else issued_at,
            }
        )
    if min_future_price < 0:
        drivers.append(
            {
                "driver_type": "predispatch_negative_price",
                "direction": "downside_price / charge_window",
                "severity": "medium",
                "headline": "Predispatch negative-price window",
                "summary": f"Predispatch price reached {round(min_future_price, 2)} AUD/MWh.",
                "source": "nem_predispatch",
                "source_url": NEM_PREDISPATCH_LISTING_URL,
                "effective_start": forward_rows[0]["time"] if forward_rows else issued_at,
                "effective_end": forward_rows[0]["time"] if forward_rows else issued_at,
            }
        )

    coverage = "full" if forward_rows else "partial"
    confidence_band = "medium" if coverage == "full" else "low"
    warnings = [] if coverage == "full" else ["predispatch_missing_fallback"]
    source_status = {
        "recent_market_history": "ok" if recent["recent_history_points"] > 0 else "missing",
        "event_state": "ok" if event_features["event_count"] > 0 else "missing",
        "nem_predispatch": "ok" if forward_rows else "missing",
    }
    coverage = {
        "mode": coverage,
        "as_of_bucket": build_as_of_bucket(issued_at, horizon),
        "source_status": source_status,
        "recent_history_points": recent["recent_history_points"],
        "forward_points": len(forward_rows),
        "event_count": event_features["event_count"],
        "forward_window_start": forward_rows[0]["time"] if forward_rows else None,
        "forward_window_end": forward_rows[-1]["time"] if forward_rows else None,
    }
    market_context = {
        "recent_avg_price_aud_mwh": round(recent["recent_avg_price"], 2),
        "recent_price_max_aud_mwh": round(recent["recent_max_price"], 2),
        "recent_price_min_aud_mwh": round(recent["recent_min_price"], 2),
        "recent_negative_ratio_pct": round(recent["negative_ratio"] * 100.0, 2),
        "recent_fcas_avg_aud_mwh": round(recent["recent_fcas_avg"], 2),
        "forward_price_min_aud_mwh": round(min_future_price, 2),
        "forward_price_max_aud_mwh": round(max_future_price, 2),
        "forward_demand_peak_mw": round(max_future_demand, 2),
    }
    payload = {
        "metadata": {
            "market": "NEM",
            "region": region,
            "horizon": horizon,
            "forecast_mode": "hybrid_signal_calibrated",
            "coverage_quality": coverage["mode"],
            "issued_at": issued_at,
            "as_of": issued_at,
            "confidence_band": confidence_band,
            "sources_used": ["recent_market_history", "event_state"] + (["nem_predispatch"] if forward_rows else []),
            "investment_grade": False,
            "warnings": warnings,
        },
        "summary": {
            "grid_stress_score": round(grid_stress, 1),
            "price_spike_risk_score": round(spike_score, 1),
            "negative_price_risk_score": round(negative_score, 1),
            "reserve_tightness_risk_score": round(reserve_score, 1),
            "fcas_opportunity_score": round(fcas_score, 1),
            "charge_window_score": round(charge_score, 1),
            "discharge_window_score": round(discharge_score, 1),
            "driver_tags": driver_tags,
        },
        "coverage": coverage,
        "market_context": market_context,
        "windows": windows,
        "drivers": drivers,
        "disclaimer": {
            "mode": "market_monitoring_only",
            "message_key": "not_investment_grade",
        },
    }
    return ensure_baseline_forecast_contract(payload, db=db)


def build_nem_long_horizon_forecast(db, region: str, horizon: str, as_of: str) -> dict:
    issued_at = format_timestamp(parse_as_of(as_of))
    as_of_dt = parse_as_of(as_of)
    horizon_end = as_of_dt + horizon_delta(horizon)
    recent = build_recent_market_features(db, "NEM", region, as_of)
    event_features = build_event_features(db, "NEM", region, as_of, horizon)

    horizon_multiplier = 1.0 if horizon == "7d" else 1.25
    price_band_width = max(recent["recent_max_price"] - recent["recent_min_price"], 0.0)
    severity_score = event_features["severity_score"]

    projected_min = round(
        min(recent["recent_min_price"], 0.0) - (recent["negative_ratio"] * 120.0 * horizon_multiplier),
        2,
    )
    projected_max = round(
        max(
            recent["recent_max_price"] * (1.55 if horizon == "7d" else 1.9),
            recent["recent_avg_price"] + price_band_width * (1.8 if horizon == "7d" else 2.4),
        ) + severity_score * (1.35 if horizon == "7d" else 1.8),
        2,
    )

    spike_score = clamp(
        price_band_width * (0.9 if horizon == "7d" else 1.1)
        + recent["recent_avg_price"] * 0.3
        + severity_score * (0.8 if horizon == "7d" else 0.95)
    )
    negative_score = clamp(
        recent["negative_ratio"] * 100.0 * (1.3 if horizon == "7d" else 1.5)
        + abs(min(recent["recent_min_price"], 0.0)) * 1.1
        + severity_score * 0.2
    )
    reserve_score = clamp(20.0 + recent["recent_fcas_avg"] * 0.5 + severity_score * 0.8)
    fcas_score = clamp(18.0 + recent["recent_fcas_avg"] * 0.9 + severity_score * 0.5)
    charge_score = clamp(negative_score + 6.0)
    discharge_score = clamp(spike_score + 8.0)
    grid_stress = clamp(max(spike_score, reserve_score, recent["recent_avg_price"] * 0.4 + severity_score * 0.35))

    driver_tags = sorted(set(event_features["state_types"]) | {"market_regime_shift"})
    drivers = _event_drivers(event_features)
    drivers.append(
        {
            "driver_type": "market_regime_shift",
            "direction": "two_way",
            "severity": "high" if grid_stress >= 70 else "medium",
            "headline": "Market regime shift",
            "summary": (
                f"Recent spot prices ranged from {round(recent['recent_min_price'], 2)} to "
                f"{round(recent['recent_max_price'], 2)} AUD/MWh, implying a broader {horizon} risk band."
            ),
            "source": "recent_market_history",
            "source_url": None,
            "effective_start": issued_at,
            "effective_end": format_timestamp(horizon_end),
        }
    )
    if recent["negative_ratio"] > 0.02 or recent["recent_min_price"] < 0:
        driver_tags.append("negative_price_regime")
        drivers.append(
            {
                "driver_type": "negative_price_regime",
                "direction": "downside_price / charge_window",
                "severity": "medium",
                "headline": "Negative-price regime risk",
                "summary": (
                    f"Recent negative-price share reached {round(recent['negative_ratio'] * 100.0, 2)}% "
                    f"with a recent low of {round(recent['recent_min_price'], 2)} AUD/MWh."
                ),
                "source": "recent_market_history",
                "source_url": None,
                "effective_start": issued_at,
                "effective_end": format_timestamp(horizon_end),
            }
        )
    if recent["recent_fcas_avg"] > 0:
        driver_tags.append("fcas_pressure_regime")
        drivers.append(
            {
                "driver_type": "fcas_pressure_regime",
                "direction": "ancillary_opportunity",
                "severity": "high" if fcas_score >= 70 else "medium",
                "headline": "FCAS pressure regime",
                "summary": (
                    f"Recent aggregate FCAS prices averaged {round(recent['recent_fcas_avg'], 2)} AUD/MWh, "
                    f"supporting a higher ancillary-service opportunity regime."
                ),
                "source": "recent_market_history",
                "source_url": None,
                "effective_start": issued_at,
                "effective_end": format_timestamp(horizon_end),
            }
        )

    driver_tags = sorted(set(driver_tags))
    confidence_band = "medium" if horizon == "7d" and recent["recent_history_points"] > 0 else "low"
    forecast_mode = "daily_regime_outlook" if horizon == "7d" else "structural_regime_outlook"
    warnings = ["confidence_constrained"]

    coverage = {
        "mode": "partial",
        "as_of_bucket": build_as_of_bucket(issued_at, horizon),
        "source_status": {
            "recent_market_history": "ok" if recent["recent_history_points"] > 0 else "missing",
            "event_state": "ok" if event_features["event_count"] > 0 else "missing",
            "nem_predispatch": "stale",
        },
        "recent_history_points": recent["recent_history_points"],
        "forward_points": 0,
        "event_count": event_features["event_count"],
        "forward_window_start": issued_at,
        "forward_window_end": format_timestamp(horizon_end),
    }
    market_context = {
        "recent_avg_price_aud_mwh": round(recent["recent_avg_price"], 2),
        "recent_price_max_aud_mwh": round(recent["recent_max_price"], 2),
        "recent_price_min_aud_mwh": round(recent["recent_min_price"], 2),
        "recent_negative_ratio_pct": round(recent["negative_ratio"] * 100.0, 2),
        "recent_fcas_avg_aud_mwh": round(recent["recent_fcas_avg"], 2),
        "forward_price_min_aud_mwh": projected_min,
        "forward_price_max_aud_mwh": projected_max,
        "forward_demand_peak_mw": None,
    }

    payload = {
        "metadata": {
            "market": "NEM",
            "region": region,
            "horizon": horizon,
            "forecast_mode": forecast_mode,
            "coverage_quality": coverage["mode"],
            "issued_at": issued_at,
            "as_of": issued_at,
            "confidence_band": confidence_band,
            "sources_used": ["recent_market_history", "event_state"],
            "investment_grade": False,
            "warnings": warnings,
        },
        "summary": {
            "grid_stress_score": round(grid_stress, 1),
            "price_spike_risk_score": round(spike_score, 1),
            "negative_price_risk_score": round(negative_score, 1),
            "reserve_tightness_risk_score": round(reserve_score, 1),
            "fcas_opportunity_score": round(fcas_score, 1),
            "charge_window_score": round(charge_score, 1),
            "discharge_window_score": round(discharge_score, 1),
            "driver_tags": driver_tags,
        },
        "coverage": coverage,
        "market_context": market_context,
        "windows": [
            {
                "start_time": issued_at,
                "end_time": format_timestamp(horizon_end),
                "window_type": "core_risk_window",
                "scores": {
                    "grid_stress_score": round(grid_stress, 1),
                    "price_spike_risk_score": round(spike_score, 1),
                    "negative_price_risk_score": round(negative_score, 1),
                    "fcas_opportunity_score": round(fcas_score, 1),
                },
                "probabilities": {
                    "price_spike_probability": round(clamp(spike_score) / 100.0, 2),
                    "negative_price_probability": round(clamp(negative_score) / 100.0, 2),
                },
                "driver_tags": driver_tags,
                "confidence": confidence_band,
            }
        ],
        "drivers": drivers,
        "disclaimer": {
            "mode": "market_monitoring_only",
            "message_key": "not_investment_grade",
        },
    }
    return ensure_baseline_forecast_contract(payload, db=db)


def build_nem_forecast(db, region: str, horizon: str, as_of: str) -> dict:
    if horizon == "24h":
        return build_nem_24h_forecast(db, region, horizon, as_of)
    return build_nem_long_horizon_forecast(db, region, horizon, as_of)


def build_wem_core_forecast(db, region: str, horizon: str, as_of: str) -> dict:
    issued_at = format_timestamp(parse_as_of(as_of))
    recent = build_recent_market_features(db, "WEM", region, as_of)
    event_features = build_event_features(db, "WEM", region, as_of, horizon)

    grid_stress = clamp(
        25.0
        + recent["binding_count_avg"] * 10.0
        + recent["binding_shadow_max"] / 10.0
        + recent["shortfall_total"] * 4.0
        + event_features["severity_score"] * 0.6
    )
    spike_score = clamp(recent["recent_max_price"] / 4.0 + recent["binding_shadow_max"] / 8.0)
    negative_score = 0.0
    reserve_score = clamp(20.0 + recent["shortfall_total"] * 8.0 + recent["recent_fcas_avg"] * 0.05)
    fcas_score = clamp(30.0 + recent["recent_fcas_avg"] * 0.1 + recent["binding_count_avg"] * 8.0)
    charge_score = clamp(15.0 + recent["network_shadow_max"] * 0.08)
    discharge_score = clamp(spike_score + 10.0)
    driver_tags = sorted(set(event_features["state_types"]) | {"wem_constraint_tightness", "wem_shortfall_signal"})

    as_of_dt = parse_as_of(as_of)
    window_end = as_of_dt + dt.timedelta(hours=24 if horizon == "24h" else 48)
    windows = [
        {
            "start_time": issued_at,
            "end_time": format_timestamp(window_end),
            "window_type": "core_risk_window",
            "scores": {
                "grid_stress_score": round(grid_stress, 1),
                "fcas_opportunity_score": round(fcas_score, 1),
            },
            "probabilities": {
                "price_spike_probability": round(clamp(spike_score) / 100.0, 2),
            },
            "driver_tags": driver_tags,
            "confidence": "low",
        }
    ]

    drivers = _event_drivers(event_features)
    drivers.append(
        {
            "driver_type": "wem_constraint_tightness",
            "direction": "upside_risk",
            "severity": "high" if recent["binding_shadow_max"] >= 300 else "medium",
            "headline": "WEM constraint tightness",
            "summary": (
                f"Recent binding shadow price peaked at {round(recent['binding_shadow_max'], 2)} "
                f"with average binding count {round(recent['binding_count_avg'], 2)}."
            ),
            "source": "wem_ess_slim",
            "source_url": None,
            "effective_start": issued_at,
            "effective_end": format_timestamp(window_end),
        }
    )
    source_status = {
        "wem_ess_slim": "ok" if recent["recent_history_points"] > 0 else "missing",
        "event_state": "ok" if event_features["event_count"] > 0 else "missing",
    }
    coverage = {
        "mode": "core_only",
        "as_of_bucket": build_as_of_bucket(issued_at, horizon),
        "source_status": source_status,
        "recent_history_points": recent["recent_history_points"],
        "forward_points": 0,
        "event_count": event_features["event_count"],
        "forward_window_start": issued_at,
        "forward_window_end": format_timestamp(window_end),
    }
    market_context = {
        "recent_avg_price_aud_mwh": round(recent["recent_avg_price"], 2),
        "recent_price_max_aud_mwh": round(recent["recent_max_price"], 2),
        "recent_fcas_avg_aud_mwh": round(recent["recent_fcas_avg"], 2),
        "binding_count_avg": round(recent["binding_count_avg"], 2),
        "binding_shadow_max": round(recent["binding_shadow_max"], 2),
        "network_shadow_max": round(recent["network_shadow_max"], 2),
        "shortfall_total_mw": round(recent["shortfall_total"], 2),
        "constraint_pressure_index": round(recent["binding_count_avg"] * 10.0 + recent["shortfall_total"], 2),
    }

    payload = {
        "metadata": {
            "market": "WEM",
            "region": region,
            "horizon": horizon,
            "forecast_mode": "hybrid_signal_calibrated",
            "coverage_quality": "core_only",
            "issued_at": issued_at,
            "as_of": issued_at,
            "confidence_band": "low",
            "sources_used": ["wem_ess_slim", "event_state"],
            "investment_grade": False,
            "warnings": ["confidence_constrained", "core_only_coverage"],
        },
        "summary": {
            "grid_stress_score": round(grid_stress, 1),
            "price_spike_risk_score": round(spike_score, 1),
            "negative_price_risk_score": round(negative_score, 1),
            "reserve_tightness_risk_score": round(reserve_score, 1),
            "fcas_opportunity_score": round(fcas_score, 1),
            "charge_window_score": round(charge_score, 1),
            "discharge_window_score": round(discharge_score, 1),
            "driver_tags": driver_tags,
        },
        "coverage": coverage,
        "market_context": market_context,
        "windows": windows,
        "drivers": drivers,
        "disclaimer": {
            "mode": "core_only",
            "message_key": "not_investment_grade",
        },
    }
    return ensure_baseline_forecast_contract(payload, db=db)


def get_grid_forecast_response(db, market: str, region: str, horizon: str, as_of: str | None = None) -> dict:
    normalized_market = "WEM" if market == "WEM" or region == "WEM" else "NEM"
    normalized_region = "WEM" if normalized_market == "WEM" else region
    as_of_dt = parse_as_of(as_of)
    issued_at = format_timestamp(as_of_dt)
    bucket = build_as_of_bucket(issued_at, horizon)
    cached = db.fetch_grid_forecast_snapshot(
        market=normalized_market,
        region=normalized_region,
        horizon=horizon,
        as_of_bucket=bucket,
    )
    if cached:
        expires_at = parse_timestamp(cached["expires_at"])
        if expires_at and expires_at > as_of_dt and _is_current_forecast_payload(cached.get("response")):
            return cached["response"]

    if normalized_market == "WEM":
        response = build_wem_core_forecast(db, normalized_region, horizon, issued_at)
    else:
        response = build_nem_forecast(db, normalized_region, horizon, issued_at)

    db.upsert_grid_forecast_snapshot(
        market=normalized_market,
        region=normalized_region,
        horizon=horizon,
        as_of_bucket=bucket,
        issued_at=response["metadata"]["issued_at"],
        expires_at=expiry_for_bucket(bucket, horizon),
        coverage_quality=response["metadata"]["coverage_quality"],
        response_payload=response,
    )
    return response


def get_grid_forecast_coverage(db, market: str, region: str, horizon: str, as_of: str | None = None) -> dict:
    response = get_grid_forecast_response(db, market=market, region=region, horizon=horizon, as_of=as_of)
    metadata = response.get("metadata", {})
    return {
        "market": metadata.get("market"),
        "region": metadata.get("region"),
        "horizon": metadata.get("horizon"),
        "coverage_quality": metadata.get("coverage_quality", "none"),
        "sources_used": metadata.get("sources_used", []),
        "source_status": (response.get("coverage") or {}).get("source_status", {}),
        "recent_history_points": (response.get("coverage") or {}).get("recent_history_points", 0),
        "forward_points": (response.get("coverage") or {}).get("forward_points", 0),
        "event_count": (response.get("coverage") or {}).get("event_count", 0),
        "investment_grade": metadata.get("investment_grade", False),
        "warnings": metadata.get("warnings", []),
    }
