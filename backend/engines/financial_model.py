from typing import List, Dict, Optional
import numpy_financial as npf
import numpy as np
from models.financial_params import (
    InvestmentParams, ScenarioConfig, FinancialMetrics,
    CashFlowYear, ScenarioResult, MonteCarloResult, BatterySpecs
)
from engines.battery_model import BatteryModel


class FinancialModel:
    @staticmethod
    def calculate_metrics(
        cash_flows: List[float],
        total_capex: float,
        discount_rate: float = 0.08,
    ) -> FinancialMetrics:
        """
        Calculate NPV, IRR, ROI, and payback from a list of annual net cash flows.
        cash_flows[0] should be the negative initial CAPEX.
        """
        npv_val = npf.npv(discount_rate, cash_flows)
        try:
            irr_val = npf.irr(cash_flows)
        except Exception:
            irr_val = None

        roi = sum(cash_flows[1:]) / total_capex if total_capex > 0 else 0

        cumulative = 0.0
        payback = None
        for i, cf in enumerate(cash_flows):
            cumulative += cf
            if cumulative >= 0 and payback is None and i > 0:
                payback = i

        return FinancialMetrics(
            npv=float(npv_val) if not np.isnan(npv_val) else 0.0,
            irr=float(irr_val) if irr_val is not None and not np.isnan(irr_val) else None,
            roi_pct=float(roi) * 100,
            payback_years=payback,
            total_capex=total_capex,
        )

    @staticmethod
    def run_scenario(
        params: InvestmentParams,
        scenario: ScenarioConfig,
        baseline_arbitrage: float,
        baseline_fcas: float,
        annual_cycles_history: List[float],
    ) -> ScenarioResult:
        """
        Build a full 20-year (or N-year) cash-flow model for a single scenario.

        baseline_arbitrage / baseline_fcas are the *annual* revenue numbers
        (already multiplied by capture_rate for arbitrage).
        """
        # Create an immutable copy of battery specs for degradation scaling
        scaled_specs = BatterySpecs(
            power_mw=params.battery.power_mw,
            duration_hours=params.battery.duration_hours,
            round_trip_efficiency=params.battery.round_trip_efficiency,
            calendar_degradation_rate=params.battery.calendar_degradation_rate * scenario.degradation_multiplier,
            base_cycle_degradation_rate=params.battery.base_cycle_degradation_rate * scenario.degradation_multiplier,
            dod_non_linear_factor=params.battery.dod_non_linear_factor,
            augmentation_threshold_soc=params.battery.augmentation_threshold_soc,
        )
        battery_model = BatteryModel(scaled_specs)

        # CAPEX
        capex = (params.financial.capex_per_kwh * params.battery.capacity_mwh * 1000) * scenario.capex_multiplier
        total_capex = capex + params.financial.grid_connection_cost

        # Baseline revenues with scenario multipliers
        arb_rev = baseline_arbitrage * scenario.arbitrage_multiplier
        fcas_rev = baseline_fcas * scenario.fcas_multiplier
        cap_rev = params.financial.capacity_payment_per_mw_year * params.battery.power_mw

        soh_history, aug_schedule = battery_model.simulate_lifetime(
            annual_cycles_history,
            params.financial.project_life_years,
        )

        cash_flow_years: List[CashFlowYear] = []
        net_cfs = [-total_capex]
        cumulative = -total_capex

        for yr in range(1, params.financial.project_life_years + 1):
            soh = soh_history[yr - 1]

            # Revenue degrades with remaining capacity
            yr_arb = arb_rev * soh
            yr_fcas = fcas_rev * soh
            yr_cap = cap_rev  # capacity payments don't degrade
            total_rev = yr_arb + yr_fcas + yr_cap

            # Opex
            fixed_om = (
                params.financial.fixed_om_per_mw_year * params.battery.power_mw
                + params.financial.land_lease_per_year
            )
            expected_cycles = (
                annual_cycles_history[yr - 1]
                if (yr - 1) < len(annual_cycles_history)
                else (sum(annual_cycles_history) / len(annual_cycles_history) if annual_cycles_history else 365.0)
            )
            throughput_mwh = expected_cycles * params.battery.capacity_mwh * soh
            var_om = params.financial.variable_om_per_mwh * throughput_mwh
            total_opex = fixed_om + var_om

            # Augmentation Capex
            aug_pct = aug_schedule[yr - 1]
            aug_capex = aug_pct * capex

            net_cf = total_rev - total_opex - aug_capex
            cumulative += net_cf
            net_cfs.append(net_cf)

            cash_flow_years.append(CashFlowYear(
                year=yr,
                revenue_arbitrage=yr_arb,
                revenue_fcas=yr_fcas,
                revenue_capacity=yr_cap,
                total_revenue=total_rev,
                opex=total_opex,
                augmentation_capex=aug_capex,
                net_cash_flow=net_cf,
                cumulative_cash_flow=cumulative,
                state_of_health=soh,
                annual_cycles=expected_cycles,
            ))

        # Project Finance: Debt Sizing based on CFADS (Cash Flow Available for Debt Service)
        # Assuming CFADS = net_cf (simplified, no tax/depreciation modeled here)
        # Debt size is determined by the minimum DSCR over the debt tenor
        tenor = min(params.financial.debt_tenor_years, params.financial.project_life_years)
        cfads_tenor = net_cfs[1:tenor+1] # Operating cash flows during tenor
        
        # Calculate maximum annual debt service that maintains target DSCR
        # We find the min CFADS to be conservative, or we could size it on average.
        # Standard approach: Size to P50/Base minimum or average. We'll use average CFADS / target_dscr for simplicity
        avg_cfads = sum(cfads_tenor) / len(cfads_tenor) if cfads_tenor else 0.0
        max_annual_debt_service = max(0.0, avg_cfads / params.financial.target_dscr) if params.financial.target_dscr > 0 else 0.0
        
        # Calculate Debt Capacity (PV of debt service at cost of debt)
        debt_capacity = npf.pv(params.financial.cost_of_debt, tenor, -max_annual_debt_service, 0) if max_annual_debt_service > 0 else 0.0
        # Cap debt at total capex (e.g. max 100% leverage, usually capped at 70-80%)
        debt_capacity = min(debt_capacity, total_capex * 0.8)
        
        # Re-calculate actual debt service based on finalized debt capacity (standard annuity)
        actual_annual_debt_service = -npf.pmt(params.financial.cost_of_debt, tenor, debt_capacity) if debt_capacity > 0 else 0.0
        
        # Calculate levered cash flows
        equity_capex = total_capex - debt_capacity
        levered_cfs = [-equity_capex]
        
        for idx, cfy in enumerate(cash_flow_years):
            yr = cfy.year
            ds = actual_annual_debt_service if yr <= tenor else 0.0
            lcf = cfy.net_cash_flow - ds
            cfy.debt_service = ds
            cfy.levered_cash_flow = lcf
            levered_cfs.append(lcf)
            
        metrics = FinancialModel.calculate_metrics(
            net_cfs, total_capex, discount_rate=params.financial.discount_rate,
        )
        
        # Update metrics with Project Finance results
        metrics.debt_capacity = float(debt_capacity)
        try:
            l_irr = npf.irr(levered_cfs)
            metrics.levered_irr = float(l_irr) if not np.isnan(l_irr) else None
        except Exception:
            metrics.levered_irr = None
            
        # Actual DSCR
        dscr_values = [cfy.net_cash_flow / actual_annual_debt_service for cfy in cash_flow_years if cfy.year <= tenor and actual_annual_debt_service > 0]
        metrics.dscr_avg = float(sum(dscr_values) / len(dscr_values)) if dscr_values else 0.0

        return ScenarioResult(
            scenario_name=scenario.name,
            metrics=metrics,
            cash_flows=cash_flow_years,
        )

    @staticmethod
    def run_monte_carlo(
        params: InvestmentParams,
        baseline_arbitrage: float,
        baseline_fcas: float,
        annual_cycles_history: List[float],
    ) -> MonteCarloResult:
        npvs: List[float] = []
        irrs: List[float] = []

        rng = np.random.default_rng()

        for _ in range(params.monte_carlo.iterations):
            capex_mult = rng.normal(1.0, params.monte_carlo.capex_volatility)
            rev_mult = rng.normal(1.0, params.monte_carlo.market_volatility)
            deg_mult = rng.normal(1.0, params.monte_carlo.degradation_volatility)

            scenario = ScenarioConfig(
                name="MC",
                capex_multiplier=max(0.5, capex_mult),
                arbitrage_multiplier=max(0.0, rev_mult),
                fcas_multiplier=max(0.0, rev_mult),
                degradation_multiplier=max(0.5, deg_mult),
            )

            res = FinancialModel.run_scenario(
                params, scenario, baseline_arbitrage, baseline_fcas, annual_cycles_history,
            )

            npvs.append(res.metrics.npv)
            if res.metrics.irr is not None:
                irrs.append(res.metrics.irr)

        return MonteCarloResult(
            npv_p10=float(np.percentile(npvs, 10)),
            npv_p50=float(np.percentile(npvs, 50)),
            npv_p90=float(np.percentile(npvs, 90)),
            irr_p10=float(np.percentile(irrs, 10)) if irrs else None,
            irr_p50=float(np.percentile(irrs, 50)) if irrs else None,
            irr_p90=float(np.percentile(irrs, 90)) if irrs else None,
        )
