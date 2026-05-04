from __future__ import annotations

from typing import Optional

from pydantic import Field

from models.bess_backtest_params import BessBacktestParams


class P3BessDecisionParams(BessBacktestParams):
    forecast_horizon: str = Field(default="24h", pattern="^(24h|7d|30d)$")
    as_of: Optional[str] = None
    reserve_soc_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    risk_mode: str = Field(default="balanced", pattern="^(conservative|balanced|aggressive)$")
