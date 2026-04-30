from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


NEM_REGION_TIMEZONES = {
    "NSW1": "Australia/Sydney",
    "QLD1": "Australia/Brisbane",
    "SA1": "Australia/Adelaide",
    "TAS1": "Australia/Hobart",
    "VIC1": "Australia/Melbourne",
}

REQUIRED_FIELDS = (
    "market",
    "country",
    "region_or_zone",
    "interval_start_utc",
    "interval_end_utc",
    "interval_minutes",
    "product_type",
    "service_type",
    "currency",
    "unit",
    "value",
    "source_name",
    "source_version",
    "ingested_at",
)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _parse_local_naive(raw_value: str, timezone_name: str) -> datetime:
    local_dt = datetime.fromisoformat(raw_value)
    return local_dt.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)


def _normalize_currency(unit: str) -> str:
    if unit.startswith("AUD/"):
        return "AUD"
    if unit.startswith("EUR/"):
        return "EUR"
    raise ValueError(f"Unsupported currency unit: {unit}")


def _validate_canonical_row(row: dict) -> dict:
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    if missing:
        raise ValueError(f"Missing canonical fields: {', '.join(missing)}")
    return row


def map_nem_trading_price_row(raw_row: dict, *, ingested_at: str, source_version: str = "trading_price_v1") -> dict:
    region = raw_row["region_id"]
    timezone_name = NEM_REGION_TIMEZONES[region]
    start_utc = _parse_local_naive(raw_row["settlement_date"], timezone_name)
    end_utc = start_utc + timedelta(minutes=5)

    return _validate_canonical_row(
        {
            "market": "NEM",
            "country": "Australia",
            "region_or_zone": region,
            "interval_start_utc": _format_utc(start_utc),
            "interval_end_utc": _format_utc(end_utc),
            "interval_minutes": 5,
            "product_type": "electricity",
            "service_type": "energy_spot",
            "currency": "AUD",
            "unit": "AUD/MWh",
            "value": raw_row["rrp_aud_mwh"],
            "source_name": "AEMO NEM",
            "source_version": source_version,
            "ingested_at": ingested_at,
        }
    )


def map_wem_ess_market_row(
    raw_row: dict,
    *,
    ingested_at: str,
    source_version: str = "wem_ess_market_price_v1",
) -> dict:
    start_utc = _parse_local_naive(raw_row["dispatch_interval"], "Australia/Perth")
    end_utc = start_utc + timedelta(minutes=5)

    return _validate_canonical_row(
        {
            "market": "WEM",
            "country": "Australia",
            "region_or_zone": "WEM",
            "interval_start_utc": _format_utc(start_utc),
            "interval_end_utc": _format_utc(end_utc),
            "interval_minutes": 5,
            "product_type": "electricity",
            "service_type": "energy_spot",
            "currency": "AUD",
            "unit": "AUD/MWh",
            "value": raw_row["energy_price"],
            "source_name": "AEMO WEM",
            "source_version": source_version,
            "ingested_at": ingested_at,
        }
    )


def map_fingrid_timeseries_row(
    dataset: dict,
    normalized_row: dict,
    *,
    source_version: str | None = None,
) -> dict:
    start_utc = _parse_utc(normalized_row["timestamp_utc"])
    end_raw = ((normalized_row.get("extra_json") or {}).get("end_time"))
    if end_raw:
        end_utc = _parse_utc(end_raw)
    else:
        frequency = dataset.get("frequency", "1h")
        if frequency.endswith("h"):
            end_utc = start_utc + timedelta(hours=int(frequency[:-1]))
        elif frequency.endswith("min"):
            end_utc = start_utc + timedelta(minutes=int(frequency[:-3]))
        else:
            raise ValueError(f"Unsupported Fingrid frequency: {frequency}")

    unit = dataset["unit"]
    version = source_version or f"dataset_{dataset['dataset_id']}_v1"

    return _validate_canonical_row(
        {
            "market": "Fingrid",
            "country": "Finland",
            "region_or_zone": "FI",
            "interval_start_utc": _format_utc(start_utc),
            "interval_end_utc": _format_utc(end_utc),
            "interval_minutes": int((end_utc - start_utc).total_seconds() // 60),
            "product_type": "ancillary_service",
            "service_type": dataset["value_kind"],
            "currency": _normalize_currency(unit),
            "unit": unit,
            "value": normalized_row["value"],
            "source_name": "Fingrid",
            "source_version": version,
            "ingested_at": normalized_row["ingested_at"],
        }
    )
