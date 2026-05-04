from __future__ import annotations


FINLAND_BOARD_FIELDS = {
    "timestamp_helsinki": {
        "field_key": "timestamp_helsinki",
        "label": "Time (Europe/Helsinki)",
        "unit": None,
        "granularity": "display",
        "source_name": "Derived",
        "source_dataset_id": None,
        "source_type": "derived",
        "category": "time",
        "methodology_note": "Localized display timestamp assembled in the backend.",
    },
    "date": {
        "field_key": "date",
        "label": "Date",
        "unit": None,
        "granularity": "day",
        "source_name": "Derived",
        "source_dataset_id": None,
        "source_type": "derived",
        "category": "time",
        "methodology_note": "Daily bucket label assembled in the backend.",
    },
    "fcr_n_price_eur_mw": {
        "field_key": "fcr_n_price_eur_mw",
        "label": "FCR-N Capacity Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "317",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly FCR-N reserve-capacity clearing price.",
    },
    "fcr_d_up_price_eur_mw": {
        "field_key": "fcr_d_up_price_eur_mw",
        "label": "FCR-D Up Capacity Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "318",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly FCR-D up reserve-capacity clearing price.",
    },
    "fcr_d_down_price_eur_mw": {
        "field_key": "fcr_d_down_price_eur_mw",
        "label": "FCR-D Down Capacity Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "315",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly FCR-D down reserve-capacity clearing price.",
    },
    "afrr_cap_up_eur_mw": {
        "field_key": "afrr_cap_up_eur_mw",
        "label": "aFRR Capacity Up Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly aFRR capacity up clearing price.",
    },
    "afrr_cap_down_eur_mw": {
        "field_key": "afrr_cap_down_eur_mw",
        "label": "aFRR Capacity Down Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly aFRR capacity down clearing price.",
    },
    "mfrr_cap_up_eur_mw": {
        "field_key": "mfrr_cap_up_eur_mw",
        "label": "mFRR Capacity Up Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly mFRR capacity up clearing price.",
    },
    "mfrr_cap_down_eur_mw": {
        "field_key": "mfrr_cap_down_eur_mw",
        "label": "mFRR Capacity Down Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly mFRR capacity down clearing price.",
    },
    "afrr_act_up_eur_mwh": {
        "field_key": "afrr_act_up_eur_mwh",
        "label": "aFRR Activation Up Price",
        "unit": "EUR/MWh",
        "granularity": "15m",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "activation",
        "methodology_note": "aFRR activation up settlement price.",
    },
    "afrr_act_down_eur_mwh": {
        "field_key": "afrr_act_down_eur_mwh",
        "label": "aFRR Activation Down Price",
        "unit": "EUR/MWh",
        "granularity": "15m",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "activation",
        "methodology_note": "aFRR activation down settlement price.",
    },
    "mfrr_act_up_eur_mwh": {
        "field_key": "mfrr_act_up_eur_mwh",
        "label": "mFRR Activation Up Price",
        "unit": "EUR/MWh",
        "granularity": "15m",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "activation",
        "methodology_note": "mFRR activation up settlement price.",
    },
    "mfrr_act_down_eur_mwh": {
        "field_key": "mfrr_act_down_eur_mwh",
        "label": "mFRR Activation Down Price",
        "unit": "EUR/MWh",
        "granularity": "15m",
        "source_name": "Fingrid",
        "source_dataset_id": "unknown",
        "source_type": "live",
        "category": "activation",
        "methodology_note": "mFRR activation down settlement price.",
    },
    "imbalance_price_eur_mwh": {
        "field_key": "imbalance_price_eur_mwh",
        "label": "Imbalance Settlement Price",
        "unit": "EUR/MWh",
        "granularity": "15m",
        "source_name": "Fingrid",
        "source_dataset_id": "319",
        "source_type": "live",
        "category": "balancing",
        "methodology_note": "Finland imbalance settlement reference price.",
    },
    "spot_price_fi_eur_mwh": {
        "field_key": "spot_price_fi_eur_mwh",
        "label": "Finland Spot Price",
        "unit": "EUR/MWh",
        "granularity": "1h",
        "source_name": "Nord Pool",
        "source_dataset_id": "nordpool_day_ahead_fi",
        "source_type": "external_join",
        "category": "spot",
        "methodology_note": "Nord Pool Finland day-ahead reference joined into board views.",
    },
}


FINLAND_BOARD_VIEWS = {
    "capacity_hourly": {
        "view_key": "capacity_hourly",
        "title": "capacity_1h",
        "granularity": "1h",
        "columns": [
            "timestamp_helsinki",
            "fcr_n_price_eur_mw",
            "fcr_d_up_price_eur_mw",
            "fcr_d_down_price_eur_mw",
            "afrr_cap_up_eur_mw",
            "afrr_cap_down_eur_mw",
            "mfrr_cap_up_eur_mw",
            "mfrr_cap_down_eur_mw",
            "spot_price_fi_eur_mwh",
        ],
    },
    "activation_15m": {
        "view_key": "activation_15m",
        "title": "activation_settlement_15m",
        "granularity": "15m",
        "columns": [
            "timestamp_helsinki",
            "afrr_act_up_eur_mwh",
            "afrr_act_down_eur_mwh",
            "mfrr_act_up_eur_mwh",
            "mfrr_act_down_eur_mwh",
            "imbalance_price_eur_mwh",
            "spot_price_fi_eur_mwh",
        ],
    },
    "daily_capacity": {
        "view_key": "daily_capacity",
        "title": "daily_averages",
        "granularity": "day",
        "columns": [
            "date",
            "fcr_n_price_eur_mw",
            "fcr_d_up_price_eur_mw",
            "fcr_d_down_price_eur_mw",
            "afrr_cap_up_eur_mw",
            "afrr_cap_down_eur_mw",
            "mfrr_cap_up_eur_mw",
            "mfrr_cap_down_eur_mw",
            "spot_price_fi_eur_mwh",
        ],
    },
    "daily_activation": {
        "view_key": "daily_activation",
        "title": "daily_averages",
        "granularity": "day",
        "columns": [
            "date",
            "afrr_act_up_eur_mwh",
            "afrr_act_down_eur_mwh",
            "mfrr_act_up_eur_mwh",
            "mfrr_act_down_eur_mwh",
            "imbalance_price_eur_mwh",
            "spot_price_fi_eur_mwh",
        ],
    },
    "summary_stats": {
        "view_key": "summary_stats",
        "title": "summary_stats",
        "granularity": "mixed",
        "columns": [],
    },
    "field_dictionary": {
        "view_key": "field_dictionary",
        "title": "field_dictionary",
        "granularity": "mixed",
        "columns": [],
    },
}


FINLAND_BOARD_OVERVIEW_CARDS = [
    {
        "field_key": "fcr_n_price_eur_mw",
        "granularity": "1h",
        "kind": "metric",
    },
    {
        "field_key": "afrr_act_up_eur_mwh",
        "granularity": "15m",
        "kind": "metric",
    },
    {
        "field_key": "mfrr_act_up_eur_mwh",
        "granularity": "15m",
        "kind": "metric",
    },
    {
        "field_key": "imbalance_price_eur_mwh",
        "granularity": "15m",
        "kind": "metric",
    },
    {
        "field_key": "spot_price_fi_eur_mwh",
        "granularity": "1h",
        "kind": "metric",
    },
    {
        "field_key": "join_completeness",
        "granularity": "board",
        "kind": "join_health",
    },
]


def get_finland_board_field(field_key: str) -> dict:
    if field_key not in FINLAND_BOARD_FIELDS:
        raise KeyError(f"Unsupported Finland board field: {field_key}")
    return FINLAND_BOARD_FIELDS[field_key]


def get_finland_board_view(view_key: str) -> dict:
    if view_key not in FINLAND_BOARD_VIEWS:
        raise KeyError(f"Unsupported Finland board view: {view_key}")
    return FINLAND_BOARD_VIEWS[view_key]


def get_finland_board_overview_cards() -> list[dict]:
    return list(FINLAND_BOARD_OVERVIEW_CARDS)
