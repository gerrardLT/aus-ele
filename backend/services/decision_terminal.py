"""Decision Terminal — U3: 投资决策规则引擎.

Pure-Python rules engine that synthesizes a GO / NO_GO / WAIT recommendation
from the investment analysis metrics. No LLM required.
"""

from __future__ import annotations

from typing import Optional


# Default IRR hurdle rate (weighted average cost of capital proxy)
DEFAULT_IRR_HURDLE = 0.08


def build_decision_terminal(
    *,
    npv: float,
    irr: Optional[float],
    payback_years: Optional[float],
    min_dscr: float,
    llcr: Optional[float],
    total_capex: float,
    power_mw: float,
    project_life_years: int,
    debt_tenor_years: int,
    irr_hurdle: float = DEFAULT_IRR_HURDLE,
    apply_cannibalization: bool = False,
    cannibalization_annual_growth_rate: float = 0.10,
    backtest_years_count: int = 2,
) -> dict:
    """Compute the decision terminal payload.

    Returns a dict suitable for embedding in the investment analysis response.
    """
    # --- Derived metrics ---
    npv_per_mw = npv / power_mw if power_mw > 0 else 0.0
    irr_val = irr if irr is not None else 0.0
    irr_margin = irr_val - irr_hurdle
    payback_val = payback_years if payback_years is not None else project_life_years + 1

    # --- Data completeness heuristic ---
    # More backtest years → higher confidence
    data_completeness = min(1.0, backtest_years_count / 3.0)
    if irr is None:
        data_completeness *= 0.7

    # --- Cannibalization exposure ---
    if not apply_cannibalization:
        cannibalization_exposure = "not_assessed"
    elif cannibalization_annual_growth_rate >= 0.15:
        cannibalization_exposure = "high"
    elif cannibalization_annual_growth_rate >= 0.08:
        cannibalization_exposure = "medium"
    else:
        cannibalization_exposure = "low"

    # --- Key risks ---
    key_risks: list[dict] = []
    if irr_margin < 0.02:
        key_risks.append({
            "type": "irr_thin_margin",
            "severity": "high" if irr_margin < 0 else "medium",
            "description": f"IRR margin over hurdle is only {irr_margin*100:.1f}pp",
        })
    if payback_val > debt_tenor_years:
        key_risks.append({
            "type": "payback_exceeds_tenor",
            "severity": "high",
            "description": f"Payback ({payback_val:.1f}y) exceeds debt tenor ({debt_tenor_years}y)",
        })
    if min_dscr < 1.1 and min_dscr > 0:
        key_risks.append({
            "type": "dscr_tight",
            "severity": "medium",
            "description": f"Min DSCR ({min_dscr:.2f}) is close to 1.0",
        })
    if cannibalization_exposure == "high":
        key_risks.append({
            "type": "cannibalization_high",
            "severity": "medium",
            "description": "High market capacity growth erodes long-term revenue",
        })
    if llcr is not None and llcr < 1.2:
        key_risks.append({
            "type": "llcr_low",
            "severity": "medium",
            "description": f"LLCR ({llcr:.2f}) below 1.2 lender comfort zone",
        })

    # --- Recommendation logic ---
    if npv < 0 or irr_val < irr_hurdle * 0.8:
        recommendation = "NO_GO"
        confidence = min(0.9, 0.6 + abs(irr_margin) * 2)
    elif (
        npv > 0
        and irr_val >= irr_hurdle
        and payback_val <= debt_tenor_years
        and (min_dscr >= 1.0 or min_dscr == 0)
        and cannibalization_exposure not in ("high",)
        and data_completeness >= 0.7
    ):
        recommendation = "GO"
        confidence = min(0.95, 0.6 + irr_margin * 2 + (0.1 if llcr and llcr >= 1.3 else 0))
    else:
        recommendation = "WAIT"
        confidence = 0.5 + data_completeness * 0.2

    return {
        "recommendation": recommendation,
        "confidence": round(confidence, 3),
        "key_risks": key_risks,
        "npv_per_mw": round(npv_per_mw, 0),
        "irr_vs_hurdle": {
            "irr": round(irr_val, 4),
            "hurdle": irr_hurdle,
            "margin": round(irr_margin, 4),
        },
        "payback_vs_tenor": {
            "payback": round(payback_val, 2),
            "tenor": debt_tenor_years,
        },
        "cannibalization_exposure": cannibalization_exposure,
        "data_completeness": round(data_completeness, 2),
    }
