"""Property-based tests for capacity data models.

Feature: market-modules-redesign

Property 5: Capacity data validation round-trip
    For any valid CapacityProject data, serializing to JSON and parsing back
    produces an identical model.

Property 6: Capacity data parsing correctness
    For any valid CapacityDataSource, get_region_summary returns correct
    registered/pipeline totals.

Validates: Requirements 4.1, 4.2, 3.1, 10.1
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import date, datetime, timezone, timedelta
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.capacity_models import (
    CapacityProject,
    CapacityDataMetadata,
    CapacityDataSource,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"]
VALID_STATUSES = ["registered", "construction", "planning", "committed"]

region_strategy = st.sampled_from(VALID_REGIONS)
status_strategy = st.sampled_from(VALID_STATUSES)

# Positive floats for capacity and duration (avoid inf/nan)
capacity_mw_strategy = st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False)
duration_hours_strategy = st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False)
energy_mwh_strategy = st.one_of(
    st.none(),
    st.floats(min_value=0.1, max_value=1000000.0, allow_nan=False, allow_infinity=False),
)

# Project name: non-empty text
project_name_strategy = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")

# Optional date strategy
optional_date_strategy = st.one_of(
    st.none(),
    st.dates(min_value=date(2000, 1, 1), max_value=date(2050, 12, 31)),
)

# Optional text strategy for owner/technology
optional_text_strategy = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != ""),
)


@st.composite
def capacity_project_strategy(draw):
    """Generate a valid CapacityProject instance."""
    return CapacityProject(
        region=draw(region_strategy),
        project_name=draw(project_name_strategy),
        capacity_mw=draw(capacity_mw_strategy),
        duration_hours=draw(duration_hours_strategy),
        energy_mwh=draw(energy_mwh_strategy),
        status=draw(status_strategy),
        expected_commissioning_date=draw(optional_date_strategy),
        actual_commissioning_date=draw(optional_date_strategy),
        owner=draw(optional_text_strategy),
        technology=draw(optional_text_strategy),
    )


@st.composite
def capacity_data_source_strategy(draw):
    """Generate a valid CapacityDataSource with random projects."""
    projects = draw(st.lists(capacity_project_strategy(), min_size=0, max_size=30))
    metadata = CapacityDataMetadata(
        last_updated=datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=10))),
        source="Test Source",
        version=draw(st.integers(min_value=1, max_value=100)),
    )
    return CapacityDataSource(metadata=metadata, projects=projects)


# ---------------------------------------------------------------------------
# Property 5: Capacity data validation round-trip
# ---------------------------------------------------------------------------


class TestCapacityDataRoundTripProperty:
    """Property 5: Capacity data validation round-trip

    For any valid CapacityProject data, serializing to JSON (model → dict → JSON
    → dict → model) produces an identical model.

    **Validates: Requirements 4.1, 4.2**
    """

    @given(project=capacity_project_strategy())
    @settings(max_examples=200)
    def test_project_round_trip_preserves_all_fields(self, project: CapacityProject):
        """Serializing a CapacityProject to dict and parsing back produces
        an identical model instance.

        Feature: market-modules-redesign, Property 5: Capacity data validation round-trip
        **Validates: Requirements 4.1, 4.2**
        """
        # Serialize to dict (JSON-compatible)
        serialized = project.model_dump(mode="json")

        # Parse back from dict
        restored = CapacityProject.model_validate(serialized)

        # All fields must match
        assert restored.region == project.region
        assert restored.project_name == project.project_name
        assert restored.capacity_mw == project.capacity_mw
        assert restored.duration_hours == project.duration_hours
        assert restored.energy_mwh == project.energy_mwh
        assert restored.status == project.status
        assert restored.expected_commissioning_date == project.expected_commissioning_date
        assert restored.actual_commissioning_date == project.actual_commissioning_date
        assert restored.owner == project.owner
        assert restored.technology == project.technology

    @given(source=capacity_data_source_strategy())
    @settings(max_examples=200)
    def test_data_source_round_trip_preserves_all_fields(self, source: CapacityDataSource):
        """Serializing a full CapacityDataSource to dict and parsing back
        produces an identical model instance.

        Feature: market-modules-redesign, Property 5: Capacity data validation round-trip
        **Validates: Requirements 4.1, 4.2**
        """
        # Serialize to dict (JSON-compatible)
        serialized = source.model_dump(mode="json")

        # Parse back from dict
        restored = CapacityDataSource.model_validate(serialized)

        # Metadata must match
        assert restored.metadata.last_updated == source.metadata.last_updated
        assert restored.metadata.source == source.metadata.source
        assert restored.metadata.version == source.metadata.version

        # Projects count must match
        assert len(restored.projects) == len(source.projects)

        # Each project must match
        for original, roundtripped in zip(source.projects, restored.projects):
            assert roundtripped.region == original.region
            assert roundtripped.project_name == original.project_name
            assert roundtripped.capacity_mw == original.capacity_mw
            assert roundtripped.duration_hours == original.duration_hours
            assert roundtripped.energy_mwh == original.energy_mwh
            assert roundtripped.status == original.status
            assert roundtripped.expected_commissioning_date == original.expected_commissioning_date
            assert roundtripped.actual_commissioning_date == original.actual_commissioning_date
            assert roundtripped.owner == original.owner
            assert roundtripped.technology == original.technology


# ---------------------------------------------------------------------------
# Property 6: Capacity data parsing correctness
# ---------------------------------------------------------------------------


class TestCapacityDataParsingCorrectnessProperty:
    """Property 6: Capacity data parsing correctness

    For any valid CapacityDataSource, get_region_summary returns correct
    registered/pipeline totals that match manual summation.

    **Validates: Requirements 3.1, 10.1**
    """

    @given(source=capacity_data_source_strategy(), region=region_strategy)
    @settings(max_examples=200)
    def test_region_summary_registered_mw_correct(self, source: CapacityDataSource, region: str):
        """get_region_summary registered_mw equals the sum of capacity_mw for
        all projects in the region with status 'registered'.

        Feature: market-modules-redesign, Property 6: Capacity data parsing correctness
        **Validates: Requirements 3.1, 10.1**
        """
        summary = source.get_region_summary(region)

        # Manually compute expected registered MW
        expected_registered = sum(
            p.capacity_mw for p in source.projects
            if p.region == region and p.status == "registered"
        )

        assert summary["registered_mw"] == expected_registered

    @given(source=capacity_data_source_strategy(), region=region_strategy)
    @settings(max_examples=200)
    def test_region_summary_pipeline_mw_correct(self, source: CapacityDataSource, region: str):
        """get_region_summary pipeline_mw equals the sum of capacity_mw for
        all projects in the region with status != 'registered'.

        Feature: market-modules-redesign, Property 6: Capacity data parsing correctness
        **Validates: Requirements 3.1, 10.1**
        """
        summary = source.get_region_summary(region)

        # Manually compute expected pipeline MW
        expected_pipeline = sum(
            p.capacity_mw for p in source.projects
            if p.region == region and p.status != "registered"
        )

        assert summary["pipeline_mw"] == expected_pipeline

    @given(source=capacity_data_source_strategy(), region=region_strategy)
    @settings(max_examples=200)
    def test_region_summary_total_mw_is_sum(self, source: CapacityDataSource, region: str):
        """get_region_summary total_mw equals registered_mw + pipeline_mw.

        Feature: market-modules-redesign, Property 6: Capacity data parsing correctness
        **Validates: Requirements 3.1, 10.1**
        """
        summary = source.get_region_summary(region)

        assert summary["total_mw"] == summary["registered_mw"] + summary["pipeline_mw"]

    @given(source=capacity_data_source_strategy(), region=region_strategy)
    @settings(max_examples=200)
    def test_region_summary_project_count_correct(self, source: CapacityDataSource, region: str):
        """get_region_summary project_count equals the number of projects
        in the specified region.

        Feature: market-modules-redesign, Property 6: Capacity data parsing correctness
        **Validates: Requirements 3.1, 10.1**
        """
        summary = source.get_region_summary(region)

        expected_count = sum(1 for p in source.projects if p.region == region)

        assert summary["project_count"] == expected_count
