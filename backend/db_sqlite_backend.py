"""
SQLite database backend implementation.

Wraps the existing DatabaseManager to conform to the DatabaseBackend
protocol. This allows the platform to use the existing SQLite-based
DatabaseManager through the new abstraction layer without modification.

Requirements: 12.1, 12.2
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any, Generator

from db_backend import DatabaseBackend
from database import DatabaseManager

logger = logging.getLogger(__name__)

# Retry configuration for SQLite (file locking scenarios)
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 10.0
_TOTAL_TIMEOUT_SECONDS = 30.0


class SQLiteBackend(DatabaseBackend):
    """
    SQLite backend that delegates to the existing DatabaseManager.

    This backend wraps DatabaseManager so that all existing business logic
    continues to work unchanged while conforming to the DatabaseBackend ABC.
    """

    def __init__(self, db_path: str = "../data/aemo_data.db"):
        """
        Initialize the SQLite backend.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._manager = DatabaseManager(db_path)
        logger.info("SQLiteBackend initialized with path: %s", db_path)

    @property
    def backend_type(self) -> str:
        return "sqlite"

    @property
    def manager(self) -> DatabaseManager:
        """
        Expose the underlying DatabaseManager for code that still needs
        direct access during the migration period.
        """
        return self._manager

    @staticmethod
    def _connect_with_pragmas(db_path: str, timeout: float = 10.0):
        """Create a SQLite connection with web-server optimized PRAGMAs."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path, timeout=timeout)
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA cache_size=-65536")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    @contextlib.contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """
        Yield a SQLite connection with retry logic.

        Retries up to 3 times within 30 seconds if the database is locked.
        """
        import sqlite3

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                conn = self._connect_with_pragmas(self._db_path)
                try:
                    yield conn
                    return
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" in str(exc).lower():
                    if attempt < _MAX_RETRIES:
                        remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                        delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                        logger.warning(
                            "SQLite connection attempt %d/%d failed (locked), "
                            "retrying in %.1fs: %s",
                            attempt, _MAX_RETRIES, delay, exc,
                        )
                        time.sleep(delay)
                else:
                    raise

        raise ConnectionError(
            f"SQLite connection failed after {_MAX_RETRIES} attempts "
            f"within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    def execute(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Execute a read query and return all rows."""
        import sqlite3

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                conn = self._connect_with_pragmas(self._db_path)
                try:
                    cursor = conn.execute(sql, params)
                    return cursor.fetchall()
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" in str(exc).lower():
                    if attempt < _MAX_RETRIES:
                        remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                        delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                        logger.warning(
                            "SQLite execute attempt %d/%d failed, retrying in %.1fs",
                            attempt, _MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                    # On last attempt, fall through to raise ConnectionError
                else:
                    raise

        raise ConnectionError(
            f"SQLite execute failed after {_MAX_RETRIES} attempts "
            f"within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    def execute_write(self, sql: str, params: tuple = ()) -> int:
        """Execute a write statement and return affected row count."""
        import sqlite3

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                conn = self._connect_with_pragmas(self._db_path)
                try:
                    cursor = conn.execute(sql, params)
                    conn.commit()
                    return cursor.rowcount
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" in str(exc).lower():
                    if attempt < _MAX_RETRIES:
                        remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                        delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                        logger.warning(
                            "SQLite write attempt %d/%d failed, retrying in %.1fs",
                            attempt, _MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                else:
                    raise

        raise ConnectionError(
            f"SQLite write failed after {_MAX_RETRIES} attempts "
            f"within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    def executemany(self, sql: str, params_list: list[tuple]) -> int:
        """Execute a batch write statement."""
        import sqlite3

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                conn = self._connect_with_pragmas(self._db_path)
                try:
                    cursor = conn.executemany(sql, params_list)
                    conn.commit()
                    return cursor.rowcount
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "locked" in str(exc).lower():
                    if attempt < _MAX_RETRIES:
                        remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                        delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                        logger.warning(
                            "SQLite executemany attempt %d/%d failed, retrying in %.1fs",
                            attempt, _MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                else:
                    raise

        raise ConnectionError(
            f"SQLite executemany failed after {_MAX_RETRIES} attempts "
            f"within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    def is_healthy(self) -> bool:
        """Check if the SQLite database file is accessible."""
        import sqlite3

        try:
            conn = self._connect_with_pragmas(self._db_path, timeout=5.0)
            try:
                conn.execute("SELECT 1")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def close(self) -> None:
        """No persistent connections to close for SQLite."""
        logger.info("SQLiteBackend closed (no persistent connections)")
