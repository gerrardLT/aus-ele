from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import telemetry
import openlineage_support


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class JobRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, job_type: str, handler: Callable):
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> Callable:
        if job_type not in self._handlers:
            raise KeyError(f"Unsupported job_type: {job_type}")
        return self._handlers[job_type]


@dataclass
class JobContext:
    db: object
    job_id: str
    lake: object | None

    def set_progress(self, progress_pct: int, progress_message: str):
        clamped = max(0, min(100, int(progress_pct)))
        self.db.update_job_progress(self.job_id, progress_pct=clamped, progress_message=progress_message)
        self.db.append_job_event(
            self.job_id,
            "progress",
            {"progress_pct": clamped, "progress_message": progress_message},
            _utc_iso(),
        )

    def is_cancel_requested(self) -> bool:
        job = self.db.fetch_job(self.job_id)
        return bool(job and job.get("cancel_requested"))


class JobOrchestrator:
    def __init__(
        self,
        db,
        *,
        registry: JobRegistry,
        lake=None,
        worker_id: str = "worker-1",
        retry_delays_seconds: list[int] | None = None,
        source_rate_limits: dict[str, int] | None = None,
    ):
        self.db = db
        self.registry = registry
        self.lake = lake
        self.worker_id = worker_id
        self.retry_delays_seconds = list(retry_delays_seconds or [30, 120, 300])
        self.source_rate_limits = dict(source_rate_limits or {})

    def enqueue(
        self,
        job_type: str,
        *,
        payload: dict,
        queue_name: str,
        source_key: str,
        priority: int = 100,
        max_attempts: int = 3,
    ) -> dict:
        created_at = _utc_iso()
        payload = dict(payload or {})
        trace_context = telemetry.serialize_current_trace_context()
        if trace_context and not payload.get("_trace_context"):
            payload["_trace_context"] = trace_context
        job = self.db.create_job(
            job_id=uuid4().hex,
            job_type=job_type,
            queue_name=queue_name,
            source_key=source_key,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            next_run_after=created_at,
            created_at=created_at,
        )
        self.db.append_job_event(job["job_id"], "queued", {"queue_name": queue_name, "source_key": source_key}, created_at)
        return job

    def _eligible_job_ids(self, now: datetime) -> list[str]:
        queued = self.db.list_jobs(status="queued", limit=500)
        eligible = []
        for job in sorted(queued, key=lambda item: (item["priority"], item["created_at"])):
            if job.get("cancel_requested"):
                continue
            next_run_after = job.get("next_run_after")
            if next_run_after:
                next_dt = datetime.fromisoformat(next_run_after.replace("Z", "+00:00"))
                if next_dt > now:
                    continue
            source_key = job["source_key"]
            cooldown_seconds = self.source_rate_limits.get(source_key, 0)
            if cooldown_seconds > 0:
                last_run = self.db.get_system_status(f"job_rate:{source_key}")
                if last_run:
                    last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    if last_dt + timedelta(seconds=cooldown_seconds) > now:
                        continue
            eligible.append(job["job_id"])
        return eligible

    def _filter_job_ids_by_queue_names(self, job_ids: list[str], queue_names: list[str] | None) -> list[str]:
        if not queue_names:
            return job_ids
        allowed = set(queue_names)
        filtered: list[str] = []
        for job_id in job_ids:
            job = self.db.fetch_job(job_id)
            if not job:
                continue
            if job.get("queue_name") in allowed:
                filtered.append(job_id)
        return filtered

    def _run_claimed_job(self, job: dict, *, now: datetime | None = None) -> dict | None:
        now = now or _utc_now()
        trace_context = (job.get("payload_json") or {}).get("_trace_context")
        parent_context = telemetry.extract_trace_context(trace_context)
        parent_otel_trace_id = telemetry.extract_trace_id_from_traceparent((trace_context or {}).get("traceparent"))
        with telemetry.start_span(
            f"job.{job['job_type']}",
            attributes={
                "job.id": job["job_id"],
                "job.type": job["job_type"],
                "job.queue": job["queue_name"],
                "job.source": job["source_key"],
                "organization.id": job.get("organization_id"),
                "workspace.id": job.get("workspace_id"),
                "job.parent_trace_id": parent_otel_trace_id,
            },
            parent_context=parent_context,
        ):
            otel_trace_id = telemetry.get_current_trace_id()
            openlineage_enabled = openlineage_support._openlineage_enabled()
            start_openlineage = None
            if openlineage_enabled:
                start_openlineage = openlineage_support.build_openlineage_run_event(
                    job,
                    event_type="START",
                    event_time=_utc_iso(),
                    otel_trace_id=otel_trace_id,
                )
                openlineage_support.emit_openlineage_event(start_openlineage)
            self.db.append_job_event(
                job["job_id"],
                "running",
                {
                    "worker_id": self.worker_id,
                    "attempt_count": job["attempt_count"],
                    "otel_trace_id": otel_trace_id,
                    "parent_otel_trace_id": parent_otel_trace_id,
                    "openlineage_event": start_openlineage,
                },
                _utc_iso(),
            )
            self.db.set_system_status(f"job_rate:{job['source_key']}", _utc_iso(now))
            handler = self.registry.get(job["job_type"])
            context = JobContext(db=self.db, job_id=job["job_id"], lake=self.lake)

            try:
                result = handler(job, context)
                artifact_path = None
                if self.lake is not None:
                    workspace_scope = job["payload_json"].get("workspace_id") or "global"
                    organization_scope = job["payload_json"].get("organization_id") or "global"
                    artifact = self.lake.write_artifact(
                        layer="derived",
                        namespace="jobs",
                        partition=(
                            f"organization={organization_scope}/"
                            f"workspace={workspace_scope}/"
                            f"job_type={job['job_type']}/"
                            f"date={now.strftime('%Y-%m-%d')}"
                        ),
                        payload=result,
                        metadata={
                            "job_id": job["job_id"],
                            "source_key": job["source_key"],
                            "organization_id": job["payload_json"].get("organization_id"),
                            "workspace_id": job["payload_json"].get("workspace_id"),
                            "otel_trace_id": otel_trace_id,
                        },
                    )
                    artifact_path = artifact["payload_path"]
                job_result = dict(result or {})
                if otel_trace_id:
                    job_result["_otel_trace_id"] = otel_trace_id
                self.db.complete_job(job["job_id"], finished_at=_utc_iso(), result=job_result, artifact_path=artifact_path)
                complete_openlineage = None
                if openlineage_enabled:
                    complete_openlineage = openlineage_support.build_openlineage_run_event(
                        job,
                        event_type="COMPLETE",
                        event_time=_utc_iso(),
                        otel_trace_id=otel_trace_id,
                        artifact_path=artifact_path,
                    )
                    openlineage_support.emit_openlineage_event(complete_openlineage)
                self.db.append_job_event(
                    job["job_id"],
                    "succeeded",
                        {
                            "artifact_path": artifact_path,
                            "otel_trace_id": otel_trace_id,
                            "parent_otel_trace_id": parent_otel_trace_id,
                            "openlineage_event": complete_openlineage,
                        },
                    _utc_iso(),
                )
                telemetry.record_job_metric(job_type=job["job_type"], status="succeeded")
                return {"job_id": job["job_id"], "status": "succeeded", "result": job_result}
            except Exception as exc:
                latest = self.db.fetch_job(job["job_id"])
                attempt_count = int((latest or job)["attempt_count"])
                max_attempts = int(job["max_attempts"])
                if attempt_count < max_attempts:
                    delay = self.retry_delays_seconds[min(attempt_count - 1, len(self.retry_delays_seconds) - 1)]
                    retry_at = _utc_now() + timedelta(seconds=delay)
                    self.db.reschedule_job_retry(job["job_id"], next_run_after=_utc_iso(retry_at), error_text=str(exc))
                    retry_openlineage = openlineage_support.build_openlineage_run_event(
                        job,
                        event_type="FAIL",
                        event_time=_utc_iso(),
                        otel_trace_id=otel_trace_id,
                        error_message=str(exc),
                    ) if openlineage_enabled else None
                    if retry_openlineage:
                        openlineage_support.emit_openlineage_event(retry_openlineage)
                    self.db.append_job_event(
                        job["job_id"],
                        "retry_waiting",
                        {
                            "error": str(exc),
                            "next_run_after": _utc_iso(retry_at),
                            "otel_trace_id": otel_trace_id,
                            "parent_otel_trace_id": parent_otel_trace_id,
                            "openlineage_event": retry_openlineage,
                        },
                        _utc_iso(),
                    )
                    telemetry.record_job_metric(job_type=job["job_type"], status="retry_waiting")
                    return {"job_id": job["job_id"], "status": "retry_waiting", "error": str(exc)}
                self.db.fail_job(job["job_id"], finished_at=_utc_iso(), error_text=str(exc))
                failed_openlineage = openlineage_support.build_openlineage_run_event(
                    job,
                    event_type="FAIL",
                    event_time=_utc_iso(),
                    otel_trace_id=otel_trace_id,
                    error_message=str(exc),
                ) if openlineage_enabled else None
                if failed_openlineage:
                    openlineage_support.emit_openlineage_event(failed_openlineage)
                self.db.append_job_event(
                    job["job_id"],
                    "failed",
                    {
                        "error": str(exc),
                        "otel_trace_id": otel_trace_id,
                        "parent_otel_trace_id": parent_otel_trace_id,
                        "openlineage_event": failed_openlineage,
                    },
                    _utc_iso(),
                )
                telemetry.record_job_metric(job_type=job["job_type"], status="failed")
                return {"job_id": job["job_id"], "status": "failed", "error": str(exc)}

    def run_once(self, *, queue_names: list[str] | None = None) -> dict | None:
        now = _utc_now()
        eligible_job_ids = self._filter_job_ids_by_queue_names(self._eligible_job_ids(now), queue_names)
        job = self.db.claim_next_job(worker_id=self.worker_id, now_iso=_utc_iso(now), runnable_job_ids=eligible_job_ids)
        if not job:
            return None
        return self._run_claimed_job(job, now=now)

    def run_once_scoped(
        self,
        *,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        queue_names: list[str] | None = None,
    ) -> dict | None:
        now = _utc_now()
        eligible_job_ids = []
        for job_id in self._filter_job_ids_by_queue_names(self._eligible_job_ids(now), queue_names):
            job = self.db.fetch_job(job_id)
            if not job:
                continue
            if organization_id and job.get("organization_id") != organization_id:
                continue
            if workspace_id and job.get("workspace_id") != workspace_id:
                continue
            eligible_job_ids.append(job_id)
        job = self.db.claim_next_job(
            worker_id=self.worker_id,
            now_iso=_utc_iso(now),
            runnable_job_ids=eligible_job_ids,
        )
        if not job:
            return None
        return self._run_claimed_job(job, now=now)
