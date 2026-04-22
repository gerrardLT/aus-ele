from typing import List, Dict
import pulp
from models.financial_params import BatterySpecs

class DispatchOptimizer:
    @staticmethod
    def run_hindsight_optimization(
        interval_data: List[Dict],
        specs: BatterySpecs
    ) -> List[Dict]:
        """
        Runs a Mixed Integer Linear Program (MILP) to find the absolute maximum
        arbitrage revenue possible with perfect foresight.
        """
        if not interval_data:
            return []

        # Create the LP problem
        prob = pulp.LpProblem("BESS_Arbitrage", pulp.LpMaximize)

        n_intervals = len(interval_data)
        max_power = specs.power_mw
        max_energy = specs.capacity_mwh
        rte = specs.round_trip_efficiency
        interval_hours = 5 / 60

        # Decision Variables
        charge = [pulp.LpVariable(f"charge_{i}", lowBound=0, upBound=max_power) for i in range(n_intervals)]
        discharge = [pulp.LpVariable(f"discharge_{i}", lowBound=0, upBound=max_power) for i in range(n_intervals)]
        soc = [pulp.LpVariable(f"soc_{i}", lowBound=0, upBound=max_energy) for i in range(n_intervals)]
        
        # Mutually exclusive charge/discharge using binary variables
        is_charging = [pulp.LpVariable(f"is_charging_{i}", cat=pulp.LpBinary) for i in range(n_intervals)]

        # Objective Function
        revenue = []
        for i in range(n_intervals):
            price = interval_data[i].get("energy_price", 0.0)
            revenue.append((discharge[i] - charge[i]) * interval_hours * price)
            
            # Constraints
            prob += charge[i] <= max_power * is_charging[i]
            prob += discharge[i] <= max_power * (1 - is_charging[i])
            
            # SoC balance
            if i == 0:
                prob += soc[i] == (max_energy * 0.5) + (charge[i] * interval_hours * rte) - (discharge[i] * interval_hours)
            else:
                prob += soc[i] == soc[i-1] + (charge[i] * interval_hours * rte) - (discharge[i] * interval_hours)

        # Terminal constraint (return to 50% SoC at the end)
        prob += soc[-1] >= max_energy * 0.5

        prob += pulp.lpSum(revenue)
        
        # Solve
        # In a real environment, you'd want to configure the solver paths, time limits, etc.
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=60)
        prob.solve(solver)

        # Extract results
        results = []
        for i in range(n_intervals):
            c_val = pulp.value(charge[i]) or 0.0
            d_val = pulp.value(discharge[i]) or 0.0
            row = interval_data[i].copy()
            row["optimized_arbitrage_mw"] = d_val - c_val
            row["optimized_soc_mwh"] = pulp.value(soc[i]) or 0.0
            results.append(row)
            
        return results

    @staticmethod
    def run_rolling_forecast(
        interval_data: List[Dict],
        specs: BatterySpecs
    ) -> List[Dict]:
        """
        Placeholder for rolling forecast simulation.
        Would use a sliding window LP with historical forecast data.
        """
        # For now, just return hindsight as fallback or raise NotImplementedError
        return DispatchOptimizer.run_hindsight_optimization(interval_data, specs)
