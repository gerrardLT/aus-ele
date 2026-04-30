from __future__ import annotations


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
