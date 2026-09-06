"""Property-based tests for API error response structure.

Feature: market-modules-redesign, Property 17: API error response structure

Uses Hypothesis to verify that for any MarketModuleError with valid error_code,
message, and suggested_action, the exception handler returns a JSON response
with exactly those three fields and the correct HTTP status code.

**Validates: Requirements 12.6**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests.support import stub_optional_dep

# Stub heavy optional dependencies that may not be installed in test env
stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from fastapi import FastAPI
from fastapi.testclient import TestClient

from exceptions import MarketModuleError
from routes import _register_market_module_error_handler


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-empty strings for error fields
non_empty_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# HTTP error status codes (4xx and 5xx)
status_code_strategy = st.integers(min_value=400, max_value=599)


# ---------------------------------------------------------------------------
# Property 17: API error response structure
# ---------------------------------------------------------------------------


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    error_code=non_empty_text,
    message=non_empty_text,
    suggested_action=non_empty_text,
    status_code=status_code_strategy,
)
def test_property_17_error_response_structure(
    error_code, message, suggested_action, status_code
):
    """Feature: market-modules-redesign, Property 17: API error response structure

    For any MarketModuleError with valid error_code, message, and suggested_action,
    the exception handler returns a JSON response with exactly those three fields
    and the correct HTTP status code.

    **Validates: Requirements 12.6**
    """
    # Create a fresh FastAPI app with the error handler registered
    app = FastAPI()
    _register_market_module_error_handler(app)

    # Create a test endpoint that raises MarketModuleError with generated values
    @app.get("/test-error")
    async def raise_error():
        raise MarketModuleError(
            error_code=error_code,
            message=message,
            suggested_action=suggested_action,
            status_code=status_code,
        )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-error")

    # Verify HTTP status code matches
    assert response.status_code == status_code, (
        f"Expected status {status_code}, got {response.status_code}"
    )

    # Verify response is valid JSON
    data = response.json()

    # Verify response has exactly the three required fields
    expected_fields = {"error_code", "message", "suggested_action"}
    actual_fields = set(data.keys())
    assert actual_fields == expected_fields, (
        f"Expected exactly fields {expected_fields}, got {actual_fields}. "
        f"Missing: {expected_fields - actual_fields}, "
        f"Extra: {actual_fields - expected_fields}"
    )

    # Verify field values match the input
    assert data["error_code"] == error_code, (
        f"error_code mismatch: expected {error_code!r}, got {data['error_code']!r}"
    )
    assert data["message"] == message, (
        f"message mismatch: expected {message!r}, got {data['message']!r}"
    )
    assert data["suggested_action"] == suggested_action, (
        f"suggested_action mismatch: expected {suggested_action!r}, "
        f"got {data['suggested_action']!r}"
    )
