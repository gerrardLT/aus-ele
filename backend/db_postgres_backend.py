"""
PostgreSQL database backend implementation.

Provides connection pool management, retry logic, and parameter placeholder
translation for PostgreSQL. Uses psycopg2 with connection pooling.

Requirements: 12.2, 12.3, 12.5
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import Any, Generator

from db_backend import DatabaseBackend

logger = logging.getLogger(__name__)

# Connection pool defaults
_DEFAULT_MIN_CONNECTIONS = 2
_DEFAULT_MAX_CONNECTIONS = 10
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 10

# Retry configuration
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 10.0
_TOTAL_TIMEOUT_SECONDS = 30.0


def _translate_placeholders(sql: str) -> str:
    """
    Translate SQLite-style ? placeholders to PostgreSQL-style %s placeholders.

    This enables business logic to use ? placeholders uniformly while the
    backend handles dialect-specific translation.
    """
    # Simple replacement: ? -> %s
    # This handles the common case. For more complex SQL with literal '?'
    # characters (rare in this codebase), manual adjustment would be needed.
    return sql.replace("?", "%s")


class PostgreSQLBackend(DatabaseBackend):
    """
    PostgreSQL backend with connection pooling and retry logic.

    Configuration is read from environment variables:
    - AUS_ELE_PG_DSN: Full connection string (postgresql://user:pass@host:port/db)
    - AUS_ELE_PG_HOST: PostgreSQL host (default: localhost)
    - AUS_ELE_PG_PORT: PostgreSQL port (default: 5432)
    - AUS_ELE_PG_DATABASE: Database name (default: aemo_data)
    - AUS_ELE_PG_USER: Database user (default: aemo)
    - AUS_ELE_PG_PASSWORD: Database password
    - AUS_ELE_PG_MIN_CONNECTIONS: Minimum pool size (default: 2)
    - AUS_ELE_PG_MAX_CONNECTIONS: Maximum pool size (default: 10)
    - AUS_ELE_PG_CONNECT_TIMEOUT: Connection timeout in seconds (default: 10)
    """

    def __init__(self):
        """
        Initialize the PostgreSQL backend with connection pooling.

        Raises:
            ImportError: If psycopg2 is not installed.
            ConnectionError: If initial connection cannot be established
                after retry attempts.
        """
        try:
            import psycopg2
            from psycopg2 import pool as pg_pool
        except ImportError as exc:
            raise ImportError(
                "psycopg2 is required for PostgreSQL backend. "
                "Install it with: pip install psycopg2-binary"
            ) from exc

        self._dsn = self._build_dsn()
        self._min_conn = int(
            os.environ.get("AUS_ELE_PG_MIN_CONNECTIONS", str(_DEFAULT_MIN_CONNECTIONS))
        )
        self._max_conn = int(
            os.environ.get("AUS_ELE_PG_MAX_CONNECTIONS", str(_DEFAULT_MAX_CONNECTIONS))
        )
        self._connect_timeout = int(
            os.environ.get("AUS_ELE_PG_CONNECT_TIMEOUT", str(_DEFAULT_CONNECT_TIMEOUT_SECONDS))
        )

        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._initialize_pool()

        logger.info(
            "PostgreSQLBackend initialized (pool: %d-%d connections, timeout: %ds)",
            self._min_conn, self._max_conn, self._connect_timeout,
        )

    @property
    def backend_type(self) -> str:
        return "postgresql"

    def _build_dsn(self) -> str:
        """Build the PostgreSQL DSN from environment variables."""
        dsn = os.environ.get("AUS_ELE_PG_DSN")
        if dsn:
            return dsn

        host = os.environ.get("AUS_ELE_PG_HOST", "localhost")
        port = os.environ.get("AUS_ELE_PG_PORT", "5432")
        database = os.environ.get("AUS_ELE_PG_DATABASE", "aemo_data")
        user = os.environ.get("AUS_ELE_PG_USER", "aemo")
        password = os.environ.get("AUS_ELE_PG_PASSWORD", "")

        return (
            f"host={host} port={port} dbname={database} "
            f"user={user} password={password} "
            f"connect_timeout={self._connect_timeout}"
        )

    def _initialize_pool(self) -> None:
        """
        Initialize the connection pool with retry logic.

        Retries up to 3 times within 30 seconds.
        """
        import psycopg2
        from psycopg2 import pool as pg_pool

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                self._pool = pg_pool.ThreadedConnectionPool(
                    minconn=self._min_conn,
                    maxconn=self._max_conn,
                    dsn=self._dsn,
                )
                return
            except psycopg2.OperationalError as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                    delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                    logger.warning(
                        "PostgreSQL pool init attempt %d/%d failed, "
                        "retrying in %.1fs: %s",
                        attempt, _MAX_RETRIES, delay, exc,
                    )
                    time.sleep(delay)

        raise ConnectionError(
            f"PostgreSQL connection pool initialization failed after "
            f"{_MAX_RETRIES} attempts within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    def _get_pooled_connection(self) -> Any:
        """
        Get a connection from the pool with retry logic.

        Returns:
            A psycopg2 connection object.

        Raises:
            ConnectionError: If connection cannot be obtained after retries.
        """
        import psycopg2

        start_time = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            elapsed = time.monotonic() - start_time
            if elapsed >= _TOTAL_TIMEOUT_SECONDS:
                break

            try:
                if self._pool is None or self._pool.closed:
                    self._initialize_pool()
                conn = self._pool.getconn()
                # Verify connection is alive
                conn.cursor().execute("SELECT 1")
                return conn
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    remaining = _TOTAL_TIMEOUT_SECONDS - (time.monotonic() - start_time)
                    delay = min(_RETRY_DELAY_SECONDS, max(0, remaining))
                    logger.warning(
                        "PostgreSQL connection attempt %d/%d failed, "
                        "retrying in %.1fs: %s",
                        attempt, _MAX_RETRIES, delay, exc,
                    )
                    time.sleep(delay)
                    # Try to reinitialize pool on connection failure
                    try:
                        if self._pool and not self._pool.closed:
                            self._pool.closeall()
                    except Exception:
                        pass
                    self._pool = None

        raise ConnectionError(
            f"PostgreSQL connection failed after {_MAX_RETRIES} attempts "
            f"within {_TOTAL_TIMEOUT_SECONDS}s: {last_error}"
        )

    @contextlib.contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """
        Yield a PostgreSQL connection from the pool.

        The connection is returned to the pool after use.
        Includes retry logic: 3 attempts within 30 seconds.
        """
        conn = self._get_pooled_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._pool and not self._pool.closed:
                self._pool.putconn(conn)

    def execute(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Execute a read query and return all rows."""
        translated_sql = _translate_placeholders(sql)
        conn = self._get_pooled_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(translated_sql, params)
            rows = cursor.fetchall()
            cursor.close()
            return rows
        finally:
            if self._pool and not self._pool.closed:
                self._pool.putconn(conn)

    def execute_write(self, sql: str, params: tuple = ()) -> int:
        """Execute a write statement and return affected row count."""
        translated_sql = _translate_placeholders(sql)
        conn = self._get_pooled_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(translated_sql, params)
            conn.commit()
            rowcount = cursor.rowcount
            cursor.close()
            return rowcount
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._pool and not self._pool.closed:
                self._pool.putconn(conn)

    def executemany(self, sql: str, params_list: list[tuple]) -> int:
        """Execute a batch write statement."""
        translated_sql = _translate_placeholders(sql)
        conn = self._get_pooled_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(translated_sql, params_list)
            conn.commit()
            rowcount = cursor.rowcount
            cursor.close()
            return rowcount
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._pool and not self._pool.closed:
                self._pool.putconn(conn)

    def is_healthy(self) -> bool:
        """Check if the PostgreSQL connection pool is healthy."""
        try:
            if self._pool is None or self._pool.closed:
                return False
            conn = self._pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return True
            finally:
                self._pool.putconn(conn)
        except Exception:
            return False

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool and not self._pool.closed:
            self._pool.closeall()
            logger.info("PostgreSQLBackend connection pool closed")
        self._pool = None
