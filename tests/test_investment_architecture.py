"""Tests for S5: Investment analysis architecture (A1/A3/A4/A5).

Validates:
- A4: Domain exceptions map to correct HTTP status codes
- A5: analysis_cache key includes degradation_rate (different rates → different keys)
- A1: Service layer is importable and delegates correctly
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.exceptions import (
    InsufficientDataError,
    InvestmentAnalysisError,
    SolverError,
    ValidationError,
)


class A4ExceptionMappingTests(unittest.TestCase):
    """A4: domain exceptions carry correct status codes and error codes."""

    def test_insufficient_data_maps_to_424(self):
        err = InsufficientDataError("No price data for region X")
        self.assertEqual(err.status_code, 424)
        self.assertEqual(err.error_code, "INSUFFICIENT_DATA")
        self.assertIn("No price data", str(err))

    def test_solver_error_maps_to_500(self):
        err = SolverError("CBC timed out after 60s")
        self.assertEqual(err.status_code, 500)
        self.assertEqual(err.error_code, "SOLVER_ERROR")

    def test_validation_error_maps_to_422(self):
        err = ValidationError("power_mw must be > 0")
        self.assertEqual(err.status_code, 422)
        self.assertEqual(err.error_code, "VALIDATION_ERROR")

    def test_base_error_maps_to_500(self):
        err = InvestmentAnalysisError("unexpected")
        self.assertEqual(err.status_code, 500)
        self.assertEqual(err.error_code, "INTERNAL_ERROR")

    def test_detail_dict_attached(self):
        err = InsufficientDataError("missing", detail={"region": "NSW1", "year": 2025})
        self.assertEqual(err.detail["region"], "NSW1")

    def test_isinstance_hierarchy(self):
        """All domain exceptions are InvestmentAnalysisError subclasses."""
        self.assertIsInstance(InsufficientDataError("x"), InvestmentAnalysisError)
        self.assertIsInstance(SolverError("x"), InvestmentAnalysisError)
        self.assertIsInstance(ValidationError("x"), InvestmentAnalysisError)


class A5CacheKeyIsolationTests(unittest.TestCase):
    """A5: cache key must include degradation_rate for isolation."""

    def test_different_degradation_rates_produce_different_keys(self):
        """Two requests differing only in degradation_rate must not share cache."""
        from routes.investment_routes import _stable_cache_key

        payload_a = {
            "region": "SA1",
            "degradation_rate": 0.02,
            "battery": {"power_mw": 50},
        }
        payload_b = {
            "region": "SA1",
            "degradation_rate": 0.05,
            "battery": {"power_mw": 50},
        }
        key_a = _stable_cache_key(payload_a)
        key_b = _stable_cache_key(payload_b)
        self.assertNotEqual(key_a, key_b, "Different degradation_rate must yield different cache keys")

    def test_same_params_produce_same_key(self):
        """Identical payloads produce identical cache keys (determinism)."""
        from routes.investment_routes import _stable_cache_key

        payload = {"region": "SA1", "degradation_rate": 0.03, "x": [1, 2, 3]}
        self.assertEqual(_stable_cache_key(payload), _stable_cache_key(payload))


class A1ServiceLayerTests(unittest.TestCase):
    """A1: service layer module is importable and has expected API."""

    def test_service_module_importable(self):
        from services import investment_service
        self.assertTrue(hasattr(investment_service, "build_backtest_summary"))
        self.assertTrue(hasattr(investment_service, "derive_arbitrage_baseline"))
        self.assertTrue(hasattr(investment_service, "get_fcas_baseline"))
        self.assertTrue(hasattr(investment_service, "build_investment_p3_decision"))
        self.assertTrue(hasattr(investment_service, "build_investment_response"))
        self.assertTrue(hasattr(investment_service, "build_decision_adjusted_scenarios"))
        self.assertTrue(hasattr(investment_service, "build_decision_adjusted_monte_carlo"))


if __name__ == "__main__":
    unittest.main()
