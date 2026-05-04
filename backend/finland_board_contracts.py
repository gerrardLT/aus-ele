from __future__ import annotations

from copy import deepcopy


FINLAND_BOARD_FIELDS = {
    "timestamp_local": {
        "field_key": "timestamp_local",
        "label": "Timestamp (local)",
        "source_type": "fingrid",
        "granularity": "15m",
        "unit": None,
    },
    "market_date": {
        "field_key": "market_date",
        "label": "Market date",
        "source_type": "derived",
        "granularity": "1d",
        "unit": None,
    },
    "fcr_n_capacity_price": {
        "field_key": "fcr_n_capacity_price",
        "label": "FCR-N capacity price",
        "source_type": "fingrid",
        "granularity": "1h",
        "unit": "EUR/MW",
    },
    "fcr_d_up_capacity_price": {
        "field_key": "fcr_d_up_capacity_price",
        "label": "FCR-D up capacity price",
        "source_type": "fingrid",
        "granularity": "1h",
        "unit": "EUR/MW",
    },
    "fcr_d_down_capacity_price": {
        "field_key": "fcr_d_down_capacity_price",
        "label": "FCR-D down capacity price",
        "source_type": "fingrid",
        "granularity": "1h",
        "unit": "EUR/MW",
    },
    "fcr_n_activation_price": {
        "field_key": "fcr_n_activation_price",
        "label": "FCR-N activation price",
        "source_type": "fingrid",
        "granularity": "15m",
        "unit": "EUR/MWh",
    },
    "fcr_d_up_activation_price": {
        "field_key": "fcr_d_up_activation_price",
        "label": "FCR-D up activation price",
        "source_type": "fingrid",
        "granularity": "15m",
        "unit": "EUR/MWh",
    },
    "fcr_d_down_activation_price": {
        "field_key": "fcr_d_down_activation_price",
        "label": "FCR-D down activation price",
        "source_type": "fingrid",
        "granularity": "15m",
        "unit": "EUR/MWh",
    },
    "daily_capacity_revenue": {
        "field_key": "daily_capacity_revenue",
        "label": "Daily capacity revenue",
        "source_type": "derived",
        "granularity": "1d",
        "unit": "EUR",
    },
    "daily_activation_revenue": {
        "field_key": "daily_activation_revenue",
        "label": "Daily activation revenue",
        "source_type": "derived",
        "granularity": "1d",
        "unit": "EUR",
    },
    "capacity_hours": {
        "field_key": "capacity_hours",
        "label": "Capacity hours",
        "source_type": "derived",
        "granularity": "1d",
        "unit": "h",
    },
    "activation_intervals": {
        "field_key": "activation_intervals",
        "label": "Activation intervals",
        "source_type": "derived",
        "granularity": "1d",
        "unit": "count",
    },
    "day_ahead_spot_price": {
        "field_key": "day_ahead_spot_price",
        "label": "Day-ahead spot price",
        "source_type": "external_join",
        "granularity": "1h",
        "unit": "EUR/MWh",
    },
}


FINLAND_BOARD_VIEWS = {
    "capacity_hourly": {
        "view_key": "capacity_hourly",
        "label": "Hourly capacity board",
        "granularity": "1h",
        "columns": [
            "timestamp_local",
            "fcr_n_capacity_price",
            "fcr_d_up_capacity_price",
            "fcr_d_down_capacity_price",
            "day_ahead_spot_price",
        ],
    },
    "activation_15m": {
        "view_key": "activation_15m",
        "label": "15-minute activation board",
        "granularity": "15m",
        "columns": [
            "timestamp_local",
            "fcr_n_activation_price",
            "fcr_d_up_activation_price",
            "fcr_d_down_activation_price",
        ],
    },
    "daily_capacity": {
        "view_key": "daily_capacity",
        "label": "Daily capacity summary",
        "granularity": "1d",
        "columns": [
            "market_date",
            "daily_capacity_revenue",
            "capacity_hours",
        ],
    },
    "daily_activation": {
        "view_key": "daily_activation",
        "label": "Daily activation summary",
        "granularity": "1d",
        "columns": [
            "market_date",
            "daily_activation_revenue",
            "activation_intervals",
        ],
    },
    "summary": {
        "view_key": "summary",
        "label": "Board summary",
        "granularity": "mixed",
        "columns": [
            "daily_capacity_revenue",
            "daily_activation_revenue",
            "day_ahead_spot_price",
        ],
    },
    "dictionary": {
        "view_key": "dictionary",
        "label": "Field dictionary",
        "granularity": "contract",
        "columns": list(FINLAND_BOARD_FIELDS.keys()),
    },
}


def get_finland_board_field(field_key: str) -> dict:
    try:
        return deepcopy(FINLAND_BOARD_FIELDS[field_key])
    except KeyError as exc:
        raise KeyError(field_key) from exc


def get_finland_board_view(view_key: str) -> dict:
    try:
        return deepcopy(FINLAND_BOARD_VIEWS[view_key])
    except KeyError as exc:
        raise KeyError(view_key) from exc
