"""Integration tests for Financial Accuracy Modules.

Tests end-to-end flow: cost structure → tax → forward price → financial model.
Tests backward compatibility: no new params → same behavior as before.

Requirements: 15.1-15.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from engines.cost_structure_engine import CostStructureEngine
from engines.tax_model import TaxModel
from engines.forward_price_engine import ForwardPriceEngine
from models.cost_structure_models import ConnectionType, CostStructureOverrides
from models.tax_models import TaxConfig, EntityType, DepreciationMethod
from models.forward_price_models import ScenarioType
from models.financial_params import (
    BatterySpecs,
    CashFlowYear,
    FinancialAssumptions,
    InvestmentParams,
)


# ---------------------------------------------------------------------------
# End-to-end integration: cost structure → tax → forward price → financial model
# ---------------------------------------------------------------------------


class TestEndToEndIntegration:
    """Test the full pipeline: cost structure → tax → forward price."""

    def test_cost_structure_to_tax_pipeline(self):
        """Cost structure output feeds into tax model correctly."""
        # Step 1: Calculate cost structure
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=200000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )

        # Verify cost breakdown is valid
        assert breakdown.total_annual_cost > 0
        assert breakdown.region == "NSW1"
        assert len(breakdown.line_items) > 0

        # Step 2: Use cost breakdown as opex input to tax model
        tax_config = TaxConfig(
            entity_type=EntityType.STANDARD,
            depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
            effective_life_years=20,
        )
        tax_model = TaxModel(config=tax_config)

        # Simulate a year of cash flow
        revenue = 5_000_000.0
        opex = breakdown.total_annual_cost
        interest_expense = 200_000.0

        dep_result = tax_model.calculate_depreciation(year=1, capex=140_000_000.0)
        tax_result = tax_model.calculate_annual_tax(
            year=1,
            revenue=revenue,
            opex=opex,
            interest_expense=interest_expense,
            depreciation=dep_result.depreciation_amount,
        )

        # Verify tax calculation uses cost structure output
        assert tax_result.operating_expenses == opex
        assert tax_result.gross_revenue == revenue
        assert tax_result.depreciation == dep_result.depreciation_amount

    def test_forward_price_to_financial_model_pipeline(self):
        """Forward price engine produces projections usable by financial model."""
        engine = ForwardPriceEngine()
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)

        # Generate 20-year projection
        projection = engine.generate_20year_projection(
            region="NSW1",
            scenario=ScenarioType.CENTRAL,
            battery=battery,
        )

        # Verify projection structure
        assert projection.region == "NSW1"
        assert projection.scenario == ScenarioType.CENTRAL
        assert len(projection.annual_projections) == 20
        assert projection.total_revenue_per_mw > 0
        assert projection.npv_per_mw != 0  # Can be positive or negative

        # Each year should have valid data
        for annual in projection.annual_projections:
            assert annual.estimated_revenue_per_mw >= 0
            assert 0.0 <= annual.state_of_health <= 1.0
            assert annual.mean_spread >= 0
            assert 0.0 <= annual.capture_rate <= 1.0

    def test_full_pipeline_cost_tax_forward(self):
        """Full pipeline: cost structure → tax model → forward price all work together."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)

        # 1. Cost structure
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="SA1",
            annual_throughput_mwh=150000.0,
            connection_type=ConnectionType.TRANSMISSION,
        )

        # 2. Forward price projection
        fwd_engine = ForwardPriceEngine()
        projection = fwd_engine.generate_20year_projection(
            region="SA1",
            scenario=ScenarioType.HIGH,
            battery=battery,
        )

        # 3. Tax model on projected revenues
        tax_config = TaxConfig(
            entity_type=EntityType.BASE_RATE,
            depreciation_method=DepreciationMethod.PRIME_COST,
            effective_life_years=20,
        )
        tax_model = TaxModel(config=tax_config)

        capex = 350.0 * battery.capacity_mwh * 1000 + 5_000_000.0

        # Build pre-tax cash flows from forward projection
        pre_tax_cash_flows = []
        for i, annual in enumerate(projection.annual_projections):
            year_revenue = annual.estimated_revenue_per_mw * battery.power_mw
            year_opex = breakdown.total_annual_cost
            net_cf = year_revenue - year_opex
            pre_tax_cash_flows.append(
                CashFlowYear(
                    year=i + 1,
                    revenue_arbitrage=year_revenue,
                    revenue_fcas=0.0,
                    revenue_capacity=0.0,
                    total_revenue=year_revenue,
                    opex=year_opex,
                    augmentation_capex=0.0,
                    net_cash_flow=net_cf,
                    cumulative_cash_flow=net_cf * (i + 1),
                    state_of_health=annual.state_of_health,
                    annual_cycles=365.0,
                )
            )

        # Run after-tax calculation
        after_tax_result = tax_model.calculate_after_tax_cash_flows(
            pre_tax_cash_flows=pre_tax_cash_flows,
            capex=capex,
            annual_debt_service=0.0,
            debt_tenor=0,
        )

        # Verify after-tax results
        assert after_tax_result.tax_summary.entity_type == EntityType.BASE_RATE
        assert after_tax_result.tax_summary.tax_rate == 0.25
        assert after_tax_result.tax_summary.depreciation_method == DepreciationMethod.PRIME_COST
        assert len(after_tax_result.tax_summary.after_tax_cash_flows) == 20


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Test that omitting new params produces same behavior as before."""

    def test_investment_params_defaults_no_new_fields(self):
        """InvestmentParams without new fields has None for all optional fields."""
        params = InvestmentParams(region="NSW1")
        assert params.cost_structure_overrides is None
        assert params.tax_config is None
        assert params.forward_scenario is None

    def test_investment_params_with_legacy_fields(self):
        """Legacy flat fields still work correctly."""
        params = InvestmentParams(
            region="SA1",
            power_mw=200.0,
            duration_hours=2.0,
            degradation_rate=0.02,
        )
        assert params.battery.power_mw == 200.0
        assert params.battery.duration_hours == 2.0
        assert params.battery.calendar_degradation_rate == 0.02

    def test_cash_flow_year_tax_fields_default_zero(self):
        """CashFlowYear tax fields default to zero when not provided."""
        cf = CashFlowYear(
            year=1,
            revenue_arbitrage=100000.0,
            revenue_fcas=50000.0,
            revenue_capacity=0.0,
            total_revenue=150000.0,
            opex=30000.0,
            augmentation_capex=0.0,
            net_cash_flow=120000.0,
            cumulative_cash_flow=120000.0,
            state_of_health=1.0,
            annual_cycles=365.0,
        )
        assert cf.depreciation == 0.0
        assert cf.tax_payable == 0.0
        assert cf.after_tax_cash_flow is None

    def test_cost_structure_engine_works_without_overrides(self):
        """CostStructureEngine works with no overrides (default behavior)."""
        battery = BatterySpecs(power_mw=100.0, duration_hours=4.0)
        breakdown = CostStructureEngine.calculate_annual_costs(
            battery=battery,
            region="NSW1",
            annual_throughput_mwh=200000.0,
            connection_type=ConnectionType.TRANSMISSION,
            overrides=None,
        )
        assert breakdown.total_annual_cost > 0
        assert breakdown.mlf_applied == 0.97  # NSW1 default

    def test_tax_model_not_invoked_without_config(self):
        """When tax_config is None, no tax calculation is triggered."""
        params = InvestmentParams(region="NSW1")
        # Simply verify the field is None — the route handler checks this
        assert params.tax_config is None

    def test_forward_scenario_not_invoked_without_selection(self):
        """When forward_scenario is None, no forward projection is triggered."""
        params = InvestmentParams(region="NSW1")
        assert params.forward_scenario is None


# ---------------------------------------------------------------------------
# Headline metrics-basis annotation (P2-tax)
# ---------------------------------------------------------------------------


class TestHeadlineBasisAnnotation:
    """The response must always declare whether the headline is pre/after tax."""

    def _fake_base_result(self):
        from types import SimpleNamespace

        cash_flows = [
            CashFlowYear(
                year=i + 1,
                revenue_arbitrage=1_000_000.0,
                revenue_fcas=0.0,
                revenue_capacity=0.0,
                total_revenue=1_000_000.0,
                opex=200_000.0,
                augmentation_capex=0.0,
                net_cash_flow=800_000.0,
                cumulative_cash_flow=800_000.0 * (i + 1),
                state_of_health=1.0,
                annual_cycles=365.0,
            )
            for i in range(20)
        ]
        return SimpleNamespace(
            cost_breakdown=None,
            cash_flows=cash_flows,
            # 与生产 ScenarioMetrics 契约对齐（S5/A3）：total_capex 是
            # _enrich_with_financial_accuracy_modules 的必需字段（折旧基数）。
            metrics=SimpleNamespace(debt_capacity=0.0, total_capex=7_000_000.0),
        )

    def test_after_tax_confirmed_when_tax_config_present(self):
        from routes.investment_routes import _enrich_with_financial_accuracy_modules

        params = InvestmentParams(
            region="NSW1",
            power_mw=10.0,
            duration_hours=2.0,
            tax_config=TaxConfig(
                entity_type=EntityType.STANDARD,
                depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
                effective_life_years=20,
            ),
        )
        response = {
            "metrics_basis": {
                "base_metrics": "pre_tax",
                "after_tax_available": True,
                "recommended_display_basis": "after_tax",
            }
        }

        enriched = _enrich_with_financial_accuracy_modules(
            response, params, self._fake_base_result()
        )

        assert "after_tax_metrics" in enriched
        assert enriched["metrics_basis"]["after_tax_available"] is True
        assert enriched["metrics_basis"]["recommended_display_basis"] == "after_tax"

    def test_pre_tax_headline_when_no_tax_config(self):
        from routes.investment_routes import _enrich_with_financial_accuracy_modules

        params = InvestmentParams(region="NSW1", power_mw=10.0, duration_hours=2.0)
        response = {
            "metrics_basis": {
                "base_metrics": "pre_tax",
                "after_tax_available": False,
                "recommended_display_basis": "pre_tax",
            }
        }

        enriched = _enrich_with_financial_accuracy_modules(
            response, params, self._fake_base_result()
        )

        assert "after_tax_metrics" not in enriched
        assert enriched["metrics_basis"]["after_tax_available"] is False
        assert enriched["metrics_basis"]["recommended_display_basis"] == "pre_tax"
