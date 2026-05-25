"""Validate Financial Accuracy Modules against real market data.

Real-world benchmarks (2024 Modo Energy data):
- NEM BESS average revenue: $148k/MW/year
- Energy trading: 69% of revenue
- FCAS: 31% (declining rapidly)
- MLF impact: up to $75k/MW in constrained regions
- TUOS demand: $5k-15k/MW/year (transmission-connected)
- AEMO participant fees: ~$0.30-0.50/MWh on gross energy
"""
import sys
import json
sys.path.insert(0, "backend")

from engines.cost_structure_engine import CostStructureEngine
from engines.tax_model import TaxModel
from engines.forward_price_engine import ForwardPriceEngine
from models.cost_structure_models import ConnectionType
from models.tax_models import TaxConfig, EntityType, DepreciationMethod
from models.forward_price_models import ScenarioType
from models.financial_params import BatterySpecs, CashFlowYear

print("=" * 70)
print("VALIDATION: Financial Accuracy Modules vs Real Market Data")
print("=" * 70)

# --- 1. Cost Structure Validation ---
print("\n--- 1. COST STRUCTURE (NSW1, 100MW/4h, Transmission) ---")
battery = BatterySpecs(power_mw=100, duration_hours=4)
breakdown = CostStructureEngine.calculate_annual_costs(
    battery=battery, region="NSW1",
    annual_throughput_mwh=200000,  # ~1.4 cycles/day typical
    connection_type=ConnectionType.TRANSMISSION,
)
print(f"Total Annual Cost: ${breakdown.total_annual_cost:,.0f}")
print(f"  Fixed: ${breakdown.total_fixed_costs:,.0f} ({breakdown.total_fixed_costs/breakdown.total_annual_cost*100:.0f}%)")
print(f"  Variable: ${breakdown.total_variable_costs:,.0f} ({breakdown.total_variable_costs/breakdown.total_annual_cost*100:.0f}%)")
print(f"  MLF Applied: {breakdown.mlf_applied}")
for item in breakdown.line_items:
    print(f"    {item.name}: ${item.annual_amount:,.0f} ({item.fee_type})")

# Real-world check
print("\n  [VALIDATION]")
print(f"  TUOS Demand $12k/MW/yr x 100MW = $1.2M -> Got ${breakdown.line_items[1].annual_amount:,.0f} ✓" if abs(breakdown.line_items[1].annual_amount - 1200000) < 1000 else "  TUOS Demand ✗")
print(f"  AEMO Fee $0.40/MWh x 200k MWh = $80k -> Got ${breakdown.line_items[0].annual_amount:,.0f} ✓" if abs(breakdown.line_items[0].annual_amount - 80000) < 1000 else "  AEMO Fee ✗")
print(f"  Cost/MW/yr = ${breakdown.total_annual_cost/100:,.0f} (real-world: $10k-20k/MW/yr for network fees)")

# --- 2. Forward Price Scenarios ---
print("\n--- 2. FORWARD PRICE SCENARIOS (NSW1) ---")
engine = ForwardPriceEngine()
scenarios = engine.get_scenarios()
print(f"Available scenarios: {[s.name for s in scenarios]}")

for scenario_type in [ScenarioType.CENTRAL, ScenarioType.HIGH, ScenarioType.LOW]:
    proj = engine.generate_20year_projection("NSW1", scenario_type, battery)
    yr1 = proj.annual_projections[0]
    yr10 = proj.annual_projections[9]
    yr20 = proj.annual_projections[19]
    print(f"\n  {scenario_type.value.upper()} Scenario:")
    print(f"    Year 1: ${yr1.estimated_revenue_per_mw:,.0f}/MW (spread=${yr1.mean_spread:.0f}, capture={yr1.capture_rate:.2f})")
    print(f"    Year 10: ${yr10.estimated_revenue_per_mw:,.0f}/MW (SoH={yr10.state_of_health:.2f})")
    print(f"    Year 20: ${yr20.estimated_revenue_per_mw:,.0f}/MW (SoH={yr20.state_of_health:.2f})")
    print(f"    20yr Total: ${proj.total_revenue_per_mw:,.0f}/MW, NPV: ${proj.npv_per_mw:,.0f}/MW")

# Real-world check
print("\n  [VALIDATION]")
central = engine.generate_20year_projection("NSW1", ScenarioType.CENTRAL, battery)
yr1_rev = central.annual_projections[0].estimated_revenue_per_mw
print(f"  2024 actual NEM avg: $148k/MW/yr (Modo Energy)")
print(f"  Model Year 1 (Central): ${yr1_rev:,.0f}/MW/yr")
if 80000 < yr1_rev < 200000:
    print(f"  -> Within reasonable range ✓")
else:
    print(f"  -> Outside expected range ✗")

# --- 3. Tax Model ---
print("\n--- 3. TAX MODEL (Standard Entity, DV, 20yr life) ---")
tax_config = TaxConfig(
    entity_type=EntityType.STANDARD,
    depreciation_method=DepreciationMethod.DIMINISHING_VALUE,
    effective_life_years=20,
)
tax_model = TaxModel(config=tax_config)

# Simulate 5 years of cash flows
capex = 350 * battery.capacity_mwh * 1000 + 5_000_000  # $145M for 100MW/4h
annual_revenue = 148000 * 100  # $14.8M (based on 2024 actual)
annual_opex = breakdown.total_annual_cost  # From cost structure

print(f"  CAPEX: ${capex:,.0f}")
print(f"  Annual Revenue: ${annual_revenue:,.0f}")
print(f"  Annual Opex: ${annual_opex:,.0f}")
print(f"  Tax Rate: {tax_config.tax_rate*100:.0f}%")
print(f"  Depreciation Method: {tax_config.depreciation_method.value}")

# Build mock cash flows
cash_flows = []
for yr in range(1, 21):
    soh = max(0, 1 - 0.015 * yr)
    rev = annual_revenue * soh
    net = rev - annual_opex
    cash_flows.append(CashFlowYear(
        year=yr, revenue_arbitrage=rev*0.7, revenue_fcas=rev*0.3,
        revenue_capacity=0, total_revenue=rev, opex=annual_opex,
        augmentation_capex=0, net_cash_flow=net,
        cumulative_cash_flow=net*yr, state_of_health=soh, annual_cycles=365,
    ))

result = tax_model.calculate_after_tax_cash_flows(
    pre_tax_cash_flows=cash_flows, capex=capex,
    annual_debt_service=0, debt_tenor=0,
)

print(f"\n  Pre-tax IRR: {result.pre_tax_irr*100:.1f}%" if result.pre_tax_irr else "  Pre-tax IRR: N/A")
print(f"  After-tax IRR: {result.after_tax_irr*100:.1f}%" if result.after_tax_irr else "  After-tax IRR: N/A")
print(f"  Pre-tax NPV: ${result.pre_tax_npv:,.0f}")
print(f"  After-tax NPV: ${result.after_tax_npv:,.0f}")
print(f"  Total Tax Paid (20yr): ${result.tax_summary.total_tax_paid:,.0f}")
print(f"  Depreciation Tax Shield NPV: ${result.tax_summary.npv_depreciation_tax_shield:,.0f}")

# Real-world check
print("\n  [VALIDATION]")
if result.pre_tax_irr and result.after_tax_irr:
    tax_drag = (result.pre_tax_irr - result.after_tax_irr) * 100
    print(f"  Tax drag on IRR: {tax_drag:.1f}pp (expected 2-4pp for 30% tax)")
    if 1.5 < tax_drag < 6:
        print(f"  -> Reasonable tax impact ✓")
    else:
        print(f"  -> Unexpected tax impact ✗")

print("\n" + "=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)
