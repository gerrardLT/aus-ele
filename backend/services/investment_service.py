"""Investment analysis service layer (S5/A1).

Thin delegation layer that establishes the service boundary for investment
analysis logic. Currently delegates to server.py implementations; functions
will be progressively inlined here as server.py is slimmed.

This allows investment_routes.py to depend on the service layer rather than
directly on the monolithic server module.
"""

from __future__ import annotations

from typing import Optional

from models.financial_params import InvestmentParams


def build_backtest_summary(params: InvestmentParams, data_version: str) -> dict:
    """Build standardized BESS backtest summary across backtest years."""
    import server as _server
    return _server._build_backtest_summary(params, data_version)


def derive_arbitrage_baseline(params: InvestmentParams, backtest_summary: dict) -> tuple[float, str]:
    """Derive annual arbitrage revenue baseline from backtest results."""
    import server as _server
    return _server._derive_arbitrage_baseline(params, backtest_summary)


def get_fcas_baseline(params: InvestmentParams, data_version: str) -> tuple[float, str]:
    """Derive annual FCAS revenue baseline (historical or manual)."""
    import server as _server
    return _server._get_fcas_baseline(params, data_version)


def build_investment_p3_decision(params: InvestmentParams) -> Optional[dict]:
    """Build the P3 investment decision layer."""
    import server as _server
    return _server._build_investment_p3_decision(params)


def build_investment_response(**kwargs) -> dict:
    """Assemble the full investment analysis response payload."""
    import server as _server
    return _server._build_investment_response(**kwargs)


def build_decision_adjusted_scenarios(
    params: InvestmentParams,
    annual_cycles_history: list,
    baseline_arbitrage: float,
    baseline_fcas: float,
    p3_decision: Optional[dict],
    dod_severity_history: Optional[list] = None,
) -> list:
    """Build decision-adjusted scenario results."""
    import server as _server
    return _server._build_decision_adjusted_scenarios(
        params, annual_cycles_history, baseline_arbitrage,
        baseline_fcas, p3_decision, dod_severity_history,
    )


def build_decision_adjusted_monte_carlo(
    params: InvestmentParams,
    annual_cycles_history: list,
    baseline_arbitrage: float,
    baseline_fcas: float,
    p3_decision: Optional[dict],
    dod_severity_history: Optional[list] = None,
):
    """Build decision-adjusted Monte Carlo results."""
    import server as _server
    return _server._build_decision_adjusted_monte_carlo(
        params, annual_cycles_history, baseline_arbitrage,
        baseline_fcas, p3_decision, dod_severity_history,
    )
