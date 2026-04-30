from __future__ import annotations

import os
import json
from pathlib import Path

import requests
import telemetry


def _openlineage_enabled() -> bool:
    return os.environ.get("AUS_ELE_OPENLINEAGE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _producer_uri() -> str:
    return os.environ.get("AUS_ELE_OPENLINEAGE_PRODUCER", "https://aus-ele.local/backend")


def _sink_kind() -> str:
    return os.environ.get("AUS_ELE_OPENLINEAGE_SINK", "none").strip().lower() or "none"


def _file_path() -> str:
    return os.environ.get("AUS_ELE_OPENLINEAGE_FILE_PATH", "openlineage-events.jsonl")


def _endpoint() -> str | None:
    value = os.environ.get("AUS_ELE_OPENLINEAGE_ENDPOINT", "").strip()
    return value or None


def get_openlineage_status() -> dict:
    enabled = _openlineage_enabled()
    sink = _sink_kind()
    status = {
        "enabled": enabled,
        "sink": sink,
    }
    if sink == "file":
        status["path"] = _file_path()
    elif sink == "http":
        status["endpoint"] = _endpoint()
    return status


def _job_namespace(job: dict) -> str:
    return f"aus-ele/{job.get('source_key') or 'unknown'}/{job.get('queue_name') or 'default'}"


def build_openlineage_run_event(
    job: dict,
    *,
    event_type: str,
    event_time: str,
    producer: str | None = None,
    otel_trace_id: str | None = None,
    error_message: str | None = None,
    artifact_path: str | None = None,
) -> dict:
    run_facets = {
        "processing_engine": {
            "_producer": producer or _producer_uri(),
            "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ProcessingEngineRunFacet.json",
            "name": "aus-ele-job-orchestrator",
            "version": "v1",
            "openlineageAdapterVersion": "custom-v1",
        }
    }
    if otel_trace_id:
        run_facets["parent"] = {
            "_producer": producer or _producer_uri(),
            "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ParentRunFacet.json",
            "run": {"runId": otel_trace_id},
            "job": {"namespace": "opentelemetry", "name": "trace"},
        }
    if error_message:
        run_facets["errorMessage"] = {
            "_producer": producer or _producer_uri(),
            "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ErrorMessageRunFacet.json",
            "message": error_message,
            "programmingLanguage": "python",
        }

    outputs = []
    if artifact_path:
        outputs.append(
            {
                "namespace": "file",
                "name": artifact_path,
                "facets": {},
            }
        )

    event = {
        "eventType": event_type,
        "eventTime": event_time,
        "producer": producer or _producer_uri(),
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
        "run": {
            "runId": job["job_id"],
            "facets": run_facets,
        },
        "job": {
            "namespace": _job_namespace(job),
            "name": job["job_type"],
            "facets": {
                "jobType": {
                    "_producer": producer or _producer_uri(),
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/JobTypeJobFacet.json",
                    "processingType": job.get("queue_name") or "default",
                    "integration": job.get("source_key") or "unknown",
                    "jobType": job.get("job_type") or "unknown",
                }
            },
        },
        "inputs": [],
        "outputs": outputs,
    }
    return event


def emit_openlineage_event(event: dict) -> dict:
    if not _openlineage_enabled():
        return {"emitted": False, "sink": "disabled"}
    sink = _sink_kind()
    if sink == "file":
        path = Path(_file_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"emitted": True, "sink": "file", "path": str(path)}
    if sink == "http":
        endpoint = _endpoint()
        if not endpoint:
            return {"emitted": False, "sink": "http", "reason": "missing_endpoint"}
        headers = {"Content-Type": "application/json"}
        headers.update(telemetry.build_trace_headers())
        response = requests.post(
            endpoint,
            json=event,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return {"emitted": True, "sink": "http", "status_code": response.status_code, "endpoint": endpoint}
    return {"emitted": False, "sink": sink, "reason": "unsupported_sink"}
