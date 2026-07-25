"""Anomaly detection API routes — U4.

GET /api/v1/anomalies/{region}?year=2025
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from services.anomaly_service import detect_anomalies

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])


@router.get("/{region}")
def get_anomalies(region: str, year: int = Query(default=2025)):
    """Detect market anomalies for a region/year."""
    anomalies = detect_anomalies(region, year)
    return {"region": region, "year": year, "anomalies": anomalies, "count": len(anomalies)}
