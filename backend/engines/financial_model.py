from typing import List, Dict, Optional
import numpy_financial as npf
import numpy as np
from models.financial_params import (
    InvestmentParams, ScenarioConfig, FinancialMetrics,
    CashFlowYear, ScenarioResult, MonteCarloResult, BatterySpecs
)
from models.cost_structure_models import ConnectionType, AnnualCostBreakdown
from engines.battery_model import BatteryModel
from engines.cost_structure_engine import CostStructureEngine


class FinancialModel:
    @staticmethod
    def compute_cannibalization_decay_factors(
        n_years: int,
        alpha: float = 0.6,
        annual_growth_rate: float = 0.10,
    ) -> List[float]:
        """Compute per-year arbitrage revenue decay factors from market BESS growth.

        Power-law model (S3/B3):
            decay_factor_t = 1 / (1 + annual_growth_rate * t) ^ alpha

        Factor is 1.0 at t=0 (no decay in year 1's baseline) and monotonically
        decreases as cumulative market capacity dilutes per-MW revenue.

        Args:
            n_years: Project life in years.
            alpha: Power-law exponent (~0.6 from QLD empirical fit).
            annual_growth_rate: Fractional market BESS capacity growth per year.

        Returns:
            List of n_years decay factors, each in (0, 1].
        """
        factors: List[float] = []
        for t in range(n_years):
            capacity_ratio = 1.0 + annual_growth_rate * t
            factors.append(1.0 / (capacity_ratio ** alpha))
        return factors

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

        # S4/M2: Count sign changes to assess IRR reliability.
        # Multiple sign changes (≥2) imply multiple IRR roots; fall back to MIRR.
        sign_changes = 0
        for i in range(1, len(cash_flows)):
            if cash_flows[i - 1] * cash_flows[i] < 0:
                sign_changes += 1
        irr_reliable = sign_changes <= 1

        mirr_val: Optional[float] = None
        if sign_changes >= 2:
            try:
                mirr_val = float(npf.mirr(
                    cash_flows,
                    finance_rate=discount_rate,
                    reinvest_rate=discount_rate,
                ))
            except Exception:
                mirr_val = None

        roi = sum(cash_flows[1:]) / total_capex if total_capex > 0 else 0

        # S4/M1: Payback with linear interpolation within the crossing year.
        cumulative = 0.0
        payback: Optional[float] = None
        for i, cf in enumerate(cash_flows):
            prev_cumulative = cumulative
            cumulative += cf
            if cumulative >= 0 and payback is None and i > 0:
                # Fraction of year i needed to recover the remaining deficit
                if cf > 0:
                    fraction = -prev_cumulative / cf
                else:
                    fraction = 0.0
                payback = (i - 1) + fraction

        return FinancialMetrics(
            npv=float(npv_val) if not np.isnan(npv_val) else 0.0,
            irr=float(irr_val) if irr_val is not None and not np.isnan(irr_val) else None,
            roi_pct=float(roi) * 100,
            payback_years=payback,
            total_capex=total_capex,
            irr_reliable=irr_reliable,
            mirr=mirr_val,
            roi_undiscounted=True,  # S4/M5: explicitly flag ROI as undiscounted
        )

    @staticmethod
    def run_scenario(
        params: InvestmentParams,
        scenario: ScenarioConfig,
        baseline_arbitrage: float,
        baseline_fcas: float,
        annual_cycles_history: List[float],
        dod_severity_history: Optional[List[float]] = None,
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
            knee_point_soh=params.battery.knee_point_soh,
            knee_acceleration_factor=params.battery.knee_acceleration_factor,
        )
        battery_model = BatteryModel(scaled_specs)

        # CAPEX
        capex = (params.financial.capex_per_kwh * params.battery.capacity_mwh * 1000) * scenario.capex_multiplier
        total_capex = capex + params.financial.grid_connection_cost

        # Baseline revenues with scenario multipliers.
        # Per-year multiplier vectors (when supplied by Monte Carlo AR(1) draws)
        # take precedence over the scalar multiplier for each project year.
        arb_rev = baseline_arbitrage * scenario.arbitrage_multiplier
        fcas_rev = baseline_fcas * scenario.fcas_multiplier
        arb_mult_by_year = scenario.arbitrage_multipliers_by_year
        fcas_mult_by_year = scenario.fcas_multipliers_by_year
        cap_rev = params.financial.capacity_payment_per_mw_year * params.battery.power_mw

        soh_history, aug_schedule = battery_model.simulate_lifetime(
            annual_cycles_history,
            params.financial.project_life_years,
            dod_severity_history,
        )

        cash_flow_years: List[CashFlowYear] = []
        net_cfs = [-total_capex]
        cumulative = -total_capex
        cost_breakdown: Optional[AnnualCostBreakdown] = None

        # S3/B3: cannibalization decay factors (all 1.0 when disabled → zero-regression)
        cannibalization_factors: Optional[List[float]] = None
        if params.apply_cannibalization:
            cannibalization_factors = FinancialModel.compute_cannibalization_decay_factors(
                params.financial.project_life_years,
                alpha=params.cannibalization_alpha,
                annual_growth_rate=params.cannibalization_annual_growth_rate,
            )

        for yr in range(1, params.financial.project_life_years + 1):
            soh = soh_history[yr - 1]

            # Revenue degrades with remaining capacity. When per-year revenue
            # multipliers are provided (Monte Carlo AR(1)), apply the year's own
            # shock instead of a single persistent scalar.
            if arb_mult_by_year is not None and (yr - 1) < len(arb_mult_by_year):
                yr_arb = baseline_arbitrage * arb_mult_by_year[yr - 1] * soh
            else:
                yr_arb = arb_rev * soh
            # S3/B3: apply cannibalization decay (multiplicative on arbitrage only)
            if cannibalization_factors is not None:
                yr_arb *= cannibalization_factors[yr - 1]
            if fcas_mult_by_year is not None and (yr - 1) < len(fcas_mult_by_year):
                yr_fcas = baseline_fcas * fcas_mult_by_year[yr - 1] * soh
            else:
                yr_fcas = fcas_rev * soh
            yr_cap = cap_rev  # capacity payments don't degrade
            total_rev = yr_arb + yr_fcas + yr_cap

            # Opex
            expected_cycles = (
                annual_cycles_history[yr - 1]
                if (yr - 1) < len(annual_cycles_history)
                else (sum(annual_cycles_history) / len(annual_cycles_history) if annual_cycles_history else 365.0)
            )
            throughput_mwh = expected_cycles * params.battery.capacity_mwh * soh

            if params.cost_structure_overrides is not None:
                # Use CostStructureEngine for component-level opex calculation
                connection_type = (
                    params.cost_structure_overrides.connection_type
                    if params.cost_structure_overrides.connection_type is not None
                    else ConnectionType.TRANSMISSION
                )
                yr_cost_breakdown = CostStructureEngine.calculate_annual_costs(
                    battery=params.battery,
                    region=params.region,
                    annual_throughput_mwh=throughput_mwh,
                    connection_type=connection_type,
                    overrides=params.cost_structure_overrides,
                )
                total_opex = yr_cost_breakdown.total_annual_cost
                # Store year-1 breakdown as representative for the scenario
                if yr == 1:
                    cost_breakdown = yr_cost_breakdown
            else:
                # Legacy simplified opex calculation (backward compatible)
                fixed_om = (
                    params.financial.fixed_om_per_mw_year * params.battery.power_mw
                    + params.financial.land_lease_per_year
                )
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
        # Debt is sized so that the MINIMUM DSCR over the tenor meets the target
        # (standard project-finance practice), then capped by max gearing —
        # the binding of the two constraints wins.
        tenor = min(params.financial.debt_tenor_years, params.financial.project_life_years)
        cfads_tenor = net_cfs[1:tenor+1] # Operating cash flows during tenor

        # Size annual debt service to the WORST (minimum) CFADS year so the
        # target DSCR is respected in every year, not just on average.
        min_cfads = min(cfads_tenor) if cfads_tenor else 0.0
        max_annual_debt_service = (
            max(0.0, min_cfads / params.financial.target_dscr)
            if params.financial.target_dscr > 0
            else 0.0
        )

        # Calculate Debt Capacity (PV of debt service at cost of debt)
        debt_capacity = npf.pv(params.financial.cost_of_debt, tenor, -max_annual_debt_service, 0) if max_annual_debt_service > 0 else 0.0
        # Cap debt at max gearing (80% of total capex) — take the tighter constraint.
        debt_capacity = min(debt_capacity, total_capex * 0.8)
        
        # Re-calculate actual debt service based on finalized debt capacity
        equity_capex = total_capex - debt_capacity
        levered_cfs = [-equity_capex]

        if params.financial.debt_repayment_mode == "sculpting" and debt_capacity > 0:
            # S4/M3: Debt sculpting — size each year's debt service to maintain
            # DSCR = target_dscr, repaying principal proportionally to CFADS.
            outstanding = float(debt_capacity)
            rate = params.financial.cost_of_debt
            for idx, cfy in enumerate(cash_flow_years):
                yr = cfy.year
                if yr <= tenor and outstanding > 0:
                    cfads_t = max(cfy.net_cash_flow, 0.0)
                    ds = cfads_t / params.financial.target_dscr if params.financial.target_dscr > 0 else 0.0
                    interest = outstanding * rate
                    principal = max(ds - interest, 0.0)
                    principal = min(principal, outstanding)  # cannot over-repay
                    ds = interest + principal
                    outstanding -= principal
                else:
                    ds = 0.0
                lcf = cfy.net_cash_flow - ds
                cfy.debt_service = ds
                cfy.levered_cash_flow = lcf
                levered_cfs.append(lcf)
        else:
            # Standard annuity (constant payment)
            actual_annual_debt_service = -npf.pmt(params.financial.cost_of_debt, tenor, debt_capacity) if debt_capacity > 0 else 0.0
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
            
        # Actual DSCR — report both the average and the minimum (the binding
        # metric lenders care about) over the debt tenor.
        dscr_values = [
            cfy.net_cash_flow / cfy.debt_service
            for cfy in cash_flow_years
            if cfy.year <= tenor and cfy.debt_service > 0
        ]
        metrics.dscr_avg = float(sum(dscr_values) / len(dscr_values)) if dscr_values else 0.0
        metrics.min_dscr = float(min(dscr_values)) if dscr_values else 0.0

        # S4/M4: LLCR = PV(CFADS over loan life) / debt outstanding
        if debt_capacity > 0 and cfads_tenor:
            pv_cfads = float(npf.npv(params.financial.cost_of_debt, [0.0] + cfads_tenor))
            metrics.llcr = pv_cfads / debt_capacity
        else:
            metrics.llcr = None

        return ScenarioResult(
            scenario_name=scenario.name,
            metrics=metrics,
            cash_flows=cash_flow_years,
            cost_breakdown=cost_breakdown,
        )

    # Fixed default seed keeps Monte Carlo runs reproducible/auditable unless
    # the caller explicitly overrides it via MonteCarloConfig.seed.
    DEFAULT_MC_SEED = 42

    @staticmethod
    def run_monte_carlo(
        params: InvestmentParams,
        baseline_arbitrage: float,
        baseline_fcas: float,
        annual_cycles_history: List[float],
        dod_severity_history: Optional[List[float]] = None,
    ) -> MonteCarloResult:
        """Monte Carlo simulation of NPV/IRR distributions.

        Methodology (science-backed):
        - Reproducible: seeded RNG (fixed default) so results are auditable.
        - Log-normal revenue/capex/degradation multipliers instead of
          normal + max(0, .) truncation, which removed the point-mass at the
          clamp and the upward mean bias. Multipliers are parameterised with
          mu = -sigma^2/2 so the mean stays at 1.0 (unbiased) while retaining
          the natural right-skew of electricity-price outcomes.
        - Arbitrage and FCAS shocks are partially correlated (configurable),
          not perfectly correlated.
        - Year-to-year revenue shocks follow an AR(1) process, avoiding the
          "single permanent shock scales every year" assumption.
        """
        npvs: List[float] = []
        irrs: List[float] = []

        mc = params.monte_carlo
        seed = mc.seed if mc.seed is not None else FinancialModel.DEFAULT_MC_SEED
        rng = np.random.default_rng(seed)

        n_years = params.financial.project_life_years
        rho = float(np.clip(mc.revenue_autocorrelation, 0.0, 0.999))
        corr = float(np.clip(mc.arb_fcas_correlation, 0.0, 1.0))
        sigma = max(0.0, mc.market_volatility)

        def _lognormal_mult(sig: float, z: float) -> float:
            # exp(mu + sig*z) with mu = -sig^2/2 keeps E[mult] == 1.0.
            return float(np.exp(-0.5 * sig * sig + sig * z))

        def _ar1_path() -> np.ndarray:
            # Stationary AR(1) standardized shocks: z_0 ~ N(0,1),
            # z_t = rho*z_{t-1} + sqrt(1-rho^2)*eps_t. Unit variance preserved.
            z = np.empty(n_years)
            z[0] = rng.standard_normal()
            scale = np.sqrt(max(0.0, 1.0 - rho * rho))
            for t in range(1, n_years):
                z[t] = rho * z[t - 1] + scale * rng.standard_normal()
            return z

        for _ in range(mc.iterations):
            # One-time / persistent asset multipliers (single draw per run).
            capex_mult = _lognormal_mult(mc.capex_volatility, rng.standard_normal())
            deg_mult = _lognormal_mult(mc.degradation_volatility, rng.standard_normal())

            # Correlated year-by-year revenue shocks.
            z_arb = _ar1_path()
            z_indep = _ar1_path()
            z_fcas = corr * z_arb + np.sqrt(max(0.0, 1.0 - corr * corr)) * z_indep

            arb_mults = [_lognormal_mult(sigma, z_arb[t]) for t in range(n_years)]
            fcas_mults = [_lognormal_mult(sigma, z_fcas[t]) for t in range(n_years)]

            scenario = ScenarioConfig(
                name="MC",
                capex_multiplier=capex_mult,
                degradation_multiplier=deg_mult,
                arbitrage_multipliers_by_year=arb_mults,
                fcas_multipliers_by_year=fcas_mults,
            )

            res = FinancialModel.run_scenario(
                params, scenario, baseline_arbitrage, baseline_fcas, annual_cycles_history,
                dod_severity_history,
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
            seed=seed,
            iterations=mc.iterations,
        )
