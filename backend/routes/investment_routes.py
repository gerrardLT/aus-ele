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
# ---------------------------------------------------------------------------

_ANALYSIS_INFLIGHT_LOCK = threading.Lock()
_ANALYSIS_INFLIGHT: Dict[str, dict] = {}

# Max seconds a waiting request will block on an in-flight computation before
# giving up with 503. Prevents indefinite hangs if the owner thread stalls.
_ANALYSIS_INFLIGHT_WAIT_TIMEOUT_SECONDS = 60

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


def _acquire_inflight_entry(cache_key: str) -> tuple[dict, bool]:
    with _ANALYSIS_INFLIGHT_LOCK:
        entry = _ANALYSIS_INFLIGHT.get(cache_key)
        if entry is not None:
            return entry, False

        entry = {"event": threading.Event(), "response": None, "error": None}
        _ANALYSIS_INFLIGHT[cache_key] = entry
        return entry, True


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
        inflight_entry, is_owner = _acquire_inflight_entry(inflight_key)
        if not is_owner:
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
                efficiency_factor = max(0.0, 1.0 - params.forecast_inefficiency)
                baseline_arbitrage = (
                    coopt_baseline.energy_revenue * efficiency_factor * params.revenue_capture_rate
                )
                arbitrage_baseline_source = "co_optimized"
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

            # Calculate capex — reuse FinancialModel's computed value (S5/A3 dedup)
            total_capex = base_result.metrics.total_capex

            # Derive annual debt service from the base result metrics
            # Use the same debt sizing logic as FinancialModel
            import numpy_financial as npf

            tenor = min(
                params.financial.debt_tenor_years,
                params.financial.project_life_years,
            )
            debt_capacity = base_result.metrics.debt_capacity
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
