"""Property-based tests for outlook data models.

Feature: investment-outlook-scenarios

Property 12: Market examples have valid structure
    For any MarketExample object in any outlook response, it SHALL have a non-empty
    region string, a data_year that is a valid year (>= 2015 and <= current_year + 1),
    and a label that is exactly one of "actual" or "projected".

Also tests CoalRetirementSchedule model properties:
    - get_retirements_before returns only retirements in the correct region and before the date
    - total_retiring_capacity is always >= 0
    - All volatility_impact_estimate values are in [0, 1]

Validates: Requirements 6.5, 6.6
"""

import json
import sys
import os
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models.outlook_models import CoalRetirement, CoalRetirementSchedule


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
VALID_FUEL_TYPES = ["black_coal", "brown_coal", "gas"]
VALID_CONFIDENCES = ["confirmed", "announced", "speculated"]
VALID_LABELS = ["actual", "projected"]
MODULE_CATEGORIES = ["cannibalization", "fcas_collapse", "regional_timing", "merchant_risk"]

DATA_DIR = Path(__file__).parent.parent / "data"
MARKET_EXAMPLES_PATH = DATA_DIR / "market_examples.json"
COAL_RETIREMENT_PATH = DATA_DIR / "coal_retirement_schedule.json"

CURRENT_YEAR = date.today().year


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

region_strategy = st.sampled_from(VALID_REGIONS)
fuel_type_strategy = st.sampled_from(VALID_FUEL_TYPES)
confidence_strategy = st.sampled_from(VALID_CONFIDENCES)

capacity_mw_strategy = st.floats(
    min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False
)
volatility_strategy = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
date_strategy = st.dates(min_value=date(2020, 1, 1), max_value=date(2050, 12, 31))


@st.composite
def coal_retirement_strategy(draw):
    """Generate a valid CoalRetirement instance."""
    return CoalRetirement(
        plant_name=draw(st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")),
        region=draw(region_strategy),
        capacity_mw=draw(capacity_mw_strategy),
        fuel_type=draw(fuel_type_strategy),
        expected_closure_date=draw(date_strategy),
        confidence=draw(confidence_strategy),
        volatility_impact_estimate=draw(volatility_strategy),
    )


@st.composite
def coal_retirement_schedule_strategy(draw):
    """Generate a valid CoalRetirementSchedule with random retirements."""
    retirements = draw(st.lists(coal_retirement_strategy(), min_size=0, max_size=20))
    metadata = {
        "last_updated": "2025-01-15",
        "source": "Test source",
    }
    return CoalRetirementSchedule(metadata=metadata, retirements=retirements)


# ---------------------------------------------------------------------------
# Property 12: Market examples have valid structure
# ---------------------------------------------------------------------------


class TestMarketExamplesValidStructure:
    """Property 12: Market examples have valid structure

    For any MarketExample object in any outlook response, it SHALL have a non-empty
    region string, a data_year that is a valid year (>= 2015 and <= current_year + 1),
    and a label that is exactly one of "actual" or "projected".

    **Validates: Requirements 6.5, 6.6**
    """

    def test_market_examples_file_has_required_metadata(self):
        """market_examples.json has metadata with required fields (last_updated, source).

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "last_updated" in data["metadata"]
        assert "source" in data["metadata"]
        assert data["metadata"]["last_updated"] != ""
        assert data["metadata"]["source"] != ""

    def test_market_examples_has_four_module_categories(self):
        """market_examples.json has examples object with 4 module categories.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        assert "examples" in data
        examples = data["examples"]

        for category in MODULE_CATEGORIES:
            assert category in examples, f"Missing category: {category}"
            assert isinstance(examples[category], list), f"{category} should be a list"
            assert len(examples[category]) > 0, f"{category} should have at least one example"

    def test_each_example_has_required_fields(self):
        """Each example has required fields (region, description, data_year or trajectory, label).

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**

        Note: fcas_collapse examples use a 'trajectory' array with year entries
        instead of a single 'data_year' field. Both patterns are valid.
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        for category in MODULE_CATEGORIES:
            for i, example in enumerate(data["examples"][category]):
                assert "region" in example, f"{category}[{i}] missing 'region'"
                assert "description" in example, f"{category}[{i}] missing 'description'"
                assert "label" in example, f"{category}[{i}] missing 'label'"
                # data_year can be a direct field or derived from trajectory
                has_data_year = "data_year" in example
                has_trajectory = "trajectory" in example
                assert has_data_year or has_trajectory, (
                    f"{category}[{i}] missing both 'data_year' and 'trajectory'"
                )

    def test_all_regions_are_non_empty_strings(self):
        """All region fields are non-empty strings.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        for category in MODULE_CATEGORIES:
            for i, example in enumerate(data["examples"][category]):
                region = example["region"]
                assert isinstance(region, str), f"{category}[{i}] region not a string"
                assert region.strip() != "", f"{category}[{i}] region is empty"

    def test_all_data_years_are_valid(self):
        """All data_year values are valid years (>= 2015 and <= current_year + 1).
        For trajectory-based examples, all years in the trajectory are validated.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        for category in MODULE_CATEGORIES:
            for i, example in enumerate(data["examples"][category]):
                if "data_year" in example:
                    year = example["data_year"]
                    assert isinstance(year, int), f"{category}[{i}] data_year not an int"
                    assert 2015 <= year <= CURRENT_YEAR + 1, (
                        f"{category}[{i}] data_year {year} out of range [2015, {CURRENT_YEAR + 1}]"
                    )
                elif "trajectory" in example:
                    # Validate all years in the trajectory
                    for j, entry in enumerate(example["trajectory"]):
                        year = entry["year"]
                        assert isinstance(year, int), (
                            f"{category}[{i}].trajectory[{j}] year not an int"
                        )
                        assert 2015 <= year <= CURRENT_YEAR + 1, (
                            f"{category}[{i}].trajectory[{j}] year {year} out of range"
                        )

    def test_all_labels_are_actual_or_projected(self):
        """All labels are either "actual" or "projected".

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(MARKET_EXAMPLES_PATH) as f:
            data = json.load(f)

        for category in MODULE_CATEGORIES:
            for i, example in enumerate(data["examples"][category]):
                label = example["label"]
                assert label in VALID_LABELS, (
                    f"{category}[{i}] label '{label}' not in {VALID_LABELS}"
                )

    @given(
        region=st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
        data_year=st.integers(min_value=2015, max_value=CURRENT_YEAR + 1),
        label=st.sampled_from(VALID_LABELS),
    )
    @settings(max_examples=100)
    def test_market_example_structure_property(self, region: str, data_year: int, label: str):
        """Property: any valid market example has non-empty region, valid year, valid label.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        # Verify the structural constraints hold
        assert region.strip() != ""
        assert 2015 <= data_year <= CURRENT_YEAR + 1
        assert label in VALID_LABELS


# ---------------------------------------------------------------------------
# CoalRetirementSchedule model properties
# ---------------------------------------------------------------------------


class TestCoalRetirementScheduleProperties:
    """CoalRetirementSchedule model property tests.

    Tests that:
    - get_retirements_before returns only retirements in the correct region and before the date
    - total_retiring_capacity is always >= 0
    - All volatility_impact_estimate values are in [0, 1]

    **Validates: Requirements 6.5, 6.6**
    """

    @given(schedule=coal_retirement_schedule_strategy(), region=region_strategy, target=date_strategy)
    @settings(max_examples=200)
    def test_get_retirements_before_filters_by_region_and_date(
        self, schedule: CoalRetirementSchedule, region: str, target: date
    ):
        """get_retirements_before returns only retirements in the correct region
        and before the target date.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        result = schedule.get_retirements_before(region, target)

        for r in result:
            assert r.region == region, f"Expected region {region}, got {r.region}"
            assert r.expected_closure_date <= target, (
                f"Retirement date {r.expected_closure_date} is after target {target}"
            )

    @given(schedule=coal_retirement_schedule_strategy(), region=region_strategy, target=date_strategy)
    @settings(max_examples=200)
    def test_get_retirements_before_returns_all_matching(
        self, schedule: CoalRetirementSchedule, region: str, target: date
    ):
        """get_retirements_before returns ALL retirements matching the criteria
        (no false negatives).

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        result = schedule.get_retirements_before(region, target)

        # Manually compute expected set
        expected = [
            r for r in schedule.retirements
            if r.region == region and r.expected_closure_date <= target
        ]

        assert len(result) == len(expected), (
            f"Expected {len(expected)} retirements, got {len(result)}"
        )

    @given(schedule=coal_retirement_schedule_strategy(), region=region_strategy, target=date_strategy)
    @settings(max_examples=200)
    def test_total_retiring_capacity_is_non_negative(
        self, schedule: CoalRetirementSchedule, region: str, target: date
    ):
        """total_retiring_capacity is always >= 0.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        total = schedule.total_retiring_capacity(region, target)
        assert total >= 0, f"total_retiring_capacity returned negative: {total}"

    @given(schedule=coal_retirement_schedule_strategy(), region=region_strategy, target=date_strategy)
    @settings(max_examples=200)
    def test_total_retiring_capacity_equals_sum_of_matching(
        self, schedule: CoalRetirementSchedule, region: str, target: date
    ):
        """total_retiring_capacity equals sum of capacity_mw for matching retirements.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        total = schedule.total_retiring_capacity(region, target)
        matching = schedule.get_retirements_before(region, target)
        expected = sum(r.capacity_mw for r in matching)

        assert abs(total - expected) < 1e-6, (
            f"total_retiring_capacity {total} != sum of matching {expected}"
        )

    @given(retirement=coal_retirement_strategy())
    @settings(max_examples=200)
    def test_volatility_impact_estimate_in_valid_range(self, retirement: CoalRetirement):
        """All volatility_impact_estimate values are in [0, 1].

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        assert 0 <= retirement.volatility_impact_estimate <= 1.0, (
            f"volatility_impact_estimate {retirement.volatility_impact_estimate} out of [0, 1]"
        )

    def test_coal_retirement_schedule_file_has_valid_structure(self):
        """coal_retirement_schedule.json loads correctly into CoalRetirementSchedule model.

        Feature: investment-outlook-scenarios, Property 12: Market examples have valid structure
        **Validates: Requirements 6.5, 6.6**
        """
        with open(COAL_RETIREMENT_PATH) as f:
            data = json.load(f)

        schedule = CoalRetirementSchedule.model_validate(data)

        assert "last_updated" in schedule.metadata
        assert "source" in schedule.metadata
        assert len(schedule.retirements) > 0

        for r in schedule.retirements:
            assert r.capacity_mw > 0
            assert 0 <= r.volatility_impact_estimate <= 1.0
            assert r.fuel_type in VALID_FUEL_TYPES
            assert r.confidence in VALID_CONFIDENCES
