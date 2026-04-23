from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Iterable
from zoneinfo import ZoneInfo

from .catalog import get_dataset_config, list_dataset_configs
from .client import FingridClient
from .schemas import normalize_fingrid_row


def _parse_utc(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_dataset_catalog(db):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.upsert_fingrid_dataset_catalog(
        [{**dataset, "enabled": 1, "updated_at": now_utc} for dataset in list_dataset_configs()]
    )


def _month_windows(start_utc: datetime, end_utc: datetime) -> Iterable[tuple[datetime, datetime]]:
    cursor = start_utc
    while cursor < end_utc:
        if cursor.month == 12:
            next_month = cursor.replace(
                year=cursor.year + 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        else:
            next_month = cursor.replace(
                month=cursor.month + 1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        window_end = min(next_month, end_utc)
        yield cursor, window_end
        cursor = window_end


def sync_dataset(
    db,
    *,
    dataset_id: str,
    mode: str,
    start: str | None = None,
    end: str | None = None,
    client: FingridClient | None = None,
    ingested_at: str | None = None,
) -> dict:
    dataset = get_dataset_config(dataset_id)
    seed_dataset_catalog(db)
    client = client or FingridClient()
    now_utc = datetime.now(timezone.utc)
    ingested_at = ingested_at or _format_utc(now_utc)

    if mode == "backfill":
        start_utc = _parse_utc(start or dataset["default_backfill_start"])
    else:
        lookback_days = int(dataset["default_incremental_lookback_days"])
        start_utc = _parse_utc(start) if start else now_utc - timedelta(days=lookback_days)

    end_utc = _parse_utc(end) if end else now_utc

    db.upsert_fingrid_sync_state(
        dataset_id=dataset_id,
        last_success_at=None,
        last_attempt_at=_format_utc(now_utc),
        last_cursor=None,
        last_synced_timestamp_utc=None,
        sync_status="running",
        last_error=None,
        backfill_started_at=_format_utc(now_utc) if mode == "backfill" else None,
        backfill_completed_at=None,
    )

    records_upserted = 0
    last_timestamp_utc = None
    windows_synced = 0

    for window_start, window_end in _month_windows(start_utc, end_utc):
        raw_rows = client.fetch_dataset_window(
            dataset_id,
            start_time_utc=_format_utc(window_start),
            end_time_utc=_format_utc(window_end),
        )
        normalized_rows = [normalize_fingrid_row(dataset, row, ingested_at=ingested_at) for row in raw_rows]
        db.upsert_fingrid_timeseries(normalized_rows)
        windows_synced += 1
        records_upserted += len(normalized_rows)
        if normalized_rows:
            last_timestamp_utc = normalized_rows[-1]["timestamp_utc"]

    db.upsert_fingrid_sync_state(
        dataset_id=dataset_id,
        last_success_at=_format_utc(now_utc),
        last_attempt_at=_format_utc(now_utc),
        last_cursor=last_timestamp_utc,
        last_synced_timestamp_utc=last_timestamp_utc,
        sync_status="ok",
        last_error=None,
        backfill_started_at=None,
        backfill_completed_at=_format_utc(now_utc) if mode == "backfill" else None,
    )

    return {
        "dataset_id": dataset_id,
        "mode": mode,
        "windows_synced": windows_synced,
        "records_upserted": records_upserted,
        "last_synced_timestamp_utc": last_timestamp_utc,
    }


def _bucket_key(local_dt, aggregation: str):
    if aggregation in {"raw", "hour"}:
        return local_dt.replace(minute=0, second=0, microsecond=0)
    if aggregation == "day":
        return local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if aggregation == "week":
        iso_year, iso_week, _ = local_dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if aggregation == "month":
        return local_dt.strftime("%Y-%m-01T00:00:00")
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def _aggregate_rows(rows: list[dict], *, aggregation: str, tz_name: str) -> list[dict]:
    if aggregation == "raw":
        return [
            {
                "timestamp": row["timestamp_local"],
                "timestamp_utc": row["timestamp_utc"],
                "value": row["value"],
                "unit": row["unit"],
            }
            for row in rows
        ]

    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        utc_dt = _parse_utc(row["timestamp_utc"])
        local_dt = utc_dt.astimezone(tz)
        buckets[_bucket_key(local_dt, aggregation)].append(row["value"])

    items = []
    for key, values in sorted(buckets.items(), key=lambda item: str(item[0])):
        timestamp = key if isinstance(key, str) else key.isoformat()
        items.append(
            {
                "timestamp": timestamp,
                "timestamp_utc": timestamp,
                "value": round(mean(values), 4),
                "unit": rows[0]["unit"] if rows else "EUR/MW",
            }
        )
    return items


def _build_summary_kpis(rows: list[dict]) -> dict:
    values = [row["value"] for row in rows if row["value"] is not None]
    if not values:
        return {
            "latest_value": None,
            "latest_timestamp": None,
            "avg_24h": None,
            "avg_7d": None,
            "avg_30d": None,
            "min_value": None,
            "max_value": None,
        }

    latest = rows[-1]
    return {
        "latest_value": latest["value"],
        "latest_timestamp": latest["timestamp_utc"],
        "avg_24h": round(mean(values[-24:]), 4),
        "avg_7d": round(mean(values[-(24 * 7):]), 4),
        "avg_30d": round(mean(values[-(24 * 30):]), 4),
        "min_value": min(values),
        "max_value": max(values),
    }


def _hourly_profile(rows: list[dict], tz_name: str) -> list[dict]:
    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        local_dt = _parse_utc(row["timestamp_utc"]).astimezone(tz)
        buckets[local_dt.hour].append(row["value"])
    return [{"hour": hour, "avg_value": round(mean(values), 4)} for hour, values in sorted(buckets.items())]


def _yearly_average_series(rows: list[dict], tz_name: str) -> list[dict]:
    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        local_dt = _parse_utc(row["timestamp_utc"]).astimezone(tz)
        buckets[local_dt.year].append(row["value"])
    return [
        {
            "timestamp": f"{year}-01-01T00:00:00",
            "timestamp_utc": f"{year}-01-01T00:00:00Z",
            "value": round(mean(values), 4),
            "unit": rows[0]["unit"] if rows else "EUR/MW",
        }
        for year, values in sorted(buckets.items())
    ]


def get_dataset_series_payload(
    db,
    *,
    dataset_id: str,
    start: str | None,
    end: str | None,
    aggregation: str,
    tz: str,
    limit: int,
) -> dict:
    dataset = get_dataset_config(dataset_id)
    rows = db.fetch_fingrid_series(dataset_id=dataset_id, start_utc=start, end_utc=end, limit=limit)
    return {
        "dataset": dataset,
        "query": {"start": start, "end": end, "aggregation": aggregation, "tz": tz, "limit": limit},
        "series": _aggregate_rows(rows, aggregation=aggregation, tz_name=tz),
    }


def get_dataset_summary_payload(db, *, dataset_id: str, start: str | None, end: str | None) -> dict:
    dataset = get_dataset_config(dataset_id)
    rows = db.fetch_fingrid_series(dataset_id=dataset_id, start_utc=start, end_utc=end)
    return {
        "dataset": dataset,
        "window": {"start": start, "end": end},
        "kpis": _build_summary_kpis(rows),
        "monthly_average_series": _aggregate_rows(rows, aggregation="month", tz_name=dataset["timezone"]),
        "yearly_average_series": _yearly_average_series(rows, dataset["timezone"]),
        "hourly_profile": _hourly_profile(rows, dataset["timezone"]),
    }


def get_dataset_status_payload(db, *, dataset_id: str) -> dict:
    dataset = get_dataset_config(dataset_id)
    coverage = db.fetch_fingrid_dataset_coverage(dataset_id)
    sync_state = db.fetch_fingrid_sync_state(dataset_id) or {
        "dataset_id": dataset_id,
        "last_success_at": None,
        "last_attempt_at": None,
        "last_cursor": None,
        "last_synced_timestamp_utc": None,
        "sync_status": "idle",
        "last_error": None,
        "backfill_started_at": None,
        "backfill_completed_at": None,
    }
    return {
        "dataset": dataset,
        "status": {
            **sync_state,
            **coverage,
        },
    }
