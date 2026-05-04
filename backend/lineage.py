from __future__ import annotations

from connector_framework import list_connector_specs


def _infer_source_identity(row: dict) -> tuple[str | None, str | None]:
    source_id = row.get("source_id")
    dataset_family = row.get("dataset_family")
    if source_id:
        return source_id, dataset_family

    dataset_key = str(row.get("dataset_key") or "")
    market = row.get("market")
    if dataset_key.startswith("trading_price_"):
        return "aemo_nem_trading_price", "settlement"
    if market == "WEM":
        return "aemo_wem_ess_market", "settlement"
    if market == "FINGRID":
        dataset_id = str((row.get("metadata_json") or {}).get("dataset_id") or dataset_key)
        return f"fingrid_dataset_{dataset_id}", "reserve_requirement"
    return None, None


def _freshness_status(freshness_minutes) -> str:
    if freshness_minutes is None:
        return "unknown"
    if freshness_minutes <= 240:
        return "fresh"
    if freshness_minutes <= 1440:
        return "delayed"
    return "stale"


def _build_source_rows_from_quality(db) -> list[dict]:
    try:
        quality_rows = db.fetch_data_quality_snapshots()
    except Exception:
        quality_rows = []

    quality_by_source = {}
    for row in quality_rows:
        source_id, dataset_family = _infer_source_identity(row)
        if source_id and source_id not in quality_by_source:
            quality_by_source[source_id] = {
                **row,
                "source_id": source_id,
                "dataset_family": dataset_family or row.get("dataset_family"),
            }

    rows = []
    for spec in list_connector_specs():
        quality_row = quality_by_source.get(spec.source_id) or {}
        freshness_minutes = quality_row.get("freshness_minutes")
        rows.append(
            {
                "source_key": spec.source_id,
                "source_id": spec.source_id,
                "market": spec.market,
                "dataset_family": quality_row.get("dataset_family") or spec.dataset_family,
                "last_updated_at": quality_row.get("computed_at"),
                "freshness_minutes": freshness_minutes,
                "status": _freshness_status(freshness_minutes),
            }
        )
    return rows


def build_source_freshness_payload(db) -> dict:
    queued = db.list_jobs(status="queued", limit=500)
    running = db.list_jobs(status="running", limit=500)
    return {
        "sources": [
            {
                "source_key": "market_core",
                "last_updated_at": db.get_last_update_time(),
                "status": "available" if db.get_last_update_time() else "unknown",
            },
            {
                "source_key": "job_system",
                "queued_jobs": len(queued),
                "running_jobs": len(running),
                "status": "busy" if running else "idle",
            },
            *_build_source_rows_from_quality(db),
        ],
        "job_summary": {
            "queued": len(queued),
            "running": len(running),
        },
    }


def build_job_lineage_payload(db, job_id: str) -> dict:
    job = db.fetch_job(job_id)
    if not job:
        raise KeyError(f"Unknown job_id: {job_id}")
    events = db.list_job_events(job_id)
    otel_trace_id = None
    parent_otel_trace_id = None
    for event in reversed(events):
        detail = event.get("detail_json") or {}
        if detail.get("otel_trace_id"):
            otel_trace_id = detail["otel_trace_id"]
        if detail.get("parent_otel_trace_id") and not parent_otel_trace_id:
            parent_otel_trace_id = detail["parent_otel_trace_id"]
        if otel_trace_id and parent_otel_trace_id:
            break
    if not otel_trace_id:
        otel_trace_id = job.get("result_json", {}).get("_otel_trace_id")
    openlineage_events = []
    for event in events:
        detail = event.get("detail_json") or {}
        if detail.get("openlineage_event"):
            openlineage_events.append(detail["openlineage_event"])
    return {
        "job": {
            "job_id": job["job_id"],
            "job_type": job["job_type"],
            "queue_name": job["queue_name"],
            "source_key": job["source_key"],
            "organization_id": job.get("organization_id"),
            "workspace_id": job.get("workspace_id"),
            "status": job["status"],
            "attempt_count": job["attempt_count"],
            "created_at": job["created_at"],
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        },
        "trace": {
            "trace_id": f"job:{job_id}",
            "otel_trace_id": otel_trace_id,
            "parent_otel_trace_id": parent_otel_trace_id,
        },
        "openlineage": {
            "events": openlineage_events,
        },
        "artifacts": {
            "result_artifact_path": job.get("artifact_path"),
            "workspace_scope": job.get("workspace_id"),
            "organization_scope": job.get("organization_id"),
        },
        "events": events,
        "payload": job.get("payload_json", {}),
        "result": job.get("result_json", {}),
    }
