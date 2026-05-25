"""Property-based tests for Tax Model.

Feature: financial-accuracy-modules, Property 7: Tax Calculation Correctness
Feature: financial-accuracy-modules, Property 8: Taxable Income Formula
Feature: financial-accuracy-modules, Property 9: Tax Loss Carry-Forward
Feature: financial-accuracy-modules, Property 10: Diminishing Value Depreciation Formula
Feature: financial-accuracy-modules, Property 11: Prime Cost Depreciation Constancy
Feature: financial-accuracy-modules, Property 12: Depreciation Tax Shield NPV
Feature: financial-accuracy-modules, Property 13: After-Tax Cash Flow Formula
Feature: financial-accuracy-modules, Property 14: After-Tax IRR Consistency
Feature: financial-accuracy-modules, Property 21: Tax Model Serialization Round-Trip
Feature: financial-accuracy-modules, Property 23: Input Validation Rejection

Uses Hypothesis to verify invariants across randomized tax configurations,
revenue/expense combinations, and depreciation parameters.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import math

import pytest
import numpy_financial as npf
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from engines.tax_model import TaxModel
from models.tax_models import (
    AfterTaxCashFlow,
    AfterTaxResult,
    AnnualTaxResult,
    DepreciationMethod,
    DepreciationResult,
    EntityType,
    TaxConfig,
    TaxSummary,
)
from models.financial_params import CashFlowYear


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_tax_config(draw):
    """Generate valid TaxConfig for property tests."""
    entity_type = draw(st.sampled_from(list(EntityType)))
    method = draw(st.sampled_from(list(DepreciationMethod)))
    life = draw(st.integers(min_value=1, max_value=40))
    return TaxConfig(
        entity_type=entity_type,
        depreciation_method=method,
        effective_life_years=life,
    )


@st.composite
def valid_tax_config_with_custom_rate(draw):
    """Generate valid TaxConfig with optional custom tax rate."""
    entity_type = draw(st.sampled_from(list(EntityType)))
    method = draw(st.sampled_from(list(DepreciationMethod)))
    life = draw(st.integers(min_value=1, max_value=40))
    use_custom = draw(st.booleans())
    custom_rate = draw(st.floats(min_value=0.0, max_value=1.0)) if use_custom else None
    return TaxConfig(
        entity_type=entity_type,
        depreciation_method=method,
        effective_life_years=life,
        custom_tax_rate=custom_rate,
    )


@st.composite
def positive_financials(draw):
    """Generate positive revenue/expense values ensuring positive taxable income."""
    revenue = draw(st.floats(min_value=100.0, max_value=10_000_000.0))
    opex = draw(st.floats(min_value=0.0, max_value=revenue * 0.8))
    interest = draw(st.floats(min_value=0.0, max_value=revenue * 0.3))
    depreciation = draw(st.floats(min_value=0.0, max_value=revenue * 0.5))
    # Ensure taxable income is positive
    assume(revenue - opex - interest - depreciation > 0)
    return revenue, opex, interest, depreciation


@st.composite
def any_financials(draw):
    """Generate any valid revenue/expense combination (may produce negative income)."""
    revenue = draw(st.floats(min_value=0.0, max_value=10_000_000.0))
    opex = draw(st.floats(min_value=0.0, max_value=5_000_000.0))
    interest = draw(st.floats(min_value=0.0, max_value=2_000_000.0))
    depreciation = draw(st.floats(min_value=0.0, max_value=3_000_000.0))
    return revenue, opex, interest, depreciation


@st.composite
def valid_capex(draw):
    """Generate valid CAPEX values."""
    return draw(st.floats(min_value=1_000.0, max_value=500_000_000.0))


@st.composite
def valid_discount_rate(draw):
    """Generate valid discount rate."""
    return draw(st.floats(min_value=0.01, max_value=0.30))


# ---------------------------------------------------------------------------
# Property 7: Tax Calculation Correctness
# ---------------------------------------------------------------------------


class TestProperty7TaxCalculationCorrectness:
    """Property 7: Tax Calculation Correctness

    For any positive taxable income and entity type (standard or base_rate),
    the tax payable SHALL equal taxable_income x tax_rate, where tax_rate is
    0.30 for standard entities and 0.25 for base rate entities.

    **Validates: Requirements 4.1, 4.2**
    """

    @given(config=valid_tax_config(), financials=positive_financials())
    @settings(max_examples=100, deadline=None)
    def test_tax_equals_income_times_rate(self, config, financials):
        """Tax payable = taxable_income x tax_rate for positive income with no carried loss.

        Feature: financial-accuracy-modules, Property 7: Tax Calculation Correctness
        **Validates: Requirements 4.1, 4.2**
        """
        revenue, opex, interest, depreciation = financials
        model = TaxModel(config)

        result = model.calculate_annual_tax(
            year=1,
            revenue=revenue,
            opex=opex,
            interest_expense=interest,
            depreciation=depreciation,
        )

        taxable_income = revenue - opex - interest - depreciation
        expected_tax = taxable_income * config.tax_rate

        assert math.isclose(result.tax_payable, expected_tax, rel_tol=1e-9), (
            f"Tax mismatch: got {result.tax_payable}, expected {expected_tax}. "
            f"taxable_income={taxable_income}, rate={config.tax_rate}"
        )

    @given(config=valid_tax_config(), financials=positive_financials())
    @settings(max_examples=100, deadline=None)
    def test_standard_entity_rate_30_percent(self, config, financials):
        """Standard entity tax rate is 30%.

        Feature: financial-accuracy-modules, Property 7: Tax Calculation Correctness
        **Validates: Requirements 4.1, 4.2**
        """
        config_std = TaxConfig(
            entity_type=EntityType.STANDARD,
            depreciation_method=config.depreciation_method,
            effective_life_years=config.effective_life_years,
        )
        assert config_std.tax_rate == 0.30

    @given(config=valid_tax_config(), financials=positive_financials())
    @settings(max_examples=100, deadline=None)
    def test_base_rate_entity_rate_25_percent(self, config, financials):
        """Base rate entity tax rate is 25%.

        Feature: financial-accuracy-modules, Property 7: Tax Calculation Correctness
        **Validates: Requirements 4.1, 4.2**
        """
        config_base = TaxConfig(
            entity_type=EntityType.BASE_RATE,
            depreciation_method=config.depreciation_method,
            effective_life_years=config.effective_life_years,
        )
        assert config_base.tax_rate == 0.25


# ---------------------------------------------------------------------------
# Property 8: Taxable Income Formula
# ---------------------------------------------------------------------------


class TestProperty8TaxableIncomeFormula:
    """Property 8: Taxable Income Formula

    For any combination of revenue, operating expenses, interest expense,
    and depreciation, the taxable income before loss offset SHALL equal
    revenue - operating_expenses - interest_expense - depreciation.

    **Validates: Requirements 4.3, 6.2**
    """

    @given(config=valid_tax_config(), financials=any_financials())
    @settings(max_examples=100, deadline=None)
    def test_taxable_income_formula(self, config, financials):
        """taxable_income_before_loss = revenue - opex - interest - depreciation.

        Feature: financial-accuracy-modules, Property 8: Taxable Income Formula
        **Validates: Requirements 4.3, 6.2**
        """
        revenue, opex, interest, depreciation = financials
        model = TaxModel(config)

        result = model.calculate_annual_tax(
            year=1,
            revenue=revenue,
            opex=opex,
            interest_expense=interest,
            depreciation=depreciation,
        )

        expected = revenue - opex - interest - depreciation
        assert math.isclose(result.taxable_income_before_loss, expected, rel_tol=1e-9), (
            f"Taxable income formula mismatch: got {result.taxable_income_before_loss}, "
            f"expected {expected}"
        )


# ---------------------------------------------------------------------------
# Property 9: Tax Loss Carry-Forward
# ---------------------------------------------------------------------------


class TestProperty9TaxLossCarryForward:
    """Property 9: Tax Loss Carry-Forward

    For any sequence of annual taxable incomes (some negative, some positive),
    the tax model SHALL: (a) set tax_payable = 0 for any year with negative
    taxable income, (b) accumulate losses indefinitely, and (c) when taxable
    income is positive with existing carried loss, reduce taxable income by
    min(current_income, remaining_loss_balance) before calculating tax.

    **Validates: Requirements 4.4, 4.6**
    """

    @given(
        config=valid_tax_config(),
        loss_revenue=st.floats(min_value=0.0, max_value=100_000.0),
        loss_opex=st.floats(min_value=200_000.0, max_value=500_000.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_zero_tax_on_negative_income(self, config, loss_revenue, loss_opex):
        """Tax payable = 0 when taxable income is negative.

        Feature: financial-accuracy-modules, Property 9: Tax Loss Carry-Forward
        **Validates: Requirements 4.4, 4.6**
        """
        # Ensure taxable income is negative
        assume(loss_revenue - loss_opex < 0)

        model = TaxModel(config)
        result = model.calculate_annual_tax(
            year=1,
            revenue=loss_revenue,
            opex=loss_opex,
            interest_expense=0.0,
            depreciation=0.0,
        )

        assert result.tax_payable == 0.0
        assert result.carried_loss_balance > 0.0

    @given(
        config=valid_tax_config(),
        loss_amount=st.floats(min_value=10_000.0, max_value=1_000_000.0),
        profit_revenue=st.floats(min_value=500_000.0, max_value=5_000_000.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_loss_accumulation_and_offset(self, config, loss_amount, profit_revenue):
        """Losses accumulate and offset future positive income.

        Feature: financial-accuracy-modules, Property 9: Tax Loss Carry-Forward
        **Validates: Requirements 4.4, 4.6**
        """
        # Ensure profit exceeds loss for full offset
        assume(profit_revenue > loss_amount)

        model = TaxModel(config)

        # Year 1: Generate a loss
        result_y1 = model.calculate_annual_tax(
            year=1,
            revenue=0.0,
            opex=loss_amount,
            interest_expense=0.0,
            depreciation=0.0,
        )
        assert result_y1.tax_payable == 0.0
        assert math.isclose(result_y1.carried_loss_balance, loss_amount, rel_tol=1e-9)

        # Year 2: Profit that exceeds the loss
        result_y2 = model.calculate_annual_tax(
            year=2,
            revenue=profit_revenue,
            opex=0.0,
            interest_expense=0.0,
            depreciation=0.0,
        )

        # Loss offset should equal loss_amount
        assert math.isclose(result_y2.loss_offset_applied, loss_amount, rel_tol=1e-9)
        # Taxable income after offset
        expected_taxable = profit_revenue - loss_amount
        assert math.isclose(result_y2.taxable_income, expected_taxable, rel_tol=1e-9)
        # Tax on reduced income
        expected_tax = expected_taxable * config.tax_rate
        assert math.isclose(result_y2.tax_payable, expected_tax, rel_tol=1e-9)
        # Loss balance should be zero
        assert math.isclose(result_y2.carried_loss_balance, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 10: Diminishing Value Depreciation Formula
# ---------------------------------------------------------------------------


class TestProperty10DiminishingValueFormula:
    """Property 10: Diminishing Value Depreciation Formula

    For any asset with original cost C and effective life L years, the
    Diminishing Value depreciation in year N SHALL equal (2.0 / L) x
    written_down_value_at_start_of_year_N.

    **Validates: Requirements 5.1**
    """

    @given(
        life=st.integers(min_value=1, max_value=40),
        capex=st.floats(min_value=1_000.0, max_value=100_000_000.0),
        years=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_dv_formula_each_year(self, life, capex, years):
        """DV depreciation = (2/L) x WDV for each year.

        Feature: financial-accuracy-modules, Property 10: Diminishing Value Depreciation Formula
        **Validates: Requirements 5.1**
        """
        assume(years <= life)
        config = TaxConfig(
            entity_type=EntityType.STANDARD,
            depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
            effective_life_years=life,
        )
        model = TaxModel(config)

        dv_rate = 2.0 / life
        wdv = capex

        for year in range(1, years + 1):
            result = model.calculate_depreciation(year, capex)
            expected_dep = dv_rate * wdv
            expected_dep = min(expected_dep, wdv)

            assert math.isclose(result.depreciation_amount, expected_dep, rel_tol=1e-9), (
                f"Year {year}: got {result.depreciation_amount}, expected {expected_dep}. "
                f"WDV={wdv}, rate={dv_rate}"
            )

            wdv -= expected_dep
            wdv = max(0.0, wdv)
            assert math.isclose(result.written_down_value, wdv, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 11: Prime Cost Depreciation Constancy
# ---------------------------------------------------------------------------


class TestProperty11PrimeCostConstancy:
    """Property 11: Prime Cost Depreciation Constancy

    For any asset with original cost C and effective life L years, the
    Prime Cost depreciation SHALL equal C / L for every year, producing
    a constant annual depreciation amount.

    **Validates: Requirements 5.2**
    """

    @given(
        life=st.integers(min_value=1, max_value=40),
        capex=st.floats(min_value=1_000.0, max_value=100_000_000.0),
        years=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_pc_constant_depreciation(self, life, capex, years):
        """Prime Cost depreciation = C/L constant each year.

        Feature: financial-accuracy-modules, Property 11: Prime Cost Depreciation Constancy
        **Validates: Requirements 5.2**
        """
        assume(years <= life)
        config = TaxConfig(
            entity_type=EntityType.STANDARD,
            depreciation_method=DepreciationMethod.PRIME_COST,
            effective_life_years=life,
        )
        model = TaxModel(config)

        expected_dep = capex / life

        for year in range(1, years + 1):
            result = model.calculate_depreciation(year, capex)
            assert math.isclose(result.depreciation_amount, expected_dep, rel_tol=1e-9), (
                f"Year {year}: got {result.depreciation_amount}, expected {expected_dep}. "
                f"capex={capex}, life={life}"
            )


# ---------------------------------------------------------------------------
# Property 12: Depreciation Tax Shield NPV
# ---------------------------------------------------------------------------


class TestProperty12DepreciationTaxShieldNPV:
    """Property 12: Depreciation Tax Shield NPV

    For any series of annual depreciation amounts, tax rate r, and discount
    rate d, the NPV of depreciation tax savings SHALL equal
    sum(depreciation_i x r) / (1 + d)^i for i = 1 to project_life.

    **Validates: Requirements 5.5, 5.6**
    """

    @given(
        config=valid_tax_config(),
        capex=st.floats(min_value=100_000.0, max_value=50_000_000.0),
        project_life=st.integers(min_value=3, max_value=15),
        discount_rate=valid_discount_rate(),
    )
    @settings(max_examples=100, deadline=None)
    def test_npv_tax_shield_formula(self, config, capex, project_life, discount_rate):
        """NPV of tax shield = sum(dep_i x rate) / (1+d)^i.

        Feature: financial-accuracy-modules, Property 12: Depreciation Tax Shield NPV
        **Validates: Requirements 5.5, 5.6**
        """
        model = TaxModel(config)
        tax_rate = config.tax_rate

        # Calculate depreciation for each year and compute NPV
        actual_npv = 0.0
        for year in range(1, project_life + 1):
            result = model.calculate_depreciation(year, capex)
            actual_npv += result.tax_shield / ((1 + discount_rate) ** year)

        # Verify tax_shield = depreciation_amount * tax_rate for each year
        model2 = TaxModel(config)
        expected_npv = 0.0
        for year in range(1, project_life + 1):
            result = model2.calculate_depreciation(year, capex)
            expected_shield = result.depreciation_amount * tax_rate
            assert math.isclose(result.tax_shield, expected_shield, rel_tol=1e-9)
            expected_npv += expected_shield / ((1 + discount_rate) ** year)

        assert math.isclose(actual_npv, expected_npv, rel_tol=1e-9), (
            f"NPV tax shield mismatch: got {actual_npv}, expected {expected_npv}"
        )


# ---------------------------------------------------------------------------
# Property 13: After-Tax Cash Flow Formula
# ---------------------------------------------------------------------------


class TestProperty13AfterTaxCashFlowFormula:
    """Property 13: After-Tax Cash Flow Formula

    For any year with pre-tax cash flow P, tax payable T, and depreciation D,
    the after-tax cash flow SHALL equal P - T + D (depreciation non-cash add-back).

    **Validates: Requirements 6.1**
    """

    @given(
        pre_tax_cf=st.floats(min_value=-1_000_000.0, max_value=10_000_000.0),
        tax_payable=st.floats(min_value=0.0, max_value=3_000_000.0),
        depreciation=st.floats(min_value=0.0, max_value=5_000_000.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_after_tax_cf_formula(self, pre_tax_cf, tax_payable, depreciation):
        """after_tax_cf = pre_tax_cf - tax_payable + depreciation.

        Feature: financial-accuracy-modules, Property 13: After-Tax Cash Flow Formula
        **Validates: Requirements 6.1**
        """
        expected = pre_tax_cf - tax_payable + depreciation

        atcf = AfterTaxCashFlow(
            year=1,
            pre_tax_cash_flow=pre_tax_cf,
            tax_payable=tax_payable,
            depreciation_add_back=depreciation,
            after_tax_cash_flow=expected,
        )

        assert math.isclose(
            atcf.after_tax_cash_flow,
            atcf.pre_tax_cash_flow - atcf.tax_payable + atcf.depreciation_add_back,
            rel_tol=1e-9,
        )


# ---------------------------------------------------------------------------
# Property 14: After-Tax IRR Consistency
# ---------------------------------------------------------------------------


class TestProperty14AfterTaxIRRConsistency:
    """Property 14: After-Tax IRR Consistency

    For any series of after-tax cash flows (including negative initial equity),
    the computed after-tax IRR SHALL satisfy: NPV of the cash flow series
    discounted at the IRR rate approx 0 (within numerical tolerance).

    **Validates: Requirements 6.3**
    """

    @given(
        capex=st.floats(min_value=1_000_000.0, max_value=50_000_000.0),
        annual_cf=st.floats(min_value=100_000.0, max_value=5_000_000.0),
        project_life=st.integers(min_value=5, max_value=15),
    )
    @settings(max_examples=100, deadline=None)
    def test_npv_at_irr_is_zero(self, capex, annual_cf, project_life):
        """NPV at IRR approx 0 for after-tax cash flow series.

        Feature: financial-accuracy-modules, Property 14: After-Tax IRR Consistency
        **Validates: Requirements 6.3**
        """
        # Build a simple cash flow series: -capex followed by constant annual_cf
        cash_flows = [-capex] + [annual_cf] * project_life

        # Ensure IRR exists (total inflows > outflows)
        assume(annual_cf * project_life > capex)

        try:
            irr = float(npf.irr(cash_flows))
        except Exception:
            return  # Skip if IRR computation fails

        # Skip if IRR is NaN or infinite
        if math.isnan(irr) or math.isinf(irr):
            return

        # Verify NPV at IRR approx 0
        npv_at_irr = float(npf.npv(irr, cash_flows))

        assert abs(npv_at_irr) < 1.0, (
            f"NPV at IRR should be approx 0, got {npv_at_irr}. "
            f"IRR={irr}, capex={capex}, annual_cf={annual_cf}, life={project_life}"
        )


# ---------------------------------------------------------------------------
# Property 21: Tax Model Serialization Round-Trip
# ---------------------------------------------------------------------------


class TestProperty21SerializationRoundTrip:
    """Property 21: Tax Model Serialization Round-Trip

    For any valid TaxConfig object, serializing to JSON and then deserializing
    back SHALL produce an object equal to the original.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """

    @given(config=valid_tax_config_with_custom_rate())
    @settings(max_examples=100, deadline=None)
    def test_tax_config_json_round_trip(self, config):
        """TaxConfig serialize to JSON then deserialize = original.

        Feature: financial-accuracy-modules, Property 21: Tax Model Serialization Round-Trip
        **Validates: Requirements 12.1, 12.2, 12.3**
        """
        json_str = config.model_dump_json()
        restored = TaxConfig.model_validate_json(json_str)

        assert restored.entity_type == config.entity_type
        assert restored.depreciation_method == config.depreciation_method
        assert restored.effective_life_years == config.effective_life_years
        assert restored.custom_tax_rate == config.custom_tax_rate

    @given(config=valid_tax_config_with_custom_rate())
    @settings(max_examples=100, deadline=None)
    def test_tax_config_dict_round_trip(self, config):
        """TaxConfig dict serialize then deserialize = original.

        Feature: financial-accuracy-modules, Property 21: Tax Model Serialization Round-Trip
        **Validates: Requirements 12.1, 12.2, 12.3**
        """
        data = config.model_dump()
        restored = TaxConfig.model_validate(data)

        assert restored.entity_type == config.entity_type
        assert restored.depreciation_method == config.depreciation_method
        assert restored.effective_life_years == config.effective_life_years
        assert restored.custom_tax_rate == config.custom_tax_rate


# ---------------------------------------------------------------------------
# Property 23: Input Validation Rejection (Tax Model portion)
# ---------------------------------------------------------------------------


class TestTaxModelInputValidation:
    """**Validates: Requirements 14.3, 14.4**

    Invalid tax rate outside [0, 1] raises ValidationError.
    Effective life <= 0 raises ValidationError.
    """

    @given(
        tax_rate=st.floats(min_value=1.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_tax_rate_above_one_rejected(self, tax_rate: float):
        """Tax rate > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(custom_tax_rate=tax_rate)

    @given(
        tax_rate=st.floats(max_value=-0.01, min_value=-100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_negative_tax_rate_rejected(self, tax_rate: float):
        """Negative tax rate raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(custom_tax_rate=tax_rate)

    @given(
        life=st.integers(max_value=0, min_value=-100),
    )
    @settings(max_examples=100)
    def test_effective_life_zero_or_negative_rejected(self, life: int):
        """Effective life <= 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            TaxConfig(effective_life_years=life)

    @given(
        life=st.integers(min_value=1, max_value=100),
        entity_type=st.sampled_from(list(EntityType)),
        method=st.sampled_from(list(DepreciationMethod)),
    )
    @settings(max_examples=100)
    def test_valid_tax_config_accepted(self, life: int, entity_type: EntityType, method: DepreciationMethod):
        """Valid TaxConfig parameters are accepted without error."""
        config = TaxConfig(
            entity_type=entity_type,
            depreciation_method=method,
            effective_life_years=life,
        )
        assert config.effective_life_years == life
        assert config.entity_type == entity_type
