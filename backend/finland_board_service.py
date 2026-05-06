from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from finland_board_contracts import (
    FINLAND_BOARD_FIELDS,
    get_finland_board_field,
    get_finland_board_overview_cards,
    get_finland_board_view,
)

GRANULARITY_ALIASES = {
    "hour": "1h",
    "1h": "1h",
    "15m": "15m",
    "day": "day",
}

VALID_CHART_MODES = {"single", "compare", "spread"}

FINGRID_FIELD_DATASET_IDS = {
    "fcr_n_price_eur_mw": "317",
    "fcr_n_volume_mw": "316",
    "fcr_d_up_price_eur_mw": "318",
    "fcr_d_up_volume_mw": "315",
    "fcr_d_down_price_eur_mw": "283",
    "fcr_d_down_volume_mw": "281",
    "imbalance_price_eur_mwh": "319",
}


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.fromisoformat(value)


def _format_timestamp(timestamp_utc: str, timestamp_local: str | None, tz: str) -> str:
    if timestamp_local:
        return datetime.fromisoformat(timestamp_local).astimezone(ZoneInfo(tz)).isoformat()
    return _parse_timestamp(timestamp_utc).astimezone(ZoneInfo(tz)).isoformat()


def _fetch_fingrid_dataset_series(
    db,
    *,
    dataset_id: str,
    start: str | None,
    end: str | None,
) -> list[dict]:
    fetcher = getattr(db, "fetch_fingrid_series", None)
    if fetcher is None:
        return []
    rows = fetcher(dataset_id=dataset_id, start_utc=start, end_utc=end)
    return list(rows or [])


def _fetch_series(db, field_key: str, start: str | None, end: str | None, granularity: str | None = None) -> list[dict]:
    fetcher = getattr(db, "fetch_finland_board_series", None)
    if fetcher is not None:
        rows = fetcher(field_key, start=start, end=end, granularity=granularity)
        if rows:
            return list(rows)

    dataset_id = FINGRID_FIELD_DATASET_IDS.get(field_key)
    if dataset_id:
        return _fetch_fingrid_dataset_series(db, dataset_id=dataset_id, start=start, end=end)
    return []


def _values(rows: list[dict]) -> list[float]:
    return [float(row["value"]) for row in rows if row.get("value") is not None]


def _build_metric_card(field_key: str, start: str | None, end: str | None, granularity: str, db) -> dict:
    field = get_finland_board_field(field_key)
    rows = _fetch_series(db, field_key, start, end, granularity)
    samples = _values(rows)
    return {
        "field_key": field_key,
        "label": field["label"],
        "unit": field["unit"],
        "granularity": granularity,
        "value": round(mean(samples), 2) if samples else None,
        "change_vs_previous": None,
        "sparkline": [round(value, 2) for value in samples[-12:]],
    }


def _build_join_card(start: str | None, end: str | None, db) -> dict:
    field = get_finland_board_field("join_completeness")
    capacity_rows = _fetch_series(db, "fcr_n_price_eur_mw", start, end, "1h")
    spot_rows = _fetch_series(db, "spot_price_fi_eur_mwh", start, end, "1h")
    capacity_keys = {row["timestamp_utc"] for row in capacity_rows}
    spot_keys = {row["timestamp_utc"] for row in spot_rows}
    matched = len(capacity_keys & spot_keys)
    total = len(capacity_keys)
    completeness = round((matched / total) * 100.0, 1) if total and spot_keys else None
    latest_coverage = None
    if capacity_rows or spot_rows:
        latest_coverage = max(
            [row["timestamp_utc"] for row in capacity_rows] + [row["timestamp_utc"] for row in spot_rows]
        )
    return {
        "field_key": field["field_key"],
        "label": field["label"],
        "unit": field["unit"],
        "granularity": field["granularity"],
        "value": completeness,
        "change_vs_previous": None,
        "sparkline": [completeness] if completeness is not None else [],
        "latest_coverage_utc": latest_coverage,
    }


def _column_payload(field_key: str) -> dict:
    field = get_finland_board_field(field_key)
    return {
        "field_key": field["field_key"],
        "label": field["label"],
        "unit": field["unit"],
        "granularity": field["granularity"],
        "source_name": field["source_name"],
        "source_type": field["source_type"],
        "category": field["category"],
    }


def _join_rows_for_view(view_config: dict, db, start: str | None, end: str | None, tz: str) -> list[dict]:
    row_map: dict[str, dict] = {}
    for field_key in view_config["columns"]:
        if field_key in {"timestamp_helsinki", "date"}:
            continue
        field = get_finland_board_field(field_key)
        rows = _fetch_series(db, field_key, start, end, field.get("granularity"))
        for point in rows:
            timestamp_utc = point["timestamp_utc"]
            row = row_map.setdefault(
                timestamp_utc,
                {
                    "timestamp_utc": timestamp_utc,
                    "timestamp_helsinki": _format_timestamp(
                        timestamp_utc,
                        point.get("timestamp_local"),
                        tz,
                    ),
                },
            )
            row[field_key] = point.get("value")
            row["date"] = row["timestamp_helsinki"][:10]
    return [row_map[key] for key in sorted(row_map)]


def _aggregate_rows_by_day(rows: list[dict], view_config: dict) -> list[dict]:
    day_map: dict[str, dict] = {}
    numeric_fields = [field_key for field_key in view_config["columns"] if field_key not in {"date", "timestamp_helsinki"}]
    for row in rows:
        date_key = row["date"]
        bucket = day_map.setdefault(date_key, {"date": date_key, "_samples": {field_key: [] for field_key in numeric_fields}})
        for field_key in numeric_fields:
            value = row.get(field_key)
            if value is not None:
                bucket["_samples"][field_key].append(float(value))

    aggregated_rows = []
    for date_key in sorted(day_map):
        bucket = day_map[date_key]
        aggregated = {"date": date_key}
        for field_key in numeric_fields:
            samples = bucket["_samples"][field_key]
            aggregated[field_key] = round(mean(samples), 4) if samples else None
        aggregated_rows.append(aggregated)
    return aggregated_rows


def _limit_table_rows(rows: list[dict], limit: int | None) -> list[dict]:
    if limit is None or limit <= 0 or len(rows) <= limit:
        return rows
    return rows[-limit:]


def _downsample_points(points: list[dict], limit: int | None) -> list[dict]:
    if limit is None or limit <= 0 or len(points) <= limit:
        return points
    if limit == 1:
        return [points[-1]]

    last_index = len(points) - 1
    indices = sorted(
        {
            round(position * last_index / (limit - 1))
            for position in range(limit)
        }
    )
    return [points[index] for index in indices]


def _points_for_series(db, field_key: str, start: str | None, end: str | None, granularity: str) -> list[dict]:
    rows = _fetch_series(db, field_key, start, end, granularity)
    return [
        {
            "timestamp_utc": row["timestamp_utc"],
            "timestamp_local": row.get("timestamp_local"),
            "value": row.get("value"),
        }
        for row in rows
    ]


def _normalize_chart_granularity(granularity: str) -> str:
    normalized = GRANULARITY_ALIASES.get(granularity)
    if normalized is None:
        raise ValueError(f"Unsupported chart granularity: {granularity}")
    return normalized


def build_finland_board_overview_payload(db, start: str | None, end: str | None) -> dict:
    cards = []
    for spec in get_finland_board_overview_cards():
        if spec["kind"] == "join_health":
            cards.append(_build_join_card(start, end, db))
        else:
            cards.append(_build_metric_card(spec["field_key"], start, end, spec["granularity"], db))
    return {
        "cards": cards,
        "window": {"start": start, "end": end},
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def build_finland_board_table_payload(
    db,
    view: str,
    start: str | None,
    end: str | None,
    tz: str,
    limit: int | None = None,
) -> dict:
    view_config = get_finland_board_view(view)
    if view in {"summary_stats", "field_dictionary"}:
        raise ValueError(f"View '{view}' is not a tabular board table view")
    rows = _join_rows_for_view(view_config, db, start, end, tz)
    if view_config["granularity"] == "day":
        rows = _aggregate_rows_by_day(rows, view_config)
    rows = _limit_table_rows(rows, limit)
    return {
        "view": view_config["view_key"],
        "title": view_config["title"],
        "granularity": view_config["granularity"],
        "timezone": tz,
        "columns": [_column_payload(field_key) for field_key in view_config["columns"]],
        "rows": rows,
    }


def build_finland_board_chart_payload(
    db,
    fields: list[str],
    mode: str,
    start: str | None,
    end: str | None,
    granularity: str,
    limit_points: int | None = None,
) -> dict:
    if mode not in VALID_CHART_MODES:
        raise ValueError(f"Unsupported chart mode: {mode}")
    normalized_granularity = _normalize_chart_granularity(granularity)
    if mode == "spread":
        if len(fields) != 2:
            raise ValueError("Spread mode requires exactly 2 fields")
        left_rows = {row["timestamp_utc"]: row for row in _fetch_series(db, fields[0], start, end, normalized_granularity)}
        right_rows = {row["timestamp_utc"]: row for row in _fetch_series(db, fields[1], start, end, normalized_granularity)}
        points = []
        for timestamp_utc in sorted(left_rows.keys() & right_rows.keys()):
            points.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "value": round(float(left_rows[timestamp_utc]["value"]) - float(right_rows[timestamp_utc]["value"]), 4),
                }
            )
        points = _downsample_points(points, limit_points)
        series = [
            {
                "field_key": f"{fields[0]}-minus-{fields[1]}",
                "label": f"{get_finland_board_field(fields[0])['label']} - {get_finland_board_field(fields[1])['label']}",
                "points": points,
            }
        ]
    else:
        series = [
            {
                "field_key": field_key,
                "label": get_finland_board_field(field_key)["label"],
                "points": _downsample_points(
                    _points_for_series(db, field_key, start, end, normalized_granularity),
                    limit_points,
                ),
            }
            for field_key in fields
        ]
    return {
        "mode": mode,
        "granularity": normalized_granularity,
        "series": series,
        "window": {"start": start, "end": end},
    }


def build_finland_board_field_catalog_rows() -> list[dict]:
    rows = []
    for field_key in sorted(FINLAND_BOARD_FIELDS):
        field = FINLAND_BOARD_FIELDS[field_key]
        rows.append(
            {
                "field_key": field["field_key"],
                "label": field["label"],
                "unit": field["unit"],
                "granularity": field["granularity"],
                "source_name": field["source_name"],
                "source_dataset_id": field["source_dataset_id"],
                "source_type": field["source_type"],
                "category": field["category"],
                "methodology_note": field["methodology_note"],
            }
        )
    return rows


def build_finland_board_readiness_payload(db, market_model_payload: dict) -> dict:
    del db
    summary = market_model_payload.get("summary", {})
    sources = market_model_payload.get("sources", [])
    metadata = market_model_payload.get("metadata", {})
    return {
        "summary": {
            "live_source_count": summary.get("live_source_count", 0),
            "configured_external_source_count": summary.get("configured_external_source_count", 0),
            "field_count": len(build_finland_board_field_catalog_rows()),
        },
        "sources": sources,
        "warnings": list(metadata.get("warnings", [])),
    }
