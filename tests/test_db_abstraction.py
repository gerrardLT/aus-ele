"""
Unit tests for the database abstraction layer.

Tests the DatabaseBackend protocol, SQLiteBackend, PostgreSQLBackend stub,
and the db_factory module.

Requirements: 12.1, 12.2, 12.3, 12.5
"""

import os
import sys
import tempfile
import time
from unittest.mock import patch, MagicMock

import pytest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from db_backend import DatabaseBackend
from db_sqlite_backend import SQLiteBackend
from db_factory import (
    create_backend,
    get_backend,
    BACKEND_SQLITE,
    BACKEND_POSTGRESQL,
)


# ---------------------------------------------------------------------------
# DatabaseBackend ABC tests
# ---------------------------------------------------------------------------


class TestDatabaseBackendABC:
    """Verify the ABC cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            DatabaseBackend()


# ---------------------------------------------------------------------------
# SQLiteBackend tests
# ---------------------------------------------------------------------------


class TestSQLiteBackend:
    """Test the SQLite backend implementation."""

    @pytest.fixture
    def tmp_db(self, tmp_path):
        """Create a temporary SQLite database path."""
        return str(tmp_path / "test.db")

    @pytest.fixture
    def backend(self, tmp_db):
        """Create a SQLiteBackend instance with a temp database."""
        return SQLiteBackend(tmp_db)

    def test_backend_type(self, backend):
        assert backend.backend_type == "sqlite"

    def test_manager_property(self, backend):
        """The manager property exposes the underlying DatabaseManager."""
        from database import DatabaseManager
        assert isinstance(backend.manager, DatabaseManager)

    def test_is_healthy(self, backend):
        assert backend.is_healthy() is True

    def test_is_healthy_bad_path(self, tmp_path):
        """A backend with an invalid path should still be healthy if SQLite can create it."""
        db_path = str(tmp_path / "subdir" / "test.db")
        backend = SQLiteBackend(db_path)
        assert backend.is_healthy() is True

    def test_get_connection_context_manager(self, backend):
        """get_connection should yield a usable connection."""
        with backend.get_connection() as conn:
            conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO test_tbl (val) VALUES (?)", ("hello",))
            conn.commit()
            cursor = conn.execute("SELECT val FROM test_tbl")
            rows = cursor.fetchall()
        assert rows == [("hello",)]

    def test_execute_read(self, backend):
        """execute() should return query results."""
        with backend.get_connection() as conn:
            conn.execute("CREATE TABLE nums (n INTEGER)")
            conn.execute("INSERT INTO nums VALUES (1)")
            conn.execute("INSERT INTO nums VALUES (2)")
            conn.execute("INSERT INTO nums VALUES (3)")
            conn.commit()

        rows = backend.execute("SELECT n FROM nums ORDER BY n")
        assert rows == [(1,), (2,), (3,)]

    def test_execute_write(self, backend):
        """execute_write() should return affected row count."""
        with backend.get_connection() as conn:
            conn.execute("CREATE TABLE items (name TEXT)")
            conn.commit()

        count = backend.execute_write("INSERT INTO items VALUES (?)", ("apple",))
        assert count == 1

        rows = backend.execute("SELECT name FROM items")
        assert rows == [("apple",)]

    def test_executemany(self, backend):
        """executemany() should batch-insert rows."""
        with backend.get_connection() as conn:
            conn.execute("CREATE TABLE batch (x INTEGER)")
            conn.commit()

        params = [(i,) for i in range(10)]
        count = backend.executemany("INSERT INTO batch VALUES (?)", params)
        assert count == 10

        rows = backend.execute("SELECT COUNT(*) FROM batch")
        assert rows == [(10,)]

    def test_close(self, backend):
        """close() should not raise."""
        backend.close()
        # SQLite backend has no persistent connections, so it should still work
        assert backend.is_healthy() is True


# ---------------------------------------------------------------------------
# SQLiteBackend retry logic tests
# ---------------------------------------------------------------------------


class TestSQLiteRetryLogic:
    """Test retry behavior for SQLite locked scenarios."""

    def test_execute_retries_on_locked(self, tmp_path):
        """Verify retry logic is triggered on OperationalError with 'locked'."""
        import sqlite3

        db_path = str(tmp_path / "retry_test.db")
        backend = SQLiteBackend(db_path)

        # Create a table first
        with backend.get_connection() as conn:
            conn.execute("CREATE TABLE retry_tbl (v INTEGER)")
            conn.commit()

        # Mock sqlite3.connect to fail once then succeed
        original_connect = sqlite3.connect
        call_count = [0]

        def mock_connect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise sqlite3.OperationalError("database is locked")
            return original_connect(*args, **kwargs)

        with patch("sqlite3.connect", side_effect=mock_connect):
            # Should retry and succeed on second attempt
            rows = backend.execute("SELECT COUNT(*) FROM retry_tbl")
            assert rows == [(0,)]
            assert call_count[0] == 2

    def test_execute_fails_after_max_retries(self, tmp_path):
        """Verify ConnectionError is raised after all retries exhausted."""
        import sqlite3

        db_path = str(tmp_path / "fail_test.db")
        backend = SQLiteBackend(db_path)

        def always_locked(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        with patch("sqlite3.connect", side_effect=always_locked):
            with patch("time.sleep"):  # Skip actual delays
                with pytest.raises(ConnectionError, match="3 attempts"):
                    backend.execute("SELECT 1")


# ---------------------------------------------------------------------------
# db_factory tests
# ---------------------------------------------------------------------------


class TestDbFactory:
    """Test the database backend factory."""

    def test_create_sqlite_backend_default(self, tmp_path):
        """Default backend should be SQLite."""
        db_path = str(tmp_path / "factory_test.db")
        with patch.dict(os.environ, {"AUS_ELE_DB_BACKEND": "sqlite", "AUS_ELE_DB_PATH": db_path}):
            backend = create_backend()
            assert backend.backend_type == "sqlite"
            assert isinstance(backend, SQLiteBackend)

    def test_create_sqlite_backend_explicit(self, tmp_path):
        """Explicit 'sqlite' argument should create SQLiteBackend."""
        db_path = str(tmp_path / "explicit_test.db")
        with patch.dict(os.environ, {"AUS_ELE_DB_PATH": db_path}):
            backend = create_backend(backend_type="sqlite")
            assert backend.backend_type == "sqlite"

    def test_create_postgresql_backend_missing_psycopg2(self):
        """PostgreSQL backend should raise ImportError if psycopg2 not available."""
        with patch.dict(os.environ, {"AUS_ELE_DB_BACKEND": "postgresql"}):
            # psycopg2 may or may not be installed; if not, ImportError is expected
            # If installed, ConnectionError is expected (no real PG server)
            with pytest.raises((ImportError, ConnectionError)):
                create_backend(backend_type="postgresql")

    def test_unsupported_backend_raises_value_error(self):
        """Unsupported backend type should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported database backend"):
            create_backend(backend_type="mysql")

    def test_env_var_controls_backend(self, tmp_path):
        """AUS_ELE_DB_BACKEND env var should control backend selection."""
        db_path = str(tmp_path / "env_test.db")
        with patch.dict(os.environ, {"AUS_ELE_DB_BACKEND": "sqlite", "AUS_ELE_DB_PATH": db_path}):
            backend = create_backend()
            assert backend.backend_type == "sqlite"

    def test_env_var_case_insensitive(self, tmp_path):
        """Backend type should be case-insensitive."""
        db_path = str(tmp_path / "case_test.db")
        with patch.dict(os.environ, {"AUS_ELE_DB_BACKEND": "SQLite", "AUS_ELE_DB_PATH": db_path}):
            backend = create_backend()
            assert backend.backend_type == "sqlite"

    def test_get_backend_singleton(self, tmp_path):
        """get_backend() should return the same instance on repeated calls."""
        # Clear the lru_cache
        get_backend.cache_clear()
        db_path = str(tmp_path / "singleton_test.db")
        with patch.dict(os.environ, {"AUS_ELE_DB_BACKEND": "sqlite", "AUS_ELE_DB_PATH": db_path}):
            b1 = get_backend()
            b2 = get_backend()
            assert b1 is b2
        # Clean up
        get_backend.cache_clear()


# ---------------------------------------------------------------------------
# PostgreSQLBackend placeholder translation tests
# ---------------------------------------------------------------------------


class TestPostgreSQLPlaceholderTranslation:
    """Test the SQL placeholder translation utility."""

    def test_translate_question_marks(self):
        from db_postgres_backend import _translate_placeholders

        sql = "SELECT * FROM users WHERE id = ? AND name = ?"
        result = _translate_placeholders(sql)
        assert result == "SELECT * FROM users WHERE id = %s AND name = %s"

    def test_translate_no_placeholders(self):
        from db_postgres_backend import _translate_placeholders

        sql = "SELECT COUNT(*) FROM users"
        result = _translate_placeholders(sql)
        assert result == sql

    def test_translate_insert(self):
        from db_postgres_backend import _translate_placeholders

        sql = "INSERT INTO tbl (a, b, c) VALUES (?, ?, ?)"
        result = _translate_placeholders(sql)
        assert result == "INSERT INTO tbl (a, b, c) VALUES (%s, %s, %s)"


# ---------------------------------------------------------------------------
# PostgreSQLBackend connection pool config tests
# ---------------------------------------------------------------------------


class TestPostgreSQLBackendConfig:
    """Test PostgreSQL backend configuration parsing."""

    def test_dsn_from_env_var(self):
        """AUS_ELE_PG_DSN should be used if set."""
        from db_postgres_backend import PostgreSQLBackend

        dsn = "postgresql://user:pass@myhost:5432/mydb"
        with patch.dict(os.environ, {"AUS_ELE_PG_DSN": dsn}):
            # We can't fully instantiate without psycopg2/server,
            # but we can test the DSN building logic
            backend = PostgreSQLBackend.__new__(PostgreSQLBackend)
            result = backend._build_dsn()
            assert result == dsn

    def test_dsn_from_components(self):
        """DSN should be built from individual env vars when AUS_ELE_PG_DSN is not set."""
        from db_postgres_backend import PostgreSQLBackend

        env = {
            "AUS_ELE_PG_HOST": "db.example.com",
            "AUS_ELE_PG_PORT": "5433",
            "AUS_ELE_PG_DATABASE": "testdb",
            "AUS_ELE_PG_USER": "testuser",
            "AUS_ELE_PG_PASSWORD": "secret",
            "AUS_ELE_PG_CONNECT_TIMEOUT": "15",
        }
        # Remove AUS_ELE_PG_DSN if present
        clean_env = {k: v for k, v in os.environ.items() if k != "AUS_ELE_PG_DSN"}
        clean_env.update(env)

        with patch.dict(os.environ, clean_env, clear=True):
            backend = PostgreSQLBackend.__new__(PostgreSQLBackend)
            backend._connect_timeout = 15
            result = backend._build_dsn()
            assert "db.example.com" in result
            assert "5433" in result
            assert "testdb" in result
            assert "testuser" in result
            assert "secret" in result
