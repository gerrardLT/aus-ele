from typing import Dict, List, Tuple
from models.financial_params import BatterySpecs

class BatteryModel:
    def __init__(self, specs: BatterySpecs):
        self.specs = specs
        
    def calculate_degradation(self, annual_cycles: float, year: int) -> float:
        """
        Calculate State of Health (SoH) reduction for a given year using a non-linear dual-factor model.
        Instead of a simple linear scaling, it applies an empirical DoD (Depth of Discharge) non-linear factor
        to simulate Rainflow cycle impact.
        Returns the degradation factor for the year.
        """
        calendar_deg = self.specs.calendar_degradation_rate
        # Non-linear cycle degradation simulating DoD severity (e.g. cycle ^ 1.2)
        # Using annual_cycles / 365 as an proxy for average daily DoD equivalents
        avg_daily_dod = min(1.0, annual_cycles / 365.0) if annual_cycles > 0 else 0
        
        # Empirical degradation: Base * Cycles * (Avg DoD)^(non_linear_factor - 1)
        # So deep cycles degrade more than shallow cycles.
        dod_multiplier = avg_daily_dod ** max(0.0, (self.specs.dod_non_linear_factor - 1.0)) if avg_daily_dod > 0 else 0
        
        cycle_deg = annual_cycles * self.specs.base_cycle_degradation_rate * (1 + dod_multiplier)
        return calendar_deg + cycle_deg
        
    def get_marginal_cost_of_degradation(self, capex_per_kwh: float) -> float:
        """
        Calculates the marginal cost of degradation ($/MWh) for the optimizer.
        If Spread < Marginal Cost, the battery should not dispatch.
        """
        # A full 100% cycle degrades by base_cycle_degradation_rate * (1 + 1^(1.2-1)) = ~ 2 * base rate
        # Cost = Replacement Capex * degradation per cycle
        capex_per_mwh = capex_per_kwh * 1000
        deg_per_cycle = self.specs.base_cycle_degradation_rate * 2.0 # simplified max DoD proxy
        return capex_per_mwh * deg_per_cycle
        
    def simulate_lifetime(self, annual_cycles_history: List[float], project_life_years: int) -> Tuple[List[float], List[float]]:
        """
        Simulate the battery State of Health (SoH) over its project life.
        Handles augmentation when SoH drops below the threshold.
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
                
            deg_factor = self.calculate_degradation(cycles, year)
            current_soh -= deg_factor
            
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
