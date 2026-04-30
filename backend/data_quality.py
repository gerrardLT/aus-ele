from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any


def summarize_quality_snapshots(rows: list[dict[str, Any]]) -> dict[str, Any]:
    markets: dict[str, dict[str, Any]] = {}
    for row in rows:
        market = row["market"]
        bucket = markets.setdefault(
            market,
            {
                "rows": [],
                "issue_count": 0,
                "grades": set(),
                "freshness_minutes": [],
            },
        )
        bucket["rows"].append(row)
        bucket["issue_count"] += len(row.get("issues_json") or [])
        bucket["grades"].add(row["data_grade"])

        freshness_minutes = row.get("freshness_minutes")
        if freshness_minutes is not None:
            bucket["freshness_minutes"].append(freshness_minutes)

    normalized_markets: dict[str, dict[str, Any]] = {}
    for market, bucket in markets.items():
        scores = [
            row["quality_score"]
            for row in bucket["rows"]
            if row.get("quality_score") is not None
        ]
        normalized_markets[market] = {
            "dataset_count": len(bucket["rows"]),
            "average_quality_score": round(mean(scores), 4) if scores else None,
            "issue_count": bucket["issue_count"],
            "data_grades": sorted(bucket["grades"]),
            "max_freshness_minutes": (
                max(bucket["freshness_minutes"])
                if bucket["freshness_minutes"]
                else None
            ),
        }

    return {
        "summary": {
            "market_count": len(normalized_markets),
            "snapshot_count": len(rows),
        },
        "markets": normalized_markets,
    }


def compute_quality_snapshots(db) -> list[dict[str, Any]]:
    collectors = (
        _compute_nem_snapshots,
        _compute_wem_snapshots,
        _compute_fingrid_snapshots,
    )
    rows: list[dict[str, Any]] = []
    implemented_collectors = 0
    for collector in collectors:
        snapshots = collector(db)
        if snapshots is None:
            continue
        implemented_collectors += 1
        rows.extend(snapshots)

    if not implemented_collectors:
        raise NotImplementedError(
            "Data quality snapshot collectors are not implemented for Task 3."
        )

    return rows


def _compute_nem_snapshots(db) -> list[dict[str, Any]] | None:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%' ORDER BY name DESC"
        )
        tables = [row[0] for row in cursor.fetchall()]

        snapshots: list[dict[str, Any]] = []
        global_last_update = db.get_last_update_time()
        for table_name in tables:
            cursor.execute(
                f"""
                SELECT region_id, COUNT(*), MIN(settlement_date), MAX(settlement_date)
                FROM {table_name}
                WHERE region_id IS NOT NULL AND region_id != 'WEM'
                GROUP BY region_id
                """
            )
            for region_id, row_count, min_settlement, max_settlement in cursor.fetchall():
                computed_at = global_last_update or max_settlement or _utc_now_iso()
                snapshots.append(
                    {
                        "scope": "market",
                        "market": "NEM",
                        "dataset_key": f"{table_name}:{region_id}",
                        "data_grade": "analytical",
                        "quality_score": 1.0 if row_count else 0.0,
                        "coverage_ratio": 1.0 if row_count else 0.0,
                        "freshness_minutes": _compute_freshness_minutes(global_last_update),
                        "issues_json": [],
                        "metadata_json": {
                            "table_name": table_name,
                            "region_id": region_id,
                            "row_count": row_count,
                            "coverage_start": min_settlement,
                            "coverage_end": max_settlement,
                        },
                        "computed_at": computed_at,
                    }
                )

    return snapshots


def _compute_wem_snapshots(db) -> list[dict[str, Any]] | None:
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT COUNT(*), MIN(dispatch_interval), MAX(dispatch_interval)
            FROM {db.WEM_ESS_MARKET_TABLE}
            """
        )
        row_count, min_interval, max_interval = cursor.fetchone()

    if not row_count:
        return []

    computed_at = db.get_last_update_time() or max_interval or _utc_now_iso()
    issues = [
        {
            "issue_code": "preview_only",
            "severity": "warning",
            "detail_json": {"reason": "wem_ess_slim_feed"},
            "detected_at": computed_at,
        }
    ]
    return [
        {
            "scope": "market",
            "market": "WEM",
            "dataset_key": db.WEM_ESS_MARKET_TABLE,
            "data_grade": "preview",
            "quality_score": 0.75,
            "coverage_ratio": 1.0,
            "freshness_minutes": _compute_freshness_minutes(db.get_last_update_time()),
            "issues_json": issues,
            "metadata_json": {
                "table_name": db.WEM_ESS_MARKET_TABLE,
                "row_count": row_count,
                "coverage_start": min_interval,
                "coverage_end": max_interval,
            },
            "computed_at": computed_at,
        }
    ]


def _compute_fingrid_snapshots(db) -> list[dict[str, Any]] | None:
    with db.get_connection() as conn:
        db.ensure_fingrid_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT dataset_id, last_success_at, last_synced_timestamp_utc, sync_status, last_error
            FROM {db.FINGRID_SYNC_STATE_TABLE}
            ORDER BY dataset_id
            """
        )
        states = cursor.fetchall()

    snapshots: list[dict[str, Any]] = []
    for dataset_id, last_success_at, last_synced_timestamp_utc, sync_status, last_error in states:
        coverage = db.fetch_fingrid_dataset_coverage(dataset_id)
        record_count = coverage.get("record_count") or 0
        computed_at = last_success_at or last_synced_timestamp_utc or _utc_now_iso()
        issues = []
        resolution_minutes = _detect_fingrid_resolutions(db, dataset_id)
        if sync_status and sync_status != "ok":
            issues.append(
                {
                    "issue_code": "sync_not_ok",
                    "severity": "warning",
                    "detail_json": {"sync_status": sync_status},
                    "detected_at": computed_at,
                }
            )
        if last_error:
            issues.append(
                {
                    "issue_code": "last_error",
                    "severity": "warning",
                    "detail_json": {"message": last_error},
                    "detected_at": computed_at,
                }
            )
        if len(resolution_minutes) > 1:
            issues.append(
                {
                    "issue_code": "resolution_mixture",
                    "severity": "warning",
                    "detail_json": {"resolution_minutes": resolution_minutes},
                    "detected_at": computed_at,
                }
            )

        snapshots.append(
            {
                "scope": "dataset",
                "market": "FINGRID",
                "dataset_key": dataset_id,
                "data_grade": "analytical-preview" if record_count else "preview",
                "quality_score": 0.82 if record_count else 0.5,
                "coverage_ratio": 1.0 if record_count else 0.0,
                "freshness_minutes": _compute_freshness_minutes(last_success_at),
                "issues_json": issues,
                "metadata_json": {
                    "dataset_id": dataset_id,
                    "record_count": record_count,
                    "coverage_start_utc": coverage.get("coverage_start_utc"),
                    "coverage_end_utc": coverage.get("coverage_end_utc"),
                    "sync_status": sync_status,
                    "resolution_minutes": resolution_minutes,
                },
                "computed_at": computed_at,
            }
        )

    return snapshots


def _compute_freshness_minutes(timestamp_value: str | None) -> float | None:
    timestamp = _parse_timestamp(timestamp_value)
    if not timestamp:
        return None
    return max(0.0, round((_utc_now() - timestamp).total_seconds() / 60, 2))


def _parse_timestamp(timestamp_value: str | None) -> datetime | None:
    if not timestamp_value:
        return None
    normalized = str(timestamp_value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(str(timestamp_value).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _detect_fingrid_resolutions(db, dataset_id: str) -> list[int]:
    with db.get_connection() as conn:
        db.ensure_fingrid_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT timestamp_utc
            FROM {db.FINGRID_TIMESERIES_TABLE}
            WHERE dataset_id = ?
            ORDER BY timestamp_utc ASC
            """,
            (dataset_id,),
        )
        timestamps = [row[0] for row in cursor.fetchall()]

    if len(timestamps) < 2:
        return []

    detected_minutes = set()
    previous = _parse_timestamp(timestamps[0])
    for current_raw in timestamps[1:]:
        current = _parse_timestamp(current_raw)
        if previous is None or current is None:
            previous = current
            continue
        delta_minutes = round((current - previous).total_seconds() / 60.0)
        if delta_minutes > 0:
            detected_minutes.add(int(delta_minutes))
        previous = current

    return sorted(detected_minutes)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")
