"""BESS revenue benchmark API routes（Phase 1，2026-08-12）。

对标 Modo ME BESS AUS NEM Index 的内部轻量基准，供外部 API 与
Agent 工具 bess_revenue_benchmark 共用同一计算入口。

口径（derived，禁止与第三方指数绝对值直接对比）：
- 理想放电量纲：正价满放，RTE 0.85，未计充电成本
- 不含 FCAS / 容量 / CIS（coverage_mode: arbitrage-only）
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Query

from deps import get_db, get_cache
from engines.benchmark_engine import (
    BENCHMARK_COVERAGE_MODE,
    NEM_BENCHMARK_REGIONS,
    build_nem_bess_benchmark,
    build_nem_bess_region_compare,
)
from result_metadata import build_result_metadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["benchmark"])

BENCHMARK_RESPONSE_CACHE_SCOPE = "api_benchmark_v1"
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fetch_response_cache(payload: dict):
    cache = get_cache()
    return cache.get_json(BENCHMARK_RESPONSE_CACHE_SCOPE, _stable_cache_key(payload))


def _store_response_cache(payload: dict, response_payload: dict):
    cache = get_cache()
    cache.set_json(
        BENCHMARK_RESPONSE_CACHE_SCOPE,
        _stable_cache_key(payload),
        response_payload,
        DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
    )
    return response_payload


def _attach_benchmark_metadata(payload: dict, *, region: str, computation_time_ms: int) -> dict:
    """附加 P4 治理 metadata（derived 口径 + 覆盖边界告警）。"""
    db = get_db()
    data_version = db.get_last_update_time() or "no_last_update"
    payload["metadata"] = build_result_metadata(
        market="NEM",
        region_or_zone=region,
        timezone="Australia/Sydney",
        currency="AUD",
        unit="kAUD/MW/year",
        interval_minutes=30,
        data_grade="derived",
        data_quality_score=None,
        coverage={"value_streams": ["energy_arbitrage_ideal"], "fcas_included": False},
        freshness={"last_updated_at": data_version},
        source_name="AEMO settlement (trading_price)",
        source_version=data_version,
        methodology_version="bess_benchmark_v1",
        warnings=["derived_caliber", "FCAS not included", "not comparable to third-party indices"],
    )
    payload["metadata"]["computation_time_ms"] = computation_time_ms
    payload["metadata"]["coverage_mode"] = BENCHMARK_COVERAGE_MODE
    return payload


@router.get(
    "/api/benchmark/nem-bess-index",
    summary="NEM BESS revenue benchmark (rolling monthly index)",
    description=(
        "Rolling monthly BESS revenue index for a NEM mainland region, expressed "
        "as kAUD/MW/year against a reference 100MW/200MWh battery (RTE 0.85). "
        "Derived ideal-discharge caliber: FCAS/capacity not included."
    ),
)
def get_nem_bess_index(
    region: str = Query("NSW1", description="NEM mainland region (NSW1, QLD1, SA1, VIC1)"),
    months: int = Query(12, ge=1, le=24, description="Rolling window size in months"),
):
    region = region.upper()
    if region not in NEM_BENCHMARK_REGIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Benchmark 仅覆盖 NEM 大陆区域 {NEM_BENCHMARK_REGIONS}",
        )

    start_time = time.time()
    cache_payload = {"endpoint": "index", "region": region, "months": months}
    cached = _fetch_response_cache(cache_payload)
    if cached is not None:
        return cached

    try:
        response = build_nem_bess_benchmark(get_db(), region, months)
    except Exception as e:
        logger.error(f"Error in nem-bess-index: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    elapsed_ms = int((time.time() - start_time) * 1000)
    response = _attach_benchmark_metadata(response, region=region, computation_time_ms=elapsed_ms)
    return _store_response_cache(cache_payload, response)


@router.get(
    "/api/benchmark/nem-bess-region-compare",
    summary="NEM BESS revenue benchmark — latest month region comparison",
    description=(
        "Latest complete month benchmark index across NSW1/QLD1/SA1/VIC1, "
        "ranked by kAUD/MW/year. Same derived ideal-discharge caliber."
    ),
)
def get_nem_bess_region_compare():
    start_time = time.time()
    cache_payload = {"endpoint": "region-compare"}
    cached = _fetch_response_cache(cache_payload)
    if cached is not None:
        return cached

    try:
        response = build_nem_bess_region_compare(get_db())
    except Exception as e:
        logger.error(f"Error in nem-bess-region-compare: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    elapsed_ms = int((time.time() - start_time) * 1000)
    response = _attach_benchmark_metadata(
        response, region="ALL_NEM_MAINLAND", computation_time_ms=elapsed_ms
    )
    return _store_response_cache(cache_payload, response)


@router.get(
    "/api/benchmark/wem-brcp-anchor",
    summary="WEM Benchmark Reserve Capacity Price (BRCP) anchor",
    description=(
        "ERA BRCP annual anchor (200MW/1200MWh battery benchmark), maintained "
        "manually via data/contract_revenue_defaults.json. Illustrative until "
        "updated with the official capacity-year value."
    ),
)
def get_wem_brcp_anchor(
    capacity_year: str = Query("2026/27", description="Capacity year, e.g. 2026/27"),
):
    from services.contract_revenue import get_wem_brcp_anchor as _anchor

    response = _anchor(capacity_year)
    response.setdefault("market", "WEM")
    response.setdefault("unit", "AUD/MW/year")
    return response
