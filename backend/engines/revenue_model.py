from typing import Dict, List
import math

class RevenueModel:
    @staticmethod
    def calculate_cooptimized_revenue(
        interval_data: List[Dict],
        power_mw: float,
        capture_rate: float
    ) -> Dict:
        """
        Calculates stacked revenue considering capacity constraints.
        This is a heuristic co-optimization if MILP isn't fully co-optimizing FCAS.
        It assumes the battery dedicates capacity to the highest value service per interval.
        """
        total_arbitrage_rev = 0.0
        total_fcas_rev = 0.0
        
        for row in interval_data:
            # Expected keys: 'price', 'fcas_raise_reg', 'fcas_lower_reg', etc.
            # Convert prices from $/MWh to $/MW per interval (5 mins = 1/12 hour)
            interval_hours = 5 / 60
            
            energy_price = row.get("energy_price", 0.0)
            
            # Simple heuristic: compare energy arbitrage spread vs FCAS value
            # In a full co-optimized MILP, this is endogenous. Here we provide a fast approximation
            # for the "auto" FCAS mode.
            
            # Calculate max possible FCAS revenue for this interval
            # Sum of raise services (mutually exclusive with charging)
            raise_fcas_price = sum([
                row.get("fcas_raise_reg", 0.0),
                row.get("fcas_raise_6sec", 0.0),
                row.get("fcas_raise_60sec", 0.0),
                row.get("fcas_raise_5min", 0.0)
            ])
            
            # Sum of lower services (mutually exclusive with discharging)
            lower_fcas_price = sum([
                row.get("fcas_lower_reg", 0.0),
                row.get("fcas_lower_6sec", 0.0),
                row.get("fcas_lower_60sec", 0.0),
                row.get("fcas_lower_5min", 0.0)
            ])
            
            # Base revenue calculation
            interval_arb = row.get("optimized_arbitrage_mw", 0.0) * energy_price * interval_hours
            
            # Headroom calculation
            # If discharging, raise FCAS headroom is reduced
            # If charging, lower FCAS headroom is reduced
            current_mw = row.get("optimized_arbitrage_mw", 0.0)
            
            if current_mw > 0: # Discharging
                available_raise_mw = max(0.0, power_mw - current_mw)
                available_lower_mw = power_mw # Can fully provide lower (equivalent to charging)
            elif current_mw < 0: # Charging
                available_raise_mw = power_mw
                available_lower_mw = max(0.0, power_mw - abs(current_mw))
            else: # Idle
                available_raise_mw = power_mw
                available_lower_mw = power_mw
                
            interval_fcas = (available_raise_mw * raise_fcas_price * interval_hours) + \
                            (available_lower_mw * lower_fcas_price * interval_hours)
                            
            total_arbitrage_rev += interval_arb
            total_fcas_rev += interval_fcas
            
        # Apply capture rates to represent real-world execution risks
        return {
            "arbitrage_revenue": total_arbitrage_rev * capture_rate,
            "fcas_revenue": total_fcas_rev * capture_rate
        }
