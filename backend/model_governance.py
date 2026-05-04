from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from connector_framework import list_connector_specs


def _parse_timestamp(timestamp_value: str | None) -> datetime | None:
    if not timestamp_value:
        return None
    normalized = str(timestamp_value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(str(timestamp_value).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    freshness = dict((metadata or {}).get("freshness") or {})
    last_updated_at = freshness.get("last_updated_at")
    parsed = _parse_timestamp(last_updated_at)
    lag_minutes = None
    status = "unknown"
    if parsed is not None:
        lag_minutes = max(0.0, round((datetime.now(timezone.utc) - parsed).total_seconds() / 60, 2))
        status = "fresh" if lag_minutes <= 240 else "delayed" if lag_minutes <= 1440 else "stale"
    return {
        "status": status,
        "last_updated_at": last_updated_at,
        "lag_minutes": lag_minutes,
    }


def _drift_payload(*, diagnostics: dict[str, Any] | None, calibration: dict[str, Any] | None, regime_error_attribution: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics = diagnostics or {}
    calibration = calibration or {}
    regime_error_attribution = regime_error_attribution or {}
    error_grade = diagnostics.get("error_grade")
    calibration_grade = calibration.get("summary_grade")
    status = "unknown"
    if diagnostics.get("status") == "available":
        status = "monitor"
        if error_grade in {"high_error", "severe_error"} or calibration_grade == "poor":
            status = "elevated"
    return {
        "status": status,
        "error_grade": error_grade,
        "calibration_grade": calibration_grade,
        "primary_gap_domain": diagnostics.get("primary_gap_domain"),
        "regime_attribution_status": regime_error_attribution.get("status"),
        "primary_regime": regime_error_attribution.get("primary_regime"),
    }


def _build_p2_forecast_value_attribution(evaluation: dict[str, Any] | None) -> dict[str, Any]:
    evaluation = evaluation or {}
    metrics = evaluation.get("metrics") or {}
    calibration = evaluation.get("calibration") or {}
    attribution = evaluation.get("regime_error_attribution") or {}
    diagnostics = evaluation.get("diagnostics") or {}

    if evaluation.get("backtest_status") != "evaluated":
        return {
            "status": "not_applicable",
            "reason": "p2_forecast_layer_has_no_evaluated_backtest_window",
        }

    mae = float(metrics.get("mae_aud_mwh") or 0.0)
    rmse = float(metrics.get("rmse_aud_mwh") or 0.0)
    brier_spike = float(metrics.get("brier_score_spike") or 0.0)
    brier_negative = float(metrics.get("brier_score_negative_price") or 0.0)
    sample_count = int((calibration.get("sample_count") or 0))
    regime_buckets = attribution.get("regime_buckets") or []

    weakest_regime = None
    weakest_regime_mae = None
    if regime_buckets:
        weakest = max(
            regime_buckets,
            key=lambda item: float(item.get("mae_aud_mwh") or 0.0),
        )
        weakest_regime = weakest.get("regime")
        weakest_regime_mae = float(weakest.get("mae_aud_mwh") or 0.0)

    error_cost_index = round(min(mae / 100.0, 1.0), 4)
    probability_skill_index = round(
        max(0.0, 1.0 - ((brier_spike + brier_negative) / 2.0)),
        4,
    )
    regime_reliability_index = round(
        max(0.0, 1.0 - min((weakest_regime_mae or mae) / 150.0, 1.0)),
        4,
    )
    overall_information_value_index = round(
        max(
            0.0,
            min(
                ((1.0 - error_cost_index) * 0.45)
                + (probability_skill_index * 0.30)
                + (regime_reliability_index * 0.25),
                1.0,
            ),
        ),
        4,
    )

    return {
        "status": "proxy_available",
        "method": "backtest_error_proxy_v1",
        "sample_count": sample_count,
        "expected_absolute_error_aud_mwh": round(mae, 4),
        "expected_tail_error_aud_mwh": round(rmse, 4),
        "error_cost_index": error_cost_index,
        "probability_skill_index": probability_skill_index,
        "regime_reliability_index": regime_reliability_index,
        "overall_information_value_index": overall_information_value_index,
        "weakest_regime": weakest_regime,
        "weakest_regime_mae_aud_mwh": round(weakest_regime_mae, 4) if weakest_regime_mae is not None else None,
        "calibration_grade": calibration.get("summary_grade"),
        "diagnostic_error_grade": diagnostics.get("error_grade"),
    }


def _disclaimer_payload(*, dataset_family: str | None, grade: str | None) -> dict[str, Any]:
    return {
        "investment_grade": False,
        "usage_scope": "research_and_operational_support_only",
        "reason_code": "preview_models_require_human_validation",
        "dataset_family": dataset_family,
        "model_grade": grade,
    }


def _freshness_status_from_lag(lag_minutes: float | None) -> str:
    if lag_minutes is None:
        return "unknown"
    if lag_minutes <= 240:
        return "fresh"
    if lag_minutes <= 1440:
        return "delayed"
    return "stale"


def _status_rank(status: str) -> int:
    order = {
        "stale": 0,
        "delayed": 1,
        "busy": 2,
        "monitor": 3,
        "available": 4,
        "fresh": 5,
        "idle": 6,
        "unknown": 7,
    }
    return order.get(status, 99)


def _build_quality_row_index(quality_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in quality_rows:
        source_id = row.get("source_id")
        if source_id and source_id not in indexed:
            indexed[source_id] = row
    return indexed


def _build_source_row(spec, quality_row: dict[str, Any] | None) -> dict[str, Any]:
    quality_row = quality_row or {}
    freshness_minutes = quality_row.get("freshness_minutes")
    freshness_status = _freshness_status_from_lag(freshness_minutes)
    issues = list(quality_row.get("issues_json") or [])
    status = "monitor" if issues else ("available" if freshness_status == "fresh" else freshness_status)
    if quality_row.get("quality_score") is None and freshness_status == "unknown":
        status = "unknown"
    return {
        "source_id": spec.source_id,
        "source_key": spec.source_id,
        "market": spec.market,
        "dataset_family": spec.dataset_family,
        "observation_kind": spec.observation_kind,
        "status": status,
        "freshness_status": freshness_status,
        "freshness_minutes": freshness_minutes,
        "last_updated_at": quality_row.get("computed_at"),
        "data_grade": quality_row.get("data_grade"),
        "quality_score": quality_row.get("quality_score"),
        "coverage_ratio": quality_row.get("coverage_ratio"),
        "issue_count": len(issues),
        "issues": issues,
        "dataset_key": quality_row.get("dataset_key"),
        "lineage": {
            "entrypoint": spec.entrypoint,
            "schema_mapping": spec.schema_mapping,
            "adapter": spec.adapter,
            "backfill_policy": spec.backfill_policy,
            "rate_limit": spec.rate_limit,
            "quality_checks": list(spec.quality_checks),
        },
    }


def _build_source_rows(quality_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quality_row_index = _build_quality_row_index(quality_rows)
    source_order = {
        row.get("source_id"): index
        for index, row in enumerate(quality_rows)
        if row.get("source_id")
    }
    rows = [
        _build_source_row(spec, quality_row_index.get(spec.source_id))
        for spec in list_connector_specs()
    ]
    rows.sort(
        key=lambda row: (
            0 if row.get("source_id") in source_order else 1,
            source_order.get(row.get("source_id"), 999),
            _status_rank(row.get("status", "unknown")),
            row.get("market") or "",
            row.get("source_id") or "",
        )
    )
    return rows


def _rollup_status(statuses: list[str]) -> str:
    normalized = [status for status in statuses if status]
    if not normalized:
        return "unknown"
    if any(status in {"stale", "elevated"} for status in normalized):
        return "elevated"
    if any(status in {"delayed", "monitor", "busy"} for status in normalized):
        return "monitor"
    if any(status in {"available", "fresh", "idle"} for status in normalized):
        return "available"
    return "unknown"


def _model_source_status(
    *,
    source_rows: list[dict[str, Any]],
    dataset_families: tuple[str, ...],
    upstream_models: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    family_set = set(dataset_families)
    relevant_rows = [row for row in source_rows if row.get("dataset_family") in family_set]
    observed_families = {row.get("dataset_family") for row in relevant_rows if row.get("dataset_family")}
    missing_families = [family for family in dataset_families if family not in observed_families]
    lineage_ready = all((row.get("lineage") or {}).get("schema_mapping") for row in relevant_rows) if relevant_rows else False
    freshness_states = [row.get("freshness_status") for row in relevant_rows if row.get("freshness_status")]
    direct_statuses = [row.get("status") for row in relevant_rows if row.get("status")]
    unknown_source_count = sum(1 for row in relevant_rows if row.get("status") == "unknown")
    issue_count = sum(int(row.get("issue_count") or 0) for row in relevant_rows)
    coverage_ratio = round(len(observed_families) / len(dataset_families), 4) if dataset_families else 1.0
    upstream_statuses = [row.get("status") for row in upstream_models if row.get("status")]
    rollup_status = _rollup_status(direct_statuses + upstream_statuses)

    if coverage_ratio < 1.0 or not lineage_ready:
        rollup_status = "elevated" if coverage_ratio < 0.75 else "monitor"
    elif unknown_source_count > 0:
        rollup_status = "elevated" if unknown_source_count >= max(2, len(relevant_rows) // 2 or 1) else "monitor"
    elif issue_count > 0 and rollup_status == "available":
        rollup_status = "monitor"

    quality_signal = "healthy"
    if coverage_ratio < 1.0:
        quality_signal = "partial_coverage"
    elif issue_count > 0:
        quality_signal = "issues_present"
    elif unknown_source_count > 0:
        quality_signal = "unverified_inputs"
    elif any(state == "delayed" for state in freshness_states):
        quality_signal = "freshness_watch"
    elif any(state == "stale" for state in freshness_states):
        quality_signal = "stale_inputs"

    freshness_status = _rollup_status(freshness_states)
    if freshness_status == "available":
        freshness_status = "fresh"

    return {
        "status": rollup_status,
        "freshness_status": freshness_status,
        "quality_signal": quality_signal,
        "lineage_status": "available" if lineage_ready else "partial",
        "coverage_status": "full" if coverage_ratio >= 1.0 else "partial",
        "coverage_ratio": coverage_ratio,
        "issue_count": issue_count,
        "unknown_source_count": unknown_source_count,
        "missing_dataset_families": missing_families,
        "source_count": len(relevant_rows),
    }


def _build_summary_drift_payload(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    p2_row = _model_source_status(
        source_rows=source_rows,
        dataset_families=(
            "load_actual",
            "load_forecast",
            "wind_forecast",
            "wind_actual",
            "solar_forecast",
            "solar_actual",
            "rooftop_pv",
            "weather",
            "settlement",
        ),
    )
    p2_model = {
        "model_key": "p2_forecast_layer",
        **p2_row,
        "forecast_value_status": "proxy_available",
        "reason": "quality-backed drift rollup from forecast-critical source freshness, lineage, and issue signals",
    }

    p3_row = _model_source_status(
        source_rows=source_rows,
        dataset_families=(
            "settlement",
            "reserve_requirement",
            "reserve_shortfall",
            "unit_availability",
            "interconnector_flow",
            "weather",
        ),
        upstream_models=(p2_model,),
    )
    p3_model = {
        "model_key": "p3_bess_decision",
        **p3_row,
        "forecast_value_status": "available",
        "reason": "quality-backed drift rollup from dispatch-critical source freshness plus P2 upstream dependency",
    }

    models = [p2_model, p3_model]
    overall_status = _rollup_status([model.get("status") for model in models])
    if overall_status == "unknown":
        overall_status = "monitor"

    monitored_model_count = sum(1 for model in models if model.get("status") in {"monitor", "elevated"})
    delayed_input_count = sum(
        1
        for row in source_rows
        if row.get("freshness_status") in {"delayed", "stale"} or int(row.get("issue_count") or 0) > 0
    )

    return {
        "status": overall_status,
        "reason": (
            "quality-backed system drift rollup derived from source freshness, lineage coverage, "
            "dataset-family completeness, and model dependency health"
        ),
        "models": models,
        "monitored_model_count": monitored_model_count,
        "delayed_or_flagged_input_count": delayed_input_count,
    }


def build_p2_governance_payload(*, metadata: dict[str, Any], evaluation: dict[str, Any] | None) -> dict[str, Any]:
    evaluation = evaluation or {}
    return {
        "lineage": dict((metadata or {}).get("lineage") or {}),
        "freshness": _freshness_payload(metadata),
        "drift": _drift_payload(
            diagnostics=evaluation.get("diagnostics"),
            calibration=evaluation.get("calibration"),
            regime_error_attribution=evaluation.get("regime_error_attribution"),
        ),
        "forecast_value_attribution": _build_p2_forecast_value_attribution(evaluation),
        "disclaimer": _disclaimer_payload(
            dataset_family=(metadata or {}).get("dataset_family"),
            grade=(metadata or {}).get("grade"),
        ),
    }


def build_p3_governance_payload(
    *,
    metadata: dict[str, Any],
    diagnostics: dict[str, Any] | None,
    calibration: dict[str, Any] | None,
    regime_error_attribution: dict[str, Any] | None,
    decision_payload: dict[str, Any],
) -> dict[str, Any]:
    revenue_attribution = (decision_payload or {}).get("revenue_attribution") or {}
    strategy_bundle = (decision_payload or {}).get("strategy_bundle") or {}
    baseline_net = float(((strategy_bundle.get("rule_based_dispatch") or {}).get("net_revenue")) or 0.0)
    adjusted_net = float((revenue_attribution.get("net_revenue_after_decision_adjustments")) or 0.0)
    net_uplift = round(adjusted_net - baseline_net, 4)
    uplift_ratio = round((adjusted_net / baseline_net), 6) if baseline_net > 0 else None
    return {
        "lineage": dict((metadata or {}).get("lineage") or {}),
        "freshness": _freshness_payload(metadata),
        "drift": _drift_payload(
            diagnostics=diagnostics,
            calibration=calibration,
            regime_error_attribution=regime_error_attribution,
        ),
        "forecast_value_attribution": {
            "status": "available",
            "baseline_net_revenue": baseline_net,
            "decision_adjusted_net_revenue": adjusted_net,
            "net_uplift": net_uplift,
            "uplift_ratio": uplift_ratio,
            "timing_alpha": revenue_attribution.get("timing_alpha"),
            "regime_capture_alpha": revenue_attribution.get("regime_capture_alpha"),
            "fcas_stack_proxy": revenue_attribution.get("fcas_stack_proxy"),
            "scenario_spread": revenue_attribution.get("scenario_spread"),
        },
        "disclaimer": _disclaimer_payload(
            dataset_family=(metadata or {}).get("dataset_family"),
            grade=(metadata or {}).get("grade"),
        ),
    }


def build_governance_summary_payload(
    *,
    source_freshness: dict[str, Any],
    quality_summary: dict[str, Any],
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    quality_rows = list(quality_rows or [])
    sources = list(source_freshness.get("sources") or [])
    source_rows = _build_source_rows(quality_rows)
    delayed_sources = [
        source for source in source_rows
        if source.get("status") in {"delayed", "stale", "busy", "monitor"}
    ]
    drift_payload = _build_summary_drift_payload(source_rows)
    return {
        "freshness": source_freshness,
        "quality": quality_summary,
        "source_rows": source_rows,
        "drift": drift_payload,
        "disclaimer": {
            "investment_grade": False,
            "usage_scope": "research_and_operational_support_only",
            "reason_code": "non_investment_grade_governance_summary",
            "human_validation_required": True,
            "binding_scope": "research_preview_only",
        },
        "summary": {
            "source_count": len(source_rows),
            "delayed_source_count": len(delayed_sources),
            "market_count": ((quality_summary.get("summary") or {}).get("market_count")),
            "snapshot_count": ((quality_summary.get("summary") or {}).get("snapshot_count")),
            "operational_source_count": len(sources),
            "monitored_model_count": drift_payload.get("monitored_model_count"),
            "delayed_or_flagged_input_count": drift_payload.get("delayed_or_flagged_input_count"),
        },
    }
