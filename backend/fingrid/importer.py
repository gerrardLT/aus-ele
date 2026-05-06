from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .catalog import get_dataset_config
from .schemas import normalize_fingrid_row
from .service import seed_dataset_catalog

START_TIME_KEYS = ("startTime", "start_time", "Start time", "Start Time", "start", "timestamp")
END_TIME_KEYS = ("endTime", "end_time", "End time", "End Time", "end")
VALUE_KEYS = ("value", "Value", "price", "Price", "volume", "Volume")
QUALITY_KEYS = ("quality", "qualityFlag", "Quality", "Quality Flag")
UPDATED_AT_KEYS = ("updatedAt", "updated_at", "Updated at", "Updated At")


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _coerce_value(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().replace(" ", "").replace(",", ".")
    if not normalized:
        return None
    return float(normalized)


def _read_csv_rows(csv_path: str | Path, delimiter: str | None = None) -> list[dict[str, str]]:
    text = Path(csv_path).read_text(encoding="utf-8-sig")
    sample = text[:4096]
    detected_delimiter = delimiter
    if detected_delimiter is None:
        try:
            detected_delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            detected_delimiter = ","
    reader = csv.DictReader(text.splitlines(), delimiter=detected_delimiter)
    return [dict(row) for row in reader]


def import_fingrid_csv(
    db,
    *,
    dataset_id: str,
    csv_path: str | Path,
    value_column: str | None = None,
    delimiter: str | None = None,
    ingested_at: str | None = None,
) -> dict:
    dataset = get_dataset_config(dataset_id)
    seed_dataset_catalog(db)
    ingested_at = ingested_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = _read_csv_rows(csv_path, delimiter=delimiter)

    normalized_rows = []
    for row in rows:
        raw_value = row.get(value_column) if value_column else _pick(row, VALUE_KEYS)
        normalized_rows.append(
            normalize_fingrid_row(
                dataset,
                {
                    "startTime": _pick(row, START_TIME_KEYS),
                    "endTime": _pick(row, END_TIME_KEYS),
                    "value": _coerce_value(raw_value),
                    "quality": _pick(row, QUALITY_KEYS),
                    "updatedAt": _pick(row, UPDATED_AT_KEYS),
                },
                ingested_at=ingested_at,
            )
        )

    db.upsert_fingrid_timeseries(normalized_rows)
    last_timestamp_utc = normalized_rows[-1]["timestamp_utc"] if normalized_rows else None
    db.upsert_fingrid_sync_state(
        dataset_id=dataset_id,
        last_success_at=ingested_at,
        last_attempt_at=ingested_at,
        last_cursor=last_timestamp_utc,
        last_synced_timestamp_utc=last_timestamp_utc,
        sync_status="ok",
        last_error=None,
        backfill_started_at=None,
        backfill_completed_at=None,
    )
    return {
        "dataset_id": dataset_id,
        "mode": "csv_import",
        "csv_path": str(csv_path),
        "records_upserted": len(normalized_rows),
        "last_synced_timestamp_utc": last_timestamp_utc,
    }
