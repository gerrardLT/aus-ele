from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _parse_timestamp(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalize_fingrid_row(dataset: dict, raw_row: dict, *, ingested_at: str) -> dict:
    start_raw = raw_row.get("startTime") or raw_row.get("start_time")
    end_raw = raw_row.get("endTime") or raw_row.get("end_time")
    if not start_raw:
        raise ValueError("Missing startTime in Fingrid row")

    start_utc = _parse_timestamp(start_raw)
    local_tz = ZoneInfo(dataset["timezone"])
    local_dt = start_utc.astimezone(local_tz)

    return {
        "dataset_id": dataset["dataset_id"],
        "series_key": dataset["series_key"],
        "timestamp_utc": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local": local_dt.isoformat(),
        "value": raw_row.get("value"),
        "unit": dataset["unit"],
        "quality_flag": raw_row.get("quality") or raw_row.get("qualityFlag"),
        "source_updated_at": raw_row.get("updatedAt") or raw_row.get("updated_at"),
        "ingested_at": ingested_at,
        "extra_json": {
            "end_time": end_raw,
        },
    }
