"""
Shared exception classes for the Tianshu platform.

MarketModuleError provides a structured error response format for all
market analysis module endpoints (spike, saturation, ranking, co-opt, WEM).
"""

from __future__ import annotations


class MarketModuleError(Exception):
    """Structured error for market module API endpoints.

    When raised inside a route handler, the registered exception handler
    returns a JSON response with error_code, message, and suggested_action.

    Args:
        error_code: Machine-readable error identifier (e.g. "SPIKE_DATA_NOT_FOUND").
        message: Human-readable error description.
        suggested_action: Guidance for the caller on how to resolve the issue.
        status_code: HTTP status code to return (default 400).
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        suggested_action: str,
        status_code: int = 400,
    ):
        self.error_code = error_code
        self.message = message
        self.suggested_action = suggested_action
        self.status_code = status_code
        super().__init__(message)
