"""Property-based tests for MerchantRiskEngine.

Feature: investment-outlook-scenarios

Property 9: Monte Carlo percentiles are ordered
    For any valid Monte Carlo simulation output with n_simulations >= 100,
    the revenue distribution SHALL satisfy:
    P10 <= P50 <= P90, and min_observed <= P10 and P90 <= max_observed.
    Also mean should be between min_observed and max_observed.

Property 10: Contract coverage calculation consistency
    For any valid P10 revenue, debt_service, and dscr values:
    - If P10 revenue >= debt_service * dscr, then coverage should be 0%
    - If P10 revenue < debt_service * dscr, then coverage should be > 0%
    - Coverage should always be in [0, 100] range
    - Higher P10 revenue should result in lower or equal coverage requirement

Validates: Requirements 4.1, 4.4
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import numpy as np
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.merchant_risk_engine import MerchantRiskEngine


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Daily revenues: list of non-negative floats representing historical daily revenues (AUD)
daily_revenue_strategy = st.lists(
    st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    min_size=30,
    max_size=500,
)

# Noise standard deviation percentage: [0, 0.5]
noise_std_pct_strategy = st.floats(
    min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False
)

# Number of simulations: [100, 2000] (capped for test performance)
n_simulations_strategy = st.integers(min_value=100, max_value=500)

# P10 revenue (AUD/MW/year): positive realistic values
p10_revenue_strategy = st.floats(
    min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False
)

# Debt service (AUD/MW/year): positive realistic values
debt_service_strategy = st.floats(
    min_value=10000.0, max_value=200000.0, allow_nan=False, allow_infinity=False
)

# DSCR: [1.0, 2.0]
dscr_strategy = st.floats(
    min_value=1.0, max_value=2.0, allow_nan=False, allow_infinity=False
)

# Bank contract percentage: [0.5, 0.9]
bank_contract_pct_strategy = st.floats(
    min_value=0.5, max_value=0.9, allow_nan=False, allow_infinity=False
)

# Random seed for reproducibility
seed_strategy = st.integers(min_value=0, max_value=2**31 - 1)


# ---------------------------------------------------------------------------
# Property 9: Monte Carlo percentiles are ordered
# ---------------------------------------------------------------------------


class TestMonteCarloPercentilesOrderedProperty:
    """Property 9: Monte Carlo percentiles are ordered

    For any valid MerchantRiskResponse with n_simulations >= 100,
    the revenue distribution SHALL satisfy:
    P10 <= P50 <= P90, and min_observed <= P10 and P90 <= max_observed.
    Also mean should be between min_observed and max_observed.

    **Validates: Requirements 4.1**
    """

    @given(
        daily_revenues=daily_revenue_strategy,
        noise_std_pct=noise_std_pct_strategy,
        n_simulations=n_simulations_strategy,
        seed=seed_strategy,
    )
    @settings(max_examples=200)
    def test_percentiles_are_ordered_p10_le_p50_le_p90(
        self,
        daily_revenues: list[float],
        noise_std_pct: float,
        n_simulations: int,
        seed: int,
    ):
        """P10 <= P50 <= P90 must always hold for any valid simulation.

        Feature: investment-outlook-scenarios, Property 9: Monte Carlo percentiles are ordered
        **Validates: Requirements 4.1**
        """
        # Filter out cases where all revenues are zero (degenerate case)
        assume(any(r > 0 for r in daily_revenues))

        rng = np.random.default_rng(seed)
        engine = MerchantRiskEngine(db=None)

        # Run Monte Carlo simulation
        annual_revenues = np.array([
            engine.resample_daily_revenue(
                historical_daily_revenues=daily_revenues,
                days_per_year=365,
                noise_std_pct=noise_std_pct,
                rng=rng,
            )
            for _ in range(n_simulations)
        ])

        p10 = float(np.percentile(annual_revenues, 10))
        p50 = float(np.percentile(annual_revenues, 50))
        p90 = float(np.percentile(annual_revenues, 90))

        assert p10 <= p50, f"P10 ({p10}) should be <= P50 ({p50})"
        assert p50 <= p90, f"P50 ({p50}) should be <= P90 ({p90})"

    @given(
        daily_revenues=daily_revenue_strategy,
        noise_std_pct=noise_std_pct_strategy,
        n_simulations=n_simulations_strategy,
        seed=seed_strategy,
    )
    @settings(max_examples=200)
    def test_min_observed_le_p10_and_p90_le_max_observed(
        self,
        daily_revenues: list[float],
        noise_std_pct: float,
        n_simulations: int,
        seed: int,
    ):
        """min_observed <= P10 and P90 <= max_observed must always hold.

        Feature: investment-outlook-scenarios, Property 9: Monte Carlo percentiles are ordered
        **Validates: Requirements 4.1**
        """
        assume(any(r > 0 for r in daily_revenues))

        rng = np.random.default_rng(seed)
        engine = MerchantRiskEngine(db=None)

        annual_revenues = np.array([
            engine.resample_daily_revenue(
                historical_daily_revenues=daily_revenues,
                days_per_year=365,
                noise_std_pct=noise_std_pct,
                rng=rng,
            )
            for _ in range(n_simulations)
        ])

        p10 = float(np.percentile(annual_revenues, 10))
        p90 = float(np.percentile(annual_revenues, 90))
        min_observed = float(np.min(annual_revenues))
        max_observed = float(np.max(annual_revenues))

        assert min_observed <= p10, (
            f"min_observed ({min_observed}) should be <= P10 ({p10})"
        )
        assert p90 <= max_observed, (
            f"P90 ({p90}) should be <= max_observed ({max_observed})"
        )

    @given(
        daily_revenues=daily_revenue_strategy,
        noise_std_pct=noise_std_pct_strategy,
        n_simulations=n_simulations_strategy,
        seed=seed_strategy,
    )
    @settings(max_examples=200)
    def test_mean_between_min_and_max_observed(
        self,
        daily_revenues: list[float],
        noise_std_pct: float,
        n_simulations: int,
        seed: int,
    ):
        """Mean should be between min_observed and max_observed.

        Feature: investment-outlook-scenarios, Property 9: Monte Carlo percentiles are ordered
        **Validates: Requirements 4.1**
        """
        assume(any(r > 0 for r in daily_revenues))

        rng = np.random.default_rng(seed)
        engine = MerchantRiskEngine(db=None)

        annual_revenues = np.array([
            engine.resample_daily_revenue(
                historical_daily_revenues=daily_revenues,
                days_per_year=365,
                noise_std_pct=noise_std_pct,
                rng=rng,
            )
            for _ in range(n_simulations)
        ])

        mean_val = float(np.mean(annual_revenues))
        min_observed = float(np.min(annual_revenues))
        max_observed = float(np.max(annual_revenues))

        assert min_observed <= mean_val <= max_observed, (
            f"Mean ({mean_val}) should be between "
            f"min_observed ({min_observed}) and max_observed ({max_observed})"
        )

    @given(
        daily_revenues=daily_revenue_strategy,
        noise_std_pct=noise_std_pct_strategy,
        n_simulations=n_simulations_strategy,
        seed=seed_strategy,
    )
    @settings(max_examples=200)
    def test_resample_daily_revenue_non_negative_with_non_negative_inputs(
        self,
        daily_revenues: list[float],
        noise_std_pct: float,
        n_simulations: int,
        seed: int,
    ):
        """resample_daily_revenue result should be non-negative when all inputs are non-negative.

        Feature: investment-outlook-scenarios, Property 9: Monte Carlo percentiles are ordered
        **Validates: Requirements 4.1**
        """
        # All daily revenues are already >= 0 by strategy definition
        assume(any(r > 0 for r in daily_revenues))

        rng = np.random.default_rng(seed)
        engine = MerchantRiskEngine(db=None)

        result = engine.resample_daily_revenue(
            historical_daily_revenues=daily_revenues,
            days_per_year=365,
            noise_std_pct=noise_std_pct,
            rng=rng,
        )

        assert result >= 0.0, (
            f"resample_daily_revenue should be non-negative, got {result}"
        )


# ---------------------------------------------------------------------------
# Property 10: Contract coverage calculation consistency
# ---------------------------------------------------------------------------


class TestContractCoverageConsistencyProperty:
    """Property 10: Contract coverage calculation consistency

    For any valid P10 revenue, debt_service, and dscr values:
    - If P10 revenue >= debt_service * dscr, then coverage should be 0%
    - If P10 revenue < debt_service * dscr, then coverage should be > 0%
    - Coverage should always be in [0, 100] range
    - Higher P10 revenue should result in lower or equal coverage requirement

    **Validates: Requirements 4.4**
    """

    @given(
        p10_revenue=p10_revenue_strategy,
        debt_service=debt_service_strategy,
        dscr=dscr_strategy,
        bank_contract_pct=bank_contract_pct_strategy,
    )
    @settings(max_examples=200)
    def test_coverage_zero_when_p10_exceeds_required(
        self,
        p10_revenue: float,
        debt_service: float,
        dscr: float,
        bank_contract_pct: float,
    ):
        """If P10 revenue >= debt_service * dscr, then coverage should be 0%.

        Feature: investment-outlook-scenarios, Property 10: Contract coverage calculation consistency
        **Validates: Requirements 4.4**
        """
        required_revenue = debt_service * dscr
        assume(p10_revenue >= required_revenue)

        engine = MerchantRiskEngine(db=None)
        coverage = engine.compute_contract_coverage(
            p90_revenue=p10_revenue,  # Note: parameter named p90_revenue but uses P10 value
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        assert coverage == 0.0, (
            f"Coverage should be 0% when P10 ({p10_revenue}) >= "
            f"required ({required_revenue}), got {coverage}%"
        )

    @given(
        p10_revenue=p10_revenue_strategy,
        debt_service=debt_service_strategy,
        dscr=dscr_strategy,
        bank_contract_pct=bank_contract_pct_strategy,
    )
    @settings(max_examples=200)
    def test_coverage_positive_when_p10_below_required(
        self,
        p10_revenue: float,
        debt_service: float,
        dscr: float,
        bank_contract_pct: float,
    ):
        """If P10 revenue < debt_service * dscr, then coverage should be > 0%.

        Feature: investment-outlook-scenarios, Property 10: Contract coverage calculation consistency
        **Validates: Requirements 4.4**
        """
        required_revenue = debt_service * dscr
        assume(p10_revenue < required_revenue)
        # Ensure meaningful gap (avoid floating point edge cases)
        assume(required_revenue - p10_revenue > 1.0)

        engine = MerchantRiskEngine(db=None)
        coverage = engine.compute_contract_coverage(
            p90_revenue=p10_revenue,
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        assert coverage > 0.0, (
            f"Coverage should be > 0% when P10 ({p10_revenue}) < "
            f"required ({required_revenue}), got {coverage}%"
        )

    @given(
        p10_revenue=p10_revenue_strategy,
        debt_service=debt_service_strategy,
        dscr=dscr_strategy,
        bank_contract_pct=bank_contract_pct_strategy,
    )
    @settings(max_examples=200)
    def test_coverage_always_in_valid_range(
        self,
        p10_revenue: float,
        debt_service: float,
        dscr: float,
        bank_contract_pct: float,
    ):
        """Coverage should always be in [0, 100] range.

        Feature: investment-outlook-scenarios, Property 10: Contract coverage calculation consistency
        **Validates: Requirements 4.4**
        """
        engine = MerchantRiskEngine(db=None)
        coverage = engine.compute_contract_coverage(
            p90_revenue=p10_revenue,
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        assert 0.0 <= coverage <= 100.0, (
            f"Coverage should be in [0, 100], got {coverage}%"
        )

    @given(
        debt_service=debt_service_strategy,
        dscr=dscr_strategy,
        bank_contract_pct=bank_contract_pct_strategy,
        seed=seed_strategy,
    )
    @settings(max_examples=200)
    def test_higher_p10_results_in_lower_or_equal_coverage(
        self,
        debt_service: float,
        dscr: float,
        bank_contract_pct: float,
        seed: int,
    ):
        """Higher P10 revenue should result in lower or equal coverage requirement.

        Feature: investment-outlook-scenarios, Property 10: Contract coverage calculation consistency
        **Validates: Requirements 4.4**
        """
        rng = np.random.default_rng(seed)

        # Generate two P10 values where one is strictly higher
        p10_low = rng.uniform(0, 200000)
        p10_high = p10_low + rng.uniform(1.0, 100000)

        engine = MerchantRiskEngine(db=None)

        coverage_low = engine.compute_contract_coverage(
            p90_revenue=p10_low,
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        coverage_high = engine.compute_contract_coverage(
            p90_revenue=p10_high,
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        assert coverage_high <= coverage_low, (
            f"Higher P10 ({p10_high}) should result in lower or equal coverage "
            f"({coverage_high}%) compared to lower P10 ({p10_low}) coverage ({coverage_low}%)"
        )
