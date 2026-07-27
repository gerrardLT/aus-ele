"""AI Agent API routes.

Provides endpoints for the AI Agent workflow orchestration system:
- POST /api/v1/agent/run          — Synchronous workflow execution
- POST /api/v1/agent/run-async    — Async workflow submission
- GET  /api/v1/agent/task/{id}    — Query async task status
- GET  /api/v1/agent/tools        — List available tools
- GET  /api/v1/agent/workflows    — List workflow templates
- GET  /api/v1/agent/history      — Execution history
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agent.orchestrator import get_orchestrator
from agent.schemas import (
    AgentAsyncResponse,
    AgentChatRequest,
    AgentContext,
    AgentHistoryResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentTaskStatusResponse,
    AgentToolsResponse,
    AgentWorkflowsResponse,
    MarketType,
    WorkflowStatus,
)
from agent.tools import get_tool_registry
from agent.workflows import list_workflow_templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["AI Agent"])

# ---------------------------------------------------------------------------
# Redis-backed async task store (shared across gunicorn workers)
# Falls back to in-memory dict when Redis is unavailable.
# ---------------------------------------------------------------------------

TASK_TTL_SECONDS = 3600  # Tasks expire after 1 hour
_TASK_PREFIX = "agent_task:"

# In-memory fallback (single-worker or Redis-down scenarios)
_fallback_tasks: Dict[str, dict] = {}


def _evict_expired_tasks() -> None:
    """Remove in-memory tasks older than TASK_TTL_SECONDS.

    Called opportunistically on each task store/get to bound memory usage
    in long-running processes (Redis handles its own TTL expiry).
    """
    now = datetime.now(timezone.utc)
    expired = [
        tid for tid, data in _fallback_tasks.items()
        if _task_age_seconds(data, now) > TASK_TTL_SECONDS
    ]
    for tid in expired:
        _fallback_tasks.pop(tid, None)


def _task_age_seconds(data: dict, now: datetime) -> float:
    """Return age of a task in seconds based on its created_at field."""
    created_raw = data.get("created_at")
    if not created_raw:
        return 0.0
    try:
        created = datetime.fromisoformat(created_raw)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created).total_seconds()
    except (ValueError, TypeError):
        return 0.0

# Strong references to in-flight background tasks. asyncio only holds a weak
# reference to tasks created via create_task, so without this set a task may be
# garbage-collected mid-execution and silently cancelled.
_background_tasks: set = set()


def _get_redis_client():
    """Get Redis client via the shared cache infrastructure."""
    try:
        from deps import get_cache
        return get_cache()._get_client()
    except Exception:
        return None


def _store_task(task_id: str, data: dict) -> None:
    """Persist task state to Redis (with in-memory fallback)."""
    # Opportunistically evict stale entries to bound memory usage.
    _evict_expired_tasks()
    # Always keep in-memory as hot cache
    _fallback_tasks[task_id] = data
    client = _get_redis_client()
    if client is not None:
        try:
            client.setex(
                f"{_TASK_PREFIX}{task_id}",
                TASK_TTL_SECONDS,
                json.dumps(data, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            logger.debug("Redis task store failed: %s", exc)


def _get_task(task_id: str) -> Optional[dict]:
    """Retrieve task state from Redis or in-memory fallback."""
    # Try Redis first (authoritative in multi-worker)
    client = _get_redis_client()
    if client is not None:
        try:
            raw = client.get(f"{_TASK_PREFIX}{task_id}")
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis task get failed: %s", exc)
    # Fallback to in-memory
    return _fallback_tasks.get(task_id)


def _update_task(task_id: str, **fields) -> None:
    """Update specific fields of a task.

    The background executor runs in the same worker that created the task, so
    the in-memory fallback is authoritative for the writer; prefer it to avoid
    an extra Redis GET on every progress update.
    """
    task = _fallback_tasks.get(task_id)
    if task is None:
        task = _get_task(task_id)
    if task is not None:
        task.update(fields)
        _store_task(task_id, task)


# ---------------------------------------------------------------------------
# Synchronous execution
# ---------------------------------------------------------------------------


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    """Execute an agent workflow synchronously.

    Suitable for short workflows (< 60s). For longer analyses,
    use /run-async instead.
    """
    orchestrator = get_orchestrator()

    context = AgentContext(
        market=request.market,
        region=request.region,
        year=request.year,
        params_override=request.params_override,
        max_steps=request.max_steps,
    )

    try:
        report = await orchestrator.run(
            query=request.query,
            context=context,
            workflow_template_id=request.workflow_template,
        )

        # Log execution to database (best-effort, off the event loop)
        await asyncio.get_running_loop().run_in_executor(None, _log_execution, report)

        return AgentRunResponse(report=report, status=report.status)

    except Exception as exc:
        logger.error("Agent run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Agent execution failed")


# ---------------------------------------------------------------------------
# Async execution
# ---------------------------------------------------------------------------


@router.post("/run-async", response_model=AgentAsyncResponse)
async def run_agent_async(request: AgentRunRequest) -> AgentAsyncResponse:
    """Submit an agent workflow for async execution.

    Returns a task_id that can be polled via GET /task/{id}.
    Task state is stored in Redis (shared across workers) with 1h TTL.
    """
    task_id = str(uuid.uuid4())[:12]

    _store_task(task_id, {
        "status": WorkflowStatus.RUNNING.value,
        "report": None,
        "progress": "Workflow submitted",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Launch background task (keep a strong reference so it isn't GC'd)
    task = asyncio.create_task(_execute_async_task(task_id, request))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return AgentAsyncResponse(task_id=task_id, status=WorkflowStatus.RUNNING)


async def _execute_async_task(task_id: str, request: AgentRunRequest) -> None:
    """Background task executor for async agent runs."""
    orchestrator = get_orchestrator()

    context = AgentContext(
        market=request.market,
        region=request.region,
        year=request.year,
        params_override=request.params_override,
        max_steps=request.max_steps,
    )

    def progress_cb(msg: str) -> None:
        _update_task(task_id, progress=msg)

    try:
        report = await orchestrator.run(
            query=request.query,
            context=context,
            workflow_template_id=request.workflow_template,
            progress_callback=progress_cb,
        )
        # Serialize report to dict for Redis storage
        report_dict = report.model_dump(mode="json")
        status_val = report.status.value if hasattr(report.status, "value") else str(report.status)
        _update_task(
            task_id,
            status=status_val,
            report=report_dict,
            progress="Completed",
        )
        await asyncio.get_running_loop().run_in_executor(None, _log_execution, report)
    except Exception as exc:
        logger.error("Async agent task %s failed: %s", task_id, exc, exc_info=True)
        _update_task(
            task_id,
            status=WorkflowStatus.FAILED.value,
            progress=f"Failed: {exc}",
        )


@router.get("/task/{task_id}", response_model=AgentTaskStatusResponse)
async def get_task_status(task_id: str) -> AgentTaskStatusResponse:
    """Query the status of an async agent task."""
    task = _get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return AgentTaskStatusResponse(
        task_id=task_id,
        status=task.get("status", WorkflowStatus.RUNNING.value),
        report=task.get("report"),
        progress=task.get("progress"),
    )


# ---------------------------------------------------------------------------
# Streaming chat (SSE) — live ReAct trace + multi-turn conversation
# ---------------------------------------------------------------------------


@router.post("/chat-stream")
async def chat_stream(request: AgentChatRequest) -> StreamingResponse:
    """Stream a multi-turn agent chat as Server-Sent Events.

    The frontend owns the conversation history (stateless backend): each turn
    sends ``query`` plus prior ``history``. The orchestrator's ReAct loop is
    streamed event-by-event (LLM tokens, tool calls, tool results, final
    report) so the caller can watch the run unfold live.

    SSE frames are ``data: {json}\\n\\n``; each JSON carries a ``type`` field
    (start/status/token/tool_call/tool_result/answer_end/report/error/done).
    """
    orchestrator = get_orchestrator()

    context = AgentContext(
        market=request.market,
        region=request.region,
        year=request.year,
        params_override=request.params_override,
        max_steps=request.max_steps,
        session_id=request.session_id,
    )
    history = [m.model_dump() for m in request.history]

    async def event_generator():
        final_report = None
        try:
            async for event in orchestrator.run_stream(
                query=request.query,
                context=context,
                history=history,
                workflow_template_id=request.workflow_template,
            ):
                if event.get("type") == "report":
                    final_report = event.get("report")
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface as SSE error, never 500
            logger.error("Agent chat-stream failed: %s", exc, exc_info=True)
            err = {"type": "error", "message": "Agent streaming failed"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        else:
            # Best-effort execution log, off the event loop.
            if final_report is not None:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, _log_execution_dict, final_report
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("chat-stream log failed: %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for live stream
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Tool & Workflow discovery
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=AgentToolsResponse)
async def list_tools() -> AgentToolsResponse:
    """List all available agent tools with descriptions."""
    registry = get_tool_registry()
    definitions = registry.list_definitions()
    return AgentToolsResponse(tools=definitions, total=len(definitions))


@router.get("/workflows", response_model=AgentWorkflowsResponse)
async def list_workflows() -> AgentWorkflowsResponse:
    """List all available predefined workflow templates."""
    templates = list_workflow_templates()
    return AgentWorkflowsResponse(workflows=templates, total=len(templates))


# ---------------------------------------------------------------------------
# Data export download
# ---------------------------------------------------------------------------


@router.get("/download/{filename}")
async def download_export(filename: str):
    """Download an exported data file (CSV/JSON)."""
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    filepath = output_dir / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "text/csv" if filename.endswith(".csv") else "application/json"
    return FileResponse(filepath, media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# Execution history
# ---------------------------------------------------------------------------


@router.get("/history", response_model=AgentHistoryResponse)
async def get_history(limit: int = 20) -> AgentHistoryResponse:
    """Get recent agent execution history."""
    try:
        rows = await asyncio.get_running_loop().run_in_executor(
            None, _fetch_history, limit
        )
        return AgentHistoryResponse(executions=rows, total=len(rows))
    except Exception as exc:
        logger.warning("Failed to fetch agent history: %s", exc)
        return AgentHistoryResponse(executions=[], total=0)


@router.get("/history/{execution_id}")
async def get_execution_detail(execution_id: str) -> Dict:
    """Get full report for a specific execution by ID."""
    try:
        row = await asyncio.get_running_loop().run_in_executor(
            None, _fetch_execution_detail, execution_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Failed to fetch execution %s: %s", execution_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch execution")


@router.delete("/history/{execution_id}")
async def delete_execution(execution_id: str) -> Dict:
    """Delete a specific execution record."""
    try:
        deleted = await asyncio.get_running_loop().run_in_executor(
            None, _delete_execution, execution_id
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {"deleted": True, "id": execution_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Failed to delete execution %s: %s", execution_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete execution")


def _fetch_history(limit: int) -> list:
    """Synchronous history query (runs in a thread pool executor)."""
    from deps import get_db

    db = get_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, query, market, region, workflow_type, status, "
            "total_duration_ms, created_at "
            "FROM agent_execution_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_execution_detail(execution_id: str) -> Optional[Dict]:
    """Fetch full execution record including report_json."""
    from deps import get_db

    db = get_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        _ensure_agent_log_table(cursor)
        cursor.execute(
            "SELECT id, query, market, region, workflow_type, status, "
            "report_json, total_duration_ms, created_at "
            "FROM agent_execution_log WHERE id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, row))
        # Parse report_json back into a dict
        if record.get("report_json"):
            try:
                record["report"] = json.loads(record["report_json"])
            except (json.JSONDecodeError, TypeError):
                record["report"] = None
        del record["report_json"]
        return record


def _delete_execution(execution_id: str) -> bool:
    """Delete an execution record from the database."""
    from deps import get_db

    db = get_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        _ensure_agent_log_table(cursor)
        cursor.execute("DELETE FROM agent_execution_log WHERE id = ?", (execution_id,))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_agent_log_table_ready = False

_CREATE_AGENT_LOG_TABLE = """
    CREATE TABLE IF NOT EXISTS agent_execution_log (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        market TEXT,
        region TEXT,
        workflow_type TEXT,
        status TEXT,
        steps_json TEXT,
        report_json TEXT,
        total_duration_ms REAL,
        created_at TIMESTAMPTZ DEFAULT now()
    )
"""


def _ensure_agent_log_table(cursor) -> None:
    """Create the agent_execution_log table once per process lifetime."""
    global _agent_log_table_ready
    if _agent_log_table_ready:
        return
    cursor.execute(_CREATE_AGENT_LOG_TABLE)
    _agent_log_table_ready = True


def _log_execution(report) -> None:
    """Log agent execution to database (best-effort, non-blocking)."""
    try:
        from deps import get_db

        db = get_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            _ensure_agent_log_table(cursor)
            cursor.execute(
                "INSERT INTO agent_execution_log "
                "(id, query, market, region, workflow_type, status, steps_json, report_json, total_duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report.id,
                    report.query,
                    report.market,
                    report.region,
                    report.workflow_type,
                    report.status.value if hasattr(report.status, "value") else str(report.status),
                    json.dumps(
                        [s.model_dump() for s in report.steps] if report.steps else [],
                        ensure_ascii=False,
                        default=str,
                    ),
                    json.dumps(
                        report.model_dump(exclude={"steps", "tool_trace"}),
                        ensure_ascii=False,
                        default=str,
                    ),
                    report.total_duration_ms,
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.debug("Failed to log agent execution: %s", exc)


def _log_execution_dict(report: dict) -> None:
    """Log a serialized (dict) agent report to the database (best-effort).

    The streaming path produces ``report.model_dump(mode="json")`` dicts rather
    than :class:`AgentReport` objects, so we persist from the dict directly.
    """
    try:
        from deps import get_db

        db = get_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            _ensure_agent_log_table(cursor)
            cursor.execute(
                "INSERT INTO agent_execution_log "
                "(id, query, market, region, workflow_type, status, steps_json, report_json, total_duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report.get("id"),
                    report.get("query", ""),
                    report.get("market"),
                    report.get("region"),
                    report.get("workflow_type"),
                    report.get("status"),
                    json.dumps(report.get("steps", []), ensure_ascii=False, default=str),
                    json.dumps(
                        {k: v for k, v in report.items() if k not in ("steps", "tool_trace")},
                        ensure_ascii=False,
                        default=str,
                    ),
                    report.get("total_duration_ms", 0.0),
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.debug("Failed to log agent execution (dict): %s", exc)
