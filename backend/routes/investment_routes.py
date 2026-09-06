"""Investment analysis API routes.

Migrated from server.py — provides the BESS investment cash flow / NPV / IRR
endpoint. Integrates DegradationModel from engines/degradation_model.py and
uses deps.py for dependency injection.

Financial Accuracy Modules integration (Task 8.3):
- TaxModel: after-tax cash flows and metrics when tax_config is provided
- ForwardPriceEngine: 20-year scenario projections when forward_scenario is provided
- CostStructureEngine: cost breakdown attached from ScenarioResult (via Task 8.4)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

from deps import get_db, get_cache
from engines.degradation_model import DegradationModel
from models.financial_params import InvestmentParams, CashFlowYear, ScenarioConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["investment-analysis"])

# ---------------------------------------------------------------------------
# Cache scope constants (mirror server.py values)
# ---------------------------------------------------------------------------

INVESTMENT_RESPONSE_CACHE_SCOPE = "investment_response_v2"
INVESTMENT_BACKTEST_CACHE_SCOPE = "investment_backtest_v1"
INVESTMENT_FCAS_CACHE_SCOPE = "investment_fcas_baseline_v1"
INVESTMENT_RESPONSE_REDIS_SCOPE = "api_investment_analysis_v1"
INVESTMENT_RESPONSE_CACHE_TTL_SECONDS = 24 * 60 * 60

# ---------------------------------------------------------------------------
# Inflight deduplication
#
# P0.7（2026-09-05）：认领信号外置。原先 ``_ANALYSIS_INFLIGHT`` 是模块级 dict，
# 去重只在单 worker 内成立 —— 而部署是 GUNICORN_WORKERS>1，同一份昂贵分析（20 年
# 现金流 + 蒙特卡洛 + co-optimization MILP）会被并发打到不同 worker 各算一遍，
# 去重形同建议。
#
# 分工刻意不对称：
# - "谁在算"（认领）→ shared_state（Redis 优先、进程内回落）。这类信号只在秒级
#   存活、需要原子性，正适合 Redis 的 SET NX；
# - "算完的结果" → 沿用已有的共享 ``analysis_cache`` 表（``_analysis_cache_store``
#   本来就会写，且早于响应缓存）。不再往状态命名空间复制一份大 payload。
# 结果是：Redis 完全不可用时，认领退回单 worker 语义 —— 等价于外置之前的行为，
# 不会出现"为了外置而引入新的失败模式"。
# ---------------------------------------------------------------------------

_ANALYSIS_INFLIGHT_LOCK = threading.Lock()
_ANALYSIS_INFLIGHT: Dict[str, dict] = {}

# Max seconds a waiting request will block on an in-flight computation before
# giving up with 503. Prevents indefinite hangs if the owner thread stalls.
_ANALYSIS_INFLIGHT_WAIT_TIMEOUT_SECONDS = 60

_INFLIGHT_CLAIM_SCOPE = "analysis_inflight_claim"
# 认领 TTL 必须显著大于单次分析的正常耗时：属主还在算而认领先过期，等于去重失效。
# 取等待超时的 2 倍，留出余量。
_INFLIGHT_CLAIM_TTL_SECONDS = int(os.environ.get("AUS_ELE_ANALYSIS_INFLIGHT_CLAIM_TTL_SECONDS", "120"))
# 跨 worker waiter 轮询共享结果缓存的间隔。
_INFLIGHT_POLL_SECONDS = float(os.environ.get("AUS_ELE_ANALYSIS_INFLIGHT_POLL_SECONDS", "0.5"))

# Hours in a (non-leap) calendar year. Used to annualize an implied FCAS
# enablement power into equivalent full-power hours when estimating the extra
# throughput cycles FCAS participation contributes to degradation.
HOURS_PER_YEAR = 8760

# ---------------------------------------------------------------------------
# OpenAPI response schemas
# ---------------------------------------------------------------------------

OPENAPI_ERROR_RESPONSES = {
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


# ---------------------------------------------------------------------------
# Helper functions (extracted from server.py)
# ---------------------------------------------------------------------------


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


def _market_data_version() -> str:
    db = get_db()
    return db.get_last_update_time() or "no_last_update"


def _stable_cache_key(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _scope_analysis_payload(
    payload: dict, *, organization_id: str | None, workspace_id: str | None
) -> dict:
    return {
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        **payload,
    }


def _analysis_data_version() -> str:
    db = get_db()
    return db.get_last_update_time() or "no_last_update"


def _analysis_cache_lookup(
    *,
    scope: str,
    payload: dict,
    data_version: str,
    allow_response_cache: bool = False,
):
    db = get_db()
    cache = get_cache()
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
        return cache.get_json(INVESTMENT_RESPONSE_REDIS_SCOPE, cache_key)

    return None


def _analysis_cache_store(
    *,
    scope: str,
    payload: dict,
    data_version: str,
    response_payload: dict,
    store_response_cache: bool = False,
):
    db = get_db()
    cache = get_cache()
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
        cache.set_json(
            INVESTMENT_RESPONSE_REDIS_SCOPE,
            cache_key,
            response_payload,
            INVESTMENT_RESPONSE_CACHE_TTL_SECONDS,
        )
    return response_payload


def _state_store():
    from shared_state import get_state_store

    return get_state_store()


def _acquire_inflight_entry(cache_key: str) -> tuple[Optional[dict], str]:
    """尝试取得 ``cache_key`` 的分析属主身份。

    返回 ``(entry, kind)``：

    - ``("owner")``：本请求负责计算，``entry`` 已登记进本地表并带认领 token；
    - ``("local")``：同 worker 已有属主，``entry`` 是它的对象，waiter 走 Event 干等
      （比轮询便宜，保留原快路径）；
    - ``("remote")``：其他 worker 持有认领，``entry`` 为 None，调用方改轮询共享结果缓存。

    本地表先于认领检查：同 worker 的第二个请求必须走 Event 而不是去抢 Redis，
    否则会在本地已有属主的情况下白丢一次认领。
    """
    store = _state_store()
    with _ANALYSIS_INFLIGHT_LOCK:
        entry = _ANALYSIS_INFLIGHT.get(cache_key)
        if entry is not None:
            return entry, "local"

    token = store.acquire_claim(_INFLIGHT_CLAIM_SCOPE, cache_key, _INFLIGHT_CLAIM_TTL_SECONDS)
    if token is None:
        return None, "remote"

    entry = {"event": threading.Event(), "response": None, "error": None, "claim_token": token}
    with _ANALYSIS_INFLIGHT_LOCK:
        rival = _ANALYSIS_INFLIGHT.get(cache_key)
        if rival is not None:
            # 极窄竞态：本地登记在 acquire 期间被别的线程插入。交回认领，
            # 否则真实属主的后续 waiter 会被一把不属于任何人的锁挡住。
            store.release_claim(_INFLIGHT_CLAIM_SCOPE, cache_key, token)
            return rival, "local"
        _ANALYSIS_INFLIGHT[cache_key] = entry
    return entry, "owner"


def _release_inflight_entry(cache_key: str, entry: dict) -> None:
    """清理本地登记并释放认领（只释放自己持有的那把）。"""
    entry["event"].set()
    with _ANALYSIS_INFLIGHT_LOCK:
        # 按对象身份删除：属主超时后同名条目可能已被下一个请求重建，
        # 无条件 pop 会把别人的登记抹掉，使其 waiter 永久干等。
        if _ANALYSIS_INFLIGHT.get(cache_key) is entry:
            _ANALYSIS_INFLIGHT.pop(cache_key, None)
    token = entry.get("claim_token")
    if token:
        _state_store().release_claim(_INFLIGHT_CLAIM_SCOPE, cache_key, token)


def _claim_inflight_after_owner_loss(cache_key: str) -> tuple[dict, str]:
    """前一个属主离场后接管：登记本地属主，尽力补一次认领。

    刻意**不再等待**：等过一轮才发现属主没了的请求已经付出了等待成本，让它直接算
    比再等 60s 更合理。补认领只是为了让之后的第三个请求还能去重；万一这一步也失败
    （极窄的三方竞态），后果是重复计算一次 —— 不影响正确性。
    """
    store = _state_store()
    token = store.acquire_claim(_INFLIGHT_CLAIM_SCOPE, cache_key, _INFLIGHT_CLAIM_TTL_SECONDS)
    entry = {"event": threading.Event(), "response": None, "error": None, "claim_token": token}
    with _ANALYSIS_INFLIGHT_LOCK:
        rival = _ANALYSIS_INFLIGHT.get(cache_key)
        if rival is not None:
            if token:
                store.release_claim(_INFLIGHT_CLAIM_SCOPE, cache_key, token)
            return rival, "local"
        _ANALYSIS_INFLIGHT[cache_key] = entry
    return entry, "owner"


def _await_remote_analysis(
    *,
    inflight_key: str,
    scope: str,
    payload: dict,
    data_version: str,
) -> Optional[dict]:
    """等待其他 worker 完成同一份分析，从共享 ``analysis_cache`` 取结果。

    三种结局：

    - 结果就绪 → 返回响应；
    - 认领消失（属主崩溃/认领到期）→ 返回 None，调用方接管自算，不让用户干等；
    - 等到超时而属主仍在算 → 抛 503（**沿用原同 worker 超时语义**，不降级为重复
      计算：否则一次超过等待窗口的慢分析会把并发请求全部转成重复计算，反而放大负载）。
    """
    store = _state_store()
    deadline = time.monotonic() + _ANALYSIS_INFLIGHT_WAIT_TIMEOUT_SECONDS
    while True:
        cached = _analysis_cache_lookup(
            scope=scope, payload=payload, data_version=data_version, allow_response_cache=True
        )
        if cached is not None:
            return cached
        if not store.is_claimed(_INFLIGHT_CLAIM_SCOPE, inflight_key):
            return None
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=503,
                detail="Analysis request timed out waiting for an in-flight computation",
            )
        time.sleep(_INFLIGHT_POLL_SECONDS)


def _effective_degradation_rate(params: InvestmentParams) -> float:
    return (
        params.degradation_rate
        if params.degradation_rate is not None
        else params.battery.calendar_degradation_rate
    )


def _attach_regime_layer(payload: dict, *, market: str, region: str) -> dict:
    """Attach regime layer to response payload.

    Delegates to the server-level regime layer cache. If unavailable,
    attaches a minimal unavailable marker.
    """
    try:
        import server as _server
        return _server._attach_regime_layer(payload, market=market, region=region)
    except Exception:
        payload.setdefault("regime_layer", {"availability_status": "not_attached"})
        payload.setdefault("regime_compact", {"availability_status": "not_attached"})
        return payload


def _compute_co_optimized_baseline(params: InvestmentParams):
    """Compute co-optimized energy+FCAS revenue baseline (S2/B2).

    Loads per-year price data and runs the joint energy+FCAS optimization.
    Returns the averaged :class:`CoOptimizedBaseline` or None when no usable
    price data is available.
    """
    from routes.coopt_routes import (
        FCAS_COLUMN_MAP,
        _load_energy_prices,
        _load_fcas_prices,
    )
    from services.investment_baseline import (
        DEFAULT_FCAS_SERVICES,
        derive_co_optimized_baseline,
    )
    from network_fees import get_settlement_interval

    db = get_db()
    interval_minutes = get_settlement_interval(params.region)
    fcas_services = [s for s in DEFAULT_FCAS_SERVICES if s in FCAS_COLUMN_MAP]

    yearly_price_data: list[dict] = []
    for year in params.backtest_years:
        energy_prices = _load_energy_prices(db, params.region, year, None, interval_minutes)
        if not energy_prices:
            continue
        fcas_prices = _load_fcas_prices(db, params.region, year, None, fcas_services)
        yearly_price_data.append({"energy_prices": energy_prices, "fcas_prices": fcas_prices})

    if not yearly_price_data:
        return None

    return derive_co_optimized_baseline(params, yearly_price_data, fcas_services=fcas_services)


# ---------------------------------------------------------------------------
# Route: /api/investment-analysis
# ---------------------------------------------------------------------------


@router.post(
    "/api/investment-analysis",
    summary="Run Market Entry Readiness analysis",
    description=(
        "Runs Market Entry Readiness analysis using standardized backtest-driven "
        "baselines when available. Response is positioned inside the market entry "
        "conclusion chain and includes decision-grade metadata for NEM plus "
        "traceability fields such as backtest_reference, backtest_observed, and "
        "backtest_fallback_used."
    ),
    responses=OPENAPI_ERROR_RESPONSES,
)
def investment_analysis(params: InvestmentParams, access_scope=None):
    """
    Compute BESS investment cash flow analysis using the Engine Layer:
    1. Base Case Evaluation
    2. Scenario Analysis
    3. Monte Carlo Simulation

    Integrates DegradationModel: when the user provides a degradation_rate,
    uses DegradationModel.from_user_input() and includes the model in the response.
    """
    try:
        # Delegate to server.py's implementation (which remains the source of truth
        # until Task 3.6 slims server.py). This ensures API contract is preserved.
        import server as _server

        if access_scope:
            _server._assert_scope_allows_internal_query(
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
            return _enrich_with_degradation_model(cached_response, params)

        inflight_key = _stable_cache_key({
            "scope": INVESTMENT_RESPONSE_CACHE_SCOPE,
            "request": request_payload,
            "data_version": data_version,
        })
        inflight_entry, inflight_kind = _acquire_inflight_entry(inflight_key)
        if inflight_kind == "remote":
            # 别的 worker 正在算同一份：等它写入共享 analysis_cache，而不是本地再算一遍
            remote_response = _await_remote_analysis(
                inflight_key=inflight_key,
                scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
                payload=request_payload,
                data_version=data_version,
            )
            if remote_response is not None:
                return _enrich_with_degradation_model(remote_response, params)
            # 属主已离场（崩溃/认领到期）：接管本地登记，自己算完
            inflight_entry, inflight_kind = _claim_inflight_after_owner_loss(inflight_key)
        if inflight_kind == "local":
            if not inflight_entry["event"].wait(timeout=_ANALYSIS_INFLIGHT_WAIT_TIMEOUT_SECONDS):
                raise HTTPException(
                    status_code=503,
                    detail="Analysis request timed out waiting for an in-flight computation",
                )
            if inflight_entry["error"] is not None:
                raise inflight_entry["error"]
            return _enrich_with_degradation_model(inflight_entry["response"], params)

        try:
            from services import investment_service as _svc

            backtest_summary = _svc.build_backtest_summary(params, data_version)

            avg_annual_cycles = backtest_summary["avg_annual_cycles"]

            # S2/B2: co-optimized joint energy+FCAS baseline (opt-in).
            coopt_baseline = None
            if params.revenue_baseline_mode == "co_optimized":
                coopt_baseline = _compute_co_optimized_baseline(params)

            if coopt_baseline is not None and coopt_baseline.years_used > 0:
                # Joint optimization replaces the additive arbitrage + FCAS sum,
                # eliminating the power-capacity double-count.
                # 方案 B（2026-08-05，任务记录附录 10）：套利基线用区域实测
                # 调度效率折扣替换文献 forecast_inefficiency，capture_rate 退出
                # 套利路径（实测值已含可达成性）；FCAS 仍乘 capture_rate。
                from engines.dispatch_efficiency import get_realized_efficiency
                realized_eff, _ = get_realized_efficiency(params.region, caliber="regional")
                baseline_arbitrage = coopt_baseline.energy_revenue * realized_eff
                arbitrage_baseline_source = "co_optimized_realized"
                baseline_fcas = coopt_baseline.fcas_revenue * params.revenue_capture_rate
                fcas_baseline_source = "co_optimized"
            else:
                baseline_arbitrage, arbitrage_baseline_source = _svc.derive_arbitrage_baseline(
                    params, backtest_summary
                )
                baseline_fcas, fcas_baseline_source = _svc.get_fcas_baseline(params, data_version)

            # FCAS implicit discharge → extra throughput cycles for degradation.
            if baseline_fcas > 0:
                if fcas_baseline_source == "historical_auto":
                    avg_fcas_price_per_mwh = (
                        baseline_fcas / (params.battery.power_mw * HOURS_PER_YEAR * params.revenue_capture_rate)
                        if params.battery.power_mw > 0 and params.revenue_capture_rate > 0
                        else 0.0
                    )
                    fcas_implicit_discharge_mwh = (
                        baseline_fcas / avg_fcas_price_per_mwh * params.fcas_activation_probability
                        if avg_fcas_price_per_mwh > 0
                        else 0.0
                    )
                else:
                    # A2: 15000 → fcas_revenue_per_mw_year (default FCAS $/MW/yr);
                    # 8760 → HOURS_PER_YEAR (annualize enablement to equivalent hours).
                    fcas_implicit_discharge_mwh = (
                        (baseline_fcas / params.fcas_revenue_per_mw_year) * params.battery.power_mw
                        * params.fcas_activation_probability * HOURS_PER_YEAR
                        if params.fcas_revenue_per_mw_year > 0
                        else 0.0
                    )
                avg_annual_cycles += (
                    fcas_implicit_discharge_mwh / params.battery.capacity_mwh
                    if params.battery.capacity_mwh > 0
                    else 0.0
                )

            annual_cycles_history = [avg_annual_cycles] * params.financial.project_life_years
            # DoD-severity from the backtest SoC trajectory (rainflow), applied to
            # the degradation model. 1.0 = full-depth cycles when unavailable.
            avg_dod_severity = backtest_summary.get("avg_dod_severity", 1.0)
            dod_severity_history = [avg_dod_severity] * params.financial.project_life_years

            from engines.financial_model import FinancialModel

            base_scenario_config = params.scenarios[0] if params.scenarios else None
            if not base_scenario_config:
                base_scenario_config = ScenarioConfig(name="Base")

            base_result = FinancialModel.run_scenario(
                params,
                base_scenario_config,
                baseline_arbitrage,
                baseline_fcas,
                annual_cycles_history,
                dod_severity_history,
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
                        dod_severity_history,
                    )
                )

            mc_result = None
            if params.monte_carlo.enabled:
                mc_result = FinancialModel.run_monte_carlo(
                    params,
                    baseline_arbitrage,
                    baseline_fcas,
                    annual_cycles_history,
                    dod_severity_history,
                )

            p3_decision = _svc.build_investment_p3_decision(params)
            decision_adjusted_scenarios = _svc.build_decision_adjusted_scenarios(
                params,
                annual_cycles_history,
                baseline_arbitrage,
                baseline_fcas,
                p3_decision,
                dod_severity_history,
            )
            decision_adjusted_result = (
                decision_adjusted_scenarios[0] if decision_adjusted_scenarios else None
            )
            decision_adjusted_monte_carlo = _svc.build_decision_adjusted_monte_carlo(
                params,
                annual_cycles_history,
                baseline_arbitrage,
                baseline_fcas,
                p3_decision,
                dod_severity_history,
            )

            response = _svc.build_investment_response(
                params=params,
                base_result=base_result,
                scenarios=scenarios,
                mc_result=mc_result,
                baseline_arbitrage=baseline_arbitrage,
                arbitrage_baseline_source=arbitrage_baseline_source,
                baseline_fcas=baseline_fcas,
                fcas_baseline_source=fcas_baseline_source,
                p3_decision=p3_decision,
                decision_adjusted_result=decision_adjusted_result,
                decision_adjusted_scenarios=decision_adjusted_scenarios,
                decision_adjusted_monte_carlo=decision_adjusted_monte_carlo,
                backtest_summary=backtest_summary,
            )
            # S2/B2: expose co-optimization comparison fields in response.
            if coopt_baseline is not None and coopt_baseline.years_used > 0:
                response["co_optimization"] = {
                    "mode": "co_optimized",
                    "energy_only_revenue": coopt_baseline.energy_only_revenue,
                    "co_optimization_uplift": coopt_baseline.co_optimization_uplift,
                    "total_net_revenue": coopt_baseline.total_net_revenue,
                    "years_used": coopt_baseline.years_used,
                    "status": coopt_baseline.status,
                }
            # U3: Decision Terminal — synthesize GO/NO_GO/WAIT recommendation.
            from services.decision_terminal import build_decision_terminal

            _m = base_result.metrics
            response["decision_terminal"] = build_decision_terminal(
                npv=_m.npv,
                irr=_m.irr,
                payback_years=_m.payback_years,
                min_dscr=_m.min_dscr,
                llcr=_m.llcr,
                total_capex=_m.total_capex,
                power_mw=params.battery.power_mw,
                project_life_years=params.financial.project_life_years,
                debt_tenor_years=params.financial.debt_tenor_years,
                irr_hurdle=params.financial.discount_rate,
                apply_cannibalization=params.apply_cannibalization,
                cannibalization_annual_growth_rate=params.cannibalization_annual_growth_rate,
                backtest_years_count=len(params.backtest_years),
            )
            response = _analysis_cache_store(
                scope=INVESTMENT_RESPONSE_CACHE_SCOPE,
                payload=request_payload,
                data_version=data_version,
                response_payload=response,
                store_response_cache=True,
            )
            response = _enrich_with_financial_accuracy_modules(response, params, base_result)
            response = _enrich_with_degradation_model(response, params)
            # Phase 2（2026-08-12）：FCAS 收益压缩风险标签（best-effort，失败降级）
            try:
                from services.fcas_compression import get_fcas_compression_label

                response["fcas_compression"] = get_fcas_compression_label()
            except Exception:  # noqa: BLE001
                response["fcas_compression"] = {
                    "available": False,
                    "risk_label": "fcas_revenue_compression",
                }
            inflight_entry["response"] = response
            return response
        except Exception as exc:
            inflight_entry["error"] = exc
            raise
        finally:
            _release_inflight_entry(inflight_key, inflight_entry)

    except HTTPException:
        raise
    except Exception as e:
        # S5/A4: map domain exceptions to machine-readable error codes.
        from services.exceptions import InvestmentAnalysisError

        if isinstance(e, InvestmentAnalysisError):
            logger.error(f"Investment analysis domain error [{e.error_code}]: {e}")
            raise HTTPException(
                status_code=e.status_code,
                detail={"code": e.error_code, "message": str(e), **e.detail},
            )
        logger.error(f"Investment analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Financial Accuracy Modules integration (Task 8.3)
# ---------------------------------------------------------------------------


def _enrich_with_financial_accuracy_modules(
    response: dict, params: InvestmentParams, base_result
) -> dict:
    """Post-process the investment analysis response with Financial Accuracy Modules.

    Integrates TaxModel, ForwardPriceEngine, and cost breakdown into the response
    when the corresponding optional parameters are provided. Maintains backward
    compatibility — omitted params leave the response unchanged.

    Args:
        response: The base investment analysis response dict.
        params: The original InvestmentParams from the request.
        base_result: The base ScenarioResult from FinancialModel.run_scenario().

    Returns:
        Enriched response dict with optional financial accuracy fields.
    """
    # 1. Attach cost_breakdown from base ScenarioResult (computed by CostStructureEngine in Task 8.4)
    if base_result.cost_breakdown is not None:
        response["cost_breakdown"] = base_result.cost_breakdown.model_dump()

    # 2. If tax_config is provided, run TaxModel for after-tax analysis
    if params.tax_config is not None:
        try:
            from engines.tax_model import TaxModel

            tax_model = TaxModel(config=params.tax_config)

            # Extract pre-tax cash flows from base result
            pre_tax_cash_flows: List[CashFlowYear] = base_result.cash_flows

            # Calculate capex — reuse FinancialModel's computed value (S5/A3 dedup).
            # Defensive getattr: degrade to zero capex (no depreciation shield)
            # instead of aborting the whole after-tax analysis if a caller
            # passes a metrics object missing the field.
            total_capex = getattr(base_result.metrics, "total_capex", 0.0)

            # Derive annual debt service from the base result metrics
            # Use the same debt sizing logic as FinancialModel
            import numpy_financial as npf

            tenor = min(
                params.financial.debt_tenor_years,
                params.financial.project_life_years,
            )
            debt_capacity = getattr(base_result.metrics, "debt_capacity", 0.0)
            if debt_capacity > 0:
                annual_debt_service = float(
                    -npf.pmt(params.financial.cost_of_debt, tenor, debt_capacity)
                )
            else:
                annual_debt_service = 0.0

            after_tax_result = tax_model.calculate_after_tax_cash_flows(
                pre_tax_cash_flows=pre_tax_cash_flows,
                capex=total_capex,
                annual_debt_service=annual_debt_service,
                debt_tenor=tenor,
                cost_of_debt=params.financial.cost_of_debt,
                discount_rate=params.financial.discount_rate,
            )

            response["tax_summary"] = after_tax_result.tax_summary.model_dump()
            response["after_tax_metrics"] = after_tax_result.model_dump()
            # Confirm the headline-basis annotation now that after-tax metrics
            # are genuinely available; the frontend prefers after-tax display.
            basis = response.get("metrics_basis")
            if isinstance(basis, dict):
                basis["after_tax_available"] = True
                basis["recommended_display_basis"] = "after_tax"

        except Exception as exc:
            logger.warning(
                "TaxModel integration failed, skipping after-tax analysis: %s", exc
            )
            # After-tax computation failed: keep the headline pre-tax and make
            # the annotation honest so the frontend does not promise after-tax.
            basis = response.get("metrics_basis")
            if isinstance(basis, dict):
                basis["after_tax_available"] = False
                basis["recommended_display_basis"] = "pre_tax"

    # 3. If forward_scenario is provided, run ForwardPriceEngine for all 3 scenarios
    if params.forward_scenario is not None:
        try:
            from deps import get_forward_price_engine
            from models.forward_price_models import ScenarioComparisonResult, ScenarioType

            engine = get_forward_price_engine()

            central_projection = engine.generate_20year_projection(
                region=params.region,
                scenario=ScenarioType.CENTRAL,
                battery=params.battery,
            )
            high_projection = engine.generate_20year_projection(
                region=params.region,
                scenario=ScenarioType.HIGH,
                battery=params.battery,
            )
            low_projection = engine.generate_20year_projection(
                region=params.region,
                scenario=ScenarioType.LOW,
                battery=params.battery,
            )

            comparison = ScenarioComparisonResult(
                region=params.region,
                central=central_projection,
                high=high_projection,
                low=low_projection,
            )

            response["scenario_projections"] = comparison.model_dump()

        except Exception as exc:
            logger.warning(
                "ForwardPriceEngine integration failed, skipping scenario projections: %s",
                exc,
            )

    return response


# ---------------------------------------------------------------------------
# DegradationModel integration
# ---------------------------------------------------------------------------


def _enrich_with_degradation_model(response: dict, params: InvestmentParams) -> dict:
    """Attach DegradationModel information to the investment analysis response.

    When the user provides a degradation_rate, uses DegradationModel.from_user_input()
    to create the model and includes it in the response payload.
    """
    try:
        degradation_model = DegradationModel.from_user_input(params.degradation_rate)
        response["degradation_model"] = degradation_model.model_dump()
    except ValueError:
        # If degradation_rate is invalid, still attach the default model
        degradation_model = DegradationModel.from_user_input(None)
        response["degradation_model"] = degradation_model.model_dump()
    return response
