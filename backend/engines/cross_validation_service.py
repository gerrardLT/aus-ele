"""Cross-Validation Service.

聚合多数据源对同一数据点的估计值，计算差异百分比，
支持煤电退役日期、收入基准、价格预测三类交叉验证。

Requirements: 7.1, 7.2, 7.3, 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.forward_price_models import EventRegistry, EventType, ScenarioType
from models.narrative_models import CrossValidationEntry, CrossValidationResponse

logger = logging.getLogger(__name__)


class CrossValidationService:
    """多源交叉验证服务。

    Aggregates data from multiple independent sources for the same data points,
    calculates discrepancy percentages, and flags stale sources.

    Graceful degradation: if the external evidence file is unavailable or empty,
    returns platform-only data without raising errors.
    """

    def __init__(
        self,
        evidence_path: Path,
        event_registry: EventRegistry,
    ) -> None:
        self.evidence_path = evidence_path
        self.event_registry = event_registry
        self.evidence: Dict[str, Any] = self._load_evidence()

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    def _load_evidence(self) -> Dict[str, Any]:
        """Load external source data from financial_evidence.json.

        Returns an empty dict if the file doesn't exist or cannot be parsed,
        enabling graceful degradation to platform-only data.
        """
        if not self.evidence_path.exists():
            logger.warning(
                "Evidence file not found: %s — cross-validation will use platform data only.",
                self.evidence_path,
            )
            return {}

        try:
            with open(self.evidence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Failed to parse evidence file %s: %s — using platform data only.",
                self.evidence_path,
                exc,
            )
            return {}

        if not data:
            logger.warning("Evidence file is empty — using platform data only.")
            return {}

        return data

    # -------------------------------------------------------------------------
    # Staleness Check
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_stale(source_date: date) -> bool:
        """Check if a source date is more than 12 months before today."""
        today = date.today()
        # 12 months ago: same day last year (handle leap year edge cases)
        try:
            threshold = today.replace(year=today.year - 1)
        except ValueError:
            # Feb 29 → Feb 28 in non-leap year
            threshold = today.replace(year=today.year - 1, day=28)
        return source_date < threshold

    # -------------------------------------------------------------------------
    # Coal Retirement Cross-Validation
    # -------------------------------------------------------------------------

    def compare_coal_retirements(self) -> List[CrossValidationEntry]:
        """对比煤电退役日期：平台 vs AEMO ISP vs 运营商公告。

        Aggregates coal retirement dates from at least three sources:
        - Platform's event registry (coal_retirement_schedule.json)
        - AEMO ISP published dates (from financial_evidence.json)
        - Operator public announcements (from financial_evidence.json)

        Returns platform-only entries if external sources are unavailable.
        """
        entries: List[CrossValidationEntry] = []

        # Extract platform coal retirement events
        platform_retirements = [
            event
            for event in self.event_registry.events
            if event.event_type == EventType.COAL_CLOSURE
        ]

        if not platform_retirements:
            return entries

        # Extract external source data for coal retirements
        external_coal_data = self._get_external_coal_data()

        for event in platform_retirements:
            platform_value = event.expected_date.isoformat()

            # Platform entry (always present)
            platform_entry = CrossValidationEntry(
                data_point=f"{event.name} closure date",
                category="coal_retirements",
                source_name="Platform Model",
                source_date=self.event_registry.last_updated,
                reported_value=platform_value,
                platform_value=platform_value,
                discrepancy_pct=0.0,
                is_stale=self._is_stale(self.event_registry.last_updated),
            )
            entries.append(platform_entry)

            # External sources for this plant
            plant_externals = external_coal_data.get(event.name, [])
            for ext in plant_externals:
                ext_date = ext["source_date"]
                ext_value = ext["reported_value"]
                discrepancy = self._calculate_date_discrepancy_pct(
                    platform_value, ext_value
                )

                entries.append(
                    CrossValidationEntry(
                        data_point=f"{event.name} closure date",
                        category="coal_retirements",
                        source_name=ext["source_name"],
                        source_date=ext_date,
                        source_url=ext.get("source_url"),
                        reported_value=ext_value,
                        platform_value=platform_value,
                        discrepancy_pct=discrepancy,
                        is_stale=self._is_stale(ext_date),
                    )
                )

        return entries

    def _get_external_coal_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract external coal retirement data from evidence file.

        Returns a dict mapping plant_name -> list of external source entries.
        Returns empty dict if evidence is unavailable (graceful degradation).
        """
        if not self.evidence:
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}

        # Look for cross_validation section first (dedicated section)
        cross_val = self.evidence.get("cross_validation", {})
        coal_sources = cross_val.get("coal_retirements", [])

        for source in coal_sources:
            plant_name = source.get("plant_name", "")
            if plant_name:
                result.setdefault(plant_name, []).append({
                    "source_name": source.get("source_name", "Unknown"),
                    "source_date": date.fromisoformat(source["source_date"]),
                    "reported_value": source.get("reported_value", ""),
                    "source_url": source.get("source_url"),
                })

        # Also extract from forward_price_evidence sources (AEMO ISP, ESOO)
        fwd_evidence = self.evidence.get("forward_price_evidence", {})
        sources = fwd_evidence.get("sources", [])
        evidence_points = fwd_evidence.get("evidence_points", [])

        # Find AEMO ISP source info
        aemo_isp_source = next(
            (s for s in sources if "isp" in s.get("id", "").lower()),
            None,
        )
        aemo_esoo_source = next(
            (s for s in sources if "esoo" in s.get("id", "").lower()),
            None,
        )

        # Extract coal retirement references from evidence points
        for point in evidence_points:
            param = point.get("parameter", "")
            if "closure" in param.lower() or "retirement" in param.lower():
                # This evidence point references coal retirement data
                source_info = aemo_esoo_source or aemo_isp_source
                if source_info:
                    # Try to match to a specific plant
                    evidence_text = point.get("evidence", "")
                    for plant_name in self._extract_plant_names(evidence_text):
                        result.setdefault(plant_name, []).append({
                            "source_name": source_info.get("name", "AEMO"),
                            "source_date": date.fromisoformat(
                                source_info["date"][:10]
                            ),
                            "reported_value": point.get("value", ""),
                            "source_url": source_info.get("url"),
                        })

        return result

    @staticmethod
    def _extract_plant_names(text: str) -> List[str]:
        """Extract known coal plant names from evidence text."""
        known_plants = [
            "Eraring", "Yallourn", "Bayswater", "Callide B",
            "Vales Point B", "Loy Yang A", "Loy Yang B",
            "Gladstone", "Tarong", "Mt Piper",
            "Torrens Island B",
        ]
        return [name for name in known_plants if name.lower() in text.lower()]

    @staticmethod
    def _calculate_date_discrepancy_pct(
        platform_date_str: str, external_date_str: str
    ) -> Optional[float]:
        """Calculate discrepancy between two dates as percentage of time span.

        Uses days difference relative to the platform date's distance from today.
        Returns None if dates cannot be compared.
        """
        try:
            platform_date = date.fromisoformat(platform_date_str[:10])
            external_date = date.fromisoformat(external_date_str[:10])
        except (ValueError, TypeError):
            return None

        days_diff = abs((platform_date - external_date).days)
        # Express as percentage of the platform's time horizon from today
        days_to_platform = abs((platform_date - date.today()).days)
        if days_to_platform == 0:
            return 0.0

        return round((days_diff / days_to_platform) * 100, 1)

    # -------------------------------------------------------------------------
    # Revenue Benchmark Cross-Validation
    # -------------------------------------------------------------------------

    def compare_revenue_benchmarks(
        self,
        region: str,
        model_revenue: float,
    ) -> List[CrossValidationEntry]:
        """对比收入基准：平台模型 vs Modo Energy 报告。

        Aggregates revenue benchmarks from:
        - Platform's model output (provided as parameter)
        - Published industry data (Modo Energy reported $148k/MW for NEM BESS in 2024)

        Returns platform-only entry if external sources are unavailable.
        """
        entries: List[CrossValidationEntry] = []
        platform_value = f"${model_revenue:,.0f}/MW/year"

        # Platform entry
        entries.append(
            CrossValidationEntry(
                data_point=f"BESS revenue {region}",
                category="revenue_benchmarks",
                source_name="Platform Model",
                source_date=date.today(),
                reported_value=platform_value,
                platform_value=platform_value,
                discrepancy_pct=0.0,
                is_stale=False,
            )
        )

        # External revenue benchmarks
        external_benchmarks = self._get_external_revenue_data(region)

        if not external_benchmarks:
            return entries

        for benchmark in external_benchmarks:
            ext_revenue = benchmark["revenue_per_mw"]
            ext_value = f"${ext_revenue:,.0f}/MW/year"

            # Calculate discrepancy percentage
            if model_revenue > 0:
                discrepancy = round(
                    ((ext_revenue - model_revenue) / model_revenue) * 100, 1
                )
            else:
                discrepancy = None

            entries.append(
                CrossValidationEntry(
                    data_point=f"BESS revenue {region}",
                    category="revenue_benchmarks",
                    source_name=benchmark["source_name"],
                    source_date=benchmark["source_date"],
                    source_url=benchmark.get("source_url"),
                    reported_value=ext_value,
                    platform_value=platform_value,
                    discrepancy_pct=discrepancy,
                    is_stale=self._is_stale(benchmark["source_date"]),
                )
            )

        return entries

    def _get_external_revenue_data(self, region: str) -> List[Dict[str, Any]]:
        """Extract external revenue benchmark data from evidence file.

        Returns empty list if evidence is unavailable (graceful degradation).
        """
        if not self.evidence:
            return []

        benchmarks: List[Dict[str, Any]] = []

        # Check dedicated cross_validation section
        cross_val = self.evidence.get("cross_validation", {})
        rev_sources = cross_val.get("revenue_benchmarks", [])

        for source in rev_sources:
            source_region = source.get("region", "")
            # Include NEM-wide benchmarks or region-specific ones
            if not source_region or source_region == region:
                benchmarks.append({
                    "source_name": source.get("source_name", "Unknown"),
                    "source_date": date.fromisoformat(source["source_date"]),
                    "revenue_per_mw": source.get("revenue_per_mw", 0),
                    "source_url": source.get("source_url"),
                })

        # Extract from forward_price_evidence
        fwd_evidence = self.evidence.get("forward_price_evidence", {})
        sources = fwd_evidence.get("sources", [])
        evidence_points = fwd_evidence.get("evidence_points", [])

        for point in evidence_points:
            param = point.get("parameter", "")
            if "spread" in param.lower() or "revenue" in param.lower():
                # Look for revenue figures in evidence text
                revenue_value = self._extract_revenue_figure(point)
                if revenue_value is not None:
                    # Find the matching source
                    source_id = point.get("source_id", "")
                    source_info = next(
                        (s for s in sources if s.get("id") == source_id),
                        None,
                    )
                    if source_info:
                        benchmarks.append({
                            "source_name": source_info.get("name", "Unknown"),
                            "source_date": date.fromisoformat(
                                source_info["date"][:10]
                            ),
                            "revenue_per_mw": revenue_value,
                            "source_url": source_info.get("url"),
                        })

        return benchmarks

    @staticmethod
    def _extract_revenue_figure(evidence_point: Dict[str, Any]) -> Optional[float]:
        """Extract revenue per MW figure from an evidence point.

        Looks for patterns like '$148k/MW' or '$148,000/MW' in the evidence text.
        Only extracts figures that represent annual BESS revenue benchmarks.
        """
        import re

        param = evidence_point.get("parameter", "")
        evidence_text = evidence_point.get("evidence", "")
        value_text = evidence_point.get("value", "")

        # Only extract from parameters that clearly relate to revenue/spread benchmarks
        if not any(
            kw in param.lower()
            for kw in ["spread", "revenue", "base_spread"]
        ):
            return None

        # Skip FCAS-specific or historical decline data
        if "fcas" in param.lower() or "collapse" in param.lower():
            return None

        combined = f"{value_text} {evidence_text}"

        # Match patterns like $148k/MW, $148,000/MW (annual revenue)
        patterns = [
            r"\$(\d+)k/MW",  # $148k/MW
            r"\$(\d{1,3}(?:,\d{3})*)/MW",  # $148,000/MW
        ]

        for pattern in patterns:
            match = re.search(pattern, combined)
            if match:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)
                # If matched 'k' pattern, multiply by 1000
                if "k/MW" in combined[match.start():match.end() + 5]:
                    value *= 1000
                return value

        return None

    # -------------------------------------------------------------------------
    # Price Forecast Cross-Validation
    # -------------------------------------------------------------------------

    def compare_price_forecasts(
        self,
        region: str,
        scenario: ScenarioType,
    ) -> List[CrossValidationEntry]:
        """对比价格预测：平台情景 vs AEMO ISP 情景。

        Aggregates price forecasts from:
        - Platform's Central/High/Low scenarios
        - AEMO ISP scenario projections

        Returns platform-only entry if external sources are unavailable.
        """
        entries: List[CrossValidationEntry] = []

        # Get platform's price forecast from event registry context
        platform_spread = self._get_platform_spread_forecast(region, scenario)
        platform_value = f"${platform_spread:.0f}/MWh mean spread ({scenario.value})"

        # Platform entry
        entries.append(
            CrossValidationEntry(
                data_point=f"Price forecast {region} ({scenario.value})",
                category="price_forecasts",
                source_name="Platform Model",
                source_date=self.event_registry.last_updated,
                reported_value=platform_value,
                platform_value=platform_value,
                discrepancy_pct=0.0,
                is_stale=self._is_stale(self.event_registry.last_updated),
            )
        )

        # External price forecast sources
        external_forecasts = self._get_external_price_data(region, scenario)

        if not external_forecasts:
            return entries

        for forecast in external_forecasts:
            ext_spread = forecast["spread_value"]
            ext_value = f"${ext_spread:.0f}/MWh mean spread"

            # Calculate discrepancy
            if platform_spread > 0:
                discrepancy = round(
                    ((ext_spread - platform_spread) / platform_spread) * 100, 1
                )
            else:
                discrepancy = None

            entries.append(
                CrossValidationEntry(
                    data_point=f"Price forecast {region} ({scenario.value})",
                    category="price_forecasts",
                    source_name=forecast["source_name"],
                    source_date=forecast["source_date"],
                    source_url=forecast.get("source_url"),
                    reported_value=ext_value,
                    platform_value=platform_value,
                    discrepancy_pct=discrepancy,
                    is_stale=self._is_stale(forecast["source_date"]),
                )
            )

        return entries

    def _get_platform_spread_forecast(
        self, region: str, scenario: ScenarioType
    ) -> float:
        """Get the platform's base spread forecast for a region.

        Uses the base spread parameters from the forward price engine constants.
        """
        # Base spread parameters (same as ForwardPriceEngine)
        base_spreads: Dict[str, float] = {
            "NSW1": 120.0,
            "QLD1": 100.0,
            "VIC1": 110.0,
            "SA1": 140.0,
            "TAS1": 90.0,
            "WEM": 80.0,
        }

        base = base_spreads.get(region, 100.0)

        # Apply scenario multiplier
        scenario_multipliers: Dict[ScenarioType, float] = {
            ScenarioType.CENTRAL: 1.0,
            ScenarioType.HIGH: 1.2,
            ScenarioType.LOW: 0.8,
        }

        return base * scenario_multipliers.get(scenario, 1.0)

    def _get_external_price_data(
        self, region: str, scenario: ScenarioType
    ) -> List[Dict[str, Any]]:
        """Extract external price forecast data from evidence file.

        Returns empty list if evidence is unavailable (graceful degradation).
        """
        if not self.evidence:
            return []

        forecasts: List[Dict[str, Any]] = []

        # Check dedicated cross_validation section
        cross_val = self.evidence.get("cross_validation", {})
        price_sources = cross_val.get("price_forecasts", [])

        for source in price_sources:
            source_region = source.get("region", "")
            source_scenario = source.get("scenario", "")
            if (not source_region or source_region == region) and (
                not source_scenario or source_scenario == scenario.value
            ):
                forecasts.append({
                    "source_name": source.get("source_name", "Unknown"),
                    "source_date": date.fromisoformat(source["source_date"]),
                    "spread_value": source.get("spread_value", 0),
                    "source_url": source.get("source_url"),
                })

        # Extract from forward_price_evidence
        fwd_evidence = self.evidence.get("forward_price_evidence", {})
        sources = fwd_evidence.get("sources", [])
        evidence_points = fwd_evidence.get("evidence_points", [])

        # Look for AEMO ISP scenario data
        for point in evidence_points:
            param = point.get("parameter", "")
            if "scenario" in param.lower() or "forecast" in param.lower():
                source_id = point.get("source_id", "")
                source_info = next(
                    (s for s in sources if s.get("id") == source_id),
                    None,
                )
                if source_info and "isp" in source_id.lower():
                    # Extract spread value if available
                    spread_val = self._extract_spread_from_evidence(point, region)
                    if spread_val is not None:
                        forecasts.append({
                            "source_name": source_info.get("name", "AEMO ISP"),
                            "source_date": date.fromisoformat(
                                source_info["date"][:10]
                            ),
                            "spread_value": spread_val,
                            "source_url": source_info.get("url"),
                        })

        return forecasts

    @staticmethod
    def _extract_spread_from_evidence(
        evidence_point: Dict[str, Any], region: str
    ) -> Optional[float]:
        """Extract spread value from an evidence point for a specific region.

        Returns None if no numeric spread value can be extracted.
        """
        import re

        evidence_text = evidence_point.get("evidence", "")
        value_text = evidence_point.get("value", "")
        combined = f"{value_text} {evidence_text}"

        # Match patterns like $120/MWh
        pattern = r"\$(\d+(?:\.\d+)?)/MWh"
        match = re.search(pattern, combined)
        if match:
            return float(match.group(1))

        return None

    # -------------------------------------------------------------------------
    # Response Builder
    # -------------------------------------------------------------------------

    def get_cross_validation_response(
        self,
        category: str,
        region: Optional[str] = None,
        scenario: ScenarioType = ScenarioType.CENTRAL,
        model_revenue: float = 148000.0,
    ) -> CrossValidationResponse:
        """Build a CrossValidationResponse for the specified category.

        Args:
            category: One of 'coal_retirements', 'revenue_benchmarks', 'price_forecasts'
            region: NEM region (required for revenue_benchmarks and price_forecasts)
            scenario: Scenario type (for price_forecasts)
            model_revenue: Platform model revenue per MW (for revenue_benchmarks)

        Returns:
            CrossValidationResponse with comparison entries.
        """
        if category == "coal_retirements":
            entries = self.compare_coal_retirements()
        elif category == "revenue_benchmarks":
            entries = self.compare_revenue_benchmarks(
                region=region or "NSW1",
                model_revenue=model_revenue,
            )
        elif category == "price_forecasts":
            entries = self.compare_price_forecasts(
                region=region or "NSW1",
                scenario=scenario,
            )
        else:
            entries = []

        return CrossValidationResponse(
            category=category,
            entries=entries,
            last_updated=date.today(),
        )
