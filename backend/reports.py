from __future__ import annotations

from statistics import mean

from market_screening import build_market_screening_payload
from result_metadata import build_result_metadata


def _fetch_price_rows(db, *, year: int, region: str, month: str | None) -> list[dict]:
    table_name = f"trading_price_{year}"
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            return []
        query = f"""
            SELECT settlement_date, region_id, rrp_aud_mwh
            FROM {table_name}
            WHERE region_id = ?
        """
        params = [region]
        if month:
            query += " AND settlement_date LIKE ?"
            params.append(f"{year}-{month}-%")
        query += " ORDER BY settlement_date ASC"
        rows = cursor.execute(query, tuple(params)).fetchall()
    return [{"settlement_date": row[0], "region_id": row[1], "rrp_aud_mwh": float(row[2] or 0.0)} for row in rows]


def _price_summary(rows: list[dict]) -> dict:
    if not rows:
        return {"avg_price": 0.0, "max_price": 0.0, "min_price": 0.0, "negative_ratio_pct": 0.0}
    prices = [row["rrp_aud_mwh"] for row in rows]
    return {
        "avg_price": round(mean(prices), 2),
        "max_price": round(max(prices), 2),
        "min_price": round(min(prices), 2),
        "negative_ratio_pct": round(sum(1 for price in prices if price < 0) / len(prices) * 100.0, 2),
    }


def generate_report_payload(
    db,
    *,
    report_type: str,
    year: int,
    region: str,
    month: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
) -> dict:
    rows = _fetch_price_rows(db, year=year, region=region, month=month)
    screening = build_market_screening_payload(db, year=year)
    candidate = next((item for item in screening["items"] if item["candidate_key"] == f"NEM:{region}" or item["region_or_zone"] == region), None)
    market_snapshot = _price_summary(rows)

    if report_type == "monthly_market_report":
        sections = [
            {
                "section_key": "executive_summary",
                "title": "Executive Summary",
                "summary": f"{region} average price was {market_snapshot['avg_price']} with peak {market_snapshot['max_price']} in the selected month.",
            },
            {
                "section_key": "market_snapshot",
                "title": "Market Snapshot",
                "summary": market_snapshot,
            },
            {
                "section_key": "screening_position",
                "title": "Screening Position",
                "summary": candidate or {},
            },
        ]
        title = f"{year}-{month or 'ALL'} Monthly Market Report | {region}"
    elif report_type == "investment_memo_draft":
        sections = [
            {
                "section_key": "investment_case",
                "title": "Investment Case",
                "summary": f"{region} shows average price {market_snapshot['avg_price']} and screening score {(candidate or {}).get('overall_score', 0)} for a BESS 2h asset.",
            },
            {
                "section_key": "market_evidence",
                "title": "Market Evidence",
                "summary": market_snapshot,
            },
            {
                "section_key": "risk_flags",
                "title": "Risk Flags",
                "summary": {
                    "negative_ratio_pct": market_snapshot["negative_ratio_pct"],
                    "data_quality_score": (candidate or {}).get("data_quality_score"),
                    "caveats": (candidate or {}).get("caveats", []),
                },
            },
        ]
        title = f"Investment Memo Draft | {region} | {year}"
    else:
        raise ValueError(f"Unsupported report_type: {report_type}")

    return {
        "report_type": report_type,
        "title": title,
        "report_context": {
            "year": year,
            "region": region,
            "month": month,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
        },
        "sections": sections,
        "reproducibility": {
            "report_inputs": {
                "report_type": report_type,
                "year": year,
                "region": region,
                "month": month,
                "organization_id": organization_id,
                "workspace_id": workspace_id,
            },
            "source_version": db.get_last_update_time() or "report_v1",
            "methodology_version": "report_payload_v1",
            "screening_reference_version": screening["metadata"]["methodology_version"],
        },
        "metadata": build_result_metadata(
            market="REPORT",
            region_or_zone=region,
            timezone="Australia/Sydney",
            currency="mixed",
            unit="report_payload",
            interval_minutes=None,
            data_grade="analytical-preview",
            data_quality_score=(candidate or {}).get("data_quality_score"),
            coverage={"row_count": len(rows)},
            freshness={"last_updated_at": db.get_last_update_time()},
            source_name="aus-ele",
            source_version=db.get_last_update_time() or "report_v1",
            methodology_version="report_payload_v1",
            warnings=["preview_only"] if region == "WEM" else [],
        ),
    }
