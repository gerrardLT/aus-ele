"""Unit tests for Cost Structure Engine.

Tests regional defaults, DUOS exemption, FPP classification,
and validation errors for invalid inputs.

Requirements: 1.5, 2.1, 14.1, 14.2
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from pydantic import ValidationError

from engines.cost_structure_engine import CostStructureEngine, SUPPORTED_REGIONS
from models.cost_structure_models import (
    ConnectionType,
    CostStructureOverrides,
    DuosCharge,
    FeeType,
    FppConfig,
    MlfConfig,
    RegionalFeeConfig,
)
from models.financial_params import BatterySpecs


# ---------------------------------------------------------------------------
# Test Regional Defaults for All 6 Regions (Requirement 2.1)
# ---------------------------------------------------------------------------


class TestRegionalDefaults:
    """Verify that all 6 regions have valid default configurations."""

    def test_supported_regions_count(self):
        """There should be exactly 6 supported regions."""
        assert len(SUPPORTED_REGIONS) == 6
        assert set(SUPPORTED_REGIONS) == {"NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"}

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_get_regional_defaults_returns_config(self, region: str):
        """Each region returns a valid RegionalFeeConfig."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert isinstance(config, RegionalFeeConfig)
        assert config.region == region

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_regional_aemo_participant_fee_in_range(self, region: str):
        """AEMO participant fee rate is within $0.30-$0.50/MWh."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 0.30 <= config.aemo_participant_fee.rate_per_mwh <= 0.50

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_regional_tuos_demand_in_range(self, region: str):
        """TUOS demand charge is within $5,000-$15,000/MW/year."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 5000.0 <= config.tuos_demand.rate_per_mw_year <= 15000.0

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_regional_tuos_energy_in_range(self, region: str):
        """TUOS energy charge is within $1.0-$3.0/MWh."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 1.0 <= config.tuos_energy.rate_per_mwh <= 3.0

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_regional_mlf_in_range(self, region: str):
        """MLF value is within 0.50-1.50."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 0.50 <= config.mlf.value <= 1.50

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_regional_fpp_in_range(self, region: str):
        """FPP net earning is within $500-$1,500/MW/year."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 500.0 <= config.fpp.net_earning_per_mw_year <= 1500.0

    def test_unknown_region_raises_error(self):
        """Unknown region code raises ValueError."""
        with pytest.raises(ValueError, match="Unknown region"):
            CostStructureEngine.get_regional_defaults("INVALID")

    def test_regional_defaults_returns_copy(self):
        """get_regional_defaults returns a deep copy (mutation-safe)."""
        config_a = CostStructureEngine.get_regional_defaults("NSW1")
        config_b = CostStructureEngine.get_regional_defaults("NSW1")
        config_a.mlf.value = 0.50
        assert config_b.mlf.value != 0.50  # Original unchanged


# ---------------------------------------------------------------------------
# Test DUOS Exemption for Transmission-Connected BESS (Requirement 1.5)
# ---------------------------------------------------------------------------


class TestDuosExemption:
    """Verify DUOS exemption logic for transmission-connected BESS."""

    def test_transmission_connected_duos_is_zero(self):
        """Transmission-connected BESS has zero DUOS cost."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=50000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        assert duos_item.annual_amount == 0.0

    def test_distribution_connected_duos_is_positive(self):
        """Distribution-connected BESS has positive DUOS cost."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(duos_rate=15.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=50000.0,
            connection_type=ConnectionType.DISTRIBUTION,
            overrides=overrides,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        assert duos_item.annual_amount == 15.0 * 50000.0

    def test_distribution_connected_zero_throughput(self):
        """Distribution-connected with zero throughput has zero DUOS cost."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        overrides = CostStructureOverrides(duos_rate=15.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=0.0,
            connection_type=ConnectionType.DISTRIBUTION,
            overrides=overrides,
        )
        duos_item = next(i for i in breakdown.line_items if i.name == "DUOS")
        assert duos_item.annual_amount == 0.0

    def test_all_regions_default_transmission(self):
        """All regions default to transmission connection (DUOS = 0)."""
        for region in SUPPORTED_REGIONS:
            config = CostStructureEngine.get_regional_defaults(region)
            assert config.duos.connection_type == ConnectionType.TRANSMISSION
            assert config.duos.rate_per_mwh == 0.0


# ---------------------------------------------------------------------------
# Test FPP Classification and Range (Requirement 1.7)
# ---------------------------------------------------------------------------


class TestFppClassification:
    """Verify FPP is classified as VARIABLE and within valid range."""

    def test_fpp_is_variable_type(self):
        """FPP is classified as VARIABLE fee type."""
        config = CostStructureEngine.get_regional_defaults("NSW1")
        assert config.fpp.fee_type == FeeType.VARIABLE

    def test_fpp_appears_as_negative_cost(self):
        """FPP appears as a negative cost (net earning reduces total)."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=50000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )
        fpp_item = next(i for i in breakdown.line_items if "FPP" in i.name)
        assert fpp_item.annual_amount < 0.0  # Net earning = negative cost

    def test_fpp_scales_with_power_mw(self):
        """FPP earning scales with battery power capacity."""
        battery_small = BatterySpecs(power_mw=50.0, duration_hours=4.0)
        battery_large = BatterySpecs(power_mw=200.0, duration_hours=4.0)

        breakdown_small = CostStructureEngine.calculate_annual_costs(
            battery=battery_small,
            region="NSW1",
            annual_throughput_mwh=50000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )
        breakdown_large = CostStructureEngine.calculate_annual_costs(
            battery=battery_large,
            region="NSW1",
            annual_throughput_mwh=50000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )

        fpp_small = next(i for i in breakdown_small.line_items if "FPP" in i.name)
        fpp_large = next(i for i in breakdown_large.line_items if "FPP" in i.name)

        # FPP earning is per MW, so 200MW should be 4x of 50MW
        assert abs(fpp_large.annual_amount) == abs(fpp_small.annual_amount) * 4.0

    @pytest.mark.parametrize("region", SUPPORTED_REGIONS)
    def test_fpp_earning_within_valid_range(self, region: str):
        """FPP net earning per MW/year is within $500-$1,500."""
        config = CostStructureEngine.get_regional_defaults(region)
        assert 500.0 <= config.fpp.net_earning_per_mw_year <= 1500.0


# ---------------------------------------------------------------------------
# Test Validation Errors for Invalid MLF and Negative Rates (Req 14.1, 14.2)
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """Verify that invalid inputs are rejected with validation errors."""

    def test_mlf_below_minimum_rejected(self):
        """MLF value below 0.50 is rejected."""
        with pytest.raises(ValidationError):
            MlfConfig(value=0.49)

    def test_mlf_above_maximum_rejected(self):
        """MLF value above 1.50 is rejected."""
        with pytest.raises(ValidationError):
            MlfConfig(value=1.51)

    def test_mlf_at_boundaries_accepted(self):
        """MLF values at exact boundaries (0.50, 1.50) are accepted."""
        config_low = MlfConfig(value=0.50)
        config_high = MlfConfig(value=1.50)
        assert config_low.value == 0.50
        assert config_high.value == 1.50

    def test_negative_aemo_rate_rejected(self):
        """Negative AEMO participant fee rate is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(aemo_participant_rate=-0.1)

    def test_aemo_rate_below_minimum_rejected(self):
        """AEMO rate below $0.30 is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(aemo_participant_rate=0.29)

    def test_aemo_rate_above_maximum_rejected(self):
        """AEMO rate above $0.50 is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(aemo_participant_rate=0.51)

    def test_negative_duos_rate_rejected(self):
        """Negative DUOS rate is rejected."""
        with pytest.raises(ValidationError):
            DuosCharge(rate_per_mwh=-1.0)

    def test_negative_tuos_demand_rejected(self):
        """TUOS demand rate below minimum is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(tuos_demand_rate=4999.0)

    def test_negative_fpp_earning_rejected(self):
        """FPP earning below minimum is rejected."""
        with pytest.raises(ValidationError):
            FppConfig(net_earning_per_mw_year=499.0)

    def test_mlf_override_below_minimum_rejected(self):
        """MLF override below 0.50 is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(mlf_value=0.49)

    def test_mlf_override_above_maximum_rejected(self):
        """MLF override above 1.50 is rejected."""
        with pytest.raises(ValidationError):
            CostStructureOverrides(mlf_value=1.51)
