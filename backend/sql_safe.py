"""Safe SQL table name validation.

Prevents SQL injection through f-string table name interpolation by
validating table names against a whitelist of known patterns.

Usage:
    from sql_safe import safe_table_name

    table = safe_table_name(f"trading_price_{year}")
    cursor.execute(f"SELECT * FROM {table} WHERE region_id = ?", (region,))
"""

from __future__ import annotations

import re

# Allowed table name patterns (regex).
# - Fixed names: exact match
# - Year-based: trading_price_YYYY, wem_trading_price_YYYY, etc.
_ALLOWED_PATTERNS: list[re.Pattern] = [
    # Year-based price tables
    re.compile(r"^trading_price_\d{4}$"),
    re.compile(r"^wem_trading_price_\d{4}$"),
    re.compile(r"^wem_ess_price_\d{4}$"),
    # FCAS tables
    re.compile(r"^fcas_4s_data$"),
    re.compile(r"^fcas_trading_price_\d{4}$"),
    # Fixed infrastructure tables
    re.compile(r"^system_status$"),
    re.compile(r"^jobs$"),
    re.compile(r"^job_events$"),
    re.compile(r"^data_completeness$"),
    re.compile(r"^audit_log$"),
    re.compile(r"^principals$"),
    re.compile(r"^sessions$"),
    re.compile(r"^workspaces$"),
    re.compile(r"^workspace_memberships$"),
    re.compile(r"^organizations$"),
    re.compile(r"^organization_memberships$"),
    re.compile(r"^workspace_invites$"),
    re.compile(r"^membership_invites$"),
    re.compile(r"^external_api_keys$"),
    re.compile(r"^external_api_usage$"),
    re.compile(r"^alerts$"),
    re.compile(r"^alert_history$"),
    re.compile(r"^capacity_data$"),
    re.compile(r"^grid_events$"),
    re.compile(r"^backtest_results$"),
    re.compile(r"^monthly_backtest$"),
    # Fingrid tables
    re.compile(r"^fingrid_\w+$"),
    # WEM tables
    re.compile(r"^wem_\w+$"),
    # SQLite internal
    re.compile(r"^sqlite_master$"),
    # Predispach tables
    re.compile(r"^predispatch_\w+$"),
]

# Simple character validation: table names may only contain
# alphanumeric characters and underscores.
_SAFE_CHARS = re.compile(r"^[a-zA-Z0-9_]+$")


def safe_table_name(name: str) -> str:
    """Validate and return a safe table name for SQL interpolation.

    Raises ValueError if the name does not match any allowed pattern
    or contains unsafe characters.

    Args:
        name: The table name to validate.

    Returns:
        The validated table name (unchanged).

    Raises:
        ValueError: If the table name is not in the allowed list.
    """
    if not name or not isinstance(name, str):
        raise ValueError(f"Invalid table name: {name!r}")

    # First check: only safe characters
    if not _SAFE_CHARS.match(name):
        raise ValueError(
            f"Table name contains invalid characters: {name!r}. "
            "Only alphanumeric and underscore allowed."
        )

    # Second check: must match at least one allowed pattern
    for pattern in _ALLOWED_PATTERNS:
        if pattern.match(name):
            return name

    raise ValueError(
        f"Table name not in allowed list: {name!r}. "
        "Add it to sql_safe._ALLOWED_PATTERNS if legitimate."
    )


def trading_price_table(year: int) -> str:
    """Build and validate a NEM trading price table name for the given year."""
    return safe_table_name(f"trading_price_{int(year)}")


def wem_trading_price_table(year: int) -> str:
    """Build and validate a WEM trading price table name for the given year."""
    return safe_table_name(f"wem_trading_price_{int(year)}")


def wem_ess_price_table(year: int) -> str:
    """Build and validate a WEM ESS price table name for the given year."""
    return safe_table_name(f"wem_ess_price_{int(year)}")


def fcas_trading_price_table(year: int) -> str:
    """Build and validate an FCAS trading price table name for the given year."""
    return safe_table_name(f"fcas_trading_price_{int(year)}")
