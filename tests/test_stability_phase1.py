"""Phase 1 (stability) unit tests.

Covers the audit follow-up fixes that do not require a live PostgreSQL:

* Global unhandled-exception handler masks internal details (opaque 500).
* ``DatabaseUnavailableError`` maps to a transient 503.
* ``_PGConnWrapper`` context manager commits on clean exit and rolls back on
  exception (M-4 transaction safety).
* ``RedisResponseCache`` circuit-breaker state is thread-safe (L-1).
"""

import sys
import threading
import types
import unittest

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

# Stub heavy optional dependencies that may be absent in the test environment.
sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseUnavailableError, _PGConnWrapper  # noqa: E402
from response_cache import RedisResponseCache  # noqa: E402


def _build_masking_app() -> FastAPI:
    """Build a minimal app replicating app.py's global error handlers."""
    app = FastAPI()

    @app.exception_handler(Exception)
    async def _handle_unhandled(request, exc):  # noqa: ARG001
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.exception_handler(DatabaseUnavailableError)
    async def _handle_db_unavailable(request, exc):  # noqa: ARG001
        return JSONResponse(
            status_code=503,
            content={"detail": "Service temporarily unavailable; please retry later."},
        )

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret table: trading_price_2024 @ /etc/passwd")

    @app.get("/db-down")
    def db_down():
        raise DatabaseUnavailableError("Database connection pool unavailable")

    return app


class GlobalErrorHandlerTests(unittest.TestCase):
    def setUp(self):
        # raise_server_exceptions=False so the handler produces the response.
        self.client = TestClient(_build_masking_app(), raise_server_exceptions=False)

    def test_unhandled_exception_is_masked_to_opaque_500(self):
        response = self.client.get("/boom")
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["detail"], "Internal server error")
        # Internal details must not leak into the response body.
        self.assertNotIn("trading_price_2024", response.text)
        self.assertNotIn("/etc/passwd", response.text)

    def test_database_unavailable_maps_to_503(self):
        response = self.client.get("/db-down")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Service temporarily unavailable; please retry later.",
        )


class _FakeConn:
    """Minimal stand-in for a psycopg2 connection recording commit/rollback."""

    def __init__(self, commit_error: Exception | None = None):
        self.commits = 0
        self.rollbacks = 0
        self._commit_error = commit_error

    def commit(self):
        if self._commit_error is not None:
            raise self._commit_error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def cursor(self):  # pragma: no cover - not exercised here
        raise NotImplementedError


class PGConnWrapperTransactionTests(unittest.TestCase):
    def test_clean_exit_commits(self):
        conn = _FakeConn()
        wrapper = _PGConnWrapper(conn, db_mgr=None)
        with wrapper:
            pass
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)

    def test_exception_rolls_back_and_propagates(self):
        conn = _FakeConn()
        wrapper = _PGConnWrapper(conn, db_mgr=None)
        with self.assertRaises(ValueError):
            with wrapper:
                raise ValueError("boom")
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)

    def test_commit_failure_rolls_back_and_reraises(self):
        conn = _FakeConn(commit_error=RuntimeError("commit failed"))
        wrapper = _PGConnWrapper(conn, db_mgr=None)
        with self.assertRaises(RuntimeError):
            with wrapper:
                pass
        self.assertEqual(conn.rollbacks, 1)


class CircuitBreakerThreadSafetyTests(unittest.TestCase):
    def test_concurrent_failure_recording_is_safe(self):
        cache = RedisResponseCache(url="redis://127.0.0.1:6399/0")
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(200):
                    cache._record_failure()
                    cache._is_circuit_open()
                    cache._get_client()
            except Exception as exc:  # pragma: no cover - race would surface here
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # After recorded failures the circuit must be open.
        self.assertTrue(cache._is_circuit_open())


if __name__ == "__main__":
    unittest.main()
