"""Property-based tests for CannibalizationEngine.

Feature: investment-outlook-scenarios

Property 1: Dilution curve follows power-law model
    For any valid alpha (0.3-1.0) and base_capacity > 0, the dilution curve should
    follow: revenue_per_mw = base_revenue / (capacity / base_capacity) ^ alpha.
    As capacity increases, revenue_per_mw decreases monotonically.

Property 2: Yearly projections count matches parameter
    For any projection_years in [1, 5], the yearly_projections list length
    should equal projection_years.

Property 3: Warning threshold consistency
    warning_triggered should be True if and only if current_dilution_pct > 50.

Validates: Requirements 1.1, 1.5, 1.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.capacity_models import (
    CapacityProject,
    CapacityDataMetadata,
    CapacityDataSource,
    CapacityDataLoader,
)
from models.outlook_models import (
    CannibalizationResponse,
    DilutionPoint,
    YearlyProjection,
)
from engines.cannibalization_engine import CannibalizationEngine


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

region_strategy = st.sampled_from(VALID_REGIONS)

# Alpha range as specified in design: [0.3, 1.0]
alpha_strategy = st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False)

# Base revenue: positive realistic values (AUD/MW/year)
base_revenue_strategy = st.floats(
    min_value=10000.0, max_value=500000.0, allow_nan=False, allow_infinity=False
)

# Base capacity: positive realistic values (MW)
base_capacity_strategy = st.floats(
    min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False
)

# Target capacity: must be >= base_capacity for meaningful dilution
target_capacity_strategy = st.floats(
    min_value=50.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)

# Projection years: [1, 5]
projection_years_strategy = st.integers(min_value=1, max_value=5)


def _make_mock_capacity_loader(region: str, registered_mw: float, pipeline_projects=None):
    """Create a mock CapacityDataLoader that returns controlled data."""
    projects = [
        CapacityProject(
            region=region,
            project_name="Existing BESS",
            capacity_mw=registered_mw,
            duration_hours=4.0,
            status="registered",
            expected_commissioning_date=None,
        ),
    ]

    if pipeline_projects:
        projects.extend(pipeline_projects)

    metadata = CapacityDataMetadata(
        last_updated=datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone(timedelta(hours=10))),
        source="Test",
        version=1,
    )
    data_source = CapacityDataSource(metadata=metadata, projects=projects)

    loader = MagicMock(spec=CapacityDataLoader)
    loader.load.return_value = data_source
    return loader


# ---------------------------------------------------------------------------
# Property 1: Dilution curve follows power-law model
# ---------------------------------------------------------------------------


class TestDilutionCurvePowerLawProperty:
    """Property 1: Dilution curve follows power-law model

    For any valid base_revenue > 0, base_capacity > 0, alpha in [0.3, 1.0],
    the computed revenue_per_mw SHALL equal base_revenue / (target_capacity / base_capacity) ^ alpha
    within floating-point tolerance, and as capacity increases, revenue_per_mw decreases monotonically.

    **Validates: Requirements 1.1**
    """

    @given(
        base_revenue=base_revenue_strategy,
        base_capacity=base_capacity_strategy,
        alpha=alpha_strategy,
        target_capacity=target_capacity_strategy,
    )
    @settings(max_examples=200)
    def test_revenue_follows_power_law_formula(
        self, base_revenue: float, base_capacity: float, alpha: float, target_capacity: float
    ):
        """The _compute_revenue method returns base_revenue / (target_capacity / base_capacity) ^ alpha.

        Feature: investment-outlook-scenarios, Property 1: Dilution curve follows power-law model
        **Validates: Requirements 1.1**
        """
        loader = _make_mock_capacity_loader("NSW1", base_capacity)
        engine = CannibalizationEngine(capacity_loader=loader)

        result = engine._compute_revenue(base_revenue, base_capacity, target_capacity, alpha)

        # Expected formula
        ratio = target_capacity / base_capacity
        expected = base_revenue / (ratio ** alpha)

        # Floating-point tolerance
        assert abs(result - expected) < 1e-6 * max(abs(expected), 1.0), (
            f"Expected {expected}, got {result} for "
            f"base_revenue={base_revenue}, base_capacity={base_capacity}, "
            f"target_capacity={target_capacity}, alpha={alpha}"
        )

    @given(
        base_revenue=base_revenue_strategy,
        base_capacity=base_capacity_strategy,
        alpha=alpha_strategy,
    )
    @settings(max_examples=200)
    def test_dilution_curve_monotonically_decreasing(
        self, base_revenue: float, base_capacity: float, alpha: float
    ):
        """As capacity increases along the dilution curve, revenue_per_mw decreases monotonically.

        Feature: investment-outlook-scenarios, Property 1: Dilution curve follows power-law model
        **Validates: Requirements 1.1**
        """
        loader = _make_mock_capacity_loader("NSW1", base_capacity)
        engine = CannibalizationEngine(capacity_loader=loader)

        max_capacity = base_capacity * 3  # 3x growth scenario
        curve = engine.compute_dilution_curve(
            base_revenue=base_revenue,
            base_capacity=base_capacity,
            alpha=alpha,
            capacity_range=(base_capacity, max_capacity),
            steps=20,
        )

        # Revenue should be monotonically decreasing
        for i in range(1, len(curve)):
            assert curve[i].revenue_per_mw <= curve[i - 1].revenue_per_mw, (
                f"Revenue not monotonically decreasing at index {i}: "
                f"{curve[i - 1].revenue_per_mw} -> {curve[i].revenue_per_mw}"
            )

    @given(
        base_revenue=base_revenue_strategy,
        base_capacity=base_capacity_strategy,
        alpha=alpha_strategy,
        target_capacity=target_capacity_strategy,
    )
    @settings(max_examples=200)
    def test_dilution_pct_matches_formula(
        self, base_revenue: float, base_capacity: float, alpha: float, target_capacity: float
    ):
        """dilution_pct equals (1 - revenue_per_mw / base_revenue) * 100.

        Feature: investment-outlook-scenarios, Property 1: Dilution curve follows power-law model
        **Validates: Requirements 1.1**
        """
        loader = _make_mock_capacity_loader("NSW1", base_capacity)
        engine = CannibalizationEngine(capacity_loader=loader)

        revenue = engine._compute_revenue(base_revenue, base_capacity, target_capacity, alpha)
        expected_dilution = (1 - revenue / base_revenue) * 100

        # Compute via dilution curve with a single step at target_capacity
        curve = engine.compute_dilution_curve(
            base_revenue=base_revenue,
            base_capacity=base_capacity,
            alpha=alpha,
            capacity_range=(target_capacity, target_capacity + 1),
            steps=1,
        )

        assert len(curve) == 1
        actual_dilution = curve[0].dilution_pct

        # Allow tolerance for rounding (engine rounds to 2 decimal places)
        assert abs(actual_dilution - round(expected_dilution, 2)) < 0.02, (
            f"Expected dilution_pct={round(expected_dilution, 2)}, got {actual_dilution}"
        )


# ---------------------------------------------------------------------------
# Property 2: Yearly projections count matches parameter
# ---------------------------------------------------------------------------


class TestYearlyProjectionsCountProperty:
    """Property 2: Yearly projections count matches parameter

    For any valid projection_years in [1, 5], the yearly_projections list
    in the response SHALL contain exactly projection_years entries.

    **Validates: Requirements 1.5**
    """

    @given(
        projection_years=projection_years_strategy,
        region=region_strategy,
    )
    @settings(max_examples=100)
    def test_yearly_projections_length_equals_parameter(
        self, projection_years: int, region: str
    ):
        """The yearly_projections list length equals projection_years parameter.

        Feature: investment-outlook-scenarios, Property 2: Yearly projections count matches parameter
        **Validates: Requirements 1.5**
        """
        # Create pipeline projects with commissioning dates spread across years
        current_year = datetime.now().year
        pipeline_projects = [
            CapacityProject(
                region=region,
                project_name=f"Pipeline Project {i}",
                capacity_mw=50.0 + i * 10,
                duration_hours=4.0,
                status="committed",
                expected_commissioning_date=date(current_year + i + 1, 6, 30),
            )
            for i in range(5)
        ]

        loader = _make_mock_capacity_loader(region, 200.0, pipeline_projects)
        engine = CannibalizationEngine(
            capacity_loader=loader,
            market_examples_path=None,
        )

        # Patch market examples loading to avoid file dependency
        with patch.object(engine, '_load_market_examples', return_value=[]):
            response = engine.simulate(
                region=region,
                base_revenue_per_mw=150000.0,
                base_capacity_mw=200.0,
                alpha=0.6,
                projection_years=projection_years,
            )

        assert len(response.yearly_projections) == projection_years, (
            f"Expected {projection_years} yearly projections, "
            f"got {len(response.yearly_projections)}"
        )

    @given(
        projection_years=projection_years_strategy,
        region=region_strategy,
    )
    @settings(max_examples=100)
    def test_yearly_projections_years_are_sequential(
        self, projection_years: int, region: str
    ):
        """Year values in yearly_projections increment sequentially from current year + 1.

        Feature: investment-outlook-scenarios, Property 2: Yearly projections count matches parameter
        **Validates: Requirements 1.5**
        """
        current_year = datetime.now().year
        pipeline_projects = [
            CapacityProject(
                region=region,
                project_name=f"Pipeline Project {i}",
                capacity_mw=50.0,
                duration_hours=4.0,
                status="committed",
                expected_commissioning_date=date(current_year + i + 1, 6, 30),
            )
            for i in range(5)
        ]

        loader = _make_mock_capacity_loader(region, 200.0, pipeline_projects)
        engine = CannibalizationEngine(
            capacity_loader=loader,
            market_examples_path=None,
        )

        with patch.object(engine, '_load_market_examples', return_value=[]):
            response = engine.simulate(
                region=region,
                base_revenue_per_mw=150000.0,
                base_capacity_mw=200.0,
                alpha=0.6,
                projection_years=projection_years,
            )

        # Verify sequential years
        for i, proj in enumerate(response.yearly_projections):
            expected_year = current_year + i + 1
            assert proj.year == expected_year, (
                f"Expected year {expected_year} at index {i}, got {proj.year}"
            )


# ---------------------------------------------------------------------------
# Property 3: Warning threshold consistency
# ---------------------------------------------------------------------------


class TestWarningThresholdConsistencyProperty:
    """Property 3: Warning threshold consistency

    warning_triggered SHALL be True if and only if current_dilution_pct > 50.0.

    **Validates: Requirements 1.6**
    """

    @given(
        alpha=alpha_strategy,
        region=region_strategy,
        construction_mw=st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_warning_triggered_iff_dilution_exceeds_50(
        self, alpha: float, region: str, construction_mw: float
    ):
        """warning_triggered is True if and only if current_dilution_pct > 50.

        Feature: investment-outlook-scenarios, Property 3: Warning threshold consistency
        **Validates: Requirements 1.6**
        """
        base_capacity = 200.0

        # Create construction projects to control dilution level
        pipeline_projects = []
        if construction_mw > 0:
            pipeline_projects.append(
                CapacityProject(
                    region=region,
                    project_name="Construction BESS",
                    capacity_mw=construction_mw,
                    duration_hours=4.0,
                    status="construction",
                    expected_commissioning_date=date(datetime.now().year + 1, 6, 30),
                )
            )

        loader = _make_mock_capacity_loader(region, base_capacity, pipeline_projects)
        engine = CannibalizationEngine(
            capacity_loader=loader,
            market_examples_path=None,
        )

        with patch.object(engine, '_load_market_examples', return_value=[]):
            response = engine.simulate(
                region=region,
                base_revenue_per_mw=150000.0,
                base_capacity_mw=base_capacity,
                alpha=alpha,
                projection_years=1,
            )

        # The invariant: warning_triggered iff current_dilution_pct > 50
        if response.current_dilution_pct > 50.0:
            assert response.warning_triggered is True, (
                f"warning_triggered should be True when dilution={response.current_dilution_pct}% > 50%"
            )
        else:
            assert response.warning_triggered is False, (
                f"warning_triggered should be False when dilution={response.current_dilution_pct}% <= 50%"
            )

    @given(
        alpha=alpha_strategy,
        region=region_strategy,
    )
    @settings(max_examples=100)
    def test_high_construction_triggers_warning(
        self, alpha: float, region: str
    ):
        """When construction capacity is very large relative to base, warning should trigger.

        Feature: investment-outlook-scenarios, Property 3: Warning threshold consistency
        **Validates: Requirements 1.6**
        """
        base_capacity = 100.0
        # Very large construction capacity should cause > 50% dilution
        large_construction_mw = 5000.0

        pipeline_projects = [
            CapacityProject(
                region=region,
                project_name="Massive Construction BESS",
                capacity_mw=large_construction_mw,
                duration_hours=4.0,
                status="construction",
                expected_commissioning_date=date(datetime.now().year + 1, 6, 30),
            )
        ]

        loader = _make_mock_capacity_loader(region, base_capacity, pipeline_projects)
        engine = CannibalizationEngine(
            capacity_loader=loader,
            market_examples_path=None,
        )

        with patch.object(engine, '_load_market_examples', return_value=[]):
            response = engine.simulate(
                region=region,
                base_revenue_per_mw=150000.0,
                base_capacity_mw=base_capacity,
                alpha=alpha,
                projection_years=1,
            )

        # With 5000MW construction on 100MW base, dilution should exceed 50%
        assert response.current_dilution_pct > 50.0, (
            f"Expected dilution > 50% with {large_construction_mw}MW construction "
            f"on {base_capacity}MW base, got {response.current_dilution_pct}%"
        )
        assert response.warning_triggered is True
