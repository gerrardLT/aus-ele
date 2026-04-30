from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Response, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib
import json
import os
import sqlite3
import sys
import threading
import uvicorn
from contextlib import asynccontextmanager
import logging
from typing import Optional, Dict, Any
import datetime
import subprocess
import uuid
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
import time

from data_quality import compute_quality_snapshots, summarize_quality_snapshots
from alerts import evaluate_alert_rules as run_alert_evaluation
from database import DatabaseManager
from fcas_opportunity import summarize_nem_fcas_opportunity
import grid_events
import grid_forecast
from fingrid import catalog as fingrid_catalog
from fingrid import service as fingrid_service
from fingrid.export import build_fingrid_csv
from network_fees import get_default_fee, get_window_sizes, get_all_fees, get_settlement_interval
from collections import defaultdict
from result_metadata import build_result_metadata
from response_cache import RedisResponseCache
from models.bess_backtest_params import BessBacktestParams
from models.financial_params import InvestmentParams
from engines.bess_backtest_v1 import run_bess_backtest_v1
from finland_market_model import build_finland_market_model_payload
from lineage import build_job_lineage_payload, build_source_freshness_payload
from logging_support import (
    install_json_log_formatter_if_enabled,
    install_structured_log_sink_if_configured,
    install_trace_log_record_factory,
)
from openlineage_support import get_openlineage_status
from access_control import (
    ORG_ROLE_PERMISSIONS,
    accept_membership_invite,
    authenticate_access_token,
    authenticate_org_actor,
    authenticate_session_token,
    assert_scope_allows_region_market,
    accept_workspace_invite,
    build_workspace_access_scope,
    check_organization_permission,
    check_workspace_permission,
    create_membership_invite,
    create_workspace_invite,
    ensure_organization_membership_from_domain_policy,
    issue_oidc_session,
    issue_access_token,
    join_organization_by_domain,
    logout_session,
    reactivate_organization_member,
    reissue_membership_invite,
    remove_organization_member,
    resolve_principal_for_oidc_claims,
    login_with_password,
    refresh_session_access_token,
    revoke_membership_invite,
    revoke_workspace_invite,
    set_principal_password,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    suspend_organization_member,
    transfer_organization_owner,
)
from external_api_v1 import (
    authenticate_external_api_key,
    build_external_api_billing_ledger,
    build_external_api_billing_summary,
    build_external_api_error,
    build_external_sla_status,
    check_external_api_quota,
    meter_external_api_usage,
    paginate_items,
    seed_external_api_client,
    summarize_external_api_quota,
    wrap_external_response,
)
from job_framework import JobOrchestrator, JobRegistry
from market_screening import build_market_screening_payload
from oidc_client import build_authorization_redirect, parse_discovery_document
from reports import generate_report_payload
from storage_lake import LocalArtifactLake
from telemetry import (
    build_collector_governance_status,
    configure_telemetry,
    get_current_trace_id,
    get_current_span_id,
    get_telemetry_status,
    record_request_metric,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
install_trace_log_record_factory(
    trace_id_supplier=get_current_trace_id,
    span_id_supplier=get_current_span_id,
)
install_json_log_formatter_if_enabled()
install_structured_log_sink_if_configured()


class AlertRuleUpsert(BaseModel):
    name: str
    rule_type: str
    market: str
    region_or_zone: str | None = None
    config: dict = Field(default_factory=dict)
    channel_type: str
    channel_target: str
    enabled: bool = True
    organization_id: str | None = None
    workspace_id: str | None = None


class JobCreateRequest(BaseModel):
    job_type: str
    queue_name: str
    source_key: str
    payload: dict = Field(default_factory=dict)
    priority: int = 100
    max_attempts: int = 3


class DataQualitySummaryPayload(BaseModel):
    summary: dict = Field(default_factory=dict)
    markets: dict = Field(default_factory=dict)


class DataQualityMarketRowsPayload(BaseModel):
    items: list[dict] = Field(default_factory=list)


class DataQualityIssueRowsPayload(BaseModel):
    items: list[dict] = Field(default_factory=list)


class ObservabilityStatusPayload(BaseModel):
    sources: list[dict] = Field(default_factory=list)
    job_summary: dict = Field(default_factory=dict)
    telemetry: dict = Field(default_factory=dict)
    openlineage: dict = Field(default_factory=dict)
    collector: dict = Field(default_factory=dict)


class ExternalApiErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False


class LooseObjectPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class AlertRuleListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class AlertStateListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class AlertDeliveryLogListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class AcceptedJobActionPayload(BaseModel):
    status: str
    detail: str | None = None
    job_id: str | None = None
    dataset_id: str | None = None
    mode: str | None = None
    job: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class JobListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class JobEventListPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class RunNextJobPayload(BaseModel):
    status: str
    result: dict[str, Any] | None = None


class FingridDatasetCatalogPayload(BaseModel):
    datasets: list[dict[str, Any]] = Field(default_factory=list)


class AvailableYearsPayload(BaseModel):
    years: list[int] = Field(default_factory=list)


class NetworkFeesPayload(BaseModel):
    fees: dict[str, Any] = Field(default_factory=dict)

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
SCRAPERS_DIR = REPO_ROOT / "scrapers"
LAKE_ROOT = Path(os.environ.get("AUS_ELE_LAKE_ROOT", REPO_ROOT / "data_lake")).resolve()


def _load_env_file(env_path: str | os.PathLike[str] | None = None):
    candidates = [Path(env_path)] if env_path else [REPO_ROOT / ".env", BACKEND_DIR / ".env"]
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
        return path
    return None


_load_env_file()
DB_PATH = os.environ.get("AUS_ELE_DB_PATH", str((REPO_ROOT / "data" / "aemo_data.db").resolve()))
db = DatabaseManager(DB_PATH)
response_cache = RedisResponseCache()

SYNC_OWNER = f"{os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'host')}:{os.getpid()}"
MARKET_SYNC_LOCK_NAME = "market_sync"
FINGRID_SYNC_LOCK_NAME = "fingrid_sync"
MARKET_SYNC_LOCK_TTL_SECONDS = int(os.environ.get("AUS_ELE_MARKET_SYNC_LOCK_TTL_SECONDS", "21600"))
FINGRID_SYNC_LOCK_TTL_SECONDS = int(os.environ.get("AUS_ELE_FINGRID_SYNC_LOCK_TTL_SECONDS", "7200"))

GRID_FORECAST_RESPONSE_CACHE_SCOPE = "api_grid_forecast_v1"
EVENT_OVERLAY_RESPONSE_CACHE_SCOPE = "api_event_overlays_v1"
PRICE_TREND_RESPONSE_CACHE_SCOPE = "api_price_trend_v1"
PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_peak_analysis_v1"
FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE = "api_fcas_analysis_v1"
HOURLY_PROFILE_RESPONSE_CACHE_SCOPE = "api_hourly_price_profile_v1"
INVESTMENT_RESPONSE_REDIS_SCOPE = "api_investment_analysis_v1"

DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 6 * 60 * 60
EVENT_OVERLAY_CACHE_TTL_SECONDS = 30 * 60
INVESTMENT_RESPONSE_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_FCAS_OPPORTUNITY_DURATION_HOURS = 4.0
GRID_FORECAST_CACHE_TTL_SECONDS = {
    "24h": 60 * 60,
    "7d": 6 * 60 * 60,
    "30d": 12 * 60 * 60,
}


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _scope_cache_payload(payload: dict, *, organization_id: str | None, workspace_id: str | None) -> dict:
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **payload,
    }


def _scope_analysis_payload(payload: dict, *, organization_id: str | None, workspace_id: str | None) -> dict:
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **payload,
    }


def _market_data_version() -> str:
    return db.get_last_update_time() or "no_last_update"


def _region_timezone(region: str) -> str:
    region_timezones = {
        "NSW1": "Australia/Sydney",
        "QLD1": "Australia/Brisbane",
        "VIC1": "Australia/Melbourne",
        "SA1": "Australia/Adelaide",
        "TAS1": "Australia/Hobart",
        "WEM": "Australia/Perth",
    }
    return region_timezones.get(region, "Australia/Sydney")


def _attach_price_trend_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="price_trend_v1",
        warnings=[],
    )
    return payload


def _attach_fingrid_metadata(payload: dict, dataset_id: str) -> dict:
    dataset = payload.get("dataset") or fingrid_catalog.get_dataset_config(dataset_id)
    payload["metadata"] = build_result_metadata(
        market="FINGRID",
        region_or_zone=dataset_id,
        timezone=dataset.get("timezone", "Europe/Helsinki"),
        currency="EUR",
        unit=dataset.get("unit", "EUR"),
        interval_minutes=None,
        data_grade="analytical-preview",
        data_quality_score=None,
        coverage={},
        freshness={},
        source_name="Fingrid",
        source_version=dataset.get("dataset_code", dataset_id),
        methodology_version="fingrid_status_v1",
        warnings=[],
    )
    return payload


def _infer_interval_hours_from_timestamps(timestamps: list[str], default_minutes: int) -> list[float]:
    if not timestamps:
        return []

    default_hours = default_minutes / 60.0
    intervals = []
    for idx in range(len(timestamps)):
        if idx + 1 < len(timestamps):
            try:
                current_ts = datetime.datetime.fromisoformat(timestamps[idx].replace("Z", "+00:00"))
                next_ts = datetime.datetime.fromisoformat(timestamps[idx + 1].replace("Z", "+00:00"))
                delta_hours = (next_ts - current_ts).total_seconds() / 3600.0
                intervals.append(delta_hours if delta_hours > 0 else default_hours)
            except Exception:
                intervals.append(default_hours)
        else:
            intervals.append(intervals[-1] if intervals else default_hours)
    return intervals


def _fetch_bess_backtest_intervals(params: BessBacktestParams) -> list[dict]:
    with db.get_connection() as conn:
        try:
            if params.market == "WEM":
                db.ensure_wem_ess_tables(conn)
                rows = conn.execute(
                    f"""
                    SELECT dispatch_interval, energy_price
                    FROM {db.WEM_ESS_MARKET_TABLE}
                    WHERE dispatch_interval LIKE ?
                    ORDER BY dispatch_interval
                    """,
                    (f"{params.year}-%",),
                ).fetchall()
                default_interval_minutes = 5
            else:
                table_name = f"trading_price_{params.year}"
                rows = conn.execute(
                    f"""
                    SELECT settlement_date, rrp_aud_mwh
                    FROM {table_name}
                    WHERE region_id = ?
                    ORDER BY settlement_date
                    """,
                    (params.region,),
                ).fetchall()
                default_interval_minutes = get_settlement_interval(params.region)
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise

    timestamps = [row[0] for row in rows]
    interval_hours = _infer_interval_hours_from_timestamps(timestamps, default_interval_minutes)
    return [
        {
            "timestamp": row[0],
            "price": float(row[1] or 0.0),
            "interval_hours": interval_hours[idx],
        }
        for idx, row in enumerate(rows)
    ]


def _attach_bess_backtest_metadata(payload: dict, params: BessBacktestParams) -> dict:
    payload["metadata"] = build_result_metadata(
        market=params.market,
        region_or_zone=params.region,
        timezone=_region_timezone(params.region),
        currency="AUD",
        unit="AUD",
        interval_minutes=5 if params.market == "WEM" else get_settlement_interval(params.region),
        data_grade="preview" if params.market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"timeline_points": payload.get("timeline_points", 0)},
        freshness={"last_updated_at": _market_data_version()},
        source_name="AEMO",
        source_version=_market_data_version(),
        methodology_version="bess_backtest_v1",
        warnings=list(payload.get("warnings", [])),
    )
    return payload


def _attach_bess_backtest_coverage_metadata(payload: dict, params: BessBacktestParams) -> dict:
    payload["metadata"] = build_result_metadata(
        market=params.market,
        region_or_zone=params.region,
        timezone=_region_timezone(params.region),
        currency="AUD",
        unit="AUD",
        interval_minutes=5 if params.market == "WEM" else get_settlement_interval(params.region),
        data_grade="preview" if params.market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"interval_count": payload.get("interval_count", 0)},
        freshness={"last_updated_at": _market_data_version()},
        source_name="AEMO",
        source_version=_market_data_version(),
        methodology_version="bess_backtest_coverage_v1",
        warnings=[] if params.market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_peak_analysis_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"row_count": len(payload.get("data", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="peak_analysis_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_hourly_price_profile_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"hour_count": len(payload.get("hourly", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="hourly_price_profile_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_event_overlay_metadata(payload: dict, *, region: str, data_version: str | None = None) -> dict:
    existing = dict(payload.get("metadata") or {})
    market = existing.get("market") or ("WEM" if region == "WEM" else "NEM")
    version = data_version or _event_overlay_data_version()
    base = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="event-state",
        interval_minutes=5 if market == "WEM" else get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={
            "coverage_quality": existing.get("coverage_quality", "none"),
            "state_count": len(payload.get("states", [])),
            "event_count": len(payload.get("events", [])),
        },
        freshness={"last_updated_at": _market_data_version()},
        source_name="AEMO",
        source_version=version,
        methodology_version="event_overlays_v1",
        warnings=list(existing.get("warnings") or ([] if market != "WEM" else ["preview_only"])),
    )
    payload["metadata"] = {**base, **existing}
    return payload


def _attach_grid_forecast_metadata(payload: dict, *, region: str, data_version: str | None = None) -> dict:
    existing = dict(payload.get("metadata") or {})
    market = existing.get("market") or ("WEM" if region == "WEM" else "NEM")
    version = data_version or _grid_forecast_data_version()
    coverage_payload = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    warnings = list(existing.get("warnings") or [])
    if market == "WEM" and "preview_only" not in warnings:
        warnings.append("preview_only")
    base = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="mixed",
        interval_minutes=5 if market == "WEM" else get_settlement_interval(region),
        data_grade="preview" if market == "WEM" else "analytical-preview",
        data_quality_score=None,
        coverage={
            "coverage_quality": existing.get("coverage_quality", "none"),
            "recent_history_points": coverage_payload.get("recent_history_points"),
            "forward_points": coverage_payload.get("forward_points"),
            "event_count": coverage_payload.get("event_count"),
        },
        freshness={
            "last_updated_at": _market_data_version(),
            "issued_at": existing.get("issued_at"),
        },
        source_name="AEMO",
        source_version=version,
        methodology_version="grid_forecast_v1",
        warnings=warnings,
    )
    payload["metadata"] = {**base, **existing}
    return payload


def _attach_fcas_analysis_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    interval_minutes = 5 if market == "WEM" else get_settlement_interval(region)
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/MW/year",
        interval_minutes=interval_minutes,
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"row_count": len(payload.get("data", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="fcas_analysis_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _attach_investment_metadata(payload: dict, *, region: str) -> dict:
    market = "WEM" if region == "WEM" else "NEM"
    data_version = _market_data_version()
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="AUD/year",
        interval_minutes=None,
        data_grade="preview" if market == "WEM" else "analytical",
        data_quality_score=None,
        coverage={"cash_flow_years": len(payload.get("cash_flows", []))},
        freshness={"last_updated_at": data_version},
        source_name="AEMO",
        source_version=data_version,
        methodology_version="investment_analysis_v1",
        warnings=[] if market != "WEM" else ["preview_only"],
    )
    return payload


def _run_standardized_bess_backtest(backtest_params: BessBacktestParams) -> dict | None:
    intervals = _fetch_bess_backtest_intervals(backtest_params)
    if not intervals:
        return None

    result = run_bess_backtest_v1(backtest_params, intervals)
    summary = result["summary"]
    return {
        "annual_revenue": summary["gross_revenue"],
        "annual_net_revenue": summary["net_revenue"],
        "annual_cycles": summary["equivalent_cycles"],
        "backtest_mode": "optimized_hindsight",
        "revenue_scope": "trajectory_gross_energy",
        "methodology_version": "bess_backtest_v1",
        "timeline_points": len(result["timeline"]),
        "input": backtest_params.model_dump(mode="json"),
        "summary": {
            "gross_revenue": summary["gross_revenue"],
            "net_revenue": summary["net_revenue"],
            "equivalent_cycles": summary["equivalent_cycles"],
            "charge_throughput_mwh": summary["charge_throughput_mwh"],
            "discharge_throughput_mwh": summary["discharge_throughput_mwh"],
            "soc_start_mwh": summary["soc_start_mwh"],
            "soc_end_mwh": summary["soc_end_mwh"],
            "soc_min_mwh": summary["soc_min_mwh"],
            "soc_max_mwh": summary["soc_max_mwh"],
            "costs": dict(summary["costs"]),
            "warnings": list(summary["warnings"]),
        },
    }


def _event_overlay_data_version() -> str:
    return _stable_cache_key({
        "market_version": _market_data_version(),
        "event_sync": db.fetch_grid_event_sync_states(),
    })


def _grid_forecast_data_version() -> str:
    return _event_overlay_data_version()


def _fetch_response_cache(scope: str, payload: dict, normalize_fn=None):
    cache_key = _stable_cache_key(payload)
    cached = response_cache.get_json(scope, cache_key)
    if cached is None:
        return None
    return normalize_fn(cached) if normalize_fn else cached


def _store_response_cache(scope: str, payload: dict, response_payload: dict, ttl_seconds: int):
    cache_key = _stable_cache_key(payload)
    response_cache.set_json(scope, cache_key, response_payload, ttl_seconds)
    return response_payload


def _cacheable_param(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    default = getattr(value, "default", None)
    if isinstance(default, (str, int, float, bool)) or default is None:
        return default
    return str(value)


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _uniform_downsample_price_rows(rows, limit: int):
    if not rows or len(rows) <= limit or limit is None or limit <= 0:
        return [{"time": row[0], "price": round(row[1], 2)} for row in rows]

    if limit == 1:
        last_row = rows[-1]
        return [{"time": last_row[0], "price": round(last_row[1], 2)}]

    step = (len(rows) - 1) / float(limit - 1)
    indices = []
    seen = set()
    for position in range(limit):
        index = int(round(position * step))
        index = max(0, min(index, len(rows) - 1))
        if index not in seen:
            seen.add(index)
            indices.append(index)

    if indices[-1] != len(rows) - 1:
        indices[-1] = len(rows) - 1

    return [{"time": rows[index][0], "price": round(rows[index][1], 2)} for index in indices]


def _downsample_price_rows(rows, limit: int):
    if not rows or len(rows) <= limit or limit is None or limit <= 0:
        return [{"time": row[0], "price": round(row[1], 2)} for row in rows]

    try:
        import numpy as np
        import lttbc

        x = np.arange(len(rows), dtype=np.float64)
        y = np.array([row[1] for row in rows], dtype=np.float64)
        dx, dy = lttbc.downsample(x, y, limit)

        data = []
        for idx_flt, val in zip(dx, dy):
            orig_idx = int(round(idx_flt))
            orig_idx = max(0, min(orig_idx, len(rows) - 1))
            data.append({"time": rows[orig_idx][0], "price": round(val, 2)})
        return data
    except Exception as exc:
        logger.warning("Falling back to uniform price downsampling because LTTB failed: %s", exc)
        return _uniform_downsample_price_rows(rows, limit)


def _cors_allow_origins() -> list[str]:
    raw_value = os.environ.get("AUS_ELE_CORS_ALLOW_ORIGINS", "").strip()
    if not raw_value:
        return ["http://127.0.0.1:5173", "http://localhost:5173"]

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["http://127.0.0.1:5173", "http://localhost:5173"]


def _cors_allow_credentials() -> bool:
    return _env_flag("AUS_ELE_CORS_ALLOW_CREDENTIALS", False)


def _scheduler_timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("AUS_ELE_SCHEDULER_TIMEZONE", "UTC"))


def _scheduler_now() -> datetime.datetime:
    return datetime.datetime.now(_scheduler_timezone())


def _scheduler_enabled() -> bool:
    return _env_flag("AUS_ELE_ENABLE_SCHEDULER", True)


def _job_worker_enabled() -> bool:
    return _env_flag("AUS_ELE_ENABLE_JOB_WORKER", True)


def _job_worker_poll_seconds() -> float:
    try:
        return float(os.environ.get("AUS_ELE_JOB_WORKER_POLL_SECONDS", "2"))
    except ValueError:
        return 2.0


def _job_worker_queue_names() -> list[str] | None:
    raw = os.environ.get("AUS_ELE_JOB_WORKER_QUEUES", "")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or None


def _utc_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _default_oidc_discovery_document(provider: dict) -> dict:
    issuer = provider["issuer"].rstrip("/")
    return parse_discovery_document(
        {
            "issuer": provider["issuer"],
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "userinfo_endpoint": f"{issuer}/userinfo",
            "jwks_uri": f"{issuer}/jwks",
        }
    )


def _metered_v1_call(*, x_api_key: str | None, endpoint: str, http_method: str, request_units: int, handler):
    started_at = time.perf_counter()
    client = None
    status_code = 200
    try:
        client = authenticate_external_api_key(db, x_api_key)
        check_external_api_quota(db, client=client, request_units=request_units)
        payload = handler(client)
        if isinstance(payload, dict):
            meta = payload.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["quota"] = summarize_external_api_quota(db, client=client)
        return payload
    except HTTPException as exc:
        status_code = exc.status_code
        if isinstance(exc.detail, str):
            if exc.status_code == 403:
                exc.detail = build_external_api_error(code="access_denied", message=exc.detail)
            elif exc.status_code == 404:
                exc.detail = build_external_api_error(code="not_found", message=exc.detail)
            elif exc.status_code >= 500:
                exc.detail = build_external_api_error(code="internal_error", message=exc.detail, retryable=True)
            else:
                exc.detail = build_external_api_error(code="request_error", message=exc.detail)
        raise
    finally:
        if client is not None:
            latency_ms = round((time.perf_counter() - started_at) * 1000)
            meter_external_api_usage(
                db,
                client_id=client["client_id"],
                endpoint=endpoint,
                http_method=http_method,
                status_code=status_code,
                request_units=request_units,
                latency_ms=latency_ms,
                api_version="v1",
            )


def _build_request_trace_id(endpoint: str) -> str:
    current_trace_id = get_current_trace_id()
    if current_trace_id:
        return current_trace_id
    suffix = endpoint.strip("/").replace("/", ".") or "root"
    return f"req.{suffix}.{uuid.uuid4().hex[:12]}"


def _require_workspace_actor(x_access_token: str | None) -> dict:
    return authenticate_access_token(db, x_access_token)


def _require_session_actor(x_session_token: str | None) -> dict:
    return authenticate_session_token(db, x_session_token)


def _assert_scope_allows_internal_query(scope: dict, *, region: str | None = None, market: str | None = None):
    return assert_scope_allows_region_market(scope, region=region, market=market)


def _filter_scope_market_items(items: list[dict], access_scope: dict | None) -> list[dict]:
    if not access_scope:
        return items
    allowed_markets = set(access_scope.get("allowed_markets") or [])
    if not allowed_markets:
        return items
    return [item for item in items if item.get("market") in allowed_markets]


def _filter_scope_region_market_items(items: list[dict], access_scope: dict | None) -> list[dict]:
    if not access_scope:
        return items
    allowed_markets = set(access_scope.get("allowed_markets") or [])
    allowed_regions = set(access_scope.get("allowed_regions") or [])
    filtered = []
    for item in items:
        market = item.get("market")
        region = item.get("region_or_zone")
        if allowed_markets and market not in allowed_markets:
            continue
        if allowed_regions and market in {"NEM", "WEM"} and region not in allowed_regions:
            continue
        filtered.append(item)
    return filtered


def _assert_artifact_scope(artifact: dict, scope: dict):
    if artifact.get("organization_id") and artifact["organization_id"] != scope.get("organization_id"):
        raise HTTPException(status_code=403, detail="Artifact organization mismatch")
    if artifact.get("workspace_id") and artifact["workspace_id"] != scope.get("workspace_id"):
        raise HTTPException(status_code=403, detail="Artifact workspace mismatch")
    return True


def _assert_job_scope(job: dict, scope: dict):
    if job.get("organization_id") and job["organization_id"] != scope.get("organization_id"):
        raise HTTPException(status_code=403, detail="Job organization mismatch")
    if job.get("workspace_id") and job["workspace_id"] != scope.get("workspace_id"):
        raise HTTPException(status_code=403, detail="Job workspace mismatch")
    return True


def _matches_text_query(values: list[str | None], query: str | None) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    if not needle:
        return True
    return any(needle in (value or "").lower() for value in values)


def _build_organization_member_view(membership: dict) -> dict:
    principal = db.fetch_principal(membership["principal_id"])
    return {
        **membership,
        "principal": principal,
    }


def _filter_organization_audit_items(
    items: list[dict],
    *,
    organization_id: str,
    query: str | None = None,
) -> list[dict]:
    filtered = []
    for item in items:
        detail = item.get("detail_json") or {}
        detail_org_id = detail.get("organization_id")
        target_matches = item.get("target_type") == "organization" and item.get("target_id") == organization_id
        if detail_org_id != organization_id and not target_matches:
            continue
        if not _matches_text_query(
            [
                item.get("action"),
                item.get("target_type"),
                item.get("target_id"),
                item.get("actor_principal_id"),
                json.dumps(detail, sort_keys=True, ensure_ascii=False),
            ],
            query,
        ):
            continue
        filtered.append(item)
    return filtered


def _build_client_access_scope(client: dict) -> dict:
    workspace_id = client.get("workspace_id")
    organization_id = client.get("organization_id")
    if not workspace_id:
        return {
            "organization_id": organization_id,
            "workspace_id": None,
            "principal_id": None,
            "workspace_role": None,
            "allowed_regions": [],
            "allowed_markets": [],
        }
    workspace = db.fetch_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=401, detail="Invalid workspace scope")
    if organization_id and workspace.get("organization_id") != organization_id:
        raise HTTPException(status_code=403, detail="Workspace organization mismatch")
    policy = db.fetch_workspace_policy(workspace_id) or {
        "allowed_regions_json": [],
        "allowed_markets_json": [],
    }
    return {
        "organization_id": workspace.get("organization_id"),
        "workspace_id": workspace_id,
        "principal_id": None,
        "workspace_role": None,
        "allowed_regions": list(policy.get("allowed_regions_json") or []),
        "allowed_markets": list(policy.get("allowed_markets_json") or []),
    }


def _assert_workspace_scope(client: dict, *, region: str | None = None, market: str | None = None):
    scope = _build_client_access_scope(client)
    return _assert_scope_allows_internal_query(scope, region=region, market=market)


def _resolve_scoped_workspace_id(access_scope: dict | None, workspace_id: str | None = None) -> str | None:
    if not access_scope:
        return workspace_id
    scope_workspace_id = access_scope.get("workspace_id")
    if workspace_id is not None and scope_workspace_id and workspace_id != scope_workspace_id:
        raise HTTPException(status_code=403, detail="Workspace scope mismatch")
    return workspace_id or scope_workspace_id


def _try_acquire_job_lock(lock_name: str, ttl_seconds: int) -> bool:
    return db.acquire_system_lock(lock_name, owner=SYNC_OWNER, ttl_seconds=ttl_seconds)


def _release_job_lock(lock_name: str):
    db.release_system_lock(lock_name, owner=SYNC_OWNER)


def _run_scraper(script_name: str, *args: str):
    script_path = (SCRAPERS_DIR / script_name).resolve()
    command = [sys.executable, str(script_path), *args]
    subprocess.run(command, check=True, cwd=str(REPO_ROOT))


job_registry = JobRegistry()
artifact_lake = LocalArtifactLake(str(LAKE_ROOT))
job_orchestrator = JobOrchestrator(
    db,
    registry=job_registry,
    lake=artifact_lake,
    worker_id="api-worker-1",
    source_rate_limits={
        "aemo": 60,
        "fingrid": 10,
        "reporting": 1,
    },
)


def enqueue_job(*, job_type: str, payload: dict, queue_name: str, source_key: str, priority: int = 100, max_attempts: int = 3):
    return job_orchestrator.enqueue(
        job_type,
        payload=payload,
        queue_name=queue_name,
        source_key=source_key,
        priority=priority,
        max_attempts=max_attempts,
    )


def _find_open_job(*, job_type: str, source_key: str):
    for job in db.list_jobs(limit=500):
        if job["job_type"] == job_type and job["source_key"] == source_key and job["status"] in {"queued", "running"}:
            return job
    return None


def enqueue_market_sync_job(*, manual: bool = False):
    existing = _find_open_job(job_type="market_sync", source_key="aemo")
    if existing:
        return existing
    return enqueue_job(
        job_type="market_sync",
        payload={"manual": manual},
        queue_name="sync",
        source_key="aemo",
        priority=40 if manual else 60,
        max_attempts=2,
    )


def enqueue_fingrid_dataset_sync_job(*, dataset_id: str, mode: str):
    existing = _find_open_job(job_type="fingrid_dataset_sync", source_key="fingrid")
    if existing and existing["payload_json"].get("dataset_id") == dataset_id and existing["payload_json"].get("mode") == mode:
        return existing
    return enqueue_job(
        job_type="fingrid_dataset_sync",
        payload={"dataset_id": dataset_id, "mode": mode},
        queue_name="sync",
        source_key="fingrid",
        priority=50,
        max_attempts=3,
    )


def enqueue_fingrid_hourly_sync_job():
    existing = _find_open_job(job_type="fingrid_hourly_sync", source_key="fingrid")
    if existing:
        return existing
    return enqueue_job(
        job_type="fingrid_hourly_sync",
        payload={"mode": "incremental"},
        queue_name="sync",
        source_key="fingrid",
        priority=70,
        max_attempts=2,
    )


def enqueue_report_generation_job(
    *,
    report_type: str,
    year: int,
    region: str,
    month: str | None = None,
    workspace_id: str | None = None,
    organization_id: str | None = None,
):
    return enqueue_job(
        job_type="report_generate",
        payload={
            "report_type": report_type,
            "year": year,
            "region": region,
            "month": month,
            "workspace_id": workspace_id,
            "organization_id": organization_id,
        },
        queue_name="reports",
        source_key="reporting",
        priority=80,
        max_attempts=2,
    )


def _register_job_handlers():
    job_registry.register(
        "market_sync",
        lambda job, context: run_sync_scrapers(bool(job["payload_json"].get("manual"))),
    )
    job_registry.register(
        "fingrid_dataset_sync",
        lambda job, context: run_fingrid_dataset_sync(
            job["payload_json"]["dataset_id"],
            str(job["payload_json"].get("mode", "incremental")),
        ),
    )
    job_registry.register(
        "fingrid_hourly_sync",
        lambda job, context: run_fingrid_hourly_sync(),
    )
    job_registry.register(
        "report_generate",
        lambda job, context: generate_report(
            report_type=job["payload_json"]["report_type"],
            year=int(job["payload_json"]["year"]),
            region=str(job["payload_json"]["region"]),
            month=job["payload_json"].get("month"),
            organization_id=job["payload_json"].get("organization_id"),
            workspace_id=job["payload_json"].get("workspace_id"),
        ),
    )


_register_job_handlers()


class JobWorkerService:
    def __init__(self, orchestrator: JobOrchestrator, *, queue_names: list[str] | None = None):
        self.orchestrator = orchestrator
        self.queue_names = list(queue_names) if queue_names else None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run_loop, name="aus-ele-job-worker", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                result = self.orchestrator.run_once(queue_names=self.queue_names)
                if result is None:
                    self.stop_event.wait(_job_worker_poll_seconds())
                    continue
            except Exception as exc:
                logger.error("Job worker loop error: %s", exc)
                self.stop_event.wait(_job_worker_poll_seconds())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting AEMO NEM API server with built-in Scheduler...")
    if _scheduler_enabled():
        scheduler = AsyncIOScheduler(timezone=_scheduler_timezone())
        scheduler.add_job(enqueue_market_sync_job, 'cron', hour=2, minute=0, id="market-daily-sync")
        scheduler.add_job(
            enqueue_fingrid_hourly_sync_job,
            'cron',
            minute=10,
            id="fingrid-hourly-sync",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=15 * 60,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Internal scheduler enabled with timezone %s", _scheduler_timezone().key)
    else:
        logger.info("Internal scheduler disabled by AUS_ELE_ENABLE_SCHEDULER")

    if _job_worker_enabled():
        worker = JobWorkerService(job_orchestrator, queue_names=_job_worker_queue_names())
        worker.start()
        app.state.job_worker = worker
        logger.info(
            "Internal job worker enabled with poll interval %ss and queues %s",
            _job_worker_poll_seconds(),
            ",".join(_job_worker_queue_names() or ["*"]),
        )
    else:
        logger.info("Internal job worker disabled by AUS_ELE_ENABLE_JOB_WORKER")
    
    yield
    # Shutdown actions
    logger.info("Shutting down AEMO NEM API server...")
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()
    if hasattr(app.state, 'job_worker'):
        app.state.job_worker.stop()

app = FastAPI(title="AEMO NEM Data API", lifespan=lifespan)

OPENAPI_ERROR_RESPONSES = {
    500: {
        "description": "Internal server error",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Internal server error",
                }
            }
        },
    }
}

OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES = {
    404: {
        "description": "Resource or source data not found",
        "content": {
            "application/json": {
                "example": {
                    "detail": "No data available for year 2026",
                }
            }
        },
    },
    **OPENAPI_ERROR_RESPONSES,
}

EXTERNAL_API_ERROR_RESPONSES = {
    401: {
        "model": ExternalApiErrorPayload,
        "description": "Missing or invalid API key.",
    },
    403: {
        "model": ExternalApiErrorPayload,
        "description": "Workspace, market, or region access denied.",
    },
    404: {
        "model": ExternalApiErrorPayload,
        "description": "Requested external API resource was not found.",
    },
    500: {
        "model": ExternalApiErrorPayload,
        "description": "Internal server error.",
    },
}

# Allow CORS for local frontend development by default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=_cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/summary")
def get_summary():
    """Returns database summary statistics (tables, time ranges, record counts) and last update time"""
    try:
        summary = db.get_summary()
        summary["last_update"] = db.get_last_update_time()
        return summary
    except Exception as e:
        logger.error(f"Error fetching summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/data-quality/refresh")
def refresh_data_quality():
    try:
        snapshots = compute_quality_snapshots(db)
        db.replace_data_quality_snapshots(snapshots)
        return {"status": "ok", "snapshots_refreshed": len(snapshots)}
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        logger.error("Error refreshing data quality snapshots: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/data-quality/summary", response_model=DataQualitySummaryPayload)
def get_data_quality_summary(access_scope: Optional[dict] = None):
    try:
        rows = db.fetch_data_quality_snapshots()
        rows = _filter_scope_market_items(rows, access_scope)
        return summarize_quality_snapshots(rows)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching data quality summary: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/data-quality/markets", response_model=DataQualityMarketRowsPayload)
def get_data_quality_markets(access_scope: Optional[dict] = None):
    try:
        items = db.fetch_data_quality_snapshots(scope="market")
        return {"items": _filter_scope_market_items(items, access_scope)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching market data quality rows: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/data-quality/issues", response_model=DataQualityIssueRowsPayload)
def get_data_quality_issues(
    market: Optional[str] = Query(None, description="Optional market code filter"),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope and market:
            _assert_scope_allows_internal_query(access_scope, market=market)
        items = db.fetch_data_quality_issues(market=market)
        return {"items": _filter_scope_market_items(items, access_scope)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching data quality issues: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/market-screening",
    summary="Get cross-market screening ranking",
    description="Returns ranked screening candidates for NEM regions, WEM, and Finland using heuristic spread, volatility, opportunity, and data-quality dimensions.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
    response_model=LooseObjectPayload,
)
def get_market_screening(
    year: int = Query(..., description="Year to evaluate"),
    access_scope: Optional[dict] = None,
):
    try:
        payload = build_market_screening_payload(db, year=year)
        payload["items"] = _filter_scope_region_market_items(payload.get("items", []), access_scope)
        if isinstance(payload.get("summary"), dict):
            payload["summary"]["candidate_count"] = len(payload["items"])
            payload["summary"]["markets_covered"] = sorted({item["market"] for item in payload["items"]})
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Market screening error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


def create_alert_rule(payload: AlertRuleUpsert):
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "rule_id": f"al_{uuid.uuid4().hex[:12]}",
        "name": payload.name,
        "rule_type": payload.rule_type,
        "market": payload.market,
        "region_or_zone": payload.region_or_zone,
        "config": payload.config,
        "channel_type": payload.channel_type,
        "channel_target": payload.channel_target,
        "enabled": payload.enabled,
        "organization_id": payload.organization_id,
        "workspace_id": payload.workspace_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    return db.upsert_alert_rule(record)


def list_alert_rules(workspace_id: str | None = None, access_scope: dict | None = None):
    scoped_workspace_id = _resolve_scoped_workspace_id(access_scope, workspace_id)
    return {"items": db.fetch_alert_rules(workspace_id=scoped_workspace_id)}


def list_alert_states(workspace_id: str | None = None, access_scope: dict | None = None):
    scoped_workspace_id = _resolve_scoped_workspace_id(access_scope, workspace_id)
    return {"items": db.fetch_alert_states(workspace_id=scoped_workspace_id)}


def list_alert_delivery_logs(limit: int = 100, workspace_id: str | None = None, access_scope: dict | None = None):
    scoped_workspace_id = _resolve_scoped_workspace_id(access_scope, workspace_id)
    return {"items": db.fetch_alert_delivery_logs(limit=limit, workspace_id=scoped_workspace_id)}


def evaluate_alert_rules(sender=None, workspace_id: str | None = None, access_scope: dict | None = None):
    scoped_workspace_id = _resolve_scoped_workspace_id(access_scope, workspace_id)
    return run_alert_evaluation(db, sender=sender, workspace_id=scoped_workspace_id)


def generate_report(
    *,
    report_type: str,
    year: int,
    region: str,
    month: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    access_scope: dict | None = None,
):
    if access_scope:
        _assert_scope_allows_internal_query(
            access_scope,
            region=region,
            market="WEM" if region == "WEM" else "NEM",
        )
    scoped_workspace_id = _resolve_scoped_workspace_id(access_scope, workspace_id)
    return generate_report_payload(
        db,
        report_type=report_type,
        year=year,
        region=region,
        month=month,
        organization_id=organization_id or (access_scope or {}).get("organization_id"),
        workspace_id=scoped_workspace_id,
    )


@app.post("/api/alerts/rules", response_model=LooseObjectPayload)
def create_alert_rule_route(payload: AlertRuleUpsert):
    try:
        return create_alert_rule(payload)
    except Exception as exc:
        logger.error("Create alert rule error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/alerts/rules", response_model=AlertRuleListPayload)
def list_alert_rules_route(workspace_id: Optional[str] = Query(None)):
    try:
        return list_alert_rules(workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List alert rules error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/alerts/states", response_model=AlertStateListPayload)
def list_alert_states_route(workspace_id: Optional[str] = Query(None)):
    try:
        return list_alert_states(workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List alert states error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/alerts/delivery-logs", response_model=AlertDeliveryLogListPayload)
def list_alert_delivery_logs_route(
    limit: int = Query(100, ge=1, le=500),
    workspace_id: Optional[str] = Query(None),
):
    try:
        return list_alert_delivery_logs(limit=limit, workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List alert delivery logs error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/alerts/evaluate", response_model=LooseObjectPayload)
def evaluate_alert_rules_route(workspace_id: Optional[str] = Query(None)):
    try:
        return evaluate_alert_rules(workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Evaluate alert rules error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/reports/generate", response_model=LooseObjectPayload)
def generate_report_route(
    report_type: str = Query(..., pattern="^(monthly_market_report|investment_memo_draft)$"),
    year: int = Query(...),
    region: str = Query(...),
    month: Optional[str] = Query(None),
):
    try:
        return generate_report(report_type=report_type, year=year, region=region, month=month)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Generate report error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/reports/jobs", response_model=AcceptedJobActionPayload)
def enqueue_report_route(
    report_type: str = Query(..., pattern="^(monthly_market_report|investment_memo_draft)$"),
    year: int = Query(...),
    region: str = Query(...),
    month: Optional[str] = Query(None),
):
    try:
        job = enqueue_report_generation_job(report_type=report_type, year=year, region=region, month=month)
        return {"status": "accepted", "job_id": job["job_id"], "job": job}
    except Exception as exc:
        logger.error("Enqueue report job error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/jobs", response_model=AcceptedJobActionPayload)
def create_job_route(payload: JobCreateRequest):
    try:
        job = enqueue_job(
            job_type=payload.job_type,
            payload=payload.payload,
            queue_name=payload.queue_name,
            source_key=payload.source_key,
            priority=payload.priority,
            max_attempts=payload.max_attempts,
        )
        return {"status": "accepted", "job_id": job["job_id"], "job": job}
    except Exception as exc:
        logger.error("Create job route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/jobs", response_model=JobListPayload)
def list_jobs_route(
    status: Optional[str] = Query(None),
    queue_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    access_scope: dict | None = None,
):
    try:
        items = db.list_jobs(status=status, queue_name=queue_name, limit=limit)
        if access_scope:
            items = [
                item
                for item in items
                if item.get("organization_id") == access_scope.get("organization_id")
                and item.get("workspace_id") == access_scope.get("workspace_id")
            ]
        return {"items": items}
    except Exception as exc:
        logger.error("List jobs route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/jobs/{job_id}", response_model=LooseObjectPayload)
def get_job_route(job_id: str, access_scope: dict | None = None):
    try:
        job = db.fetch_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if access_scope:
            _assert_job_scope(job, access_scope)
        return job
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get job route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/jobs/{job_id}/events", response_model=JobEventListPayload)
def get_job_events_route(job_id: str, access_scope: dict | None = None):
    try:
        job = db.fetch_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if access_scope:
            _assert_job_scope(job, access_scope)
        return {"items": db.list_job_events(job_id)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get job events route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/jobs/{job_id}/lineage", response_model=LooseObjectPayload)
def get_job_lineage_route(job_id: str, access_scope: dict | None = None):
    try:
        payload = build_job_lineage_payload(db, job_id)
        if access_scope:
            _assert_job_scope(payload["job"], access_scope)
        return payload
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get job lineage route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/jobs/{job_id}/cancel", response_model=AcceptedJobActionPayload)
def cancel_job_route(job_id: str, access_scope: dict | None = None):
    try:
        if access_scope:
            job = db.fetch_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found or not cancellable")
            _assert_job_scope(job, access_scope)
        if not db.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found or not cancellable")
        return {"status": "accepted", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Cancel job route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/jobs/{job_id}/retry", response_model=AcceptedJobActionPayload)
def retry_job_route(job_id: str, access_scope: dict | None = None):
    try:
        if access_scope:
            job = db.fetch_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found or not retryable")
            _assert_job_scope(job, access_scope)
        if not db.retry_job(job_id, next_run_after=_utc_timestamp()):
            raise HTTPException(status_code=404, detail="Job not found or not retryable")
        db.append_job_event(job_id, "retry_queued", {}, _utc_timestamp())
        return {"status": "accepted", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Retry job route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/jobs/run-next", response_model=RunNextJobPayload)
def run_next_job_route(queue_names: str | None = Query(None), access_scope: dict | None = None):
    try:
        queue_names_value = queue_names if isinstance(queue_names, str) else None
        queue_name_items = [item.strip() for item in (queue_names_value or "").split(",") if item.strip()] or None
        if access_scope:
            result = job_orchestrator.run_once_scoped(
                organization_id=access_scope.get("organization_id"),
                workspace_id=access_scope.get("workspace_id"),
                queue_names=queue_name_items,
            )
        else:
            result = job_orchestrator.run_once(queue_names=queue_name_items)
        return {"status": "idle" if result is None else "ok", "result": result}
    except Exception as exc:
        logger.error("Run-next job route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/observability/status", response_model=ObservabilityStatusPayload)
def get_observability_status(access_scope: dict | None = None):
    try:
        payload = build_source_freshness_payload(db)
        payload["telemetry"] = get_telemetry_status()
        payload["openlineage"] = get_openlineage_status()
        payload["collector"] = build_collector_governance_status(payload["telemetry"], payload["openlineage"])
        if not access_scope:
            return payload
        queued = db.list_jobs(status="queued", limit=500)
        running = db.list_jobs(status="running", limit=500)
        queued = [job for job in queued if job.get("organization_id") == access_scope.get("organization_id") and job.get("workspace_id") == access_scope.get("workspace_id")]
        running = [job for job in running if job.get("organization_id") == access_scope.get("organization_id") and job.get("workspace_id") == access_scope.get("workspace_id")]
        sources = []
        for source in payload.get("sources", []):
            if source.get("source_key") == "job_system":
                sources.append(
                    {
                        **source,
                        "queued_jobs": len(queued),
                        "running_jobs": len(running),
                        "status": "busy" if running else "idle",
                    }
                )
            else:
                sources.append(source)
        return {
            **payload,
            "sources": sources,
            "job_summary": {"queued": len(queued), "running": len(running)},
        }
    except Exception as exc:
        logger.error("Observability status route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations")
def create_organization_route(name: str = Query(...)):
    try:
        return seed_organization(db, name=name)
    except Exception as exc:
        logger.error("Create organization route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/organizations")
def list_organizations_route():
    try:
        return {"items": db.list_organizations()}
    except Exception as exc:
        logger.error("List organizations route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/members")
def add_organization_member_route(
    organization_id: str,
    principal_id: str = Query(...),
    role: str = Query(...),
    status: str = Query("active"),
):
    try:
        return seed_organization_membership(
            db,
            organization_id=organization_id,
            principal_id=principal_id,
            role=role,
            status=status,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Add organization member route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/organizations/{organization_id}/members")
def list_organization_members_route(
    organization_id: str,
    principal_id: str = Query(...),
    status: Optional[str] = None,
    role: Optional[str] = None,
    query: Optional[str] = None,
):
    try:
        authenticate_org_actor(db, organization_id, principal_id)
        items = [
            _build_organization_member_view(item)
            for item in db.list_organization_memberships(organization_id, status=status, role=role)
        ]
        if query:
            items = [
                item
                for item in items
                if _matches_text_query(
                    [
                        item["principal_id"],
                        item["role"],
                        item["status"],
                        item.get("principal", {}).get("email"),
                        item.get("principal", {}).get("display_name"),
                    ],
                    query,
                )
            ]
        return {"items": items}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List organization members route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/invites")
def create_organization_invite_route(
    organization_id: str,
    principal_id: str = Query(...),
    email: str = Query(...),
    target_role: str = Query(...),
    expires_at: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, principal_id)
        return create_membership_invite(
            db,
            actor=actor,
            organization_id=organization_id,
            workspace_id=None,
            target_scope_type="organization",
            email=email,
            target_role=target_role,
            expires_at=expires_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Create organization invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/organizations/{organization_id}/invites")
def list_organization_invites_route(
    organization_id: str,
    principal_id: str = Query(...),
    status: Optional[str] = Query(None),
):
    try:
        actor = authenticate_org_actor(db, organization_id, principal_id)
        check_organization_permission(actor, "member_manage")
        return {"items": db.list_membership_invites(organization_id, status=status)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List organization invites route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/invites/{invite_id}/revoke")
def revoke_organization_invite_route(
    invite_id: str,
    organization_id: str = Query(...),
    principal_id: str = Query(...),
    revoke_reason: str = Query("manual_revoke"),
):
    try:
        actor = authenticate_org_actor(db, organization_id, principal_id)
        return revoke_membership_invite(db, actor=actor, invite_id=invite_id, revoke_reason=revoke_reason)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Revoke organization invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/invites/{invite_id}/reissue")
def reissue_organization_invite_route(
    invite_id: str,
    organization_id: str = Query(...),
    principal_id: str = Query(...),
    expires_at: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, principal_id)
        return reissue_membership_invite(db, actor=actor, invite_id=invite_id, expires_at=expires_at)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Reissue organization invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/organizations/invites/accept")
def accept_organization_invite_route(invite_token: str = Query(...), display_name: str = Query(...)):
    try:
        return accept_membership_invite(db, invite_token=invite_token, display_name=display_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Accept organization invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/members/{principal_id}/suspend")
def suspend_organization_member_route(
    organization_id: str,
    principal_id: str,
    actor_principal_id: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, actor_principal_id)
        return suspend_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Suspend organization member route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/members/{principal_id}/reactivate")
def reactivate_organization_member_route(
    organization_id: str,
    principal_id: str,
    actor_principal_id: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, actor_principal_id)
        return reactivate_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Reactivate organization member route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/members/{principal_id}/remove")
def remove_organization_member_route(
    organization_id: str,
    principal_id: str,
    actor_principal_id: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, actor_principal_id)
        return remove_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Remove organization member route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/members/bulk-update")
def bulk_update_organization_members_route(
    organization_id: str,
    actor_principal_id: str = Query(...),
    principal_ids: str = Query(..., description="Comma-separated principal ids"),
    operation: str = Query(..., description="suspend | reactivate | remove"),
):
    try:
        actor = authenticate_org_actor(db, organization_id, actor_principal_id)
        targets = [item.strip() for item in principal_ids.split(",") if item.strip()]
        items = []
        for principal_id in targets:
            if operation == "suspend":
                items.append(suspend_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id))
            elif operation == "reactivate":
                items.append(reactivate_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id))
            elif operation == "remove":
                items.append(remove_organization_member(db, actor=actor, organization_id=organization_id, principal_id=principal_id))
            else:
                raise HTTPException(status_code=400, detail="Unsupported bulk operation")
        return {"organization_id": organization_id, "operation": operation, "items": items}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Bulk update organization members route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/owner-transfer")
def transfer_organization_owner_route(
    organization_id: str,
    actor_principal_id: str = Query(...),
    new_owner_principal_id: str = Query(...),
):
    try:
        actor = authenticate_org_actor(db, organization_id, actor_principal_id)
        return transfer_organization_owner(
            db,
            actor=actor,
            organization_id=organization_id,
            new_owner_principal_id=new_owner_principal_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Transfer organization owner route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/organizations/{organization_id}/audit-logs")
def list_organization_audit_logs_route(
    organization_id: str,
    principal_id: str = Query(...),
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    actor_principal_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 100,
):
    try:
        actor = authenticate_org_actor(db, organization_id, principal_id)
        check_organization_permission(actor, "read_audit")
        items = db.fetch_audit_logs(
            action=action,
            target_type=target_type,
            actor_principal_id=actor_principal_id,
            limit=limit,
        )
        items = _filter_organization_audit_items(items, organization_id=organization_id, query=query)
        return {"items": items}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List organization audit logs route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/principals")
def create_principal_route(email: str = Query(...), display_name: str = Query(...)):
    try:
        return seed_principal(db, email=email, display_name=display_name)
    except Exception as exc:
        logger.error("Create principal route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/oidc/providers")
def create_oidc_provider_route(
    organization_id: str,
    provider_key: str = Query(...),
    issuer: str = Query(...),
    discovery_url: str = Query(...),
    client_id: str = Query(...),
    client_secret: str = Query(...),
    scopes: str = Query("openid,email,profile"),
):
    try:
        if not db.fetch_organization(organization_id):
            raise HTTPException(status_code=404, detail="Organization not found")
        return db.upsert_oidc_provider(
            {
                "provider_id": f"op_{provider_key}_{organization_id}",
                "organization_id": organization_id,
                "provider_key": provider_key,
                "issuer": issuer,
                "discovery_url": discovery_url,
                "client_id": client_id,
                "client_secret_encrypted": client_secret,
                "scopes_json": [item.strip() for item in scopes.split(",") if item.strip()],
                "enabled": 1,
                "created_at": _utc_timestamp(),
                "updated_at": _utc_timestamp(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Create OIDC provider route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/organizations/{organization_id}/domains")
def create_organization_domain_route(
    organization_id: str,
    domain: str = Query(...),
    join_mode: str = Query("invite_only"),
):
    try:
        if not db.fetch_organization(organization_id):
            raise HTTPException(status_code=404, detail="Organization not found")
        return db.upsert_organization_domain(
            {
                "domain_id": f"dom_{uuid.uuid4().hex[:12]}",
                "organization_id": organization_id,
                "domain": domain.strip().lower(),
                "verified_at": None,
                "join_mode": join_mode,
                "created_at": _utc_timestamp(),
                "updated_at": _utc_timestamp(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Create organization domain route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/password/set")
def set_password_route(principal_id: str = Query(...), password: str = Query(...)):
    try:
        return set_principal_password(db, principal_id=principal_id, password=password)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Set password route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/login")
def login_route(email: str = Query(...), password: str = Query(...), workspace_id: str = Query(...)):
    try:
        return login_with_password(db, email=email, password=password, workspace_id=workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Login route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/domain-join")
def domain_join_route(
    organization_id: str = Query(...),
    email: str = Query(...),
    display_name: str = Query(...),
    password: str = Query(...),
):
    try:
        return join_organization_by_domain(
            db,
            organization_id=organization_id,
            email=email,
            display_name=display_name,
            password=password,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Domain join route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/oidc/start")
def start_oidc_login_route(
    organization_id: str = Query(...),
    provider_key: str = Query(...),
    redirect_uri: str = Query(...),
):
    try:
        provider = db.fetch_oidc_provider_by_key(organization_id, provider_key)
        if not provider or not provider.get("enabled"):
            raise HTTPException(status_code=404, detail="OIDC provider not found")
        state = uuid.uuid4().hex
        nonce = uuid.uuid4().hex
        discovery = _default_oidc_discovery_document(provider)
        return {
            "organization_id": organization_id,
            "provider_key": provider_key,
            "state": state,
            "nonce": nonce,
            "authorization_url": build_authorization_redirect(
                provider=provider,
                discovery=discovery,
                redirect_uri=redirect_uri,
                state=state,
                nonce=nonce,
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Start OIDC login route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/auth/oidc/callback")
def complete_oidc_callback_route(
    organization_id: str = Query(...),
    provider_key: str = Query(...),
    subject: str = Query(...),
    email: str = Query(...),
    email_verified: bool = Query(...),
    display_name: str = Query(...),
    workspace_id: str = Query(...),
    state: str = Query(...),
    expected_state: str = Query(...),
    nonce: str = Query(...),
    expected_nonce: str = Query(...),
):
    try:
        if state != expected_state:
            raise HTTPException(status_code=401, detail="Invalid OIDC state")
        if nonce != expected_nonce:
            raise HTTPException(status_code=401, detail="Invalid OIDC nonce")

        provider = db.fetch_oidc_provider_by_key(organization_id, provider_key)
        if not provider or not provider.get("enabled"):
            raise HTTPException(status_code=404, detail="OIDC provider not found")

        workspace = db.fetch_workspace(workspace_id)
        if not workspace or workspace["organization_id"] != organization_id:
            raise HTTPException(status_code=403, detail="Workspace mismatch")

        domain = email.split("@", 1)[-1].strip().lower()
        domain_record = db.fetch_organization_domain_by_name(domain)
        if not domain_record or domain_record["organization_id"] != organization_id:
            raise HTTPException(status_code=403, detail="Organization domain mismatch")

        resolved = resolve_principal_for_oidc_claims(
            db,
            provider_key=provider_key,
            subject=subject,
            email=email.strip().lower(),
            email_verified=email_verified,
            display_name=display_name,
        )
        org_membership, _, _ = ensure_organization_membership_from_domain_policy(
            db,
            organization_id=organization_id,
            principal_id=resolved["principal"]["principal_id"],
            email=email.strip().lower(),
        )
        membership = db.fetch_workspace_membership(workspace_id, resolved["principal"]["principal_id"])
        if membership is None:
            raise HTTPException(status_code=403, detail="Workspace access denied")

        session = issue_oidc_session(
            db,
            principal_id=resolved["principal"]["principal_id"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            auth_identity_id=resolved["auth_identity"]["auth_identity_id"],
            auth_method="oidc",
        )
        return {
            "principal": resolved["principal"],
            "auth_identity": resolved["auth_identity"],
            "organization_membership": org_membership,
            "session": session,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Complete OIDC callback route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/auth/session")
def get_session_route(x_session_token: Optional[str] = Header(None, alias="X-Session-Token")):
    try:
        return _require_session_actor(x_session_token)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get session route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/refresh")
def refresh_session_route(x_session_token: Optional[str] = Header(None, alias="X-Session-Token")):
    try:
        return refresh_session_access_token(db, x_session_token)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Refresh session route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/logout")
def logout_route(x_session_token: Optional[str] = Header(None, alias="X-Session-Token")):
    try:
        logout_session(db, x_session_token)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Logout route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/workspaces")
def create_workspace_route(organization_id: str = Query(...), name: str = Query(...)):
    try:
        return seed_workspace(db, organization_id=organization_id, name=name)
    except Exception as exc:
        logger.error("Create workspace route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/workspaces")
def list_workspaces_route(organization_id: Optional[str] = Query(None)):
    try:
        return {"items": db.list_workspaces(organization_id=organization_id)}
    except Exception as exc:
        logger.error("List workspaces route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/workspaces/{workspace_id}/members")
def add_workspace_member_route(workspace_id: str, principal_id: str = Query(...), role: str = Query(...)):
    try:
        return seed_workspace_membership(db, workspace_id=workspace_id, principal_id=principal_id, role=role)
    except Exception as exc:
        logger.error("Add workspace member route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/workspaces/{workspace_id}/members")
def list_workspace_members_route(workspace_id: str, x_access_token: Optional[str] = Header(None, alias="X-Access-Token")):
    try:
        actor = _require_workspace_actor(x_access_token)
        if actor["workspace"]["workspace_id"] != workspace_id:
            raise HTTPException(status_code=403, detail="Workspace mismatch")
        check_workspace_permission(actor, "member_manage")
        return {"items": db.list_workspace_memberships(workspace_id)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List workspace members route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/workspaces/{workspace_id}/invites")
def create_workspace_invite_route(
    workspace_id: str,
    email: str = Query(...),
    role: str = Query(...),
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token"),
):
    try:
        actor = _require_workspace_actor(x_access_token)
        return create_workspace_invite(db, actor=actor, workspace_id=workspace_id, email=email, role=role)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Create workspace invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/invites/{invite_id}/revoke")
def revoke_workspace_invite_route(invite_id: str, x_access_token: Optional[str] = Header(None, alias="X-Access-Token")):
    try:
        actor = _require_workspace_actor(x_access_token)
        return revoke_workspace_invite(db, actor=actor, invite_id=invite_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Revoke workspace invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/invites/accept")
def accept_workspace_invite_route(
    invite_token: str = Query(...),
    display_name: str = Query(...),
    password: str = Query(...),
):
    try:
        return accept_workspace_invite(db, invite_token=invite_token, display_name=display_name, password=password)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Accept workspace invite route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/access-tokens")
def create_access_token_route(principal_id: str = Query(...), workspace_id: str = Query(...)):
    try:
        return issue_access_token(db, principal_id=principal_id, workspace_id=workspace_id)
    except Exception as exc:
        logger.error("Create access token route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/workspaces/{workspace_id}/export-permission")
def get_workspace_export_permission_route(workspace_id: str, x_access_token: Optional[str] = Header(None, alias="X-Access-Token")):
    try:
        actor = _require_workspace_actor(x_access_token)
        if actor["workspace"]["workspace_id"] != workspace_id:
            raise HTTPException(status_code=403, detail="Workspace mismatch")
        allowed = "export" in set()
        try:
            check_workspace_permission(actor, "export")
            allowed = True
        except HTTPException:
            allowed = False
        return {
            "workspace_id": workspace_id,
            "principal_id": actor["principal"]["principal_id"],
            "role": actor["membership"]["role"],
            "allowed": allowed,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get export permission route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/audit-logs")
def list_audit_logs_route(
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token"),
    workspace_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        actor = _require_workspace_actor(x_access_token)
        check_workspace_permission(actor, "read_audit")
        scoped_workspace_id = workspace_id or actor["workspace"]["workspace_id"]
        if scoped_workspace_id != actor["workspace"]["workspace_id"]:
            raise HTTPException(status_code=403, detail="Workspace mismatch")
        return {"items": db.fetch_audit_logs(workspace_id=scoped_workspace_id, limit=limit)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("List audit logs route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin/external-api/billing-summary", response_model=LooseObjectPayload)
def get_external_api_billing_summary_route(
    client_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return {
            **build_external_api_billing_summary(db, client_id=client_id, limit=limit),
            "ledger": build_external_api_billing_ledger(db, client_id=client_id, limit=limit),
        }
    except Exception as exc:
        logger.error("External API billing summary route error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/status", responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_status(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    trace_id = _build_request_trace_id("/api/v1/status")
    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/status",
        http_method="GET",
        request_units=1,
        handler=lambda client: wrap_external_response(
            endpoint="status",
            data=build_external_sla_status(db, api_version="v1"),
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        ),
    )


@app.get("/api/v1/prices", responses=EXTERNAL_API_ERROR_RESPONSES)
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
    trace_id = _build_request_trace_id("/api/v1/prices")
    def handler(client):
        _assert_workspace_scope(client, region=region, market="NEM" if region != "WEM" else "WEM")
        payload = get_price_trend(year=year, region=region, month=month, quarter=quarter, day_type=day_type, limit=5000)
        paged = paginate_items(payload.get("data", []), offset=offset, limit=limit)
        return wrap_external_response(
            endpoint="prices",
            data={
                "market_context": {
                    "region": payload.get("region"),
                    "year": payload.get("year"),
                    "stats": payload.get("stats", {}),
                    "metadata": payload.get("metadata", {}),
                },
                "items": paged["items"],
            },
            api_version="v1",
            pagination=paged["pagination"],
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
                "lineage": {
                    "source_version": payload.get("metadata", {}).get("source_version"),
                    "methodology_version": payload.get("metadata", {}).get("methodology_version"),
                },
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/prices",
        http_method="GET",
        request_units=max(1, limit // 50 or 1),
        handler=handler,
    )


@app.get("/api/v1/events", responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_events(
    year: int = Query(...),
    region: str = Query(...),
    market: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    day_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    trace_id = _build_request_trace_id("/api/v1/events")
    def handler(client):
        inferred_market = market or ("WEM" if region == "WEM" else "NEM")
        _assert_workspace_scope(client, region=region, market=inferred_market)
        payload = get_event_overlays(year=year, region=region, market=market, month=month, quarter=quarter, day_type=day_type)
        paged = paginate_items(payload.get("events", []), offset=offset, limit=limit)
        return wrap_external_response(
            endpoint="events",
            data={
                "items": paged["items"],
                "states": payload.get("states", []),
                "metadata": payload.get("metadata", {}),
            },
            api_version="v1",
            pagination=paged["pagination"],
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
                "lineage": {
                    "source_version": payload.get("metadata", {}).get("source_version"),
                    "methodology_version": payload.get("metadata", {}).get("methodology_version"),
                },
            },
        )

    return _metered_v1_call(x_api_key=x_api_key, endpoint="/api/v1/events", http_method="GET", request_units=max(1, limit // 50 or 1), handler=handler)


@app.get("/api/v1/fcas", responses=EXTERNAL_API_ERROR_RESPONSES)
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
    trace_id = _build_request_trace_id("/api/v1/fcas")
    def handler(client):
        _assert_workspace_scope(client, region=region, market="NEM" if region != "WEM" else "WEM")
        payload = get_fcas_analysis(year=year, region=region, aggregation=aggregation, capacity_mw=capacity_mw, month=month, quarter=quarter, day_type=day_type)
        paged = paginate_items(payload.get("data", []), offset=offset, limit=limit)
        return wrap_external_response(
            endpoint="fcas",
            data={
                "summary": {k: v for k, v in payload.items() if k != "data"},
                "items": paged["items"],
            },
            api_version="v1",
            pagination=paged["pagination"],
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
                "lineage": {
                    "source_version": payload.get("metadata", {}).get("source_version"),
                    "methodology_version": payload.get("metadata", {}).get("methodology_version"),
                },
            },
        )

    return _metered_v1_call(x_api_key=x_api_key, endpoint="/api/v1/fcas", http_method="GET", request_units=max(1, limit // 50 or 1), handler=handler)


@app.post("/api/v1/bess/backtests", responses=EXTERNAL_API_ERROR_RESPONSES)
def run_v1_bess_backtest(params: BessBacktestParams, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    trace_id = _build_request_trace_id("/api/v1/bess/backtests")
    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/bess/backtests",
        http_method="POST",
        request_units=5,
        handler=lambda client: wrap_external_response(
            endpoint="bess/backtests",
            data=run_bess_backtest(params),
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        ),
    )


@app.post("/api/v1/investment/scenarios", responses=EXTERNAL_API_ERROR_RESPONSES)
def run_v1_investment_scenarios(params: InvestmentParams, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    trace_id = _build_request_trace_id("/api/v1/investment/scenarios")
    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/investment/scenarios",
        http_method="POST",
        request_units=8,
        handler=lambda client: wrap_external_response(
            endpoint="investment/scenarios",
            data=investment_analysis(params),
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        ),
    )


@app.get("/api/v1/developer/portal", response_model=LooseObjectPayload, responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_developer_portal(
    ledger_limit: int = Query(20, ge=1, le=200),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    trace_id = _build_request_trace_id("/api/v1/developer/portal")
    ledger_limit = _cacheable_param(ledger_limit) or 20

    def handler(client):
        quota = summarize_external_api_quota(db, client=client)
        billing = build_external_api_billing_summary(
            db,
            client_id=client["client_id"],
            limit=max(10, ledger_limit),
        )
        ledger = build_external_api_billing_ledger(
            db,
            client_id=client["client_id"],
            limit=ledger_limit,
        )
        return wrap_external_response(
            endpoint="developer/portal",
            data={
                "client": {
                    "client_id": client["client_id"],
                    "client_name": client.get("client_name"),
                    "plan": client.get("plan"),
                    "organization_id": client.get("organization_id"),
                    "workspace_id": client.get("workspace_id"),
                    "enabled": client.get("enabled"),
                    "created_at": client.get("created_at"),
                    "updated_at": client.get("updated_at"),
                },
                "quota": quota,
                "billing": billing,
                "ledger": ledger,
            },
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/developer/portal",
        http_method="GET",
        request_units=1,
        handler=handler,
    )


@app.get("/api/v1/data-quality", responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_data_quality(
    market: Optional[str] = Query(None),
    issue_offset: int = Query(0, ge=0),
    issue_limit: int = Query(100, ge=1, le=500),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    trace_id = _build_request_trace_id("/api/v1/data-quality")
    def handler(client):
        _assert_workspace_scope(client, market=market)
        summary = get_data_quality_summary()
        markets = get_data_quality_markets()
        issues = get_data_quality_issues(market=market)
        paged = paginate_items(issues.get("items", []), offset=issue_offset, limit=issue_limit)
        return wrap_external_response(
            endpoint="data-quality",
            data={
                "summary": summary,
                "markets": markets.get("items", []),
                "issues": paged["items"],
            },
            api_version="v1",
            pagination=paged["pagination"],
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/data-quality",
        http_method="GET",
        request_units=max(1, issue_limit // 50 or 1),
        handler=handler,
    )


@app.get("/api/v1/jobs/{job_id}", responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_job(job_id: str, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    trace_id = _build_request_trace_id("/api/v1/jobs")

    def handler(client):
        job = db.fetch_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        client_workspace_id = client.get("workspace_id")
        job_workspace_id = job.get("workspace_id")
        if client_workspace_id and job_workspace_id and client_workspace_id != job_workspace_id:
            raise HTTPException(status_code=403, detail="Workspace access denied")
        return wrap_external_response(
            endpoint="jobs",
            data={"job": job},
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/jobs",
        http_method="GET",
        request_units=1,
        handler=handler,
    )


@app.get("/api/v1/jobs", responses=EXTERNAL_API_ERROR_RESPONSES)
def list_v1_jobs(
    status: Optional[str] = Query(None),
    queue_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    trace_id = _build_request_trace_id("/api/v1/jobs.list")
    status = _cacheable_param(status)
    queue_name = _cacheable_param(queue_name)
    limit = _cacheable_param(limit) or 100

    def handler(client):
        items = db.list_jobs(status=status, queue_name=queue_name, limit=limit)
        client_workspace_id = client.get("workspace_id")
        if client_workspace_id:
            items = [item for item in items if item.get("workspace_id") in {None, client_workspace_id}]
        return wrap_external_response(
            endpoint="jobs",
            data={"items": items},
            api_version="v1",
            pagination={"limit": limit, "returned": len(items)},
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/jobs",
        http_method="GET",
        request_units=1,
        handler=handler,
    )


@app.get("/api/v1/jobs/{job_id}/lineage", responses=EXTERNAL_API_ERROR_RESPONSES)
def get_v1_job_lineage(job_id: str, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    trace_id = _build_request_trace_id("/api/v1/jobs.lineage")

    def handler(client):
        lineage = build_job_lineage_payload(db, job_id)
        client_workspace_id = client.get("workspace_id")
        job_workspace_id = lineage["job"].get("workspace_id")
        if client_workspace_id and job_workspace_id and client_workspace_id != job_workspace_id:
            raise HTTPException(status_code=403, detail="Workspace access denied")
        return wrap_external_response(
            endpoint="jobs/lineage",
            data=lineage,
            api_version="v1",
            meta={
                "client_id": client["client_id"],
                "plan": client["plan"],
                "organization_id": client.get("organization_id"),
                "workspace_id": client.get("workspace_id"),
                "trace_id": trace_id,
            },
        )

    return _metered_v1_call(
        x_api_key=x_api_key,
        endpoint="/api/v1/jobs/lineage",
        http_method="GET",
        request_units=1,
        handler=handler,
    )


@app.get(
    "/api/event-overlays",
    summary="Get event overlay explanations",
    description="Returns normalized event/state overlays for the requested market window. Response metadata includes the standard contract fields plus overlay-specific fields such as coverage_quality and time_granularity.",
    responses=OPENAPI_ERROR_RESPONSES,
)
def get_event_overlays(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, WEM)"),
    market: Optional[str] = Query(None, description="Optional market override: NEM or WEM"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(
                access_scope,
                region=region,
                market=grid_events.infer_market(region, market),
            )
        market = _cacheable_param(market)
        month = _cacheable_param(month)
        quarter = _cacheable_param(quarter)
        day_type = _cacheable_param(day_type)
        cache_payload = {
            "year": year,
            "region": region,
            "market": market,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "data_version": _event_overlay_data_version(),
        }
        cached = _fetch_response_cache(EVENT_OVERLAY_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return _attach_event_overlay_metadata(cached, region=region, data_version=cache_payload["data_version"])

        response = grid_events.get_event_overlay_response(
            db,
            year=year,
            region=region,
            market=market,
            month=month,
            quarter=quarter,
            day_type=day_type,
        )
        response = _attach_event_overlay_metadata(response, region=region, data_version=cache_payload["data_version"])
        return _store_response_cache(
            EVENT_OVERLAY_RESPONSE_CACHE_SCOPE,
            cache_payload,
            response,
            EVENT_OVERLAY_CACHE_TTL_SECONDS,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Event overlay error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/grid-forecast",
    summary="Get grid forecast view",
    description="Returns grid forecast windows, drivers, coverage context, and unified metadata. The metadata contract is standardised while preserving forecast-specific fields such as forecast_mode and coverage_quality.",
    responses=OPENAPI_ERROR_RESPONSES,
)
def get_grid_forecast(
    market: str = Query(..., description="Market code: NEM or WEM"),
    region: str = Query(..., description="Region code such as NSW1 or WEM"),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$", description="Forecast horizon"),
    as_of: Optional[str] = Query(None, description="Optional forecast issue timestamp"),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, region=region, market=market)
        market = _cacheable_param(market)
        region = _cacheable_param(region)
        horizon = _cacheable_param(horizon)
        as_of = _cacheable_param(as_of)
        cache_payload = {
            "market": market,
            "region": region,
            "horizon": horizon,
            "as_of_bucket": grid_forecast.build_as_of_bucket(as_of, horizon),
            "data_version": _grid_forecast_data_version(),
        }
        cached = _fetch_response_cache(GRID_FORECAST_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return _attach_grid_forecast_metadata(cached, region=region, data_version=cache_payload["data_version"])

        response = grid_forecast.get_grid_forecast_response(
            db,
            market=market,
            region=region,
            horizon=horizon,
            as_of=as_of,
        )
        response = _attach_grid_forecast_metadata(response, region=region, data_version=cache_payload["data_version"])
        return _store_response_cache(
            GRID_FORECAST_RESPONSE_CACHE_SCOPE,
            cache_payload,
            response,
            GRID_FORECAST_CACHE_TTL_SECONDS.get(horizon, DEFAULT_RESPONSE_CACHE_TTL_SECONDS),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Grid forecast error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/grid-forecast/coverage", response_model=LooseObjectPayload)
def get_grid_forecast_coverage(
    market: str = Query(..., description="Market code: NEM or WEM"),
    region: str = Query(..., description="Region code such as NSW1 or WEM"),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$", description="Forecast horizon"),
    as_of: Optional[str] = Query(None, description="Optional forecast issue timestamp"),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, region=region, market=market)
        return grid_forecast.get_grid_forecast_coverage(
            db,
            market=market,
            region=region,
            horizon=horizon,
            as_of=as_of,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Grid forecast coverage error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def run_sync_scrapers(lock_pre_acquired: bool = False):
    """Background task to run scrapers and update the database."""
    lock_acquired = lock_pre_acquired
    try:
        if not lock_acquired:
            lock_acquired = _try_acquire_job_lock(MARKET_SYNC_LOCK_NAME, MARKET_SYNC_LOCK_TTL_SECONDS)
            if not lock_acquired:
                logger.info("Skipping market sync because another market sync is already running.")
                return {"status": "skipped", "reason": "already_running"}

        logger.info("Starting Background Data Syncing Tasks...")
        # WEM and NEM Sync: Incremental (Last 14 days)
        now_local = _scheduler_now()
        two_weeks_ago = (now_local - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
        today = now_local.strftime('%Y-%m-%d')
        
        logger.info(f"Running WEM Scraper from {two_weeks_ago} to {today}...")
        _run_scraper("aemo_wem_scraper.py", "--start", two_weeks_ago, "--end", today, "--db", DB_PATH)

        logger.info("Running WEM ESS slim sync for latest 30 days...")
        _run_scraper("aemo_wem_ess_scraper.py", "--days", "30", "--db", DB_PATH)
        
        logger.info("Running NEM Scraper...")
        start_month = (now_local - datetime.timedelta(days=14)).strftime('%Y-%m')
        end_month = now_local.strftime('%Y-%m')
        _run_scraper(
            "aemo_nem_scraper.py",
            "--start",
            start_month,
            "--end",
            end_month,
            "--db-path",
            DB_PATH,
            "--fcas",
        )

        logger.info("Running Grid Event Scraper...")
        _run_scraper("aemo_grid_event_scraper.py", "--days", "180", "--db", DB_PATH)

        
        # Record Success Time
        db.set_last_update_time(now_local.strftime('%Y-%m-%d %H:%M:%S'))
        logger.info("Data Syncing Completed successfully!")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error in data sync task: {e}")
        return {"status": "error", "detail": str(e)}
    finally:
        if lock_acquired:
            _release_job_lock(MARKET_SYNC_LOCK_NAME)


def _fingrid_sync_enabled() -> bool:
    return bool(os.environ.get("FINGRID_API_KEY"))


def run_fingrid_dataset_sync(dataset_id: str, mode: str = "incremental", lock_pre_acquired: bool = False):
    if not _fingrid_sync_enabled():
        logger.info("Skipping Fingrid dataset sync because FINGRID_API_KEY is not configured.")
        return {"status": "skipped", "reason": "missing_api_key", "dataset_id": dataset_id}

    lock_acquired = lock_pre_acquired
    if not lock_acquired:
        lock_acquired = _try_acquire_job_lock(FINGRID_SYNC_LOCK_NAME, FINGRID_SYNC_LOCK_TTL_SECONDS)
        if not lock_acquired:
            logger.info("Skipping Fingrid dataset sync because another Fingrid sync is already running.")
            return {"status": "skipped", "reason": "already_running", "dataset_id": dataset_id}

    try:
        return fingrid_service.sync_dataset(db, dataset_id=dataset_id, mode=mode)
    except Exception as e:
        logger.error("Error in Fingrid dataset sync task for dataset %s (%s): %s", dataset_id, mode, e)
        return {"status": "error", "dataset_id": dataset_id, "mode": mode, "detail": str(e)}
    finally:
        if lock_acquired:
            _release_job_lock(FINGRID_SYNC_LOCK_NAME)


def run_fingrid_hourly_sync(lock_pre_acquired: bool = False):
    """Background task to incrementally sync Fingrid datasets once per hour."""
    if not _fingrid_sync_enabled():
        logger.info("Skipping Fingrid hourly sync because FINGRID_API_KEY is not configured.")
        return {"status": "skipped", "reason": "missing_api_key", "datasets_synced": 0}

    lock_acquired = lock_pre_acquired
    if not lock_acquired:
        lock_acquired = _try_acquire_job_lock(FINGRID_SYNC_LOCK_NAME, FINGRID_SYNC_LOCK_TTL_SECONDS)
        if not lock_acquired:
            logger.info("Skipping Fingrid hourly sync because another Fingrid sync is already running.")
            return {"status": "skipped", "reason": "already_running", "datasets_synced": 0}

    try:
        logger.info("Starting Fingrid hourly incremental sync...")
        results = []
        failures = []
        for dataset in fingrid_catalog.list_dataset_configs():
            dataset_id = dataset["dataset_id"]
            try:
                results.append(fingrid_service.sync_dataset(db, dataset_id=dataset_id, mode="incremental"))
            except Exception as e:
                logger.error("Error syncing Fingrid dataset %s during hourly sync: %s", dataset_id, e)
                failures.append({"dataset_id": dataset_id, "detail": str(e)})
        if failures:
            return {
                "status": "error",
                "datasets_synced": len(results),
                "datasets_failed": len(failures),
                "results": results,
                "failures": failures,
                "detail": "; ".join(f"{item['dataset_id']}: {item['detail']}" for item in failures),
            }
        logger.info("Completed Fingrid hourly incremental sync.")
        return {"status": "ok", "datasets_synced": len(results), "results": results}
    except Exception as e:
        logger.error(f"Error in Fingrid hourly sync task: {e}")
        return {"status": "error", "datasets_synced": 0, "detail": str(e)}
    finally:
        if lock_acquired:
            _release_job_lock(FINGRID_SYNC_LOCK_NAME)

@app.post("/api/sync_data", response_model=AcceptedJobActionPayload)
def sync_data(background_tasks: BackgroundTasks = None):
    """Trigger data scrape via the managed job queue."""
    if background_tasks is not None:
        lock_acquired = _try_acquire_job_lock(MARKET_SYNC_LOCK_NAME, MARKET_SYNC_LOCK_TTL_SECONDS)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="A market sync is already in progress")
        background_tasks.add_task(run_sync_scrapers, True)
        return {"status": "accepted", "detail": "Update started in background"}
    job = enqueue_market_sync_job(manual=True)
    return {"status": "accepted", "detail": "Update queued", "job_id": job["job_id"]}


@app.get("/api/fingrid/datasets", response_model=FingridDatasetCatalogPayload)
def get_fingrid_datasets():
    fingrid_service.seed_dataset_catalog(db)
    return {"datasets": fingrid_catalog.list_dataset_configs()}


@app.get(
    "/api/finland/market-model",
    summary="Get Finland market model context",
    description="Returns the current Finland market model source composition. The payload makes Finland explicit as a multi-source market model rather than a single Fingrid dataset view.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
    response_model=LooseObjectPayload,
)
def get_finland_market_model():
    fingrid_service.seed_dataset_catalog(db)
    return build_finland_market_model_payload(db)


@app.get(
    "/api/fingrid/datasets/{dataset_id}/status",
    summary="Get Fingrid dataset status",
    description="Returns the current Fingrid dataset status snapshot with unified metadata fields, including methodology_version and source_version.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_fingrid_dataset_status(dataset_id: str, access_scope: Optional[dict] = None):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, market="FINGRID")
        payload = fingrid_service.get_dataset_status_payload(db, dataset_id=dataset_id)
        return _attach_fingrid_metadata(payload, dataset_id)
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.post("/api/fingrid/datasets/{dataset_id}/sync")
def sync_fingrid_dataset(
    dataset_id: str,
    background_tasks: BackgroundTasks = None,
    mode: str = Query("incremental"),
):
    try:
        fingrid_catalog.get_dataset_config(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")

    if not _fingrid_sync_enabled():
        raise HTTPException(status_code=503, detail="FINGRID_API_KEY is not configured")

    if background_tasks is not None:
        lock_acquired = _try_acquire_job_lock(FINGRID_SYNC_LOCK_NAME, FINGRID_SYNC_LOCK_TTL_SECONDS)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="A Fingrid sync is already in progress")
        background_tasks.add_task(run_fingrid_dataset_sync, dataset_id, mode, True)
        return {"status": "accepted", "dataset_id": dataset_id, "mode": mode}

    job = enqueue_fingrid_dataset_sync_job(dataset_id=dataset_id, mode=mode)
    return {"status": "accepted", "dataset_id": dataset_id, "mode": mode, "job_id": job["job_id"]}


@app.get("/api/fingrid/datasets/{dataset_id}/series")
def get_fingrid_dataset_series(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tz: str = Query("Europe/Helsinki"),
    aggregation: str = Query("raw", pattern="^(raw|hour|1h|2h|4h|day|week|month)$"),
    limit: Optional[int] = Query(None),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, market="FINGRID")
        return fingrid_service.get_dataset_series_payload(
            db,
            dataset_id=dataset_id,
            start=start,
            end=end,
            aggregation=aggregation,
            tz=tz,
            limit=limit,
        )
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.get("/api/fingrid/datasets/{dataset_id}/summary")
def get_fingrid_dataset_summary(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, market="FINGRID")
        return fingrid_service.get_dataset_summary_payload(db, dataset_id=dataset_id, start=start, end=end)
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.get("/api/fingrid/datasets/{dataset_id}/export")
def export_fingrid_dataset_csv(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tz: str = Query("Europe/Helsinki"),
    aggregation: str = Query("raw", pattern="^(raw|hour|1h|2h|4h|day|week|month)$"),
    limit: Optional[int] = Query(None),
    access_scope: Optional[dict] = None,
):
    if access_scope:
        _assert_scope_allows_internal_query(access_scope, market="FINGRID")
    payload = fingrid_service.get_dataset_series_payload(
        db,
        dataset_id=dataset_id,
        start=start,
        end=end,
        aggregation=aggregation,
        tz=tz,
        limit=limit,
    )
    csv_text = build_fingrid_csv(payload["series"])
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="fingrid-{dataset_id}.csv"'},
    )


def _build_temporal_filters(
    year: int,
    month: Optional[str],
    quarter: Optional[str],
    day_type: Optional[str],
    *,
    time_field: str = "settlement_date",
    region: Optional[str] = None,
    region_field: Optional[str] = "region_id",
    force_year_prefix: bool = False,
):
    if not isinstance(month, str):
        month = None
    if not isinstance(quarter, str):
        quarter = None
    if not isinstance(day_type, str):
        day_type = None

    clauses = []
    params = []

    if region_field and region is not None:
        clauses.append(f"{region_field} = ?")
        params.append(region)

    if month and len(month) == 2:
        clauses.append(f"{time_field} LIKE ?")
        params.append(f"{year}-{month}-%")
    elif quarter in ["Q1", "Q2", "Q3", "Q4"]:
        q_map = {
            "Q1": ("01", "02", "03"),
            "Q2": ("04", "05", "06"),
            "Q3": ("07", "08", "09"),
            "Q4": ("10", "11", "12"),
        }
        q_values = ", ".join(f"'{value}'" for value in q_map[quarter])
        clauses.append(f"substr({time_field}, 6, 2) IN ({q_values})")
        if force_year_prefix:
            clauses.append(f"{time_field} LIKE ?")
            params.append(f"{year}-%")
    elif force_year_prefix:
        clauses.append(f"{time_field} LIKE ?")
        params.append(f"{year}-%")

    if day_type == "WEEKDAY":
        clauses.append(
            f"CAST(strftime('%w', substr({time_field}, 1, 19)) AS INTEGER) IN (1, 2, 3, 4, 5)"
        )
    elif day_type == "WEEKEND":
        clauses.append(
            f"CAST(strftime('%w', substr({time_field}, 1, 19)) AS INTEGER) IN (0, 6)"
        )

    return " AND ".join(clauses) if clauses else "1=1", params


@app.get("/api/years", response_model=AvailableYearsPayload)
def get_available_years():
    """Returns a list of years for which data tables exist"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'")
            tables = [r[0] for r in cursor.fetchall()]
            years = sorted([int(t.split('_')[-1]) for t in tables], reverse=True)
            return {"years": years}
    except Exception as e:
        logger.error(f"Error fetching years: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/price-trend",
    summary="Get price trend analysis",
    description="Returns historical price series, aggregate statistics, and unified metadata. The metadata object is the response contract anchor for market, timezone, unit, freshness, source_version, and methodology_version.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_price_trend(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1, QLD1)"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    limit: Optional[int] = Query(1500, description="Max points to return to avoid overwhelming frontend."),
    access_scope: Optional[dict] = None,
):
    """
    Returns time series data with dynamic sampling to handle large arrays.
    """
    if access_scope:
        _assert_scope_allows_internal_query(
            access_scope,
            region=region,
            market="WEM" if region == "WEM" else "NEM",
        )
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    limit = _cacheable_param(limit)
    table_name = f"trading_price_{year}"
    try:
        cache_payload = {
            "year": year,
            "region": region,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "limit": limit,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(PRICE_TREND_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return _attach_price_trend_metadata(cached, region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data available for year {year}")

            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )

            # Get total count for the region and applied filters
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", tuple(params))
            total_rows = cursor.fetchone()[0]
            
            if total_rows == 0:
                response = {
                    "region": region, "year": year, "month": month, "total_points": 0, "returned_points": 0,
                    "stats": {"min": 0, "max": 0, "avg": 0},
                    "advanced_stats": {"neg_ratio": 0, "neg_avg": 0, "neg_min": 0, "pos_avg": 0, "pos_max": 0, "days_below_100": 0, "days_above_300": 0},
                    "hourly_distribution": [], "data": []
                }
                response = _attach_price_trend_metadata(response, region=region)
                return _store_response_cache(
                    PRICE_TREND_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # Fetch the time-series data
            query_data = f"""
                SELECT settlement_date, rrp_aud_mwh
                FROM {table_name}
                WHERE {where_clause}
                ORDER BY settlement_date ASC
            """
            
            cursor.execute(query_data, tuple(params))
            rows = cursor.fetchall()
            
            data = _downsample_price_rows(rows, limit)
            
            # Calculate all statistics in a single highly optimized SQL query
            # This turns 6 separate full table scans into just 1
            stats_query = f"""
                SELECT 
                    MIN(rrp_aud_mwh) as overall_min,
                    MAX(rrp_aud_mwh) as overall_max,
                    AVG(rrp_aud_mwh) as overall_avg,
                    SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count,
                    AVG(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END) as neg_avg,
                    MIN(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END) as neg_min,
                    AVG(CASE WHEN rrp_aud_mwh > 0 THEN rrp_aud_mwh ELSE NULL END) as pos_avg,
                    MAX(CASE WHEN rrp_aud_mwh > 0 THEN rrp_aud_mwh ELSE NULL END) as pos_max,
                    COUNT(DISTINCT CASE WHEN rrp_aud_mwh < -100 THEN substr(settlement_date, 1, 10) ELSE NULL END) as days_below_100,
                    COUNT(DISTINCT CASE WHEN rrp_aud_mwh > 300 THEN substr(settlement_date, 1, 10) ELSE NULL END) as days_above_300
                FROM {table_name}
                WHERE {where_clause}
            """
            cursor.execute(stats_query, tuple(params))
            aggs = cursor.fetchone()
            
            o_min, o_max, o_avg = aggs[0], aggs[1], aggs[2]
            neg_count = aggs[3] if aggs[3] else 0
            neg_avg = aggs[4] 
            neg_min = aggs[5] 
            pos_avg = aggs[6] 
            pos_max = aggs[7] 
            days_below_100 = aggs[8] if aggs[8] else 0
            days_above_300 = aggs[9] if aggs[9] else 0
            
            neg_ratio = round((neg_count / total_rows) * 100, 2) if total_rows > 0 else 0

            # Hourly Distribution of Negative Prices (requires GROUP BY so kept separate, but relatively fast)
            hourly_query = f"""
                SELECT 
                    substr(datetime(settlement_date, '-1 second'), 12, 2) as hour_bucket,
                    COUNT(*)
                FROM {table_name}
                WHERE {where_clause} AND rrp_aud_mwh < 0
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, tuple(params))
            hourly_rows = cursor.fetchall()
            
            # Pad with 0s for missing hours
            hourly_dict = {r[0]: r[1] for r in hourly_rows}
            hourly_distribution = []
            for h in range(24):
                hr_str = f"{h:02d}"
                hourly_distribution.append({
                    "hour": hr_str,
                    "count": hourly_dict.get(hr_str, 0)
                })
            
            response = {
                "region": region,
                "year": year,
                "month": month,
                "total_points": total_rows,
                "returned_points": len(data),
                "stats": {
                    "min": round(o_min, 2) if o_min is not None else 0,
                    "max": round(o_max, 2) if o_max is not None else 0,
                    "avg": round(o_avg, 2) if o_avg is not None else 0,
                },
                "advanced_stats": {
                    "neg_ratio": neg_ratio,
                    "neg_avg": round(neg_avg, 2) if neg_avg is not None else None,
                    "neg_min": round(neg_min, 2) if neg_min is not None else None,
                    "pos_avg": round(pos_avg, 2) if pos_avg is not None else None,
                    "pos_max": round(pos_max, 2) if pos_max is not None else None,
                    "days_below_100": days_below_100,
                    "days_above_300": days_above_300
                },
                "hourly_distribution": hourly_distribution,
                "data": data
            }
            response = _attach_price_trend_metadata(response, region=region)
            return _store_response_cache(
                PRICE_TREND_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.error(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/network-fees", response_model=NetworkFeesPayload)
def get_network_fees():
    """Returns default network fees (TUOS+DUOS) for all regions."""
    return {"fees": get_all_fees()}


@app.get(
    "/api/peak-analysis",
    summary="Get peak and trough spread analysis",
    description="Returns sliding-window peak/trough spread analysis with unified metadata. Consumers should read metadata for timezone, interval_minutes, currency, source_version, and methodology_version.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_peak_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    aggregation: str = Query("monthly", description="Aggregation: daily, weekly, monthly, yearly"),
    network_fee: Optional[float] = Query(None, description="Override network fee ($/MWh). If omitted, uses default for region."),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    access_scope: Optional[dict] = None,
):
    """
    Sliding-window peak/trough analysis with network fee integration.
    Returns peak/trough averages for 1h/2h/4h/6h windows and spread calculations.
    """
    aggregation = _cacheable_param(aggregation)
    network_fee = _cacheable_param(network_fee)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    table_name = f"trading_price_{year}"
    fee = network_fee if network_fee is not None else get_default_fee(region)
    windows = get_window_sizes(region)

    try:
        if access_scope:
            _assert_scope_allows_internal_query(
                access_scope,
                region=region,
                market="WEM" if region == "WEM" else "NEM",
            )
        cache_payload = {
            "year": year,
            "region": region,
            "aggregation": aggregation,
            "network_fee": network_fee,
            "effective_network_fee": fee,
            "month": month,
            "quarter": quarter,
            "day_type": day_type,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return _attach_peak_analysis_metadata(cached, region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            # Fetch all data for this year+region, ordered by time
            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )
            cursor.execute(
                f"SELECT settlement_date, rrp_aud_mwh FROM {table_name} "
                f"WHERE {where_clause} ORDER BY settlement_date ASC",
                tuple(params),
            )
            rows = cursor.fetchall()

            if not rows:
                response = {
                    "region": region, "year": year, "aggregation": aggregation,
                    "network_fee": fee, "data": [], "summary": {}
                }
                response = _attach_peak_analysis_metadata(response, region=region)
                return _store_response_cache(
                    PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # Group by day: { "2025-01-15": [price1, price2, ...] }
            daily_prices = defaultdict(list)
            for date_str, price in rows:
                day_key = date_str[:10]  # "2025-01-15"
                daily_prices[day_key].append(price)

            # Sliding window analysis for each day
            daily_results = []
            for day, prices in sorted(daily_prices.items()):
                n = len(prices)
                result = {"date": day}

                for label, w_size in windows.items():
                    if n < w_size:
                        # Not enough data points for this window
                        result[f"peak_{label}"] = None
                        result[f"trough_{label}"] = None
                        continue

                    # Efficient sliding window using running sum
                    window_sum = sum(prices[:w_size])
                    best_max = window_sum
                    best_min = window_sum

                    for i in range(1, n - w_size + 1):
                        window_sum += prices[i + w_size - 1] - prices[i - 1]
                        if window_sum > best_max:
                            best_max = window_sum
                        if window_sum < best_min:
                            best_min = window_sum

                    result[f"peak_{label}"] = round(best_max / w_size, 2)
                    result[f"trough_{label}"] = round(best_min / w_size, 2)

                # Calculate spreads for 2h/4h/6h
                for label in ["2h", "4h", "6h"]:
                    peak = result.get(f"peak_{label}")
                    trough = result.get(f"trough_{label}")
                    if peak is not None and trough is not None:
                        spread = round(peak - trough, 2)
                        result[f"spread_{label}"] = spread
                        result[f"net_spread_{label}"] = round(spread - 2 * fee, 2)
                    else:
                        result[f"spread_{label}"] = None
                        result[f"net_spread_{label}"] = None

                daily_results.append(result)

            # Aggregate based on requested granularity
            if aggregation == "daily":
                aggregated = daily_results
            else:
                aggregated = _aggregate_peak_data(daily_results, aggregation)

            # Compute overall summary
            summary = _compute_summary(daily_results)

            response = {
                "region": region,
                "year": year,
                "aggregation": aggregation,
                "network_fee": fee,
                "filters": {
                    "month": month,
                    "quarter": quarter,
                    "day_type": day_type,
                },
                "data": aggregated,
                "summary": summary
            }
            response = _attach_peak_analysis_metadata(response, region=region)
            return _store_response_cache(
                PEAK_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Peak analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _aggregate_peak_data(daily_results: list, aggregation: str) -> list:
    """Aggregate daily peak/trough results by week, month, or year."""
    groups = defaultdict(list)

    for row in daily_results:
        day = row["date"]
        if aggregation == "weekly":
            # ISO week: "2025-W03"
            d = datetime.datetime.strptime(day, "%Y-%m-%d")
            iso_year, iso_week, _ = d.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        elif aggregation == "monthly":
            key = day[:7]  # "2025-01"
        elif aggregation == "yearly":
            key = day[:4]  # "2025"
        else:
            key = day
        groups[key].append(row)

    numeric_fields = [
        "peak_1h", "peak_2h", "peak_4h", "peak_6h",
        "trough_1h", "trough_2h", "trough_4h", "trough_6h",
        "spread_2h", "spread_4h", "spread_6h",
        "net_spread_2h", "net_spread_4h", "net_spread_6h",
    ]

    aggregated = []
    for period, items in sorted(groups.items()):
        entry = {"period": period, "days_count": len(items)}
        for field in numeric_fields:
            values = [item[field] for item in items if item.get(field) is not None]
            entry[field] = round(sum(values) / len(values), 2) if values else None
        aggregated.append(entry)

    return aggregated


def _compute_summary(daily_results: list) -> dict:
    """Compute overall summary stats across all daily results."""
    summary = {}
    for label in ["2h", "4h", "6h"]:
        spreads = [r[f"spread_{label}"] for r in daily_results if r.get(f"spread_{label}") is not None]
        nets = [r[f"net_spread_{label}"] for r in daily_results if r.get(f"net_spread_{label}") is not None]
        summary[f"avg_spread_{label}"] = round(sum(spreads) / len(spreads), 2) if spreads else None
        summary[f"avg_net_spread_{label}"] = round(sum(nets) / len(nets), 2) if nets else None
        summary[f"max_spread_{label}"] = round(max(spreads), 2) if spreads else None
        summary[f"min_spread_{label}"] = round(min(spreads), 2) if spreads else None
    summary["total_days"] = len(daily_results)
    return summary


# ============================================================
# Hourly Price Profile (for Clock Heatmap / Charging Window)
# ============================================================

@app.get(
    "/api/hourly-price-profile",
    summary="Get hourly price profile",
    description="Returns hourly average/min/max price profile data for heatmap-style views, together with unified metadata describing market, unit, freshness, and contract version fields.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_hourly_price_profile(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID"),
    month: Optional[str] = Query(None, description="Optional month filter (01-12)"),
    access_scope: Optional[dict] = None,
):
    """
    Returns average, min, max prices for each hour of the day.
    Used for the Clock Heatmap / Negative Pricing Window visualization.
    """
    month = _cacheable_param(month)
    table_name = f"trading_price_{year}"
    try:
        if access_scope:
            _assert_scope_allows_internal_query(
                access_scope,
                region=region,
                market="WEM" if region == "WEM" else "NEM",
            )
        cache_payload = {
            "year": year,
            "region": region,
            "month": month,
            "data_version": _market_data_version(),
        }
        cached = _fetch_response_cache(HOURLY_PROFILE_RESPONSE_CACHE_SCOPE, cache_payload)
        if cached is not None:
            return _attach_hourly_price_profile_metadata(cached, region=region)

        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            where = "region_id = ?"
            params = [region]
            if month and len(month) == 2:
                where += " AND settlement_date LIKE ?"
                params.append(f"{year}-{month}-%")

            query = f"""
                SELECT
                    CAST(substr(settlement_date, 12, 2) AS INTEGER) as hour,
                    ROUND(AVG(rrp_aud_mwh), 2) as avg_price,
                    ROUND(MIN(rrp_aud_mwh), 2) as min_price,
                    ROUND(MAX(rrp_aud_mwh), 2) as max_price,
                    COUNT(*) as count,
                    SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as neg_count,
                    ROUND(AVG(CASE WHEN rrp_aud_mwh < 0 THEN rrp_aud_mwh ELSE NULL END), 2) as neg_avg
                FROM {table_name}
                WHERE {where}
                GROUP BY hour
                ORDER BY hour ASC
            """
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            hourly = []
            for r in rows:
                total = r[4] if r[4] else 1
                hourly.append({
                    "hour": r[0],
                    "avg_price": r[1],
                    "min_price": r[2],
                    "max_price": r[3],
                    "count": r[4],
                    "neg_pct": round((r[5] / total) * 100, 1) if r[5] else 0,
                    "neg_avg": r[6],
                })

            # Pad missing hours
            hour_map = {h["hour"]: h for h in hourly}
            result = []
            for h in range(24):
                if h in hour_map:
                    result.append(hour_map[h])
                else:
                    result.append({
                        "hour": h, "avg_price": 0, "min_price": 0,
                        "max_price": 0, "count": 0, "neg_pct": 0, "neg_avg": None
                    })

            response = {"region": region, "year": year, "month": month, "hourly": result}
            response = _attach_hourly_price_profile_metadata(response, region=region)
            return _store_response_cache(
                HOURLY_PROFILE_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hourly profile error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================
# FCAS (Frequency Control Ancillary Services) Analysis
# ============================================================

FCAS_SERVICES = {
    "raise1sec": "Raise 1 Sec",
    "raise6sec": "Raise 6 Sec",
    "raise60sec": "Raise 60 Sec",
    "raise5min": "Raise 5 Min",
    "raisereg": "Raise Reg",
    "lower1sec": "Lower 1 Sec",
    "lower6sec": "Lower 6 Sec",
    "lower60sec": "Lower 60 Sec",
    "lower5min": "Lower 5 Min",
    "lowerreg": "Lower Reg",
}

FCAS_COLUMNS = list(f"{k}_rrp" for k in FCAS_SERVICES.keys())
FCAS_GROUPS = {
    key: ("raise" if key.startswith("raise") else "lower")
    for key in FCAS_SERVICES.keys()
}

WEM_ESS_SERVICES = {
    "regulation_raise": {
        "label": "Regulation Raise",
        "price_col": "regulation_raise_price",
        "available_col": "available_regulation_raise",
        "in_service_col": "in_service_regulation_raise",
        "requirement_col": "requirement_regulation_raise",
        "shortfall_col": "shortfall_regulation_raise",
        "dispatch_total_col": "dispatch_total_regulation_raise",
        "capped_col": "capped_regulation_raise",
        "group": "raise",
    },
    "regulation_lower": {
        "label": "Regulation Lower",
        "price_col": "regulation_lower_price",
        "available_col": "available_regulation_lower",
        "in_service_col": "in_service_regulation_lower",
        "requirement_col": "requirement_regulation_lower",
        "shortfall_col": "shortfall_regulation_lower",
        "dispatch_total_col": "dispatch_total_regulation_lower",
        "capped_col": "capped_regulation_lower",
        "group": "lower",
    },
    "contingency_raise": {
        "label": "Contingency Raise",
        "price_col": "contingency_raise_price",
        "available_col": "available_contingency_raise",
        "in_service_col": "in_service_contingency_raise",
        "requirement_col": "requirement_contingency_raise",
        "shortfall_col": "shortfall_contingency_raise",
        "dispatch_total_col": "dispatch_total_contingency_raise",
        "capped_col": "capped_contingency_raise",
        "group": "raise",
    },
    "contingency_lower": {
        "label": "Contingency Lower",
        "price_col": "contingency_lower_price",
        "available_col": "available_contingency_lower",
        "in_service_col": "in_service_contingency_lower",
        "requirement_col": "requirement_contingency_lower",
        "shortfall_col": "shortfall_contingency_lower",
        "dispatch_total_col": "dispatch_total_contingency_lower",
        "capped_col": "capped_contingency_lower",
        "group": "lower",
    },
    "rocof": {
        "label": "RoCoF",
        "price_col": "rocof_price",
        "available_col": "available_rocof",
        "in_service_col": "in_service_rocof",
        "requirement_col": "requirement_rocof",
        "shortfall_col": "shortfall_rocof",
        "dispatch_total_col": "dispatch_total_rocof",
        "capped_col": "capped_rocof",
        "group": "raise",
    },
}


def _aggregate_period_key(date_str: str, aggregation: str) -> str:
    if aggregation == "daily":
        return date_str[:10]
    if aggregation == "weekly":
        d = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return date_str[:7]


def _estimate_wem_capture(row: dict, service_meta: dict, capacity_mw: float) -> tuple[float, float, float]:
    dispatch_total = row.get(service_meta["dispatch_total_col"]) or 0.0
    shortfall = row.get(service_meta["shortfall_col"]) or 0.0
    in_service = row.get(service_meta["in_service_col"]) or 0.0
    requirement = row.get(service_meta["requirement_col"]) or 0.0
    available = row.get(service_meta["available_col"]) or 0.0

    candidate_mw = min(capacity_mw, max(dispatch_total + shortfall, dispatch_total, 0.0))
    if in_service > 0:
        capture_rate = min(dispatch_total / in_service, 1.0)
    elif dispatch_total > 0:
        capture_rate = 1.0
    else:
        capture_rate = 0.0

    enabled_mw = min(candidate_mw * capture_rate, max(dispatch_total + shortfall, 0.0))
    tightness = 0.0
    if requirement > 0:
        tightness = max(0.0, 1 - min(available / requirement, 1.0))
    return enabled_mw, capture_rate, tightness


def _build_wem_preview_scores(service_breakdown: list[dict], *, coverage_days: int, preview_mode: str) -> dict:
    if not service_breakdown:
        return {
            "scarcity_score": 0,
            "opportunity_score": 0,
            "quality_score": 0,
            "preview_caveat": "No WEM preview data available.",
        }

    scarcity_components = []
    opportunity_components = []
    for service in service_breakdown:
        shortfall_signal = min(service.get("shortfall_intervals", 0) * 25.0, 100.0)
        capped_signal = min(service.get("capped_intervals", 0) * 15.0, 100.0)
        tightness_signal = min((service.get("avg_tightness", 0.0) or 0.0) * 100.0, 100.0)
        scarcity_components.append((tightness_signal * 0.5) + (shortfall_signal * 0.35) + (capped_signal * 0.15))

        price_signal = min((service.get("avg_price", 0.0) or 0.0) * 2.0, 100.0)
        capture_signal = min((service.get("avg_capture_rate", 0.0) or 0.0) * 100.0, 100.0)
        opportunity_components.append((price_signal * 0.55) + (capture_signal * 0.25) + (tightness_signal * 0.20))

    scarcity_score = round(sum(scarcity_components) / len(scarcity_components), 1)
    opportunity_score = round(sum(opportunity_components) / len(opportunity_components), 1)

    coverage_score = min((coverage_days / 7.0) * 100.0, 100.0)
    preview_penalty = 30.0 if preview_mode == "single_day_preview" else 10.0
    quality_score = round(max(0.0, (coverage_score * 0.6) + 25.0 - preview_penalty), 1)

    return {
        "scarcity_score": scarcity_score,
        "opportunity_score": opportunity_score,
        "quality_score": quality_score,
        "preview_caveat": (
            "WEM preview scoring is derived from slim ESS tables and should be treated as preview-grade, "
            "not investment-grade."
        ),
    }


def _get_wem_ess_analysis(
    year: int,
    aggregation: str,
    capacity_mw: float,
    month: Optional[str] = None,
    quarter: Optional[str] = None,
    day_type: Optional[str] = None,
):
    market_table = db.WEM_ESS_MARKET_TABLE
    constraint_table = db.WEM_ESS_CONSTRAINT_TABLE
    interval_hours = 5 / 60

    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        where_clause, params = _build_temporal_filters(
            year,
            month,
            quarter,
            day_type,
            time_field="m.dispatch_interval",
            region=None,
            region_field=None,
            force_year_prefix=True,
        )
        cursor.execute(
            f"""
            SELECT m.*,
                   c.binding_count,
                   c.near_binding_count,
                   c.binding_max_shadow_price
            FROM {market_table} m
            LEFT JOIN {constraint_table} c ON c.dispatch_interval = m.dispatch_interval
            WHERE {where_clause}
            ORDER BY m.dispatch_interval ASC
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

    if not rows:
        return {
            "region": "WEM",
            "year": year,
            "has_fcas_data": False,
            "message": "No WEM ESS slim data available for this year. Run the WEM ESS latest-month sync first.",
            "data": [],
            "summary": {},
            "hourly": [],
            "service_breakdown": [],
        }

    records = [dict(zip(col_names, row)) for row in rows]
    grouped = defaultdict(list)
    hourly_buckets = defaultdict(list)
    service_breakdown = []

    for record in records:
        period = _aggregate_period_key(record["dispatch_interval"], aggregation)
        grouped[period].append(record)
        hour_bucket = record["dispatch_interval"][11:13]
        total_price = 0.0
        for service_key, meta in WEM_ESS_SERVICES.items():
            total_price += record.get(meta["price_col"]) or 0.0
        hourly_buckets[hour_bucket].append(total_price)

    for service_key, meta in WEM_ESS_SERVICES.items():
        prices = []
        revenues = []
        requirements = []
        in_service = []
        available = []
        dispatch_totals = []
        capture_rates = []
        tightness_scores = []
        shortfall_intervals = 0
        capped_intervals = 0

        for record in records:
            price = record.get(meta["price_col"])
            if price is None:
                continue
            prices.append(price)
            requirements.append(record.get(meta["requirement_col"]) or 0.0)
            in_service.append(record.get(meta["in_service_col"]) or 0.0)
            available.append(record.get(meta["available_col"]) or 0.0)
            dispatch_totals.append(record.get(meta["dispatch_total_col"]) or 0.0)
            enabled_mw, capture_rate, tightness = _estimate_wem_capture(record, meta, capacity_mw)
            revenues.append(enabled_mw * price * interval_hours / 1000)
            capture_rates.append(capture_rate)
            tightness_scores.append(tightness)
            if (record.get(meta["shortfall_col"]) or 0.0) > 0:
                shortfall_intervals += 1
            if record.get(meta["capped_col"]) == 1:
                capped_intervals += 1

        avg_price = sum(prices) / len(prices) if prices else 0.0
        service_breakdown.append(
            {
                "service": meta["label"],
                "key": service_key,
                "group": meta["group"],
                "avg_price": round(avg_price, 2),
                "max_price": round(max(prices), 2) if prices else 0.0,
                "est_revenue_k": round(sum(revenues), 1),
                "avg_requirement_mw": round(sum(requirements) / len(requirements), 2) if requirements else 0.0,
                "avg_in_service_mw": round(sum(in_service) / len(in_service), 2) if in_service else 0.0,
                "avg_available_mw": round(sum(available) / len(available), 2) if available else 0.0,
                "avg_dispatch_total_mw": round(sum(dispatch_totals) / len(dispatch_totals), 2) if dispatch_totals else 0.0,
                "avg_capture_rate": round(sum(capture_rates) / len(capture_rates), 4) if capture_rates else 0.0,
                "avg_tightness": round(sum(tightness_scores) / len(tightness_scores), 4) if tightness_scores else 0.0,
                "shortfall_intervals": shortfall_intervals,
                "capped_intervals": capped_intervals,
            }
        )

    hourly = []
    for h in range(24):
        hour_key = f"{h:02d}"
        values = hourly_buckets.get(hour_key, [])
        hourly.append(
            {
                "hour": hour_key,
                "avg_total_fcas": round(sum(values) / len(values), 2) if values else 0.0,
            }
        )

    data = []
    for period, items in sorted(grouped.items()):
        entry = {"period": period, "intervals": len(items)}
        for service_key, meta in WEM_ESS_SERVICES.items():
            values = [item.get(meta["price_col"]) for item in items if item.get(meta["price_col"]) is not None]
            entry[service_key] = round(sum(values) / len(values), 2) if values else 0.0
        entry["total_fcas_avg"] = round(
            sum(
                sum(item.get(meta["price_col"]) or 0.0 for meta in WEM_ESS_SERVICES.values())
                for item in items
            ) / len(items),
            2,
        )
        entry["binding_count_avg"] = round(
            sum(item.get("binding_count") or 0 for item in items) / len(items),
            2,
        )
        entry["binding_shadow_max"] = round(
            max(item.get("binding_max_shadow_price") or 0.0 for item in items),
            2,
        )
        data.append(entry)

    total_avg_fcas = sum(item["avg_price"] for item in service_breakdown)
    total_est_revenue = sum(item["est_revenue_k"] for item in service_breakdown)
    avg_capture_rate = (
        round(sum(item["avg_capture_rate"] for item in service_breakdown) / len(service_breakdown), 4)
        if service_breakdown else 0.0
    )
    coverage_days = len({record["dispatch_interval"][:10] for record in records})
    preview_mode = "single_day_preview" if coverage_days == 1 else "multi_day_preview"
    wem_scores = _build_wem_preview_scores(
        service_breakdown,
        coverage_days=coverage_days,
        preview_mode=preview_mode,
    )

    return {
        "region": "WEM",
        "year": year,
        "has_fcas_data": True,
        "aggregation": aggregation,
        "estimate_basis": "price_taker_share_using_dispatch_total_and_in_service",
        "summary": {
            "total_avg_fcas_price": round(total_avg_fcas, 2),
            "total_est_revenue_k": round(total_est_revenue, 1),
            "total_intervals": len(records),
            "capacity_mw": capacity_mw,
            "data_points_with_fcas": len(records),
            "avg_capture_rate": avg_capture_rate,
            "revenue_scope": "loaded_window",
            "coverage_start": records[0]["dispatch_interval"],
            "coverage_end": records[-1]["dispatch_interval"],
            "coverage_days": coverage_days,
            "preview_mode": preview_mode,
            "investment_grade": False,
            "message": (
                "WEM ESS revenue uses a slim-table preview estimate based on dispatchTotal and "
                "inService quantities. Current output is not investment-grade project finance data."
            ),
            **wem_scores,
        },
        "service_breakdown": service_breakdown,
        "hourly": hourly,
        "data": data,
    }


@app.get(
    "/api/fcas-analysis",
    summary="Get FCAS and ESS revenue analysis",
    description="Returns FCAS analysis results with unified metadata. WEM responses may remain preview-grade and expose that state through metadata.data_grade and metadata.warnings.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def get_fcas_analysis(
    year: int = Query(..., description="Year to query"),
    region: str = Query(..., description="Region ID (e.g., NSW1)"),
    aggregation: str = Query("daily", description="Aggregation: daily, weekly, monthly"),
    capacity_mw: float = Query(100, description="Battery capacity in MW for revenue estimation"),
    month: Optional[str] = Query(None, description="Month (01-12) to filter by"),
    quarter: Optional[str] = Query(None, description="Quarter to filter by (Q1, Q2, Q3, Q4)"),
    day_type: Optional[str] = Query(None, description="Day type to filter by (WEEKDAY, WEEKEND)"),
    access_scope: Optional[dict] = None,
):
    """
    FCAS revenue analysis endpoint.
    Returns per-service average prices, revenue estimates, hourly distribution,
    and time series data for charting.
    """
    if access_scope:
        _assert_scope_allows_internal_query(
            access_scope,
            region=region,
            market="WEM" if region == "WEM" else "NEM",
        )
    aggregation = _cacheable_param(aggregation)
    capacity_mw = _cacheable_param(capacity_mw)
    month = _cacheable_param(month)
    quarter = _cacheable_param(quarter)
    day_type = _cacheable_param(day_type)
    cache_payload = {
        "year": year,
        "region": region,
        "aggregation": aggregation,
        "capacity_mw": capacity_mw,
        "month": month,
        "quarter": quarter,
        "day_type": day_type,
        "data_version": _market_data_version(),
    }
    cached = _fetch_response_cache(FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE, cache_payload)
    if cached is not None:
        return _attach_fcas_analysis_metadata(cached, region=region)

    if region == "WEM":
        try:
            response = _get_wem_ess_analysis(year, aggregation, capacity_mw, month, quarter, day_type)
            response = _attach_fcas_analysis_metadata(response, region=region)
            return _store_response_cache(
                FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.error(f"WEM ESS analysis error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    table_name = f"trading_price_{year}"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"No data for year {year}")

            # Check if FCAS columns exist in the table
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            available_fcas = [c for c in FCAS_COLUMNS if c in existing_cols]

            if not available_fcas:
                response = {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "No FCAS data available. Run scraper with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }
                response = _attach_fcas_analysis_metadata(response, region=region)
                return _store_response_cache(
                    FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            where_clause, params = _build_temporal_filters(
                year,
                month,
                quarter,
                day_type,
                time_field="settlement_date",
                region=region,
                region_field="region_id",
            )
            nonnull_expr = " OR ".join(f"{col} IS NOT NULL" for col in available_fcas)

            # Check if there's actually non-null FCAS data
            check_query = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause} AND ({nonnull_expr})"
            cursor.execute(check_query, tuple(params))
            fcas_count = cursor.fetchone()[0]

            if fcas_count == 0:
                response = {
                    "region": region, "year": year, "has_fcas_data": False,
                    "message": "FCAS columns exist but no data yet. Re-sync with --fcas flag.",
                    "data": [], "summary": {}, "hourly": [], "service_breakdown": []
                }
                response = _attach_fcas_analysis_metadata(response, region=region)
                return _store_response_cache(
                    FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                    cache_payload,
                    response,
                    DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                )

            # 1. Overall service breakdown: average price per FCAS service
            avg_selects = ", ".join(
                f"AVG({col}) as avg_{col}" for col in available_fcas
            )
            max_selects = ", ".join(
                f"MAX({col}) as max_{col}" for col in available_fcas
            )
            cursor.execute(
                f"SELECT {avg_selects}, {max_selects}, COUNT(*) as total_intervals "
                f"FROM {table_name} WHERE {where_clause} AND ({nonnull_expr})",
                tuple(params),
            )
            agg_row = cursor.fetchone()

            n_fcas = len(available_fcas)
            total_intervals = agg_row[2 * n_fcas] if agg_row else 0

            service_breakdown = []
            for i, col in enumerate(available_fcas):
                svc_key = col.replace("_rrp", "")
                avg_price = agg_row[i] if agg_row and agg_row[i] is not None else 0
                max_price = agg_row[n_fcas + i] if agg_row and agg_row[n_fcas + i] is not None else 0
                # Revenue estimate: price * capacity * (5min / 60min) per interval
                est_revenue = avg_price * capacity_mw * total_intervals * (5 / 60) / 1000  # in $k
                service_breakdown.append({
                    "service": FCAS_SERVICES.get(svc_key, svc_key),
                    "key": svc_key,
                    "group": FCAS_GROUPS.get(svc_key),
                    "avg_price": round(avg_price, 2),
                    "max_price": round(max_price, 2),
                    "est_revenue_k": round(est_revenue, 1),
                })

            # 2. Hourly distribution of FCAS prices (average by hour)
            total_fcas_expr = " + ".join(f"COALESCE({col}, 0)" for col in available_fcas)
            hourly_query = f"""
                SELECT 
                    CAST(substr(settlement_date, 12, 2) AS INTEGER) as hour_bucket,
                    AVG({total_fcas_expr}) as avg_total_fcas,
                    COUNT(*) as cnt
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                GROUP BY hour_bucket
                ORDER BY hour_bucket ASC
            """
            cursor.execute(hourly_query, tuple(params))
            hourly_rows = cursor.fetchall()
            hourly_dict = {r[0]: round(r[1], 2) for r in hourly_rows}
            hourly = [{"hour": f"{h:02d}", "avg_total_fcas": hourly_dict.get(h, 0)} for h in range(24)]

            # 3. Time series aggregated by day/week/month
            if aggregation == "daily":
                date_expr = "substr(settlement_date, 1, 10)"
            elif aggregation == "weekly":
                date_expr = "strftime('%Y-W%W', settlement_date)"
            else:  # monthly
                date_expr = "substr(settlement_date, 1, 7)"

            fcas_avg_selects = ", ".join(
                f"ROUND(AVG({col}), 2) as {col}" for col in available_fcas
            )
            ts_query = f"""
                SELECT {date_expr} as period, {fcas_avg_selects},
                       ROUND(AVG({total_fcas_expr}), 2) as total_fcas_avg,
                       COUNT(*) as intervals
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                GROUP BY period
                ORDER BY period ASC
            """
            cursor.execute(ts_query, tuple(params))
            ts_rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]

            ts_data = []
            for row in ts_rows:
                entry = {}
                for j, col_name in enumerate(col_names):
                    entry[col_name] = row[j]
                ts_data.append(entry)

            cursor.execute(
                f"""
                SELECT settlement_date, rrp_aud_mwh, {", ".join(available_fcas)}
                FROM {table_name}
                WHERE {where_clause} AND ({nonnull_expr})
                ORDER BY settlement_date ASC
                """,
                tuple(params),
            )
            opportunity_columns = [desc[0] for desc in cursor.description]
            opportunity_rows = [dict(zip(opportunity_columns, row)) for row in cursor.fetchall()]
            opportunity = summarize_nem_fcas_opportunity(
                opportunity_rows,
                capacity_mw=capacity_mw,
                duration_hours=DEFAULT_FCAS_OPPORTUNITY_DURATION_HOURS,
            )
            opportunity_by_key = {
                item["key"]: item for item in opportunity["service_breakdown"]
            }
            enriched_breakdown = []
            for service in service_breakdown:
                opportunity_item = opportunity_by_key.get(service["key"], {})
                enriched_breakdown.append(
                    {
                        **service,
                        "avg_reserved_capacity_mw": opportunity_item.get("avg_reserved_capacity_mw", 0.0),
                        "opportunity_cost_k": opportunity_item.get("opportunity_cost_k", 0.0),
                        "net_incremental_revenue_k": opportunity_item.get("net_incremental_revenue_k", 0.0),
                        "soc_binding_interval_ratio": opportunity_item.get("soc_binding_interval_ratio", 0.0),
                        "power_binding_interval_ratio": opportunity_item.get("power_binding_interval_ratio", 0.0),
                        "incremental_revenue_positive": opportunity_item.get("incremental_revenue_positive", False),
                    }
                )

            # 4. Overall summary
            total_avg_fcas = sum(s["avg_price"] for s in enriched_breakdown)
            total_est_revenue_k = sum(s["est_revenue_k"] for s in enriched_breakdown)

            summary = {
                "total_avg_fcas_price": round(total_avg_fcas, 2),
                "total_est_revenue_k": round(total_est_revenue_k, 1),
                "total_intervals": total_intervals,
                "capacity_mw": capacity_mw,
                "data_points_with_fcas": fcas_count,
                "total_opportunity_cost_k": opportunity["summary"]["total_opportunity_cost_k"],
                "total_net_incremental_revenue_k": opportunity["summary"]["total_net_incremental_revenue_k"],
                "viable_service_count": opportunity["summary"]["viable_service_count"],
                "assumed_duration_hours": opportunity["summary"]["assumed_duration_hours"],
            }

            response = {
                "region": region,
                "year": year,
                "has_fcas_data": True,
                "aggregation": aggregation,
                "filters": {
                    "month": month,
                    "quarter": quarter,
                    "day_type": day_type,
                },
                "summary": summary,
                "service_breakdown": enriched_breakdown,
                "hourly": hourly,
                "data": ts_data,
            }
            response = _attach_fcas_analysis_metadata(response, region=region)
            return _store_response_cache(
                FCAS_ANALYSIS_RESPONSE_CACHE_SCOPE,
                cache_payload,
                response,
                DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FCAS analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================
# Investment Analysis (BESS Cash Flow / NPV / IRR)
# ============================================================

from models.financial_params import InvestmentParams, DispatchMode, FcasRevenueMode
from engines.financial_model import FinancialModel
import bess_backtest

INVESTMENT_RESPONSE_CACHE_SCOPE = "investment_response_v2"
INVESTMENT_BACKTEST_CACHE_SCOPE = "investment_backtest_v1"
INVESTMENT_FCAS_CACHE_SCOPE = "investment_fcas_baseline_v1"
_ANALYSIS_INFLIGHT_LOCK = threading.Lock()
_ANALYSIS_INFLIGHT: Dict[str, dict] = {}

def _analysis_data_version() -> str:
    return db.get_last_update_time() or "no_last_update"

def _analysis_cache_lookup(
    *,
    scope: str,
    payload: dict,
    data_version: str,
    allow_response_cache: bool = False,
):
    cache_key = _stable_cache_key(payload)
    organization_id = payload.get("organization_id")
    workspace_id = payload.get("workspace_id")
    cached = db.fetch_analysis_cache(
        scope=scope,
        cache_key=cache_key,
        data_version=data_version,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if cached is not None:
        return cached["response_payload"]

    if allow_response_cache:
        return response_cache.get_json(INVESTMENT_RESPONSE_REDIS_SCOPE, cache_key)

    return None


def _analysis_cache_store(
    *,
    scope: str,
    payload: dict,
    data_version: str,
    response_payload: dict,
    store_response_cache: bool = False,
):
    cache_key = _stable_cache_key(payload)
    organization_id = payload.get("organization_id")
    workspace_id = payload.get("workspace_id")
    db.upsert_analysis_cache(
        scope=scope,
        cache_key=cache_key,
        data_version=data_version,
        response_payload=response_payload,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if store_response_cache:
        response_cache.set_json(
            INVESTMENT_RESPONSE_REDIS_SCOPE,
            cache_key,
            response_payload,
            INVESTMENT_RESPONSE_CACHE_TTL_SECONDS,
        )
    return response_payload


def _effective_degradation_rate(params: InvestmentParams) -> float:
    return (
        params.degradation_rate
        if params.degradation_rate is not None
        else params.battery.calendar_degradation_rate
    )


def _build_backtest_summary(params: InvestmentParams, data_version: str) -> dict:
    standardized_params = [params.to_bess_backtest_params(year=year) for year in params.backtest_years]
    payload = {
        "inputs": [item.model_dump(mode="json") for item in standardized_params],
    }
    cached = _analysis_cache_lookup(
        scope=INVESTMENT_BACKTEST_CACHE_SCOPE,
        payload=payload,
        data_version=data_version,
    )
    if cached is not None:
        return cached

    total_arb_revenue = 0.0
    total_arb_net_revenue = 0.0
    total_cycles = 0.0
    valid_years = 0
    backtest_modes = []
    revenue_scopes = []
    backtest_drivers = []

    for backtest_params in standardized_params:
        standardized_result = _run_standardized_bess_backtest(backtest_params)
        if standardized_result is None:
            continue

        total_arb_revenue += standardized_result["annual_revenue"]
        total_arb_net_revenue += standardized_result["annual_net_revenue"]
        total_cycles += standardized_result["annual_cycles"]
        valid_years += 1
        backtest_modes.append(standardized_result["backtest_mode"])
        revenue_scopes.append(standardized_result["revenue_scope"])
        backtest_drivers.append(
            {
                "year": backtest_params.year,
                "methodology_version": standardized_result["methodology_version"],
                "backtest_mode": standardized_result["backtest_mode"],
                "revenue_scope": standardized_result["revenue_scope"],
                "timeline_points": standardized_result["timeline_points"],
                "input": standardized_result["input"],
                "summary": standardized_result["summary"],
            }
        )

    summary = {
        "avg_annual_arbitrage_raw": total_arb_revenue / valid_years if valid_years > 0 else 0.0,
        "avg_annual_arbitrage_net": total_arb_net_revenue / valid_years if valid_years > 0 else 0.0,
        "avg_annual_cycles": total_cycles / valid_years if valid_years > 0 else 365.0,
        "valid_years": valid_years,
        "backtest_mode": " / ".join(dict.fromkeys(backtest_modes)) if backtest_modes else "unavailable",
        "revenue_scope": " / ".join(dict.fromkeys(revenue_scopes)) if revenue_scopes else "unavailable",
        "fallback_used": False,
        "backtest_reference": {
            "methodology_version": (
                " / ".join(dict.fromkeys(item["methodology_version"] for item in backtest_drivers))
                if backtest_drivers
                else "unavailable"
            ),
            "inputs": [item.model_dump(mode="json") for item in standardized_params],
            "drivers": backtest_drivers,
        },
        "warnings": [] if backtest_drivers else ["no_standardized_backtest_data"],
    }
    return _analysis_cache_store(
        scope=INVESTMENT_BACKTEST_CACHE_SCOPE,
        payload=payload,
        data_version=data_version,
        response_payload=summary,
    )


def _estimate_nem_fcas_baseline(params: InvestmentParams) -> tuple[float, str]:
    annualized_net_incremental_total = 0.0
    valid_years = 0

    with db.get_connection() as conn:
        for year in params.backtest_years:
            table_name = f"trading_price_{year}"
            try:
                cursor = conn.execute(
                    f"""
                    SELECT settlement_date, rrp_aud_mwh, {", ".join(FCAS_COLUMNS)}
                    FROM {table_name}
                    WHERE region_id = ?
                    ORDER BY settlement_date ASC
                    """,
                    (params.region,),
                )
            except Exception:
                continue

            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if rows:
                summary = summarize_nem_fcas_opportunity(
                    rows,
                    capacity_mw=params.battery.power_mw,
                    duration_hours=params.battery.duration_hours,
                )["summary"]
                annualized_net_incremental_total += max(summary["total_net_incremental_revenue_k"], 0.0) * 1000.0
                valid_years += 1

    baseline = (annualized_net_incremental_total / valid_years) * params.revenue_capture_rate if valid_years > 0 else 0.0
    return baseline, "historical_auto"


def _get_fcas_baseline(params: InvestmentParams, data_version: str) -> tuple[float, str]:
    if params.fcas_revenue_mode == FcasRevenueMode.MANUAL:
        return params.fcas_revenue_per_mw_year * params.battery.power_mw, "manual_input"

    payload = {
        "region": params.region,
        "backtest_years": list(params.backtest_years),
        "power_mw": params.battery.power_mw,
        "revenue_capture_rate": params.revenue_capture_rate,
        "fcas_revenue_mode": params.fcas_revenue_mode.value,
        "fcas_revenue_per_mw_year": params.fcas_revenue_per_mw_year,
    }
    cached = _analysis_cache_lookup(
        scope=INVESTMENT_FCAS_CACHE_SCOPE,
        payload=payload,
        data_version=data_version,
    )
    if cached is not None:
        return cached["baseline_fcas"], cached["source"]

    if params.region == "WEM":
        result = {
            "baseline_fcas": params.fcas_revenue_per_mw_year * params.battery.power_mw,
            "source": "manual_input_wem_fallback",
        }
    else:
        baseline_fcas, source = _estimate_nem_fcas_baseline(params)
        result = {
            "baseline_fcas": baseline_fcas,
            "source": source,
        }

    cached_result = _analysis_cache_store(
        scope=INVESTMENT_FCAS_CACHE_SCOPE,
        payload=payload,
        data_version=data_version,
        response_payload=result,
    )
    return cached_result["baseline_fcas"], cached_result["source"]


def _derive_arbitrage_baseline(params: InvestmentParams, backtest_summary: dict) -> tuple[float, str]:
    efficiency_factor = max(0.0, 1.0 - params.forecast_inefficiency)
    methodology_version = backtest_summary.get("backtest_reference", {}).get("methodology_version", "")

    if "bess_backtest_v1" in methodology_version:
        observed_net = backtest_summary.get("avg_annual_arbitrage_net", 0.0)
        baseline = observed_net * efficiency_factor * params.revenue_capture_rate
        return baseline, "observed_net_revenue"

    return 0.0, "no_standardized_backtest_data"


def _build_investment_response(
    *,
    params: InvestmentParams,
    base_result,
    scenarios: list,
    mc_result,
    baseline_arbitrage: float,
    arbitrage_baseline_source: str,
    baseline_fcas: float,
    fcas_baseline_source: str,
    backtest_summary: dict,
) -> dict:
    base_metrics = base_result.metrics.model_dump()
    storage_capex = max(
        0.0,
        base_result.metrics.total_capex - params.financial.grid_connection_cost,
    )
    base_cash_flows = []
    for row in base_result.cash_flows:
        payload = row.model_dump()
        if storage_capex > 0 and payload.get("augmentation_capex", 0) > 0:
            payload["degradation_factor"] = max(
                0.0,
                1.0 - (payload["augmentation_capex"] / storage_capex),
            )
        else:
            payload["degradation_factor"] = payload.get("state_of_health")
        base_cash_flows.append(payload)

    assumptions = [
        "Using Dual-factor degradation model.",
        "Monte Carlo simulations: " + ("Enabled" if params.monte_carlo.enabled else "Disabled"),
        f"Backtest revenue scope: {backtest_summary.get('revenue_scope', 'unavailable')}.",
        f"Arbitrage baseline source: {arbitrage_baseline_source}.",
    ]
    if params.region == "WEM":
        assumptions.append("WEM auto FCAS falls back to manual input because only slim preview data is available.")
    if backtest_summary.get("valid_years", 0) == 0:
        assumptions.append("No standardized BESS backtest coverage was available for the requested years.")

    observed_net_arbitrage = backtest_summary.get("avg_annual_arbitrage_net", baseline_arbitrage)
    backtest_drivers = backtest_summary.get("backtest_reference", {}).get("drivers", [])
    primary_driver = backtest_drivers[0] if backtest_drivers else {}

    response = {
        "region": params.region,
        "params_summary": {
            "power_mw": params.battery.power_mw,
            "duration_hours": params.battery.duration_hours,
            "project_life": params.financial.project_life_years,
        },
        "base_metrics": base_metrics,
        "scenarios": [scenario.model_dump() for scenario in scenarios],
        "monte_carlo": mc_result.model_dump() if mc_result else None,
        "assumptions": assumptions,
        # Legacy compatibility fields still consumed by tests and parts of the UI.
        "metrics": base_metrics,
        "cash_flows": base_cash_flows,
        "baseline_revenue": {
            "arbitrage": baseline_arbitrage,
            "arbitrage_net_observed": observed_net_arbitrage,
            "fcas": baseline_fcas,
            "capacity": params.financial.capacity_payment_per_mw_year * params.battery.power_mw,
        },
        "backtest_observed": {
            "gross_energy_revenue": backtest_summary.get("avg_annual_arbitrage_raw", baseline_arbitrage),
            "net_energy_revenue": observed_net_arbitrage,
            "equivalent_cycles": backtest_summary.get("avg_annual_cycles"),
            "methodology_version": primary_driver.get("methodology_version", "unavailable"),
            "revenue_scope": backtest_summary.get("revenue_scope", "unavailable"),
            "baseline_source": arbitrage_baseline_source,
        },
        "backtest_mode": backtest_summary.get("backtest_mode", "unavailable"),
        "revenue_scope": backtest_summary.get("revenue_scope", "unavailable"),
        "backtest_reference": backtest_summary.get("backtest_reference", {}),
        "backtest_fallback_used": bool(backtest_summary.get("fallback_used")),
        "arbitrage_baseline_source": arbitrage_baseline_source,
        "effective_degradation_rate": _effective_degradation_rate(params),
        "fcas_baseline_source": fcas_baseline_source,
    }
    return _attach_investment_metadata(response, region=params.region)


def _acquire_inflight_entry(cache_key: str) -> tuple[dict, bool]:
    with _ANALYSIS_INFLIGHT_LOCK:
        entry = _ANALYSIS_INFLIGHT.get(cache_key)
        if entry is not None:
            return entry, False

        entry = {"event": threading.Event(), "response": None, "error": None}
        _ANALYSIS_INFLIGHT[cache_key] = entry
        return entry, True


@app.post(
    "/api/bess/backtests",
    summary="Run standardized BESS backtest",
    description="Runs the standardized BESS backtest engine and returns summary metrics, timeline output, and unified metadata for source/version traceability.",
    responses=OPENAPI_NOT_FOUND_AND_ERROR_RESPONSES,
)
def run_bess_backtest(params: BessBacktestParams, access_scope=None):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, region=params.region, market=params.market)
        intervals = _fetch_bess_backtest_intervals(params)
        if not intervals:
            raise HTTPException(status_code=404, detail="No backtest source data found")

        result = run_bess_backtest_v1(params, intervals)
        summary = result["summary"]
        response = {
            "market": params.market,
            "region": params.region,
            "year": params.year,
            "params_summary": {
                "power_mw": params.power_mw,
                "energy_mwh": params.energy_mwh,
                "duration_hours": params.duration_hours,
                "round_trip_efficiency": params.round_trip_efficiency,
                "max_cycles_per_day": params.max_cycles_per_day,
            },
            "revenue_breakdown": {
                "gross_energy_revenue": summary["gross_revenue"],
                "net_revenue": summary["net_revenue"],
            },
            "cost_breakdown": summary["costs"],
            "soc_summary": {
                "soc_start_mwh": summary["soc_start_mwh"],
                "soc_end_mwh": summary["soc_end_mwh"],
                "soc_min_mwh": summary["soc_min_mwh"],
                "soc_max_mwh": summary["soc_max_mwh"],
            },
            "cycle_summary": {
                "charge_throughput_mwh": summary["charge_throughput_mwh"],
                "discharge_throughput_mwh": summary["discharge_throughput_mwh"],
                "equivalent_cycles": summary["equivalent_cycles"],
            },
            "warnings": summary["warnings"],
            "timeline_points": len(result["timeline"]),
            "timeline": result["timeline"],
        }
        return _attach_bess_backtest_metadata(response, params)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("BESS backtest API error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/bess/backtests/coverage",
    summary="Get standardized BESS backtest coverage",
    description="Returns source-data coverage for the standardized BESS backtest path, including interval count, coverage start/end, inferred interval minutes, and unified metadata.",
    responses=OPENAPI_ERROR_RESPONSES,
)
def get_bess_backtest_coverage(
    market: str = Query(..., description="Market code: NEM or WEM"),
    region: str = Query(..., description="Region code such as NSW1 or WEM"),
    year: int = Query(..., description="Source year to inspect"),
    access_scope: Optional[dict] = None,
):
    try:
        if access_scope:
            _assert_scope_allows_internal_query(access_scope, region=region, market=market)
        params = BessBacktestParams(
            market=market,
            region=region,
            year=year,
            power_mw=1.0,
            energy_mwh=1.0,
            duration_hours=1.0,
        )
        intervals = _fetch_bess_backtest_intervals(params)
        payload = {
            "market": params.market,
            "region": params.region,
            "year": params.year,
            "has_source_data": bool(intervals),
            "interval_count": len(intervals),
            "coverage_start": intervals[0]["timestamp"] if intervals else None,
            "coverage_end": intervals[-1]["timestamp"] if intervals else None,
            "interval_minutes": (
                round(intervals[0]["interval_hours"] * 60)
                if intervals
                else (5 if params.market == "WEM" else get_settlement_interval(params.region))
            ),
        }
        return _attach_bess_backtest_coverage_metadata(payload, params)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("BESS backtest coverage API error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post(
    "/api/investment-analysis",
    summary="Run investment analysis",
    description="Runs investment analysis using standardized backtest-driven baselines when available. Response includes unified metadata plus traceability fields such as backtest_reference, backtest_observed, and backtest_fallback_used.",
    responses=OPENAPI_ERROR_RESPONSES,
)
def investment_analysis(params: InvestmentParams, access_scope=None):
    """
    Compute BESS investment cash flow analysis using the new Engine Layer:
    1. Base Case Evaluation
    2. Scenario Analysis
    3. Monte Carlo Simulation
    """
    try:
        if access_scope:
            _assert_scope_allows_internal_query(
                access_scope,
                region=params.region,
                market="WEM" if params.region == "WEM" else "NEM",
            )
        data_version = _analysis_data_version()
        request_payload = params.model_dump(mode="json", exclude_none=True)
        if access_scope:
            request_payload = _scope_analysis_payload(
                request_payload,
                organization_id=access_scope.get("organization_id"),
                workspace_id=access_scope.get("workspace_id"),
            )

        cached_response = _analysis_cache_lookup(
            scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
            payload=request_payload,
            data_version=data_version,
            allow_response_cache=True,
        )
        if cached_response is not None:
            return cached_response

        inflight_key = _stable_cache_key({
            "scope": INVESTMENT_RESPONSE_CACHE_SCOPE,
            "request": request_payload,
            "data_version": data_version,
        })
        inflight_entry, is_owner = _acquire_inflight_entry(inflight_key)
        if not is_owner:
            inflight_entry["event"].wait()
            if inflight_entry["error"] is not None:
                raise inflight_entry["error"]
            return inflight_entry["response"]

        try:
            backtest_summary = _build_backtest_summary(params, data_version)

            baseline_arbitrage, arbitrage_baseline_source = _derive_arbitrage_baseline(params, backtest_summary)
            avg_annual_cycles = backtest_summary["avg_annual_cycles"]

            baseline_fcas, fcas_baseline_source = _get_fcas_baseline(params, data_version)
            if baseline_fcas > 0:
                if fcas_baseline_source == "historical_auto":
                    avg_fcas_price_per_mwh = (
                        baseline_fcas / (params.battery.power_mw * 8760 * params.revenue_capture_rate)
                        if params.battery.power_mw > 0 and params.revenue_capture_rate > 0
                        else 0.0
                    )
                    fcas_implicit_discharge_mwh = (
                        baseline_fcas / avg_fcas_price_per_mwh * params.fcas_activation_probability
                        if avg_fcas_price_per_mwh > 0
                        else 0.0
                    )
                else:
                    fcas_implicit_discharge_mwh = (
                        (baseline_fcas / 15000) * params.battery.power_mw * params.fcas_activation_probability * 8760
                    )
                avg_annual_cycles += (
                    fcas_implicit_discharge_mwh / params.battery.capacity_mwh
                    if params.battery.capacity_mwh > 0
                    else 0.0
                )

            annual_cycles_history = [avg_annual_cycles] * params.financial.project_life_years

            base_scenario_config = params.scenarios[0] if params.scenarios else None
            if not base_scenario_config:
                from models.financial_params import ScenarioConfig
                base_scenario_config = ScenarioConfig(name="Base")

            base_result = FinancialModel.run_scenario(
                params,
                base_scenario_config,
                baseline_arbitrage,
                baseline_fcas,
                annual_cycles_history,
            )

            scenarios = [base_result]
            for config in params.scenarios[1:]:
                scenarios.append(
                    FinancialModel.run_scenario(
                        params,
                        config,
                        baseline_arbitrage,
                        baseline_fcas,
                        annual_cycles_history,
                    )
                )

            mc_result = None
            if params.monte_carlo.enabled:
                mc_result = FinancialModel.run_monte_carlo(
                    params,
                    baseline_arbitrage,
                    baseline_fcas,
                    annual_cycles_history,
                )

            response = _build_investment_response(
                params=params,
                base_result=base_result,
                scenarios=scenarios,
                mc_result=mc_result,
                baseline_arbitrage=baseline_arbitrage,
                arbitrage_baseline_source=arbitrage_baseline_source,
                baseline_fcas=baseline_fcas,
                fcas_baseline_source=fcas_baseline_source,
                backtest_summary=backtest_summary,
            )
            response = _analysis_cache_store(
                scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
                payload=request_payload,
                data_version=data_version,
                response_payload=response,
                store_response_cache=True,
            )
            inflight_entry["response"] = response
            return response
        except Exception as exc:
            inflight_entry["error"] = exc
            raise
        finally:
            inflight_entry["event"].set()
            with _ANALYSIS_INFLIGHT_LOCK:
                _ANALYSIS_INFLIGHT.pop(inflight_key, None)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Investment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8085)
