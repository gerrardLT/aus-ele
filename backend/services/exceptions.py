"""Domain exceptions for investment analysis (S5/A4).

Maps business-level failures to machine-readable error codes and appropriate
HTTP status codes, replacing the generic 500 catch-all.
"""

from __future__ import annotations


class InvestmentAnalysisError(Exception):
    """Base exception for investment analysis domain errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


class InsufficientDataError(InvestmentAnalysisError):
    """Raised when required market/backtest data is missing or incomplete.

    Maps to HTTP 424 (Failed Dependency) — the upstream data source did not
    provide what the analysis needs.
    """

    status_code = 424
    error_code = "INSUFFICIENT_DATA"


class SolverError(InvestmentAnalysisError):
    """Raised when an optimization/solver backend fails or times out.

    Maps to HTTP 500 with a machine-readable code distinguishing solver
    failures from generic internal errors.
    """

    status_code = 500
    error_code = "SOLVER_ERROR"


class ValidationError(InvestmentAnalysisError):
    """Raised when input parameters fail domain-level validation.

    Maps to HTTP 422 (Unprocessable Entity) — syntactically valid request
    but semantically impossible parameters.
    """

    status_code = 422
    error_code = "VALIDATION_ERROR"
