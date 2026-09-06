"""Data quality API routes.

Migrated from server.py — provides data quality monitoring endpoints
for refresh, summary, market-level rows, and issue tracking.
Delegates to server.py's existing implementations to preserve API contract.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from deps import get_db, get_cache

# R4.3：server.py 去装饰器死副本后，本模块成为生产 owner，response_model 需在此
# 声明以维持 OpenAPI $ref。payload 真源在 models.api_payloads（不能模块级依赖
# server —— 会在 register_all_routes 递归时让本模块被 skip，见该文件 docstring）。
from models.api_payloads import DataQualityIssueRowsPayload, DataQualitySummaryPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-quality"])


# ---------------------------------------------------------------------------
# Route: POST /api/data-quality/refresh
# ---------------------------------------------------------------------------


@router.post("/api/data-quality/refresh")
def refresh_data_quality():
    """Recompute and persist data quality snapshots."""
    import server as _server

    return _server.refresh_data_quality()


# ---------------------------------------------------------------------------
# Route: GET /api/data-quality/summary
# ---------------------------------------------------------------------------


@router.get("/api/data-quality/summary", response_model=DataQualitySummaryPayload)
def get_data_quality_summary(access_scope: Optional[dict] = None):
    """Return aggregated data quality summary across all markets."""
    import server as _server

    return _server.get_data_quality_summary(access_scope=access_scope)


# ---------------------------------------------------------------------------
# Route: GET /api/data-quality/markets
# ---------------------------------------------------------------------------


@router.get("/api/data-quality/markets")
def get_data_quality_markets(access_scope: Optional[dict] = None):
    """Return per-market data quality snapshot rows."""
    import server as _server

    return _server.get_data_quality_markets(access_scope=access_scope)


# ---------------------------------------------------------------------------
# Route: GET /api/data-quality/issues
# ---------------------------------------------------------------------------


@router.get("/api/data-quality/issues", response_model=DataQualityIssueRowsPayload)
def get_data_quality_issues(
    market: Optional[str] = Query(None, description="Optional market code filter"),
    access_scope: Optional[dict] = None,
):
    """Return data quality issues, optionally filtered by market."""
    import server as _server

    return _server.get_data_quality_issues(market=market, access_scope=access_scope)
