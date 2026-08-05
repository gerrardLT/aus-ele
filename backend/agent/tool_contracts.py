"""Canonical output-field contracts for agent tools (P1: kill field drift).

The agent system repeatedly suffered "field drift" bugs: a producer tool returns
a dict under one key while a consumer (synthesizer / another tool) reads a
different key via ``data.get("...")`` — silently producing empty results
(e.g. reading ``candidates`` when the producer returns ``items``).

This module is the single source of truth for the output field names of the
drift-prone tools. **Producers and consumers must reference these constants
instead of raw string literals.** A rename then becomes a one-line edit that
keeps both sides in sync, and a typo fails loudly (NameError/AttributeError at
import/use) instead of a silent ``.get()`` miss.

Scope: this targets the hot-spot tools that actually drifted. It is a
deliberately lightweight contract layer rather than full Pydantic schemas for
all 31 tools (which would be a large, risky refactor).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# market_screening / regional_ranking
# ---------------------------------------------------------------------------
# build_market_screening_payload() returns {"items": [...], "summary": {...}}.
# Each item carries label / market / region_or_zone / overall_score.
SCREENING_ITEMS_KEY = "items"
SCREENING_MARKET_KEY = "market"
SCREENING_REGION_KEY = "region_or_zone"
SCREENING_LABEL_KEY = "label"
SCREENING_SCORE_KEY = "overall_score"

# ---------------------------------------------------------------------------
# investment_analysis
# ---------------------------------------------------------------------------
# _exec_investment_analysis() returns {"results": {...}} with financial metrics.
INVEST_RESULTS_KEY = "results"
INVEST_NPV_KEY = "npv_aud"
INVEST_IRR_KEY = "irr_pct"
INVEST_PAYBACK_KEY = "payback_years"
INVEST_ROI_KEY = "roi_pct"

# ---------------------------------------------------------------------------
# regional_ranking (agent tool output)
# ---------------------------------------------------------------------------
REGIONAL_RANKING_KEY = "ranking"
REGIONAL_TOTAL_KEY = "total_candidates"
