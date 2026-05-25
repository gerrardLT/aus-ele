"""Unit tests for Tax Model.

Tests entity type selection, default tax rates, effective life defaults,
depreciation method switching, and validation errors.

Requirements: 4.5, 5.3, 5.4, 14.3, 14.4
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import math

import pytest
from pydantic import ValidationError

from engines.tax_model import TaxModel
from models.tax_models import (
    DepreciationMethod,
    EntityType,
    TaxConfig,
)


# ---------------------------------------------------------------------------
# Entity Type Selection and Default Tax Rates
# ---------------------------------------------------------------------------


class TestEntityTypeAndTaxRates:
    """Test entity type selection and default tax rates (30%/25%)."""

    def test_standard_entity_default_rate(self):
        """Standard entity has 30% tax rate."""
        config = TaxConfig(entity_type=EntityType.STANDARD)
        assert config.tax_rate == 0.30

    def test_base_rate_entity_default_rate(self):
        """Base rate entity has 25% tax rate."""
        config = TaxConfig(entity_type=EntityType.BASE_RATE)
        assert config.tax_rate == 0.25

    def test_default_entity_type_is_standard(self):
        """Default entity type is standard."""
        config = TaxConfig()
        assert config.entity_type == EntityType.STANDARD
        assert config.tax_rate == 0.30

    def test_custom_tax_rate_overrides_entity_default(self):
        """Custom tax rate overrides entity type default."""
        config = TaxConfig(
            entity_type=EntityType.STANDARD,
            custom_tax_rate=0.15,
        )
        assert config.tax_rate == 0.15

    def test_custom_tax_rate_zero(self):
        """Custom tax rate of 0 is valid (tax-free)."""
        config = TaxConfig(custom_tax_rate=0.0)
        assert config.tax_rate == 0.0

    def test_custom_tax_rate_one(self):
        """Custom tax rate of 1.0 (100%) is valid."""
        config = TaxConfig(custom_tax_rate=1.0)
        assert config.tax_rate == 1.0


# ---------------------------------------------------------------------------
# Default Effective Life
# ---------------------------------------------------------------------------


class TestDefaultEffectiveLife:
    """Test default effective life (20 years)."""

    def test_default_effective_life_is_20(self):
        """Default effective life is 20 years for BESS assets."""
        config = TaxConfig()
        assert config.effective_life_years == 20

    def test_custom_effective_life(self):
        """Custom effective life can be set."""
        config = TaxConfig(effective_life_years=15)
        assert config.effective_life_years == 15

    def test_effective_life_minimum_is_1(self):
        """Effective life of 1 year is valid."""
        config = TaxConfig(effective_life_years=1)
        assert config.effective_life_years == 1


# ---------------------------------------------------------------------------
# Depreciation Method Switching
# ---------------------------------------------------------------------------


class TestDepreciationMethodSwitching:
    """Test depreciation method switching (DV vs PC)."""

    def test_default_method_is_diminishing_value(self):
        """Default depreciation method is Diminishing Value."""
        config = TaxConfig()
        assert config.depreciation_method == DepreciationMethod.DIMINISHING_VALUE

    def test_switch_to_prime_cost(self):
        """Can switch to Prime Cost method."""
        config = TaxConfig(depreciation_method=DepreciationMethod.PRIME_COST)
        assert config.depreciation_method == DepreciationMethod.PRIME_COST

    def test_dv_produces_decreasing_depreciation(self):
        """Diminishing Value produces decreasing depreciation amounts."""
        config = TaxConfig(
            depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
            effective_life_years=20,
        )
        model = TaxModel(config)
        capex = 1_000_000.0

        dep_amounts = []
        for year in range(1, 6):
            result = model.calculate_depreciation(year, capex)
            dep_amounts.append(result.depreciation_amount)

        # Each year's depreciation should be less than the previous
        for i in range(1, len(dep_amounts)):
            assert dep_amounts[i] < dep_amounts[i - 1], (
                f"DV depreciation should decrease: year {i + 1} ({dep_amounts[i]}) "
                f">= year {i} ({dep_amounts[i - 1]})"
            )

    def test_pc_produces_constant_depreciation(self):
        """Prime Cost produces constant depreciation amounts."""
        config = TaxConfig(
            depreciation_method=DepreciationMethod.PRIME_COST,
            effective_life_years=20,
        )
        model = TaxModel(config)
        capex = 1_000_000.0
        expected = capex / 20  # 50,000

        for year in range(1, 6):
            result = model.calculate_depreciation(year, capex)
            assert math.isclose(result.depreciation_amount, expected, rel_tol=1e-9), (
                f"Year {year}: got {result.depreciation_amount}, expected {expected}"
            )

    def test_dv_first_year_depreciation(self):
        """DV first year: (2/L) × capex."""
        config = TaxConfig(
            depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
            effective_life_years=20,
        )
        model = TaxModel(config)
        capex = 1_000_000.0

        result = model.calculate_depreciation(1, capex)
        expected = (2.0 / 20) * capex  # 100,000
        assert math.isclose(result.depreciation_amount, expected, rel_tol=1e-9)

    def test_pc_total_depreciation_equals_capex(self):
        """Prime Cost total depreciation over effective life equals capex."""
        life = 10
        config = TaxConfig(
            depreciation_method=DepreciationMethod.PRIME_COST,
            effective_life_years=life,
        )
        model = TaxModel(config)
        capex = 500_000.0

        total_dep = 0.0
        for year in range(1, life + 1):
            result = model.calculate_depreciation(year, capex)
            total_dep += result.depreciation_amount

        assert math.isclose(total_dep, capex, rel_tol=1e-9), (
            f"Total PC depreciation {total_dep} should equal capex {capex}"
        )


# ---------------------------------------------------------------------------
# Validation Errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """Test validation errors for invalid tax rate and effective life."""

    def test_invalid_tax_rate_above_1(self):
        """Tax rate > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(custom_tax_rate=1.5)

    def test_invalid_tax_rate_negative(self):
        """Negative tax rate raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(custom_tax_rate=-0.1)

    def test_invalid_effective_life_zero(self):
        """Effective life of 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(effective_life_years=0)

    def test_invalid_effective_life_negative(self):
        """Negative effective life raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(effective_life_years=-5)
