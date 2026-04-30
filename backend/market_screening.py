from __future__ import annotations

import math
import os
from collections import defaultdict
from statistics import mean

from data_quality import compute_quality_snapshots
from entsoe_finland import fetch_finland_day_ahead_summary
from fingrid.catalog import get_dataset_config
from fcas_opportunity import summarize_nem_fcas_opportunity
from result_metadata import build_result_metadata


SCREENING_PROFILE = {
    "power_mw": 100.0,
    "duration_hours": 2.0,
}

NEM_REGIONS = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(len(ordered) - 1, idx))]


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _quality_by_market(db) -> dict[str, float]:
    rows = db.fetch_data_quality_snapshots()
    if not rows:
        rows = compute_quality_snapshots(db)
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        score = row.get("quality_score")
        if score is not None:
            buckets[row["market"]].append(float(score))
    return {market: mean(scores) * 100.0 for market, scores in buckets.items() if scores}


def _diversification_score(values: list[float]) -> float:
    if not values:
        return 0.0
    positives = [max(value, 0.0) for value in values]
    total = sum(positives)
    if total <= 0:
        return 0.0
    top_share = max(positives) / total
    return _clamp((1.0 - top_share) * 100.0)


def _summarize_price_shape(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "spread_score": 0.0,
            "volatility_score": 0.0,
            "negative_ratio_pct": 0.0,
            "avg_price": 0.0,
            "p90_p10_spread": 0.0,
        }
    p10 = _percentile(values, 0.10)
    p90 = _percentile(values, 0.90)
    avg_price = mean(values)
    spread = p90 - p10
    negative_ratio = sum(1 for value in values if value < 0) / len(values)
    volatility = _stddev(values)
    return {
        "spread_score": round(_clamp((spread / 200.0) * 100.0), 1),
        "volatility_score": round(_clamp((volatility / (abs(avg_price) + 1.0)) * 140.0), 1),
        "negative_ratio_pct": round(negative_ratio * 100.0, 1),
        "avg_price": round(avg_price, 2),
        "p90_p10_spread": round(spread, 2),
    }


def _overall_score(item: dict) -> float:
    return round(
        (
            item["spread_score"] * 0.18
            + item["volatility_score"] * 0.12
            + item["storage_fit_score"] * 0.20
            + item["fcas_or_ess_opportunity_score"] * 0.20
            + item["grid_risk_score"] * 0.10
            + item["revenue_concentration_score"] * 0.10
            + item["data_quality_score"] * 0.10
        ),
        1,
    )


def _rank(items: list[dict]) -> list[dict]:
    ordered = sorted(items, key=lambda item: item["overall_score"], reverse=True)
    for idx, item in enumerate(ordered, start=1):
        item["rank"] = idx
    return ordered


def _build_nem_candidates(db, *, year: int, quality_scores: dict[str, float]) -> list[dict]:
    table_name = f"trading_price_{year}"
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            return []
        cursor.execute(
            f"""
            SELECT settlement_date, region_id, rrp_aud_mwh,
                   raise1sec_rrp, raise6sec_rrp, raise60sec_rrp, raise5min_rrp, raisereg_rrp,
                   lower1sec_rrp, lower6sec_rrp, lower60sec_rrp, lower5min_rrp, lowerreg_rrp
            FROM {table_name}
            ORDER BY settlement_date ASC
            """
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    by_region: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["region_id"] in NEM_REGIONS:
            by_region[row["region_id"]].append(row)

    items = []
    for region, region_rows in by_region.items():
        prices = [float(row.get("rrp_aud_mwh") or 0.0) for row in region_rows]
        price_shape = _summarize_price_shape(prices)
        opportunity = summarize_nem_fcas_opportunity(
            region_rows,
            capacity_mw=SCREENING_PROFILE["power_mw"],
            duration_hours=SCREENING_PROFILE["duration_hours"],
        )
        service_nets = [item["net_incremental_revenue_k"] for item in opportunity["service_breakdown"]]
        storage_fit = _clamp(
            price_shape["spread_score"] * 0.5
            + price_shape["volatility_score"] * 0.2
            + price_shape["negative_ratio_pct"] * 0.3
        )
        fcas_score = _clamp(
            opportunity["summary"]["total_net_incremental_revenue_k"] * 0.05
            + opportunity["summary"]["viable_service_count"] * 12.0
        )
        grid_risk = _clamp(price_shape["spread_score"] * 0.65 + price_shape["volatility_score"] * 0.35)
        item = {
            "candidate_key": f"NEM:{region}",
            "market": "NEM",
            "region_or_zone": region,
            "label": region,
            "asset_profile": "BESS 2h",
            "spread_score": price_shape["spread_score"],
            "volatility_score": price_shape["volatility_score"],
            "storage_fit_score": round(storage_fit, 1),
            "fcas_or_ess_opportunity_score": round(fcas_score, 1),
            "grid_risk_score": round(grid_risk, 1),
            "revenue_concentration_score": round(_diversification_score(service_nets), 1),
            "data_quality_score": round(quality_scores.get("NEM", 0.0), 1),
            "supporting_metrics": {
                "avg_price": price_shape["avg_price"],
                "p90_p10_spread": price_shape["p90_p10_spread"],
                "negative_ratio_pct": price_shape["negative_ratio_pct"],
                "viable_service_count": opportunity["summary"]["viable_service_count"],
                "net_incremental_revenue_k": opportunity["summary"]["total_net_incremental_revenue_k"],
                "row_count": len(region_rows),
            },
            "caveats": [],
        }
        item["overall_score"] = _overall_score(item)
        items.append(item)
    return items


def _build_wem_candidates(db, *, year: int, quality_scores: dict[str, float]) -> list[dict]:
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT dispatch_interval, energy_price
            FROM {db.WEM_ESS_MARKET_TABLE}
            WHERE dispatch_interval LIKE ?
            ORDER BY dispatch_interval ASC
            """,
            (f"{year}-%",),
        )
        price_rows = cursor.fetchall()

    if not price_rows:
        return []

    prices = [float(row[1] or 0.0) for row in price_rows]
    price_shape = _summarize_price_shape(prices)

    # Reuse the existing FCAS preview analysis path without creating a server import cycle.
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT m.*, c.binding_count, c.near_binding_count, c.binding_max_shadow_price
            FROM {db.WEM_ESS_MARKET_TABLE} m
            LEFT JOIN {db.WEM_ESS_CONSTRAINT_TABLE} c ON c.dispatch_interval = m.dispatch_interval
            WHERE m.dispatch_interval LIKE ?
            ORDER BY m.dispatch_interval ASC
            """,
            (f"{year}-%",),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    service_revenues = []
    scarcity_acc = []
    opportunity_acc = []
    for row in rows:
        scarcity_acc.append((row.get("binding_count") or 0) * 12.0 + (row.get("binding_max_shadow_price") or 0.0) / 8.0)
        opportunity_acc.append(
            (row.get("regulation_raise_price") or 0.0)
            + (row.get("regulation_lower_price") or 0.0)
            + (row.get("contingency_raise_price") or 0.0)
            + (row.get("contingency_lower_price") or 0.0)
            + (row.get("rocof_price") or 0.0)
        )
        service_revenues.extend(
            [
                float(row.get("regulation_raise_price") or 0.0),
                float(row.get("regulation_lower_price") or 0.0),
                float(row.get("contingency_raise_price") or 0.0),
                float(row.get("contingency_lower_price") or 0.0),
                float(row.get("rocof_price") or 0.0),
            ]
        )

    scarcity_score = round(_clamp(mean(scarcity_acc)), 1) if scarcity_acc else 0.0
    opportunity_score = round(_clamp(mean(opportunity_acc) * 1.5), 1) if opportunity_acc else 0.0
    quality_score = round(quality_scores.get("WEM", 0.0), 1)
    item = {
        "candidate_key": "WEM:WEM",
        "market": "WEM",
        "region_or_zone": "WEM",
        "label": "WEM",
        "asset_profile": "BESS 2h",
        "spread_score": price_shape["spread_score"],
        "volatility_score": price_shape["volatility_score"],
        "storage_fit_score": round(_clamp(price_shape["spread_score"] * 0.45 + opportunity_score * 0.35 + scarcity_score * 0.20), 1),
        "fcas_or_ess_opportunity_score": opportunity_score,
        "grid_risk_score": scarcity_score,
        "revenue_concentration_score": round(_diversification_score(service_revenues), 1),
        "data_quality_score": quality_score,
        "supporting_metrics": {
            "avg_price": price_shape["avg_price"],
            "p90_p10_spread": price_shape["p90_p10_spread"],
            "coverage_intervals": len(rows),
            "preview_mode": "slim_preview",
        },
        "caveats": ["preview_only", "not_investment_grade"],
        "preview_caveat": "WEM screening uses slim preview ESS tables and remains analytical-preview only.",
    }
    item["overall_score"] = _overall_score(item)
    return [item]


def _build_fingrid_candidates(db, *, year: int, quality_scores: dict[str, float]) -> list[dict]:
    dataset = get_dataset_config("317")
    rows = db.fetch_fingrid_series(dataset_id="317")
    year_rows = [row for row in rows if str(row.get("timestamp_utc", "")).startswith(f"{year}-")]
    if not year_rows:
        return []

    values = [float(row.get("value") or 0.0) for row in year_rows]
    price_shape = _summarize_price_shape(values)
    avg_value = mean(values) if values else 0.0
    source_stack = "fingrid_only"
    spot_avg_price = None
    entsoe_prices: list[float] = []

    if os.environ.get("ENTSOE_SECURITY_TOKEN"):
        try:
            entsoe_payload = fetch_finland_day_ahead_summary()
            entsoe_prices = [
                float(item["price"])
                for item in entsoe_payload.get("series", [])
                if str(item.get("timestamp_utc", "")).startswith(f"{year}-")
            ]
            if entsoe_prices:
                spot_avg_price = round(mean(entsoe_prices), 2)
                source_stack = "fingrid+entsoe"
        except Exception:
            entsoe_prices = []

    combined_shape = _summarize_price_shape(entsoe_prices) if entsoe_prices else price_shape
    item = {
        "candidate_key": "FINGRID:FI",
        "market": "FINGRID",
        "region_or_zone": "FI",
        "label": "Finland",
        "asset_profile": "BESS 2h",
        "spread_score": combined_shape["spread_score"],
        "volatility_score": combined_shape["volatility_score"],
        "storage_fit_score": round(_clamp(combined_shape["spread_score"] * 0.25 + combined_shape["volatility_score"] * 0.25 + avg_value * 1.1), 1),
        "fcas_or_ess_opportunity_score": round(_clamp(avg_value * 1.8), 1),
        "grid_risk_score": round(_clamp(combined_shape["volatility_score"] * 0.55 + combined_shape["spread_score"] * 0.25), 1),
        "revenue_concentration_score": 20.0,
        "data_quality_score": round(quality_scores.get("FINGRID", 0.0), 1),
        "supporting_metrics": {
            "avg_price": round(avg_value, 2),
            "p90_p10_spread": combined_shape["p90_p10_spread"],
            "record_count": len(year_rows),
            "dataset_id": "317",
            "source_stack": source_stack,
            "spot_avg_price": spot_avg_price,
        },
        "caveats": ["single_service_market", "analytical_preview"] + (["multi_source_preview"] if entsoe_prices else []),
        "preview_caveat": (
            "Finland screening combines Fingrid reserve-capacity pricing with ENTSO-E day-ahead spot context, but still does not represent a full power-market stack."
            if entsoe_prices
            else "Finland screening currently reflects Fingrid reserve-capacity pricing only, not a full power-market stack."
        ),
    }
    item["overall_score"] = _overall_score(item)
    return [item]


def build_market_screening_payload(db, *, year: int) -> dict:
    quality_scores = _quality_by_market(db)
    items = []
    items.extend(_build_nem_candidates(db, year=year, quality_scores=quality_scores))
    items.extend(_build_wem_candidates(db, year=year, quality_scores=quality_scores))
    items.extend(_build_fingrid_candidates(db, year=year, quality_scores=quality_scores))
    ranked = _rank(items)

    return {
        "year": year,
        "asset_profile": "BESS 2h",
        "summary": {
            "candidate_count": len(ranked),
            "markets_covered": sorted({item["market"] for item in ranked}),
        },
        "items": ranked,
        "metadata": build_result_metadata(
            market="MULTI",
            region_or_zone="SCREENING",
            timezone="UTC",
            currency="mixed",
            unit="score_0_100",
            interval_minutes=None,
            data_grade="analytical-preview",
            data_quality_score=round(mean(quality_scores.values()), 1) if quality_scores else None,
            coverage={"candidate_count": len(ranked)},
            freshness={"last_updated_at": db.get_last_update_time()},
            source_name="AEMO+Fingrid",
            source_version=db.get_last_update_time() or "market_screening_v1",
            methodology_version="market_screening_v1",
            warnings=["heuristic_scores"],
        ),
    }
