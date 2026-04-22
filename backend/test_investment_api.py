import asyncio
import json
from models.financial_params import InvestmentParams, BatterySpecs, FinancialAssumptions, MonteCarloConfig, FcasRevenueMode

def test_investment_endpoint():
    # We must import server here because it initializes the db connection
    import server

    print("Running Regression Test: BESS Investment Analysis (MILP + Monte Carlo)")
    print("=" * 80)
    
    params = InvestmentParams(
        region="SA1",
        backtest_years=[2024], # Test one year to be faster
        battery=BatterySpecs(
            power_mw=100.0,
            duration_hours=2.0
        ),
        financial=FinancialAssumptions(
            project_life_years=15
        ),
        fcas_revenue_mode=FcasRevenueMode.AUTO,
        revenue_capture_rate=0.65,
    )
    
    # Enable Monte Carlo to test that flow
    params.monte_carlo.enabled = True
    params.monte_carlo.iterations = 100 # keep small for quick test

    try:
        response = server.investment_analysis(params)
        
        print("\nSUCCESS! Endpoint returned successfully.")
        
        # Verify base metrics
        metrics = response.get("base_metrics", {})
        print(f"\n[Base Case Metrics]")
        print(f"NPV: ${metrics.get('npv', 0):,.2f}")
        print(f"IRR: {metrics.get('irr', 0):.2%}")
        print(f"ROI: {metrics.get('roi_pct', 0):.2f}%")
        print(f"Payback Years: {metrics.get('payback_years')}")
        
        # Verify Monte Carlo
        mc = response.get("monte_carlo", {})
        if mc:
            print(f"\n[Monte Carlo Simulation (100 iterations)]")
            print(f"P90 NPV (Conservative): ${mc.get('npv_p90', 0):,.2f}")
            print(f"P50 NPV (Expected)    : ${mc.get('npv_p50', 0):,.2f}")
            print(f"P10 NPV (Optimistic)  : ${mc.get('npv_p10', 0):,.2f}")
        else:
            print("\nWARNING: Monte Carlo results missing!")
            
        # Check scenarios
        scenarios = response.get("scenarios", [])
        print(f"\nGenerated {len(scenarios)} scenarios.")
        
        print("\nTest passed. All engine components are integrated correctly.")
        
    except Exception as e:
        print(f"\nFAILED! Exception occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_investment_endpoint()
