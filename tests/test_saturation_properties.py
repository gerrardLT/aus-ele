"""Property-based tests for saturation calculation.

Feature: market-modules-redesign

Property 7: Saturation ratio calculation
    For any region with peak_load > 0, saturation_ratio = registered_mw / peak_load_mw,
    and is always >= 0.

Property 8: Revenue dilution monotonicity
    Higher saturation_ratio always produces higher or equal dilution_estimate
    (monotonically non-decreasing).

Validates: Requirements 3.2, 3.4, 10.2
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from routes.saturation_routes import _calculate_dilution_estimate, _build_region_saturation
from models.capacity_models import (
    CapacityProject,
    CapacityDataMetadata,
    CapacityDataSource,
)
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Saturation ratios: non-negative floats in a reasonable range
saturation_ratio_strategy = st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False)

# Positive MW values for registered capacity
registered_mw_strategy = st.floats(min_value=0, max_value=50000, allow_nan=False, allow_infinity=False)

# Positive peak load values (must be > 0 for ratio calculation)
peak_load_strategy = st.floats(min_value=0.1, max_value=50000, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property 7: Saturation ratio calculation
# ---------------------------------------------------------------------------


class TestSaturationRatioCalculationProperty:
    """Property 7: Saturation ratio calculation

    For any region with peak_load > 0, saturation_ratio = registered_mw / peak_load_mw,
    and is always >= 0.

    **Validates: Requirements 3.2, 10.2**
    """

    @given(registered_mw=registered_mw_strategy, peak_load=peak_load_strategy)
    @settings(max_examples=200)
    def test_saturation_ratio_equals_registered_over_peak_load(
        self, registered_mw: float, peak_load: float
    ):
        """For any region with peak_load > 0, saturation_ratio = registered_mw / peak_load_mw.

        Feature: market-modules-redesign, Property 7: Saturation ratio calculation
        **Validates: Requirements 3.2, 10.2**
        """
        # Build a minimal CapacityDataSource with a single registered project
        metadata = CapacityDataMetadata(
            last_updated=datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=10))),
            source="Test Source",
            version=1,
        )

        projects = []
        if registered_mw > 0:
            projects.append(
                CapacityProject(
                    region="SA1",
                    project_name="Test Project",
                    capacity_mw=registered_mw,
                    duration_hours=2.0,
                    status="registered",
                )
            )

        data = CapacityDataSource(metadata=metadata, projects=projects)

        # Temporarily override PEAK_LOAD_MW for SA1
        import routes.saturation_routes as sat_mod
        original_peak = sat_mod.PEAK_LOAD_MW.get("SA1")
        sat_mod.PEAK_LOAD_MW["SA1"] = peak_load

        try:
            result = _build_region_saturation(data, "SA1")

            # Verify ratio calculation
            expected_ratio = round(registered_mw / peak_load, 4)
            assert result["saturation_ratio"] == expected_ratio

            # Ratio must always be >= 0
            assert result["saturation_ratio"] >= 0
        finally:
            # Restore original peak load
            sat_mod.PEAK_LOAD_MW["SA1"] = original_peak

    @given(registered_mw=registered_mw_strategy, peak_load=peak_load_strategy)
    @settings(max_examples=200)
    def test_saturation_ratio_is_non_negative(
        self, registered_mw: float, peak_load: float
    ):
        """Saturation ratio is always >= 0 when peak_load > 0 and registered_mw >= 0.

        Feature: market-modules-redesign, Property 7: Saturation ratio calculation
        **Validates: Requirements 3.2, 10.2**
        """
        # Direct calculation check
        ratio = registered_mw / peak_load
        assert ratio >= 0

        # Also verify through the dilution function (which takes ratio as input)
        dilution = _calculate_dilution_estimate(ratio)
        assert dilution >= 0


# ---------------------------------------------------------------------------
# Property 8: Revenue dilution monotonicity
# ---------------------------------------------------------------------------


class TestRevenueDilutionMonotonicityProperty:
    """Property 8: Revenue dilution monotonicity

    Higher saturation_ratio always produces higher or equal dilution_estimate
    (monotonically non-decreasing).

    **Validates: Requirements 3.4, 10.2**
    """

    @given(
        ratio_a=saturation_ratio_strategy,
        ratio_b=saturation_ratio_strategy,
    )
    @settings(max_examples=200)
    def test_higher_saturation_produces_higher_or_equal_dilution(
        self, ratio_a: float, ratio_b: float
    ):
        """For any two saturation ratios where a <= b,
        dilution(a) <= dilution(b) (monotonically non-decreasing).

        Feature: market-modules-redesign, Property 8: Revenue dilution monotonicity
        **Validates: Requirements 3.4, 10.2**
        """
        # Ensure ratio_a <= ratio_b
        r_low = min(ratio_a, ratio_b)
        r_high = max(ratio_a, ratio_b)

        dilution_low = _calculate_dilution_estimate(r_low)
        dilution_high = _calculate_dilution_estimate(r_high)

        # Monotonicity: higher ratio => higher or equal dilution
        assert dilution_low <= dilution_high

    @given(ratio=saturation_ratio_strategy)
    @settings(max_examples=200)
    def test_dilution_is_bounded_between_0_and_80(self, ratio: float):
        """Dilution estimate is always between 0% and 80% (inclusive).

        Feature: market-modules-redesign, Property 8: Revenue dilution monotonicity
        **Validates: Requirements 3.4, 10.2**
        """
        dilution = _calculate_dilution_estimate(ratio)

        assert dilution >= 0.0
        assert dilution <= 80.0

    @given(ratio=saturation_ratio_strategy)
    @settings(max_examples=200)
    def test_dilution_equals_ratio_times_100_capped_at_80(self, ratio: float):
        """Dilution model: dilution_pct = min(saturation_ratio * 100, 80).

        Feature: market-modules-redesign, Property 8: Revenue dilution monotonicity
        **Validates: Requirements 3.4, 10.2**
        """
        dilution = _calculate_dilution_estimate(ratio)
        expected = min(ratio * 100, 80.0)

        assert abs(dilution - expected) < 1e-9
