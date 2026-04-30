from __future__ import annotations

from typing import Any


def build_result_metadata(
    *,
    market: str,
    region_or_zone: str,
    timezone: str,
    currency: str,
    unit: str,
    interval_minutes: int | None,
    data_grade: str,
    data_quality_score: float | None,
    coverage: dict[str, Any] | None,
    freshness: dict[str, Any] | None,
    source_name: str,
    source_version: str,
    methodology_version: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "market": market,
        "region_or_zone": region_or_zone,
        "timezone": timezone,
        "currency": currency,
        "unit": unit,
        "interval_minutes": interval_minutes,
        "data_grade": data_grade,
        "data_quality_score": data_quality_score,
        "coverage": dict(coverage) if coverage else {},
        "freshness": dict(freshness) if freshness else {},
        "source_name": source_name,
        "source_version": source_version,
        "methodology_version": methodology_version,
        "warnings": list(warnings) if warnings else [],
    }
