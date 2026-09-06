"""
Tianshu Platform — Clean Application Entry Point.

Usage:  uvicorn app:app --host 0.0.0.0 --port 8085

Business logic and legacy helpers remain in server.py during incremental migration.
Route modules in routes/ delegate to server.py as needed.
"""
from __future__ import annotations

import datetime
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from zoneinfo import ZoneInfo

from brand import BRAND_DISPLAY
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
    if raw is None or not raw.strip():
        # 与 server._env_flag 保持一致：空串回落到 default，避免 `FLAG=` 打开
        # default=False 的安全开关（如 CORS credentials）。
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


def _reconciliation_enabled() -> bool:
    return _env_flag("AUS_ELE_RECONCILIATION_ENABLED", True)


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


def _account_deletion_sweep_enabled() -> bool:
    # 单独一个开关而不是复用 AUS_ELE_ENABLE_SCHEDULER：这是全系统唯一一个**物理删除数据**
    # 的周期任务。运维想停它的时候，绝不能顺手把市场数据同步也停掉；反之亦然。
    return _env_flag("AUS_ELE_ENABLE_ACCOUNT_DELETION_SWEEP", True)


def run_account_deletion_sweep() -> int:
    """执行所有宽限期已过的账户删除请求，返回成功清除的账户数。

    没有这个任务，R1.7 的「30 天后永久删除」就只是一句写在界面和法律文件上的承诺：
    端点只写入排期行，谁都不去读它，账户会永远停在 pending —— 那比不做删除更糟，因为
    用户已经拿到了「已受理」的凭证。

    每小时而不是每天一次：`scheduled_delete_at` 是给用户看过一个**精确时刻**，日级扫描
    意味着实际删除可以比屏幕上那个日期晚将近一天。扫一次只是一条带索引的 SELECT。

    生产是 `gunicorn app:app --workers N`，每个 worker 都跑着自己的 AsyncIOScheduler，
    所以这个 tick 会被 N 个进程同时触发 —— 必须用 P0.7 的认领锁按「小时桶」去重，否则
    两个 worker 会同时 purge 同一个 principal（互相撞行、把对方挤成 failed）。锁故意
    **成功不释放**：这一小时已经有人干完了；只在整体抛错时释放，让同小时内的别的 worker
    还有机会补做。
    """
    from deps import get_db
    from services import data_rights
    from shared_state import get_state_store

    hour_bucket = datetime.datetime.now(_scheduler_timezone()).strftime("%Y-%m-%dT%H")
    store = get_state_store()
    token = store.acquire_claim("scheduler", f"account-deletion-sweep:{hour_bucket}", 3700)
    if token is None:
        return 0

    try:
        results = data_rights.execute_due_deletions(get_db())
    except Exception:  # noqa: BLE001 - 锁要交还，本轮失败不能把这一小时锁死
        store.release_claim("scheduler", f"account-deletion-sweep:{hour_bucket}", token)
        raise

    executed = [r for r in results if r.get("status") == "executed"]
    failed = [r for r in results if r.get("status") != "executed"]
    if results:
        # 只记数量与状态，绝不记被删账户的内容：日志是比 API 更宽松的读取通道。
        logger.info("Account deletion sweep: %d executed, %d failed", len(executed), len(failed))
    if failed:
        logger.warning("Account deletion sweep left %d failed request(s) pending for retry", len(failed))
    return len(executed)


# --- Lifespan (scheduler + job worker) ---
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage startup/shutdown of scheduler and background job worker."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import server as _server  # scheduler job functions live here during migration

    logger.info("Starting %s...", BRAND_DISPLAY)

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

        if _reconciliation_enabled():
            rh = _cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3)
            from engines.backtest_expansion import run_monthly_reconciliation
            scheduler.add_job(run_monthly_reconciliation, "cron", day=1, hour=rh,
                              id="monthly-reconciliation", max_instances=1, coalesce=True, misfire_grace_time=3600)
            logger.info("Monthly reconciliation job registered (day=1, hour=%02d, tz=%s)", rh, tz.key)

        if _account_deletion_sweep_enabled():
            sweep_minute = _cron_minute("AUS_ELE_ACCOUNT_DELETION_SWEEP_MINUTE", 15)
            scheduler.add_job(run_account_deletion_sweep, "cron", minute=sweep_minute,
                              id="account-deletion-sweep", max_instances=1, coalesce=True,
                              misfire_grace_time=1800)
            logger.info("Account deletion sweep registered (hourly at :%02d, tz=%s)", sweep_minute, tz.key)

        scheduler.start()
        application.state.scheduler = scheduler
        logger.info("Scheduler enabled (tz=%s, market=%02d:%02d, fingrid-hourly=:%02d, fingrid-daily=%02d:%02d, wem-ess=%02d:%02d)",
                    tz.key, mh, mm, fhm, fdh, fdm, wem_ess_h, wem_ess_m)
    else:
        logger.info("Scheduler disabled (AUS_ELE_ENABLE_SCHEDULER)")

    if _job_worker_enabled():
        orchestrator = get_job_orchestrator()
        # Recover jobs stuck in 'running' from a previous crash
        recovered = orchestrator.recover_stuck_jobs(timeout_minutes=120)
        if recovered:
            logger.info("Recovered %d stuck job(s) at startup", recovered)
        worker = _server.JobWorkerService(orchestrator, queue_names=_job_worker_queue_names())
        worker.start()
        application.state.job_worker = worker
        logger.info("Job worker enabled (poll=%ss, queues=%s)",
                    _job_worker_poll_seconds(), ",".join(_job_worker_queue_names() or ["*"]))
    else:
        logger.info("Job worker disabled (AUS_ELE_ENABLE_JOB_WORKER)")

    yield

    logger.info("Shutting down %s...", BRAND_DISPLAY)
    if hasattr(application.state, "scheduler"):
        application.state.scheduler.shutdown()
    if hasattr(application.state, "job_worker"):
        application.state.job_worker.stop()


# --- Application creation ---
app = FastAPI(title=f"{BRAND_DISPLAY} API", lifespan=lifespan)

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


# --- Global unhandled-exception handler (H-2 follow-up) ---
# Any exception that escapes a route handler is logged server-side (with the
# current trace id for correlation) but returned to the client as an opaque
# 500, so internal details (table/column names, file paths, SQL fragments,
# third-party URLs) never leak. HTTPException is handled by FastAPI itself and
# therefore does not reach this handler.
@app.exception_handler(Exception)
async def _handle_unhandled_exception(request: Request, exc: Exception):  # noqa: ARG001
    trace_id = get_current_trace_id()
    logger.exception(
        "Unhandled exception on %s %s (trace_id=%s)",
        request.method,
        request.url.path,
        trace_id or "-",
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Map database unavailability (e.g. connection-pool exhaustion) to a transient,
# retryable 503 instead of the generic 500 above.
from database import DatabaseUnavailableError  # noqa: E402


@app.exception_handler(DatabaseUnavailableError)
async def _handle_database_unavailable(request: Request, exc: DatabaseUnavailableError):  # noqa: ARG001
    logger.error("Database unavailable on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable; please retry later."},
    )

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
