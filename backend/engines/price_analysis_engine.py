"""Price analysis engine — output unit fixed to $/MWh.

Performs pure statistical analysis on price time series without any
battery or capacity parameters influencing the result.
"""

from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel


class AnalysisMetadata(BaseModel):
    """Standard metadata for all analysis results."""

    market: str
    region_or_zone: str
    timezone: str = "Australia/Sydney"
    currency: str = "AUD"
    unit: str  # "$/MWh" | "$" | "MW" | "MWh"
    interval_minutes: int | None = None
    interval_seconds: int | None = None
    data_grade: str = "production"
    data_quality_score: float | None = None
    data_completeness: str = "complete"  # "complete" | "preview"
    coverage: dict | None = None
    freshness: str | None = None
    source_name: str | None = None
    source_version: str | None = None
    methodology_version: str | None = None
    computation_time_ms: int | None = None
    ignored_filters: list[str] | None = None
    warnings: list[str] | None = None


class PriceAnalysisResult(BaseModel):
    """Result of price analysis — unit is always $/MWh."""

    statistics: dict[str, float]
    distribution: list[dict[str, Any]]
    time_series: list[dict[str, Any]]
    metadata: AnalysisMetadata


class PriceAnalysisEngine:
    """Price analysis engine — output unit fixed to $/MWh.

    Performs pure statistical analysis on price time series.
    No battery parameters are used or accepted.
    """

    def analyze(
        self,
        prices: list[dict],
        *,
        region: str,
        market: str,
        interval_minutes: int = 5,
    ) -> PriceAnalysisResult:
        """Analyze a price time series and return $/MWh statistics.

        Args:
            prices: List of dicts with at least a 'price' key (and optionally 'timestamp').
            region: Market region/zone identifier (e.g. "NSW1").
            market: Market identifier (e.g. "NEM", "WEM").
            interval_minutes: Data interval in minutes (default 5).

        Returns:
            PriceAnalysisResult with statistics, distribution histogram, and time series.
        """
        price_values = [float(p["price"]) for p in prices]

        stats = self._compute_statistics(price_values)
        distribution = self._compute_distribution(price_values)
        time_series = self._build_time_series(prices)

        metadata = AnalysisMetadata(
            market=market,
            region_or_zone=region,
            unit="$/MWh",
            interval_minutes=interval_minutes,
        )

        return PriceAnalysisResult(
            statistics=stats,
            distribution=distribution,
            time_series=time_series,
            metadata=metadata,
        )

    def _compute_statistics(self, values: list[float]) -> dict[str, float]:
        """Compute descriptive statistics for price values."""
        if not values:
            return {
                "mean": 0.0,
                "median": 0.0,
                "p25": 0.0,
                "p75": 0.0,
                "max": 0.0,
                "min": 0.0,
            }

        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p25": self._percentile(sorted_values, 25),
            "p75": self._percentile(sorted_values, 75),
            "max": max(values),
            "min": min(values),
        }

    def _percentile(self, sorted_values: list[float], pct: int) -> float:
        """Calculate percentile using linear interpolation."""
        if not sorted_values:
            return 0.0
        n = len(sorted_values)
        if n == 1:
            return sorted_values[0]

        # Use linear interpolation (same as numpy default)
        k = (pct / 100.0) * (n - 1)
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_values[-1]
        d = k - f
        return sorted_values[f] + d * (sorted_values[c] - sorted_values[f])

    def _compute_distribution(self, values: list[float], num_bins: int = 20) -> list[dict[str, Any]]:
        """Compute a histogram distribution of price values."""
        if not values:
            return []

        min_val = min(values)
        max_val = max(values)

        # Handle case where all values are the same
        if min_val == max_val:
            return [{"bin_start": min_val, "bin_end": min_val, "count": len(values), "frequency": 1.0}]

        bin_width = (max_val - min_val) / num_bins
        bins: list[dict[str, Any]] = []

        for i in range(num_bins):
            bin_start = min_val + i * bin_width
            bin_end = min_val + (i + 1) * bin_width
            # Last bin includes the max value
            if i == num_bins - 1:
                count = sum(1 for v in values if bin_start <= v <= bin_end)
            else:
                count = sum(1 for v in values if bin_start <= v < bin_end)
            bins.append({
                "bin_start": round(bin_start, 4),
                "bin_end": round(bin_end, 4),
                "count": count,
                "frequency": round(count / len(values), 6),
            })

        return bins

    def _build_time_series(self, prices: list[dict]) -> list[dict[str, Any]]:
        """Build time series output from input price records."""
        return [
            {
                "timestamp": p.get("timestamp"),
                "price": float(p["price"]),
            }
            for p in prices
        ]
