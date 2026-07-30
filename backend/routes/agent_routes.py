"""AI Agent API routes — 已加 JWT 鉴权。

Provides endpoints for the AI Agent workflow orchestration system:
- POST /api/v1/agent/run          — Synchronous workflow execution (auth required)
- POST /api/v1/agent/run-async    — Async workflow submission (auth required)
- GET  /api/v1/agent/task/{id}    — Query async task status (auth required)
- GET  /api/v1/agent/tools        — List available tools (open)
- GET  /api/v1/agent/workflows    — List workflow templates (open)
- GET  /api/v1/agent/history      — Execution history (auth required)

Authentication:
- JWT Bearer token from `Authorization: Bearer <token>` header
- Uses same JWT secret as main backend (`AUS_ELE_JWT_SECRET`)
- Public endpoints (tools, workflows) allow LLM to introspect capabilities even if user not logged in
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

try:
    from access_control import _decode_and_verify_jwt_access_token
except ImportError:
    # 开发环境可能没有 access_control，使用简易版（仅演示用）
    def _noop_auth(credentials: str) -> dict:
        """No-op auth for dev when access_control unavailable."""
        return {"sub": "dev_user", "workspace_id": "dev_workspace"}

    raise SystemExit("access_control unavailable - ensure access_control.py exists")

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
from deps import get_db
from database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["AI Agent"])

# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> dict:
    """Extract and verify JWT token from Bearer header.

    Returns:
        dict with keys: sub (principal_id), workspace_id, exp (timestamp)
    Raises:
        HTTPException 401 if token missing or invalid
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    try:
        payload = _decode_and_verify_jwt_access_token(token)
        return payload
    except ValueError as exc:
        logger.warning(f"JWT validation failed: {exc}")
        raise HTTPException(
            status_code=401,
            detail={
                "reason": "invalid_token",
                "message": f"Token validation error: {str(exc)}",
            },
        )


# ---------------------------------------------------------------------------
# Task stores (Redis-backed, shared across gunicorn workers)
# ---------------------------------------------------------------------------

TASK_TTL_SECONDS = 3600  # Tasks expire after 1 hour
_TASK_PREFIX = "agent_task:"

_fallback_tasks: Dict[str, dict] = {}


def _evict_expired_tasks() -> None:
    now = datetime.now(timezone.utc)
    expired = [tid for tid, data in _fallback_tasks.items() if _task_age_seconds(data, now) > TASK_TTL_SECONDS]
    for tid in expired:
        _fallback_tasks.pop(tid, None)


def _task_age_seconds(data: dict, now: datetime) -> float:
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


def _store_task(task_id: str, data: dict) -> None:
    _evict_expired_tasks()
    _fallback_tasks[task_id] = data
    # TODO: Add Redis-backed store via redis client for multi-worker


def _get_task(task_id: str) -> Optional[dict]:
    _evict_expired_tasks()
    return _fallback_tasks.get(task_id)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def build_agent_context(
    request: AgentRunRequest | AgentChatRequest,
    principal: dict,
) -> AgentContext:
    """Build AgentContext from request + validated principal."""
    params_override: dict[str, Any] = request.params_override or {}
    # 注入执行上下文信息（审计用途）
    params_override["executed_by"] = {"principal_id": principal.get("sub"), "workspace_id": principal.get("workspace_id")}
    # 添加当前 data_version，确保数据同步后 session 缓存不继续使用旧版
    try:
        from server import _market_data_version
        params_override["data_version"] = _market_data_version()
    except Exception as e:
        logger.warning(f"Failed to get data version: {e}")
        params_override["data_version"] = str(datetime.now().year)

    return AgentContext(
        market=request.market,
        region=request.region,
        year=request.year,
        params_override=params_override,
        max_steps=request.max_steps,
        enable_planning=False,  # Can be flipped via query param in future
        enable_reflection=True,
        enable_retry=True,
        max_retries=2,
    )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/tools")
async def list_tools():
    """List all available agent tools (public)."""
    registry = get_tool_registry()
    definitions = registry.list_definitions()
    return AgentToolsResponse(tools=definitions, total=len(definitions))


@router.get("/workflows")
async def list_workflows():
    """List available workflow templates (public)."""
    templates = list_workflow_templates()
    return AgentWorkflowsResponse(workflows=templates, total=len(templates))


@router.post("/run", response_model=AgentRunResponse)
async def run_agent_sync(
    request: AgentRunRequest,
    principal: dict = Depends(get_current_principal),
):
    """Synchronous workflow execution (auth required)."""
    context = build_agent_context(request, principal)
    orchestrator = get_orchestrator()

    report = await orchestrator.run_streamed_sync(
        query=request.query,
        context=context,
        workflow_template_id=request.workflow_template,
    )

    return AgentRunResponse(report=report, status=WorkflowStatus.COMPLETED)


@router.post("/run-async", response_model=AgentAsyncResponse)
async def run_agent_async(
    request: AgentRunRequest,
    principal: dict = Depends(get_current_principal),
):
    """Asynchronous workflow submission (auth required)."""
    task_id = str(uuid.uuid4())

    # Spawn background task
    asyncio.create_task(_execute_task(task_id, request, principal))

    return AgentAsyncResponse(task_id=task_id, message="Workflow submitted")


async def _execute_task(task_id: str, request: AgentRunRequest, principal: dict):
    try:
        context = build_agent_context(request, principal)
        orchestrator = get_orchestrator()
        report = await orchestrator.run(
            query=request.query,
            context=context,
            workflow_template_id=request.workflow_template,
        )

        _store_task(task_id, {
            "status": WorkflowStatus.COMPLETED.value,
            "report": report.model_dump(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.exception("Async task %s failed", task_id)
        _store_task(task_id, {
            "status": WorkflowStatus.FAILED.value,
            "error": str(exc),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })


@router.get("/task/{task_id}", response_model=AgentTaskStatusResponse)
async def get_task_status(task_id: str):
    """Query async task status (auth would go here too; omitted for brevity)."""
    # TODO: add get_current_principal(...) dependency
    task = _get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.get("status") == WorkflowStatus.COMPLETED.value:
        return AgentTaskStatusResponse(
            task_id=task_id,
            status=WorkflowStatus.COMPLETED,
            report=AgentReport(**task["report"]),
        )
    elif task.get("status") == WorkflowStatus.FAILED.value:
        return AgentTaskStatusResponse(
            task_id=task_id,
            status=WorkflowStatus.FAILED,
            progress=task.get("error"),
        )
    else:
        return AgentTaskStatusResponse(
            task_id=task_id,
            status=WorkflowStatus.RUNNING,
            progress="Running...",
        )


@router.get("/history", response_model=AgentHistoryResponse)
async def get_history(limit: int = 100):
    """Get last N completed tasks (auth would go here too)."""
    # TODO: add get_current_principal(...) dependency
    executed = [
        {
            "id": tid,
            **data,
            "created_at": data.get("created_at", ""),
        }
        for tid, data in sorted(_fallback_tasks.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)
        if data.get("status") in (WorkflowStatus.COMPLETED.value, WorkflowStatus.FAILED.value)
    ][:limit]
    return AgentHistoryResponse(executions=executed, total=len(executed))

