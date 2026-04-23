from datetime import datetime, timedelta, timezone
from typing import Iterable

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


def get_dataset_series_payload(db, *, dataset_id: str, start: str | None, end: str | None, aggregation: str, tz: str, limit: int) -> dict:
    raise NotImplementedError


def get_dataset_summary_payload(db, *, dataset_id: str, start: str | None, end: str | None) -> dict:
    raise NotImplementedError


def get_dataset_status_payload(db, *, dataset_id: str) -> dict:
    raise NotImplementedError
