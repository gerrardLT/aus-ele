"""
AEMO Intelligence Platform — Clean Application Entry Point.

Usage:  uvicorn app:app --host 0.0.0.0 --port 8085

Business logic and legacy helpers remain in server.py during incremental migration.
Route modules in routes/ delegate to server.py as needed.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from zoneinfo import ZoneInfo

from deps import get_job_orchestrator
from routes import register_all_routes
from routes.health import router as health_router
from logging_support import (
    install_json_log_formatter_if_enabled,
    install_structured_log_sink_if_configured,
    install_trace_log_record_factory,
)
from telemetry import (
    configure_telemetry,
    get_current_trace_id,
    get_current_span_id,
    record_request_metric,
)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
install_trace_log_record_factory(
    trace_id_supplier=get_current_trace_id,
    span_id_supplier=get_current_span_id,
)
install_json_log_formatter_if_enabled()
install_structured_log_sink_if_configured()


# --- Environment helpers ---
def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _cors_allow_origins() -> list[str]:
    raw = os.environ.get("AUS_ELE_CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return ["http://127.0.0.1:5173", "http://localhost:5173"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://127.0.0.1:5173", "http://localhost:5173"]


def _cors_allow_credentials() -> bool:
    return _env_flag("AUS_ELE_CORS_ALLOW_CREDENTIALS", False)


def _scheduler_enabled() -> bool:
    return _env_flag("AUS_ELE_ENABLE_SCHEDULER", True)


def _scheduler_timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("AUS_ELE_SCHEDULER_TIMEZONE", "UTC"))


def _cron_hour(name: str, default: int) -> int:
    try:
        return max(0, min(23, int(os.environ.get(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _cron_minute(name: str, default: int) -> int:
    try:
        return max(0, min(59, int(os.environ.get(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _job_worker_enabled() -> bool:
    return _env_flag("AUS_ELE_ENABLE_JOB_WORKER", True)


def _job_worker_poll_seconds() -> float:
    try:
        return float(os.environ.get("AUS_ELE_JOB_WORKER_POLL_SECONDS", "2"))
    except ValueError:
        return 2.0


def _job_worker_queue_names() -> list[str] | None:
    raw = os.environ.get("AUS_ELE_JOB_WORKER_QUEUES", "")
    items = [i.strip() for i in raw.split(",") if i.strip()]
    return items or None


# --- Lifespan (scheduler + job worker) ---
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage startup/shutdown of scheduler and background job worker."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import server as _server  # scheduler job functions live here during migration

    logger.info("Starting AEMO Intelligence Platform...")

    if _scheduler_enabled():
        tz = _scheduler_timezone()
        scheduler = AsyncIOScheduler(timezone=tz)
        mh = _cron_hour("AUS_ELE_MARKET_SYNC_HOUR", 1)
        mm = _cron_minute("AUS_ELE_MARKET_SYNC_MINUTE", 20)
        fhm = _cron_minute("AUS_ELE_FINGRID_HOURLY_SYNC_MINUTE", 45)
        fdh = _cron_hour("AUS_ELE_FINGRID_DAILY_SYNC_HOUR", 4)
        fdm = _cron_minute("AUS_ELE_FINGRID_DAILY_SYNC_MINUTE", 10)
        wem_ess_h = _cron_hour("AUS_ELE_WEM_ESS_SYNC_HOUR", 6)
        wem_ess_m = _cron_minute("AUS_ELE_WEM_ESS_SYNC_MINUTE", 0)
        scheduler.add_job(_server.enqueue_market_sync_job, "cron", hour=mh, minute=mm,
                          id="market-daily-sync", max_instances=1, coalesce=True, misfire_grace_time=3600)
        scheduler.add_job(_server.enqueue_fingrid_hourly_sync_job, "cron", minute=fhm,
                          id="fingrid-hourly-sync", max_instances=1, coalesce=True, misfire_grace_time=900)
        scheduler.add_job(_server.enqueue_fingrid_daily_sync_job, "cron", hour=fdh, minute=fdm,
                          id="fingrid-daily-sync", max_instances=1, coalesce=True, misfire_grace_time=3600)

        from pipelines.wem_ess_sync import enqueue_wem_ess_sync_job
        scheduler.add_job(enqueue_wem_ess_sync_job, "cron", hour=wem_ess_h, minute=wem_ess_m,
                          id="wem-ess-daily-sync", max_instances=1, coalesce=True, misfire_grace_time=3600)

        scheduler.start()
        application.state.scheduler = scheduler
        logger.info("Scheduler enabled (tz=%s, market=%02d:%02d, fingrid-hourly=:%02d, fingrid-daily=%02d:%02d, wem-ess=%02d:%02d)",
                    tz.key, mh, mm, fhm, fdh, fdm, wem_ess_h, wem_ess_m)
    else:
        logger.info("Scheduler disabled (AUS_ELE_ENABLE_SCHEDULER)")

    if _job_worker_enabled():
        worker = _server.JobWorkerService(get_job_orchestrator(), queue_names=_job_worker_queue_names())
        worker.start()
        application.state.job_worker = worker
        logger.info("Job worker enabled (poll=%ss, queues=%s)",
                    _job_worker_poll_seconds(), ",".join(_job_worker_queue_names() or ["*"]))
    else:
        logger.info("Job worker disabled (AUS_ELE_ENABLE_JOB_WORKER)")

    yield

    logger.info("Shutting down AEMO Intelligence Platform...")
    if hasattr(application.state, "scheduler"):
        application.state.scheduler.shutdown()
    if hasattr(application.state, "job_worker"):
        application.state.job_worker.stop()


# --- Application creation ---
app = FastAPI(title="AEMO NEM Data API", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=_cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Trace header middleware
class TraceHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        record_request_metric(endpoint=request.url.path, method=request.method)
        trace_id = get_current_trace_id()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response


app.add_middleware(TraceHeaderMiddleware)
configure_telemetry(app)

# --- Route registration ---
app.include_router(health_router)
register_all_routes(app)

# Include legacy routes from server.py that haven't been migrated to route modules yet.
# This ensures ALL existing API endpoints remain accessible via app.py.
import server as _legacy_server

for route in _legacy_server.app.routes:
    path = getattr(route, "path", None)
    if path and path.startswith("/api/"):
        existing_paths = {getattr(r, "path", None) for r in app.routes}
        if path not in existing_paths:
            app.routes.append(route)

# --- Entry point ---
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8085)
