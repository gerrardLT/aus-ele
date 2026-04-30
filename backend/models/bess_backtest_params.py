from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class BessBacktestParams(BaseModel):
    market: str
    region: str
    year: int

    power_mw: float = Field(gt=0)
    energy_mwh: Optional[float] = Field(default=None, gt=0)
    duration_hours: Optional[float] = Field(default=None, gt=0)

    min_soc_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_soc_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    initial_soc_pct: float = Field(default=50.0, ge=0.0, le=100.0)

    round_trip_efficiency: float = Field(default=0.87, gt=0.0, le=1.0)

    network_fee_per_mwh: float = Field(default=0.0, ge=0.0)
    degradation_cost_per_mwh: float = Field(default=0.0, ge=0.0)
    variable_om_per_mwh: float = Field(default=0.0, ge=0.0)

    availability_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    max_cycles_per_day: float = Field(default=1.0, ge=0.0)

    @model_validator(mode="after")
    def normalize_energy_duration_contract(self):
        if self.energy_mwh is None and self.duration_hours is None:
            raise ValueError("energy_mwh or duration_hours must be provided")

        if self.energy_mwh is None:
            self.energy_mwh = self.power_mw * self.duration_hours
        elif self.duration_hours is None:
            self.duration_hours = self.energy_mwh / self.power_mw
        else:
            expected_energy = self.power_mw * self.duration_hours
            if abs(expected_energy - self.energy_mwh) > 1e-6:
                raise ValueError("energy_mwh must equal power_mw * duration_hours")

        if self.min_soc_pct > self.max_soc_pct:
            raise ValueError("min_soc_pct must be less than or equal to max_soc_pct")
        if not (self.min_soc_pct <= self.initial_soc_pct <= self.max_soc_pct):
            raise ValueError("initial_soc_pct must be within min_soc_pct and max_soc_pct")

        return self

    @property
    def initial_soc_mwh(self) -> float:
        return self.energy_mwh * (self.initial_soc_pct / 100.0)

    def to_storage_config(self) -> dict:
        return {
            "duration_hours": self.duration_hours,
            "power_mw": self.power_mw,
            "capacity_mwh": self.energy_mwh,
        }

    @classmethod
    def from_investment_params(cls, params, year: Optional[int] = None) -> "BessBacktestParams":
        selected_year = year if year is not None else params.backtest_years[0]
        market = "WEM" if params.region == "WEM" else "NEM"
        return cls(
            market=market,
            region=params.region,
            year=selected_year,
            power_mw=params.battery.power_mw,
            energy_mwh=params.battery.capacity_mwh,
            duration_hours=params.battery.duration_hours,
            round_trip_efficiency=params.battery.round_trip_efficiency,
            variable_om_per_mwh=params.financial.variable_om_per_mwh,
        )
