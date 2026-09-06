"""Finland market API routes.

Migrated from server.py — provides Finland market board endpoints
including overview, table, chart, readiness, and market model.
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
from models.api_payloads import FinlandMarketModelPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["finland-market"])


# ---------------------------------------------------------------------------
# Route: GET /api/finland/board/overview
# ---------------------------------------------------------------------------


@router.get("/api/finland/board/overview")
def get_finland_board_overview(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """Return Finland board overview cards for the requested time window."""
    import server as _server

    return _server.get_finland_board_overview(start=start, end=end)


# ---------------------------------------------------------------------------
# Route: GET /api/finland/board/table
# ---------------------------------------------------------------------------


@router.get("/api/finland/board/table")
def get_finland_board_table(
    view: str = Query(..., description="Board table view key"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tz: str = Query("Europe/Helsinki"),
    limit: int = Query(240, ge=50, le=5000, description="Maximum rows returned to keep the board responsive."),
):
    """Return a Finland board table view for the requested time window and timezone."""
    import server as _server

    return _server.get_finland_board_table(
        view=view, start=start, end=end, tz=tz, limit=limit
    )


# ---------------------------------------------------------------------------
# Route: GET /api/finland/board/chart
# ---------------------------------------------------------------------------


@router.get("/api/finland/board/chart")
def get_finland_board_chart(
    fields: list[str] = Query(..., description="One or more Finland board field keys"),
    mode: str = Query("single", description="Chart mode"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    granularity: str = Query("1h"),
    limit_points: int = Query(240, ge=50, le=5000, description="Maximum points per series returned to the linked chart."),
):
    """Return one or more Finland board chart series for the requested fields and granularity."""
    import server as _server

    return _server.get_finland_board_chart(
        fields=fields,
        mode=mode,
        start=start,
        end=end,
        granularity=granularity,
        limit_points=limit_points,
    )


# ---------------------------------------------------------------------------
# Route: GET /api/finland/board/readiness
# ---------------------------------------------------------------------------


@router.get("/api/finland/board/readiness")
def get_finland_board_readiness():
    """Return Finland board readiness combining field catalog with market model source context."""
    import server as _server

    return _server.get_finland_board_readiness()


# ---------------------------------------------------------------------------
# Route: GET /api/finland/market-model
# ---------------------------------------------------------------------------


@router.get("/api/finland/market-model", response_model=FinlandMarketModelPayload)
def get_finland_market_model():
    """Return the current Finland market model source composition."""
    import server as _server

    return _server.get_finland_market_model()
