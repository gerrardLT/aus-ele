"""Property-based tests for Regional Ranking module.

Feature: market-modules-redesign

Uses Hypothesis to verify correctness properties of the regional ranking
normalization and weighted scoring logic.

Tests:
- Property 9a: Normalization produces values in [0, 1]
- Property 9b: Weighted sum of normalized scores is in [0, 1]
- Property 9c: Normalization preserves ordering

**Validates: Requirements 5.1, 5.3**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests.support import stub_optional_dep

# Stub heavy optional dependencies that may not be installed in test env
stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from routes.ranking_routes import _normalize_scores, NEM_REGIONS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for raw region scores: dict of 5 NEM regions -> non-negative floats
region_scores_strategy = st.fixed_dictionaries(
    {region: st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
     for region in NEM_REGIONS}
)

# Strategy for valid weights (all >= 0, at least one > 0)
weights_strategy = st.tuples(
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
).filter(lambda ws: sum(ws) > 0)


# ---------------------------------------------------------------------------
# Property 9a: Normalization produces values in [0, 1]
# ---------------------------------------------------------------------------


class TestNormalizationRange:
    """Property 9a: For any dict of 5 region scores, _normalize_scores
    produces values in [0, 1].

    **Validates: Requirements 5.1, 5.3**
    """

    @given(raw_scores=region_scores_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_normalized_values_in_unit_interval(self, raw_scores):
        """All normalized scores must be between 0 and 1 inclusive."""
        normalized = _normalize_scores(raw_scores)

        assert len(normalized) == len(raw_scores), (
            f"Normalization changed number of regions: {len(raw_scores)} -> {len(normalized)}"
        )

        for region, value in normalized.items():
            assert 0.0 <= value <= 1.0, (
                f"Normalized score for {region} is {value}, expected in [0, 1]. "
                f"Raw scores: {raw_scores}"
            )


# ---------------------------------------------------------------------------
# Property 9b: Weighted sum of normalized scores is in [0, 1]
# ---------------------------------------------------------------------------


class TestWeightedSumRange:
    """Property 9b: For any normalized scores and valid weights,
    the weighted sum is in [0, 1].

    **Validates: Requirements 5.1, 5.3**
    """

    @given(raw_scores=region_scores_strategy, weights=weights_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_weighted_sum_in_unit_interval(self, raw_scores, weights):
        """Weighted sum of normalized dimension scores must be in [0, 1]."""
        normalized = _normalize_scores(raw_scores)

        # Normalize weights to sum to 1 (same as the API does)
        total_weight = sum(weights)
        norm_weights = [w / total_weight for w in weights]

        # Compute weighted sum for each region (simulating 5 dimensions with same scores)
        # In the real API, each dimension has its own normalized scores.
        # Here we test that a single dimension's normalized score, when weighted, stays in [0, 1].
        for region in NEM_REGIONS:
            # Simulate weighted sum: each dimension contributes weight_i * score_i
            # With all dimensions having the same normalized value, weighted sum = value
            # (since weights sum to 1). Test with one weight applied:
            weighted_score = norm_weights[0] * normalized[region]
            assert 0.0 <= weighted_score <= 1.0, (
                f"Single-dimension weighted score for {region} is {weighted_score}, "
                f"expected in [0, 1]"
            )

        # Also test full weighted sum across 5 identical dimensions
        # (worst case: all dimensions have score 1.0 -> sum = 1.0)
        for region in NEM_REGIONS:
            full_weighted_sum = sum(
                w * normalized[region] for w in norm_weights
            )
            assert -1e-10 <= full_weighted_sum <= 1.0 + 1e-10, (
                f"Full weighted sum for {region} is {full_weighted_sum}, "
                f"expected in [0, 1]. Normalized: {normalized[region]}, "
                f"Weights: {norm_weights}"
            )


# ---------------------------------------------------------------------------
# Property 9c: Normalization preserves ordering
# ---------------------------------------------------------------------------


class TestNormalizationOrdering:
    """Property 9c: Normalization preserves ordering — if score_a > score_b,
    then normalized_a >= normalized_b.

    **Validates: Requirements 5.1, 5.3**
    """

    @given(raw_scores=region_scores_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ordering_preserved(self, raw_scores):
        """If raw score_a > score_b, then normalized_a >= normalized_b."""
        normalized = _normalize_scores(raw_scores)

        regions = list(raw_scores.keys())
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                r_i, r_j = regions[i], regions[j]
                if raw_scores[r_i] > raw_scores[r_j]:
                    assert normalized[r_i] >= normalized[r_j], (
                        f"Ordering not preserved: raw {r_i}={raw_scores[r_i]} > "
                        f"{r_j}={raw_scores[r_j]}, but normalized "
                        f"{r_i}={normalized[r_i]} < {r_j}={normalized[r_j]}"
                    )
                elif raw_scores[r_j] > raw_scores[r_i]:
                    assert normalized[r_j] >= normalized[r_i], (
                        f"Ordering not preserved: raw {r_j}={raw_scores[r_j]} > "
                        f"{r_i}={raw_scores[r_i]}, but normalized "
                        f"{r_j}={normalized[r_j]} < {r_i}={normalized[r_i]}"
                    )
