from typing import Dict, List, Tuple
from models.financial_params import BatterySpecs

class BatteryModel:
    def __init__(self, specs: BatterySpecs):
        self.specs = specs
        
    def calculate_degradation(self, annual_cycles: float, year: int, dod_severity: float = 1.0) -> float:
        """
        Calculate State of Health (SoH) reduction for a given year using a dual-factor model.

        Cycle degradation is driven by *equivalent full cycles* (already DoD-weighted by
        the rainflow decomposition of the SoC timeline) scaled by a ``dod_severity``
        multiplier. ``dod_severity`` is the Wohler-weighted severity from
        ``rainflow.dod_severity_from_soc`` and equals 1.0 for full-depth cycles, <1.0
        for predominantly shallow cycling. This replaces the previous
        ``annual_cycles / 365`` average-DoD proxy (which conflated cycle *frequency*
        with *depth*) and the hardcoded 2x cycle-degradation factor.

        Returns the degradation factor for the year.
        """
        calendar_deg = self.specs.calendar_degradation_rate
        severity = max(0.0, dod_severity)
        cycle_deg = annual_cycles * self.specs.base_cycle_degradation_rate * severity
        return calendar_deg + cycle_deg
        
    def get_marginal_cost_of_degradation(self, capex_per_kwh: float, dod_severity: float = 1.0) -> float:
        """
        Calculates the marginal cost of degradation ($/MWh) for the optimizer.
        If Spread < Marginal Cost, the battery should not dispatch.

        Cost = Replacement Capex present-value x capacity lost per equivalent full cycle.
        ``dod_severity`` (default 1.0 for a full-depth cycle) scales the per-cycle
        capacity loss so the marginal cost stays consistent with the degradation model
        used in the dispatch decision. The previous hardcoded 2x factor is removed.
        """
        capex_per_mwh = capex_per_kwh * 1000
        deg_per_cycle = self.specs.base_cycle_degradation_rate * max(0.0, dod_severity)
        return capex_per_mwh * deg_per_cycle
        
    def simulate_lifetime(
        self,
        annual_cycles_history: List[float],
        project_life_years: int,
        dod_severity_history: List[float] = None,
    ) -> Tuple[List[float], List[float]]:
        """
        Simulate the battery State of Health (SoH) over its project life.

        SoH is accumulated *multiplicatively* (current_soh *= (1 - deg_factor)) rather
        than by linear subtraction, so annual losses compound on the remaining
        capacity as they do physically. A knee-point acceleration is applied once SoH
        drops below ``knee_point_soh`` to capture the well-documented end-of-life
        degradation acceleration. Augmentation restores capacity to 100% when SoH
        falls to the augmentation threshold.

        Args:
            annual_cycles_history: Equivalent full cycles per year (from the backtest).
            project_life_years: Number of years to simulate.
            dod_severity_history: Optional per-year DoD-severity multipliers derived
                from the SoC timeline via rainflow. Defaults to 1.0 (full-depth) when
                absent, preserving backward compatibility.

        Returns:
            - List of SoH at the end of each year (e.g., [0.98, 0.95, ...])
            - List of Augmentation Capex percentages required each year
        """
        soh_history = []
        augmentation_schedule = []
        
        current_soh = 1.0
        
        for year in range(1, project_life_years + 1):
            # Use historical cycles if available, else average of history, else assume 365 cycles
            if year - 1 < len(annual_cycles_history):
                cycles = annual_cycles_history[year - 1]
            elif len(annual_cycles_history) > 0:
                cycles = sum(annual_cycles_history) / len(annual_cycles_history)
            else:
                cycles = 365.0

            # DoD-severity for the year (1.0 = full-depth cycles when not supplied).
            if dod_severity_history and year - 1 < len(dod_severity_history):
                dod_severity = dod_severity_history[year - 1]
            elif dod_severity_history:
                dod_severity = sum(dod_severity_history) / len(dod_severity_history)
            else:
                dod_severity = 1.0

            deg_factor = self.calculate_degradation(cycles, year, dod_severity)

            # End-of-life knee: accelerate degradation once SoH is below the knee point.
            if current_soh < self.specs.knee_point_soh:
                deg_factor *= self.specs.knee_acceleration_factor

            # Multiplicative (compounding) SoH loss on remaining capacity.
            current_soh *= (1.0 - deg_factor)
            if current_soh < 0.0:
                current_soh = 0.0
            
            aug_capex_pct = 0.0
            if current_soh <= self.specs.augmentation_threshold_soc:
                # Augment back to 100% capacity
                # Cost is proportional to the capacity replaced
                capacity_to_replace = 1.0 - current_soh
                aug_capex_pct = capacity_to_replace
                current_soh = 1.0
                
            soh_history.append(current_soh)
            augmentation_schedule.append(aug_capex_pct)
            
        return soh_history, augmentation_schedule

    def get_efficiency_for_soc(self, soc: float) -> float:
        """
        Advanced model: RTE can vary based on State of Charge.
        For now, returns the constant RTE, but provides the hook for SoC-dependent curves.
        """
        return self.specs.round_trip_efficiency
