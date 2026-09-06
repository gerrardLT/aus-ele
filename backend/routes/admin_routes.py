"""System administration API routes.

Migrated from server.py — provides system management endpoints including
observability status, job management, and alert rules.
Delegates to server.py's existing implementations to preserve API contract.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from deps import get_db, get_cache

# R4.3：server.py 去装饰器死副本后，本模块成为生产 owner，response_model 需在此
# 声明以维持 OpenAPI $ref。payload 真源在 models.api_payloads（不能模块级依赖
# server —— 会在 register_all_routes 递归时让本模块被 skip，见该文件 docstring）。
from models.api_payloads import (
    AcceptedJobActionPayload,
    AlertRuleListPayload,
    JobListPayload,
    ObservabilityStatusPayload,
    RunNextJobPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Route: GET /api/observability/status
# ---------------------------------------------------------------------------


@router.get("/api/observability/status", response_model=ObservabilityStatusPayload)
def get_observability_status(access_scope: dict | None = None):
    """Return observability status including source freshness, telemetry, and OpenLineage."""
    import server as _server

    return _server.get_observability_status(access_scope=access_scope)


# ---------------------------------------------------------------------------
# Route: GET /api/jobs (list jobs)
# ---------------------------------------------------------------------------


@router.get("/api/jobs", response_model=JobListPayload)
def list_jobs_route(
    status: Optional[str] = Query(None),
    queue_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    access_scope: dict | None = None,
):
    """List jobs with optional status and queue filters."""
    import server as _server

    return _server.list_jobs_route(
        status=status, queue_name=queue_name, limit=limit, access_scope=access_scope
    )


# ---------------------------------------------------------------------------
# Route: POST /api/jobs (create job)
# ---------------------------------------------------------------------------


class _JobCreateRequest(BaseModel):
    """Mirror of server.JobCreateRequest for route-level validation."""

    job_type: str
    queue_name: str
    source_key: str
    payload: dict = Field(default_factory=dict)
    priority: int = 100
    max_attempts: int = 3


@router.post("/api/jobs", response_model=AcceptedJobActionPayload)
def create_job_route(payload: _JobCreateRequest):
    """Create a new job and enqueue it for processing."""
    import server as _server

    return _server.create_job_route(payload)


# ---------------------------------------------------------------------------
# Route: POST /api/jobs/run-next
# ---------------------------------------------------------------------------


@router.post("/api/jobs/run-next", response_model=RunNextJobPayload)
def run_next_job_route(
    queue_names: str | None = Query(None),
    access_scope: dict | None = None,
):
    """Run the next available job from the queue."""
    import server as _server

    return _server.run_next_job_route(queue_names=queue_names, access_scope=access_scope)


# ---------------------------------------------------------------------------
# Route: GET /api/alerts/rules
# ---------------------------------------------------------------------------


@router.get("/api/alerts/rules", response_model=AlertRuleListPayload)
def list_alert_rules_route(workspace_id: Optional[str] = Query(None), request: Request = None):
    """List configured alert rules, scoped to the caller's workspace (auth required)."""
    import server as _server

    # 鉴权收紧（2026-08-14）：本路由先于 server.py 内联路由注册，
    # 是 GET /api/alerts/rules 的实际入口，必须同样鉴权
    actor = _server._require_alerts_actor(request)
    return _server.list_alert_rules(
        workspace_id=_server._scoped_alert_workspace(actor, workspace_id)
    )
