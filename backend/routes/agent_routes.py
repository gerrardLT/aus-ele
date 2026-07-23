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

from agent.orchestrator import get_orchestrator
from agent.schemas import (
    AgentAsyncResponse,
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


def _get_redis_client():
    """Get Redis client via the shared cache infrastructure."""
    try:
        from deps import get_cache
        return get_cache()._get_client()
    except Exception:
        return None


def _store_task(task_id: str, data: dict) -> None:
    """Persist task state to Redis (with in-memory fallback)."""
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
    """Update specific fields of a task."""
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

        # Log execution to database (best-effort)
        _log_execution(report)

        return AgentRunResponse(report=report, status=report.status)

    except Exception as exc:
        logger.error("Agent run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}")


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

    # Launch background task
    asyncio.create_task(_execute_async_task(task_id, request))

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
        _log_execution(report)
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
        status=task.get("status", "unknown"),
        report=task.get("report"),
        progress=task.get("progress"),
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
# Execution history
# ---------------------------------------------------------------------------


@router.get("/history", response_model=AgentHistoryResponse)
async def get_history(limit: int = 20) -> AgentHistoryResponse:
    """Get recent agent execution history."""
    try:
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
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return AgentHistoryResponse(executions=rows, total=len(rows))
    except Exception as exc:
        logger.warning("Failed to fetch agent history: %s", exc)
        return AgentHistoryResponse(executions=[], total=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_execution(report) -> None:
    """Log agent execution to database (best-effort, non-blocking)."""
    try:
        from deps import get_db

        db = get_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Ensure table exists
            cursor.execute("""
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
            """)
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
