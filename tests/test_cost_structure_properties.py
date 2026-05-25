"""Property-based tests for Cost Structure Engine.

Feature: financial-accuracy-modules, Property 1: Variable Cost Linearity
Feature: financial-accuracy-modules, Property 2: Fixed Cost Independence from Throughput
Feature: financial-accuracy-modules, Property 3: DUOS Connection Type Invariant
Feature: financial-accuracy-modules, Property 4: MLF Multiplicative Application
Feature: financial-accuracy-modules, Property 5: Cost Breakdown Summation Invariant
Feature: financial-accuracy-modules, Property 6: Regional Override Preservation
Feature: financial-accuracy-modules, Property 20: Serialization Round-Trip
Feature: financial-accuracy-modules, Property 23: Input Validation Rejection
Feature: financial-accuracy-modules, Property 24: Gross Energy Calculation

Uses Hypothesis to verify invariants across randomized fee parameters,
battery specs, and throughput volumes.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engines.cost_structure_engine import CostStructureEngine, SUPPORTED_REGIONS
from models.cost_structure_models import (
    AemoParticipantFee,
    AemoRegistrationFee,
    AnnualCostBreakdown,
    ConnectionType,
    CostLineItem,
    CostStructureOverrides,
    DuosCharge,
    FeeType,
    FppConfig,
    MlfConfig,
    RegionalFeeConfig,
    TuosDemandCharge,
    TuosEnergyCharge,
)
from models.financial_params import BatterySpecs
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_battery_specs(draw):
    """Generate valid BatterySpecs for cost calculations."""
    power_mw = draw(st.floats(min_value=1.0, max_value=500.0))
    duration_hours = draw(st.floats(min_value=1.0, max_value=12.0))
    return BatterySpecs(power_mw=power_mw, duration_hours=duration_hours)


@st.composite
def valid_throughput(draw):
    """Generate valid annual throughput in MWh (positive, realistic)."""
    return draw(st.floats(min_value=0.0, max_value=500000.0))


@st.composite
def valid_region(draw):
    """Generate a valid region code."""
    return draw(st.sampled_from(SUPPORTED_REGIONS))


@st.composite
def valid_connection_type(draw):
    """Generate a valid connection type."""
    return draw(st.sampled_from(list(ConnectionType)))


@st.composite
def valid_mlf(draw):
    """Generate a valid MLF value in range [0.50, 1.50]."""
    return draw(st.floats(min_value=0.50, max_value=1.50))


@st.composite
def valid_settlement_price(draw):
    """Generate a valid settlement price."""
    return draw(st.floats(min_value=-1000.0, max_value=15000.0, allow_nan=False, allow_infinity=False))


@st.composite
def valid_regional_fee_config(draw):
    """Generate a valid RegionalFeeConfig."""
    region = draw(valid_region())
    aemo_rate = draw(st.floats(min_value=0.30, max_value=0.50))
    aemo_reg = draw(st.floats(min_value=5000.0, max_value=50000.0))
    tuos_demand = draw(st.floats(min_value=5000.0, max_value=15000.0))
    tuos_energy = draw(st.floats(min_value=1.0, max_value=3.0))
    connection_type = draw(valid_connection_type())
    duos_rate = draw(st.floats(min_value=0.0, max_value=30.0))
    mlf_val = draw(st.floats(min_value=0.50, max_value=1.50))
    fpp_earning = draw(st.floats(min_value=500.0, max_value=1500.0))

    return RegionalFeeConfig(
        region=region,
        aemo_participant_fee=AemoParticipantFee(rate_per_mwh=aemo_rate),
        aemo_registration_fee=AemoRegistrationFee(amount=aemo_reg),
        tuos_demand=TuosDemandCharge(rate_per_mw_year=tuos_demand),
        tuos_energy=TuosEnergyCharge(rate_per_mwh=tuos_energy),
        duos=DuosCharge(connection_type=connection_type, rate_per_mwh=duos_rate),
        mlf=MlfConfig(value=mlf_val),
        fpp=FppConfig(net_earning_per_mw_year=fpp_earning),
    )


# ---------------------------------------------------------------------------
# Property 1: Variable Cost Linearity
# ---------------------------------------------------------------------------


class TestVariableCostLinearity:
    """**Validates: Requirements 1.1, 1.4, 3.2**

    For any valid variable fee rate and energy volume (throughput), the
    calculated variable cost component SHALL equal rate × volume.
    """

    @given(
        rate=st.floats(min_value=0.30, max_value=0.50),
        throughput=st.floats(min_value=0.0, max_value=500000.0),
    )
    @settings(max_examples=100)
    def test_aemo_participant_fee_linearity(self, rate: float, throughput: float):
        """AEMO Participant Fee = rate × gross_energy (throughput)."""
        expected = rate * throughput
        # Use a battery and region with the specific rate
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(aemo_participant_rate=rate)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=throughput,
            connection_type=ConnectionType.TRANSMISSION,
            overrides=overrides,
        )
        aemo_item = next(i for i in breakdown.line_items if i.name == "AEMO Participant Fee")
        assert math.isclose(aemo_item.annual_amount, expected, rel_tol=1e-9)

    @given(
        rate=st.floats(min_value=1.0, max_value=3.0),
        throughput=st.floats(min_value=0.0, max_value=500000.0),
    )
    @settings(max_examples=100)
    def test_tuos_energy_linearity(self, rate: float, throughput: float):
        """TUOS Energy = rate × throughput."""
        expected = rate * throughput
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(tuos_energy_rate=rate)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=throughput,
            connection_type=ConnectionType.TRANSMISSION,
            overrides=overrides,
        )
        tuos_item = next(i for i in breakdown.line_items if i.name == "TUOS Energy")
        assert math.isclose(tuos_item.annual_amount, expected, rel_tol=1e-9)

    @given(
        rate=st.floats(min_value=5.0, max_value=30.0),
        throughput=st.floats(min_value=0.0, max_value=500000.0),
    )
    @settings(max_examples=100)
    def test_duos_linearity_distribution(self, rate: float, throughput: float):
        """DUOS (distribution) = rate × throughput."""
        expected = rate * throughput
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(duos_rate=rate)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=throughput,
            connection_type=ConnectionType.DISTRIBUTION,
            overrides=overrides,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        assert math.isclose(duos_item.annual_amount, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 2: Fixed Cost Independence from Throughput
# ---------------------------------------------------------------------------


class TestFixedCostIndependence:
    """**Validates: Requirements 1.3, 3.1**

    Fixed costs (TUOS Demand) don't change with throughput.
    """

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput_a=st.floats(min_value=0.0, max_value=500000.0),
        throughput_b=st.floats(min_value=0.0, max_value=500000.0),
    )
    @settings(max_examples=100)
    def test_fixed_costs_unchanged_by_throughput(
        self, battery: BatterySpecs, region: str, throughput_a: float, throughput_b: float
    ):
        """Fixed costs remain the same regardless of throughput."""
        breakdown_a = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput_a,
            connection_type=ConnectionType.TRANSMISSION,
        )
        breakdown_b = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput_b,
            connection_type=ConnectionType.TRANSMISSION,
        )
        assert math.isclose(
            breakdown_a.total_fixed_costs, breakdown_b.total_fixed_costs, rel_tol=1e-9
        )
        # Also check individual fixed line items
        fixed_items_a = [i for i in breakdown_a.line_items if i.fee_type == FeeType.FIXED]
        fixed_items_b = [i for i in breakdown_b.line_items if i.fee_type == FeeType.FIXED]
        for item_a, item_b in zip(fixed_items_a, fixed_items_b):
            assert math.isclose(item_a.annual_amount, item_b.annual_amount, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 3: DUOS Connection Type Invariant
# ---------------------------------------------------------------------------


class TestDuosConnectionTypeInvariant:
    """**Validates: Requirements 1.5**

    Transmission = 0, Distribution = rate × throughput.
    """

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput=st.floats(min_value=1.0, max_value=500000.0),
    )
    @settings(max_examples=100)
    def test_transmission_duos_is_zero(
        self, battery: BatterySpecs, region: str, throughput: float
    ):
        """Transmission-connected BESS has zero DUOS cost."""
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput,
            connection_type=ConnectionType.TRANSMISSION,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        assert duos_item.annual_amount == 0.0

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput=st.floats(min_value=1.0, max_value=500000.0),
        duos_rate=st.floats(min_value=5.0, max_value=30.0),
    )
    @settings(max_examples=100)
    def test_distribution_duos_is_positive(
        self, battery: BatterySpecs, region: str, throughput: float, duos_rate: float
    ):
        """Distribution-connected BESS with throughput > 0 has positive DUOS cost."""
        overrides = CostStructureOverrides(duos_rate=duos_rate)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput,
            connection_type=ConnectionType.DISTRIBUTION,
            overrides=overrides,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        expected = duos_rate * throughput
        assert duos_item.annual_amount > 0.0
        assert math.isclose(duos_item.annual_amount, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 4: MLF Multiplicative Application
# ---------------------------------------------------------------------------


class TestMlfMultiplicativeApplication:
    """**Validates: Requirements 1.6, 3.4**

    apply_mlf(price, mlf) = price × mlf.
    """

    @given(
        price=valid_settlement_price(),
        mlf=valid_mlf(),
    )
    @settings(max_examples=100)
    def test_mlf_is_multiplicative(self, price: float, mlf: float):
        """MLF is applied as a multiplier, not additive."""
        result = CostStructureEngine.apply_mlf(price, mlf)
        expected = price * mlf
        assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-15)

    @given(
        price=valid_settlement_price(),
    )
    @settings(max_examples=100)
    def test_mlf_identity_at_one(self, price: float):
        """MLF of 1.0 leaves price unchanged."""
        result = CostStructureEngine.apply_mlf(price, 1.0)
        assert math.isclose(result, price, rel_tol=1e-9, abs_tol=1e-15)


# ---------------------------------------------------------------------------
# Property 5: Cost Breakdown Summation Invariant
# ---------------------------------------------------------------------------


class TestCostBreakdownSummation:
    """**Validates: Requirements 3.5**

    Line items sum = total, fixed + variable = total.
    """

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput=st.floats(min_value=1.0, max_value=500000.0),
        connection_type=valid_connection_type(),
    )
    @settings(max_examples=100)
    def test_line_items_sum_equals_total(
        self, battery: BatterySpecs, region: str, throughput: float, connection_type: ConnectionType
    ):
        """Sum of all line item amounts equals total_annual_cost."""
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput,
            connection_type=connection_type,
        )
        line_items_sum = sum(item.annual_amount for item in breakdown.line_items)
        assert math.isclose(line_items_sum, breakdown.total_annual_cost, rel_tol=1e-9)

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput=st.floats(min_value=1.0, max_value=500000.0),
        connection_type=valid_connection_type(),
    )
    @settings(max_examples=100)
    def test_fixed_plus_variable_equals_total(
        self, battery: BatterySpecs, region: str, throughput: float, connection_type: ConnectionType
    ):
        """total_fixed_costs + total_variable_costs = total_annual_cost."""
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput,
            connection_type=connection_type,
        )
        assert math.isclose(
            breakdown.total_fixed_costs + breakdown.total_variable_costs,
            breakdown.total_annual_cost,
            rel_tol=1e-9,
        )

    @given(
        battery=valid_battery_specs(),
        region=valid_region(),
        throughput=st.floats(min_value=1.0, max_value=500000.0),
        connection_type=valid_connection_type(),
    )
    @settings(max_examples=100)
    def test_percentages_sum_to_100(
        self, battery: BatterySpecs, region: str, throughput: float, connection_type: ConnectionType
    ):
        """Sum of percentage_of_total values equals 100% (within tolerance)."""
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=throughput,
            connection_type=connection_type,
        )
        # Only check when total is non-zero (percentages are meaningful)
        if breakdown.total_annual_cost != 0.0:
            pct_sum = sum(item.percentage_of_total for item in breakdown.line_items)
            assert math.isclose(pct_sum, 100.0, abs_tol=0.01)


# ---------------------------------------------------------------------------
# Property 6: Regional Override Preservation
# ---------------------------------------------------------------------------


class TestRegionalOverridePreservation:
    """**Validates: Requirements 2.4, 2.5**

    Overridden values applied, non-overridden retain defaults.
    """

    @given(
        region=valid_region(),
        override_rate=st.floats(min_value=0.30, max_value=0.50),
    )
    @settings(max_examples=100)
    def test_override_applied_correctly(self, region: str, override_rate: float):
        """Overridden AEMO participant rate is applied."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(aemo_participant_rate=override_rate)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=10000.0,
            connection_type=ConnectionType.TRANSMISSION,
            overrides=overrides,
        )
        aemo_item = next(i for i in breakdown.line_items if i.name == "AEMO Participant Fee")
        expected = override_rate * 10000.0
        assert math.isclose(aemo_item.annual_amount, expected, rel_tol=1e-9)

    @given(
        region=valid_region(),
        override_tuos_demand=st.floats(min_value=5000.0, max_value=15000.0),
    )
    @settings(max_examples=100)
    def test_non_overridden_retain_defaults(self, region: str, override_tuos_demand: float):
        """Non-overridden parameters retain their regional defaults."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        defaults = CostStructureEngine.get_regional_defaults(region)

        # Only override TUOS demand
        overrides = CostStructureOverrides(tuos_demand_rate=override_tuos_demand)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region=region,
            annual_throughput_mwh=10000.0,
            connection_type=ConnectionType.TRANSMISSION,
            overrides=overrides,
        )

        # TUOS demand should use override
        tuos_item = next(i for i in breakdown.line_items if i.name == "TUOS Demand")
        expected_tuos = override_tuos_demand * battery.power_mw
        assert math.isclose(tuos_item.annual_amount, expected_tuos, rel_tol=1e-9)

        # AEMO Participant Fee should use regional default
        aemo_item = next(i for i in breakdown.line_items if i.name == "AEMO Participant Fee")
        expected_aemo = defaults.aemo_participant_fee.rate_per_mwh * 10000.0
        assert math.isclose(aemo_item.annual_amount, expected_aemo, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 20: Serialization Round-Trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """**Validates: Requirements 11.1, 11.2, 11.3**

    serialize → deserialize = original for RegionalFeeConfig.
    """

    @given(config=valid_regional_fee_config())
    @settings(max_examples=100)
    def test_regional_fee_config_round_trip(self, config: RegionalFeeConfig):
        """RegionalFeeConfig serializes to JSON and deserializes back to equal object."""
        json_str = config.model_dump_json()
        restored = RegionalFeeConfig.model_validate_json(json_str)
        assert restored == config

    @given(config=valid_regional_fee_config())
    @settings(max_examples=100)
    def test_regional_fee_config_dict_round_trip(self, config: RegionalFeeConfig):
        """RegionalFeeConfig serializes to dict and deserializes back to equal object."""
        data = config.model_dump()
        restored = RegionalFeeConfig.model_validate(data)
        assert restored == config


# ---------------------------------------------------------------------------
# Property 24: Gross Energy Calculation
# ---------------------------------------------------------------------------


class TestGrossEnergyCalculation:
    """**Validates: Requirements 3.3**

    gross_energy = charge + discharge = annual_throughput.
    """

    @given(
        charge_energy=st.floats(min_value=0.0, max_value=250000.0),
        discharge_energy=st.floats(min_value=0.0, max_value=250000.0),
    )
    @settings(max_examples=100)
    def test_gross_energy_equals_charge_plus_discharge(
        self, charge_energy: float, discharge_energy: float
    ):
        """Gross energy for AEMO fee = charge + discharge = annual_throughput."""
        annual_throughput = charge_energy + discharge_energy
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        rate = 0.40  # Default AEMO rate for NSW1

        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=annual_throughput,
            connection_type=ConnectionType.TRANSMISSION,
        )
        aemo_item = next(i for i in breakdown.line_items if i.name == "AEMO Participant Fee")
        # AEMO fee is calculated on gross energy (= annual_throughput = charge + discharge)
        expected = rate * annual_throughput
        assert math.isclose(aemo_item.annual_amount, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 23: Input Validation Rejection (Cost Structure portion)
# ---------------------------------------------------------------------------


class TestCostStructureInputValidation:
    """**Validates: Requirements 14.1, 14.2**

    Invalid MLF outside [0.50, 1.50] raises ValidationError.
    Negative fee rates raise ValidationError.
    """

    @given(
        mlf=st.floats(min_value=1.51, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_mlf_above_range_rejected(self, mlf: float):
        """MLF > 1.50 raises ValidationError."""
        with pytest.raises(ValidationError):
            MlfConfig(value=mlf)

    @given(
        mlf=st.floats(max_value=0.49, min_value=-10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_mlf_below_range_rejected(self, mlf: float):
        """MLF < 0.50 raises ValidationError."""
        with pytest.raises(ValidationError):
            MlfConfig(value=mlf)

    @given(
        rate=st.floats(max_value=-0.01, min_value=-100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_negative_aemo_participant_rate_rejected(self, rate: float):
        """Negative AEMO participant fee rate raises ValidationError."""
        with pytest.raises(ValidationError):
            AemoParticipantFee(rate_per_mwh=rate)

    @given(
        rate=st.floats(max_value=-0.01, min_value=-100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_negative_duos_rate_rejected(self, rate: float):
        """Negative DUOS rate raises ValidationError."""
        with pytest.raises(ValidationError):
            DuosCharge(rate_per_mwh=rate)

    @given(
        mlf=st.floats(min_value=0.50, max_value=1.50, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_valid_mlf_accepted(self, mlf: float):
        """Valid MLF within [0.50, 1.50] is accepted."""
        config = MlfConfig(value=mlf)
        assert config.value == mlf

    @given(
        mlf_override=st.floats(min_value=1.51, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_mlf_override_above_range_rejected(self, mlf_override: float):
        """MLF override > 1.50 in CostStructureOverrides raises ValidationError."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(mlf_value=mlf_override)

    @given(
        mlf_override=st.floats(max_value=0.49, min_value=-10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_mlf_override_below_range_rejected(self, mlf_override: float):
        """MLF override < 0.50 in CostStructureOverrides raises ValidationError."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(mlf_value=mlf_override)
