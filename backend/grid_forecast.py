import csv
import datetime as dt
import io
import json
import logging
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
    if not isinstance(coverage, dict) or not isinstance(market_context, dict):
        return False
    return True


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
    return {
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

    return {
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

    return {
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
