from __future__ import annotations

import datetime
from typing import Any

from fastapi import HTTPException


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_day_start_iso() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


PLAN_DAILY_UNIT_LIMITS = {
    "starter": 1000,
    "growth": 10000,
    "pro": 50000,
    "internal": None,
    "enterprise": None,
}

PLAN_PRICE_PER_1000_UNITS_USD = {
    "starter": 2.0,
    "growth": 1.0,
    "pro": 0.5,
    "internal": 0.0,
    "enterprise": 0.0,
}


def build_external_api_error(*, code: str, message: str, retryable: bool = False) -> dict:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
    }


def seed_external_api_client(
    db,
    *,
    client_id: str,
    api_key: str,
    client_name: str,
    plan: str,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    enabled: bool = True,
) -> dict:
    now = _utc_now_iso()
    return db.upsert_external_api_client(
        {
            "client_id": client_id,
            "api_key": api_key,
            "client_name": client_name,
            "plan": plan,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }
    )


def authenticate_external_api_key(db, api_key: str | None) -> dict:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail=build_external_api_error(code="missing_api_key", message="Missing API key"),
        )
    client = db.fetch_external_api_client_by_key(api_key)
    if not client or not client.get("enabled"):
        raise HTTPException(
            status_code=401,
            detail=build_external_api_error(code="invalid_api_key", message="Invalid API key"),
        )
    return client


def summarize_external_api_quota(db, *, client: dict) -> dict:
    daily_unit_limit = PLAN_DAILY_UNIT_LIMITS.get(client.get("plan"), 1000)
    used_units = db.sum_external_api_usage_units(
        client_id=client["client_id"],
        created_at_from=_utc_day_start_iso(),
    )
    remaining_units = None if daily_unit_limit is None else max(0, daily_unit_limit - used_units)
    return {
        "plan": client.get("plan"),
        "window": "day",
        "daily_unit_limit": daily_unit_limit,
        "used_units": used_units,
        "remaining_units": remaining_units,
    }


def check_external_api_quota(db, *, client: dict, request_units: int) -> dict:
    quota = summarize_external_api_quota(db, client=client)
    daily_unit_limit = quota["daily_unit_limit"]
    if daily_unit_limit is not None and quota["used_units"] + request_units > daily_unit_limit:
        raise HTTPException(
            status_code=429,
            detail=build_external_api_error(
                code="quota_exceeded",
                message="Daily API quota exceeded",
                retryable=False,
            ),
        )
    return quota


def _estimate_usage_cost_usd(*, plan: str, request_units: int) -> float:
    rate = PLAN_PRICE_PER_1000_UNITS_USD.get(plan, 2.0)
    return round((max(0, request_units) / 1000.0) * rate, 4)


def build_external_api_billing_summary(db, *, client_id: str | None = None, limit: int = 100) -> dict:
    created_at_from = _utc_day_start_iso()
    rows = db.summarize_external_api_usage(
        created_at_from=created_at_from,
        client_id=client_id,
        limit=limit,
    )
    items = []
    total_request_count = 0
    total_request_units = 0
    total_estimated_cost_usd = 0.0
    for row in rows:
        client = db.fetch_external_api_client(row["client_id"])
        quota = summarize_external_api_quota(db, client=client) if client else {}
        estimated_cost_usd = _estimate_usage_cost_usd(plan=row["plan"], request_units=row["request_units"])
        total_request_count += row["request_count"]
        total_request_units += row["request_units"]
        total_estimated_cost_usd += estimated_cost_usd
        items.append(
            {
                **row,
                "quota": quota,
                "estimated_cost_usd": estimated_cost_usd,
            }
        )
    return {
        "window": {
            "type": "day",
            "from": created_at_from,
        },
        "totals": {
            "request_count": total_request_count,
            "request_units": total_request_units,
            "estimated_cost_usd": round(total_estimated_cost_usd, 4),
        },
        "items": items,
    }


def build_external_api_billing_ledger(db, *, client_id: str | None = None, limit: int = 100) -> dict:
    rows = db.fetch_external_api_usage(client_id=client_id, limit=limit)
    items = []
    for row in rows:
        client = db.fetch_external_api_client(row["client_id"])
        plan = (client or {}).get("plan", "unknown")
        items.append(
            {
                **row,
                "plan": plan,
                "estimated_cost_usd": _estimate_usage_cost_usd(plan=plan, request_units=int(row.get("request_units") or 0)),
            }
        )
    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "returned": len(items),
        },
    }


def paginate_items(items: list[Any], *, offset: int = 0, limit: int = 100) -> dict:
    safe_offset = max(0, int(offset))
    safe_limit = max(1, min(int(limit), 500))
    total = len(items)
    page = items[safe_offset : safe_offset + safe_limit]
    next_offset = safe_offset + safe_limit if safe_offset + safe_limit < total else None
    return {
        "items": page,
        "pagination": {
            "offset": safe_offset,
            "limit": safe_limit,
            "returned": len(page),
            "total": total,
            "next_offset": next_offset,
        },
    }


def meter_external_api_usage(
    db,
    *,
    client_id: str,
    endpoint: str,
    http_method: str,
    status_code: int,
    request_units: int,
    latency_ms: int | None,
    api_version: str,
):
    db.insert_external_api_usage(
        client_id=client_id,
        endpoint=endpoint,
        http_method=http_method,
        status_code=status_code,
        request_units=request_units,
        latency_ms=latency_ms,
        api_version=api_version,
        created_at=_utc_now_iso(),
    )


def build_external_sla_status(db, *, api_version: str) -> dict:
    queued_jobs = db.list_jobs(status="queued", limit=500)
    running_jobs = db.list_jobs(status="running", limit=500)
    status = "degraded" if len(running_jobs) > 10 else "operational"
    return {
        "api_version": api_version,
        "status": status,
        "job_summary": {
            "queued": len(queued_jobs),
            "running": len(running_jobs),
        },
        "freshness": {
            "last_market_update_at": db.get_last_update_time(),
        },
    }


def wrap_external_response(
    *,
    endpoint: str,
    data: dict,
    api_version: str,
    pagination: dict | None = None,
    meta: dict | None = None,
) -> dict:
    return {
        "api_version": api_version,
        "endpoint": endpoint,
        "data": data,
        "pagination": pagination or {},
        "meta": meta or {},
    }
