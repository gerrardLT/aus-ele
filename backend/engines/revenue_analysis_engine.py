"""Revenue analysis engine — output unit fixed to $.

Calculates revenue based on price data and battery physical parameters
(power, energy capacity, round-trip efficiency, degradation, network fees).
"""

from __future__ import annotations

from math import sqrt
from typing import Any

from pydantic import BaseModel

from .exceptions import DimensionMismatchError
from .price_analysis_engine import AnalysisMetadata


class RevenueAnalysisResult(BaseModel):
    """Result of revenue analysis — unit is always $."""

    total_revenue: float
    gross_revenue: float
    net_revenue: float
    costs: dict[str, float]
    interval_revenues: list[dict[str, Any]]
    summary: dict[str, Any]
    metadata: AnalysisMetadata


class RevenueAnalysisEngine:
    """Revenue analysis engine — output unit fixed to $.

    Calculates revenue from price series combined with battery physical
    parameters. Validates input dimensions to prevent mixing price
    statistics ($/MWh) with revenue calculations ($).
    """

    def calculate(
        self,
        prices: list[dict],
        *,
        power_mw: float,
        energy_mwh: float,
        round_trip_efficiency: float,
        degradation_rate: float | None = None,
        network_fee_per_mwh: float = 0.0,
    ) -> RevenueAnalysisResult:
        """Calculate revenue from price series and battery parameters.

        Args:
            prices: List of dicts with 'price' key (and optionally 'timestamp',
                    'interval_hours'). Must be raw price series, not statistics.
            power_mw: Battery power capacity in MW.
            energy_mwh: Battery energy capacity in MWh.
            round_trip_efficiency: Round-trip efficiency (0 to 1).
            degradation_rate: Optional annual degradation rate (0 to 0.15).
            network_fee_per_mwh: Network fee per MWh of discharge (default 0).

        Returns:
            RevenueAnalysisResult with revenue breakdown and metadata.
        """
        one_way_efficiency = sqrt(round_trip_efficiency)

        # Apply degradation factor to effective capacity if provided
        effective_energy_mwh = energy_mwh
        if degradation_rate is not None and degradation_rate > 0:
            # Apply a simple mid-period degradation factor for single-period analysis
            effective_energy_mwh = energy_mwh * (1.0 - degradation_rate / 2.0)

        gross_revenue = 0.0
        total_network_fees = 0.0
        total_degradation_cost = 0.0
        interval_revenues: list[dict[str, Any]] = []

        for record in prices:
            price = float(record["price"])
            interval_hours = float(record.get("interval_hours", 5.0 / 60.0))

            # Maximum energy that can be discharged in this interval
            max_discharge_mwh = min(
                power_mw * interval_hours,
                effective_energy_mwh,
            )

            # Revenue from discharging at this price (simplified: assumes full discharge
            # when price is positive, accounting for efficiency losses)
            if price > 0:
                discharge_mwh = max_discharge_mwh * one_way_efficiency
                interval_gross = discharge_mwh * price
                interval_network_fee = discharge_mwh * network_fee_per_mwh
            else:
                discharge_mwh = 0.0
                interval_gross = 0.0
                interval_network_fee = 0.0

            gross_revenue += interval_gross
            total_network_fees += interval_network_fee

            interval_revenues.append({
                "timestamp": record.get("timestamp"),
                "price": price,
                "interval_hours": interval_hours,
                "discharge_mwh": discharge_mwh,
                "gross_revenue": interval_gross,
                "network_fee": interval_network_fee,
            })

        # Degradation cost estimate (proportional to throughput)
        total_discharge_mwh = sum(r["discharge_mwh"] for r in interval_revenues)
        if degradation_rate is not None:
            total_degradation_cost = total_discharge_mwh * degradation_rate * 0.5
        else:
            total_degradation_cost = 0.0

        net_revenue = gross_revenue - total_network_fees - total_degradation_cost

        metadata = AnalysisMetadata(
            market="NEM",
            region_or_zone="NSW1",
            unit="$",
        )

        return RevenueAnalysisResult(
            total_revenue=net_revenue,
            gross_revenue=gross_revenue,
            net_revenue=net_revenue,
            costs={
                "network_fees": total_network_fees,
                "degradation": total_degradation_cost,
            },
            interval_revenues=interval_revenues,
            summary={
                "total_discharge_mwh": total_discharge_mwh,
                "power_mw": power_mw,
                "energy_mwh": energy_mwh,
                "effective_energy_mwh": effective_energy_mwh,
                "round_trip_efficiency": round_trip_efficiency,
                "degradation_rate": degradation_rate,
                "network_fee_per_mwh": network_fee_per_mwh,
            },
            metadata=metadata,
        )

    def validate_input_dimensions(self, input_data: dict) -> None:
        """Validate input dimensions before revenue calculation.

        Raises DimensionMismatchError if the input is a price statistics result
        (unit == "$/MWh") rather than a raw price series.

        Args:
            input_data: Dict that may contain a 'metadata' key with 'unit' field.

        Raises:
            DimensionMismatchError: If input has metadata.unit == "$/MWh".
        """
        if input_data.get("metadata", {}).get("unit") == "$/MWh":
            raise DimensionMismatchError(
                expected_unit="raw_price_series",
                received_unit="$/MWh",
                message="价格统计结果不能直接用于收入计算，请使用原始价格序列",
            )
