"""External API routes.

Migrated from server.py — provides external-facing API v1 endpoints
for prices, FCAS data, and billing summary.
Delegates to server.py's existing implementations to preserve API contract.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, Query

from deps import get_db, get_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-api"])


# ---------------------------------------------------------------------------
# Route: GET /api/v1/prices
# ---------------------------------------------------------------------------


@router.get("/api/v1/prices")
def get_v1_prices(
    year: int = Query(...),
    region: str = Query(...),
    month: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    day_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Return paginated price data for the specified market region and year."""
    import server as _server

    return _server.get_v1_prices(
        year=year,
        region=region,
        month=month,
        quarter=quarter,
        day_type=day_type,
        offset=offset,
        limit=limit,
        x_api_key=x_api_key,
    )


# ---------------------------------------------------------------------------
# Route: GET /api/v1/fcas
# ---------------------------------------------------------------------------


@router.get("/api/v1/fcas")
def get_v1_fcas(
    year: int = Query(...),
    region: str = Query(...),
    aggregation: str = Query("daily"),
    capacity_mw: float = Query(100),
    month: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    day_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Return paginated FCAS analysis data for the specified market region."""
    import server as _server

    return _server.get_v1_fcas(
        year=year,
        region=region,
        aggregation=aggregation,
        capacity_mw=capacity_mw,
        month=month,
        quarter=quarter,
        day_type=day_type,
        offset=offset,
        limit=limit,
        x_api_key=x_api_key,
    )


# ---------------------------------------------------------------------------
# Route: GET /api/admin/external-api/billing-summary
# ---------------------------------------------------------------------------


@router.get("/api/admin/external-api/billing-summary")
def get_external_api_billing_summary_route(
    client_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Return external API billing summary and usage ledger."""
    import server as _server

    return _server.get_external_api_billing_summary_route(
        client_id=client_id, limit=limit
    )
