"""
Default network fees (TUOS + DUOS) by NEM/WEM region.

These are approximate typical commercial/industrial rates in $/MWh,
derived from AER 2024-25 regulatory determinations.
Users can override these values in the frontend.
"""

# Typical combined TUOS + DUOS rates ($/MWh) for commercial/industrial customers
DEFAULT_NETWORK_FEES = {
    "NSW1": 45.0,   # Ausgrid / Endeavour / Essential Energy
    "QLD1": 42.0,   # Energex / Ergon Energy
    "VIC1": 38.0,   # Five Victorian DNSPs combined
    "SA1":  55.0,   # SA Power Networks (highest nationally)
    "TAS1": 48.0,   # TasNetworks
    "WEM":  40.0,   # Western Power
}

# Settlement interval in minutes for each market
SETTLEMENT_INTERVALS = {
    "NSW1": 5,
    "QLD1": 5,
    "VIC1": 5,
    "SA1":  5,
    "TAS1": 5,
    "WEM":  30,
}


def get_default_fee(region: str) -> float:
    """Return the default network fee for a given region, or 40.0 as fallback."""
    return DEFAULT_NETWORK_FEES.get(region, 40.0)


def get_settlement_interval(region: str) -> int:
    """Return the settlement interval in minutes for a given region."""
    return SETTLEMENT_INTERVALS.get(region, 5)


def get_window_sizes(region: str) -> dict:
    """
    Return sliding window sizes (in number of data points) for each
    target hour window, based on the region's settlement interval.

    For NEM (5-min): 1h=12, 2h=24, 4h=48, 6h=72 points
    For WEM (30-min): 1h=2, 2h=4, 4h=8, 6h=12 points
    """
    interval = get_settlement_interval(region)
    points_per_hour = 60 // interval
    return {
        "1h": points_per_hour * 1,
        "2h": points_per_hour * 2,
        "4h": points_per_hour * 4,
        "6h": points_per_hour * 6,
    }


def get_all_fees() -> list:
    """Return all default fees as a list of dicts for API response."""
    return [
        {"region": region, "fee": fee}
        for region, fee in DEFAULT_NETWORK_FEES.items()
    ]
