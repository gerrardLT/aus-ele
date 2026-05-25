"""Property-based tests for DegradationModel consistency.

Feature: platform-optimization, Property 4: 衰减模型一致性

For any valid degradation_rate value (0 ≤ rate ≤ 0.15), Investment_Model's response
degradation_model.model_type should be "user-linear" and degradation_model.annual_rate
equals the input value; for invalid values (rate < 0 or rate > 0.15), the system should
raise a ValueError.

Validates: Requirements 2.1, 2.2, 2.4, 2.5
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.degradation_model import DegradationModel


# ---------------------------------------------------------------------------
# Property 4: 衰减模型一致性
# ---------------------------------------------------------------------------


class TestDegradationModelConsistencyProperty:
    """Property 4: 衰减模型一致性

    For any valid degradation_rate in [0, 0.15]:
    - model_type == "user-linear"
    - annual_rate == input value

    For any invalid degradation_rate (< 0 or > 0.15):
    - raises ValueError

    **Validates: Requirements 2.1, 2.2, 2.4, 2.5**
    """

    @given(rate=st.floats(min_value=0.0, max_value=0.15))
    @settings(max_examples=200)
    def test_valid_rate_produces_user_linear_model(self, rate: float):
        """For any valid rate in [0, 0.15], from_user_input returns a user-linear model
        with annual_rate equal to the input value.

        Feature: platform-optimization, Property 4: 衰减模型一致性
        **Validates: Requirements 2.1, 2.2, 2.4**
        """
        model = DegradationModel.from_user_input(rate)

        assert model.model_type == "user-linear"
        assert model.annual_rate == rate

    @given(rate=st.floats(min_value=0.0, max_value=0.15))
    @settings(max_examples=200)
    def test_valid_rate_capacity_decreases_over_time(self, rate: float):
        """For any valid rate, capacity_at_year is monotonically non-increasing.

        Feature: platform-optimization, Property 4: 衰减模型一致性
        **Validates: Requirements 2.1, 2.4**
        """
        assume(rate > 0.0)  # Zero rate means no degradation, skip trivial case
        model = DegradationModel.from_user_input(rate)

        # Capacity at year 0 should be 1.0
        assert model.capacity_at_year(0, cycles_per_year=365.0) == 1.0

        # Capacity should decrease over years
        prev_capacity = 1.0
        for year in range(1, 21):
            capacity = model.capacity_at_year(year, cycles_per_year=365.0)
            assert capacity <= prev_capacity
            assert capacity >= 0.0
            prev_capacity = capacity

    @given(
        rate=st.one_of(
            # Negative values
            st.floats(max_value=-0.0001, allow_nan=False, allow_infinity=False),
            # Values above 0.15
            st.floats(min_value=0.1501, max_value=1e6, allow_nan=False, allow_infinity=False),
        )
    )
    @settings(max_examples=200)
    def test_invalid_rate_raises_value_error(self, rate: float):
        """For any rate outside [0, 0.15], from_user_input raises ValueError.

        Feature: platform-optimization, Property 4: 衰减模型一致性
        **Validates: Requirements 2.5**
        """
        with pytest.raises(ValueError):
            DegradationModel.from_user_input(rate)

    def test_none_rate_produces_dual_factor_default(self):
        """When no rate is provided, the model falls back to dual-factor-default.

        Feature: platform-optimization, Property 4: 衰减模型一致性
        **Validates: Requirements 2.2**
        """
        model = DegradationModel.from_user_input(None)

        assert model.model_type == "dual-factor-default"
        assert model.annual_rate is None
        assert "calendar" in model.parameters
        assert "cyclic_per_cycle" in model.parameters
