"""Anomaly Detection Service — U4: 市场异常主动检测.

Scans trading_price tables for:
- Price spikes (rrp > P99 threshold)
- FCAS price collapse (daily avg < 30% of historical mean)
- Negative price frequency anomaly

Returns structured anomaly events for the frontend AnomalyBadge.
"""

from __future__ import annotations

import logging
from typing import Optional

from deps import get_db

logger = logging.getLogger(__name__)

# Thresholds
SPIKE_PERCENTILE = 99
FCAS_COLLAPSE_RATIO = 0.3
NEGATIVE_PRICE_FREQ_THRESHOLD = 0.08  # >8% negative intervals = anomaly


def detect_anomalies(region: str, year: int) -> list[dict]:
    """Detect market anomalies for a given region and year.

    Returns a list of anomaly dicts:
        [{type, severity, description, related_stage, timestamp}]
    """
    # Defense-in-depth: validate year range before table name interpolation
    if not (2000 <= year <= 2100):
        return []

    db = get_db()
    anomalies: list[dict] = []
    table_name = f"trading_price_{year}"

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (table_name,),
            )
            if not cursor.fetchone():
                return []

            # --- Price spike detection ---
            cursor.execute(
                f"SELECT PERCENTILE_CONT(0.{SPIKE_PERCENTILE}) WITHIN GROUP (ORDER BY rrp_aud_mwh) FROM {table_name} WHERE region_id = %s",
                (region,),
            )
            row = cursor.fetchone()
            p99 = float(row[0]) if row and row[0] is not None else None

            if p99 and p99 > 500:  # Only flag if P99 itself is extreme
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE region_id = %s AND rrp_aud_mwh > %s",
                    (region, p99),
                )
                spike_count = cursor.fetchone()[0]
                if spike_count > 0:
                    anomalies.append({
                        "type": "price_spike",
                        "severity": "high" if p99 > 1000 else "medium",
                        "description": f"{spike_count} intervals exceeded P99 (${p99:.0f}/MWh)",
                        "related_stage": "market-screening",
                        "timestamp": f"{year}",
                    })

            # --- Negative price frequency ---
            cursor.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE region_id = %s",
                (region,),
            )
            total_intervals = cursor.fetchone()[0]

            if total_intervals > 0:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE region_id = %s AND rrp_aud_mwh < 0",
                    (region,),
                )
                neg_count = cursor.fetchone()[0]
                neg_freq = neg_count / total_intervals

                if neg_freq > NEGATIVE_PRICE_FREQ_THRESHOLD:
                    anomalies.append({
                        "type": "negative_price_frequency",
                        "severity": "medium",
                        "description": f"Negative prices in {neg_freq*100:.1f}% of intervals ({neg_count}/{total_intervals})",
                        "related_stage": "revenue-deep-dive",
                        "timestamp": f"{year}",
                    })

            # --- FCAS price collapse (check raisereg as proxy) ---
            try:
                cursor.execute(
                    f"SELECT AVG(raisereg_rrp) FROM {table_name} WHERE region_id = %s AND raisereg_rrp IS NOT NULL",
                    (region,),
                )
                avg_fcas = cursor.fetchone()[0]
                if avg_fcas is not None:
                    avg_fcas = float(avg_fcas)
                    # Check recent month vs overall
                    cursor.execute(
                        f"SELECT AVG(raisereg_rrp) FROM {table_name} WHERE region_id = %s AND raisereg_rrp IS NOT NULL AND settlement_date >= %s",
                        (region, f"{year}-12-01"),
                    )
                    recent_row = cursor.fetchone()
                    recent_fcas = float(recent_row[0]) if recent_row and recent_row[0] is not None else None

                    if recent_fcas is not None and avg_fcas > 0 and recent_fcas < avg_fcas * FCAS_COLLAPSE_RATIO:
                        anomalies.append({
                            "type": "fcas_collapse",
                            "severity": "high",
                            "description": f"FCAS raise-reg avg dropped to ${recent_fcas:.1f} (vs ${avg_fcas:.1f} historical)",
                            "related_stage": "revenue-deep-dive",
                            "timestamp": f"{year}-12",
                        })
            except Exception:
                pass  # raisereg_rrp column may not exist

    except Exception as e:
        logger.warning(f"Anomaly detection failed for {region}/{year}: {e}")

    return anomalies
