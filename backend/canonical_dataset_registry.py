from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetFamilySpec:
    family: str
    observation_kind: str
    default_unit: str | None = None
    scope_type: str = "region"
    supports_counterpart: bool = False


DATASET_FAMILY_REGISTRY = {
    "load_forecast": DatasetFamilySpec("load_forecast", "forecast", "MW", "region", True),
    "load_actual": DatasetFamilySpec("load_actual", "actual", "MW", "region", True),
    "wind_forecast": DatasetFamilySpec("wind_forecast", "forecast", "MW", "region", True),
    "wind_actual": DatasetFamilySpec("wind_actual", "actual", "MW", "region", True),
    "solar_forecast": DatasetFamilySpec("solar_forecast", "forecast", "MW", "region", True),
    "solar_actual": DatasetFamilySpec("solar_actual", "actual", "MW", "region", True),
    "rooftop_pv": DatasetFamilySpec("rooftop_pv", "actual", "MW", "region", False),
    "outage": DatasetFamilySpec("outage", "event", None, "region", False),
    "unit_availability": DatasetFamilySpec("unit_availability", "state", "MW", "region", False),
    "interconnector_flow": DatasetFamilySpec("interconnector_flow", "actual", "MW", "interconnector", False),
    "reserve_requirement": DatasetFamilySpec("reserve_requirement", "state", "MW", "region", False),
    "reserve_shortfall": DatasetFamilySpec("reserve_shortfall", "event", "MW", "region", False),
    "weather": DatasetFamilySpec("weather", "actual", None, "region", False),
    "constraint": DatasetFamilySpec("constraint", "state", None, "region", False),
    "settlement": DatasetFamilySpec("settlement", "settlement", "AUD", "region", False),
}


def get_dataset_family_spec(family: str) -> DatasetFamilySpec:
    try:
        return DATASET_FAMILY_REGISTRY[family]
    except KeyError as exc:
        raise KeyError(f"Unknown dataset family: {family}") from exc
