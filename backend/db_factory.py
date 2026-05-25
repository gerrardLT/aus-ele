"""
Database backend factory.

Reads the AUS_ELE_DB_BACKEND environment variable to determine which
database backend to instantiate. Supports 'sqlite' (default) and
'postgresql'.

Requirements: 12.1, 12.2, 12.3, 12.5

Usage:
    from db_factory import create_backend, get_backend

    # Create a new backend instance
    backend = create_backend()

    # Get the singleton backend (for use in deps.py)
    backend = get_backend()
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from db_backend import DatabaseBackend

logger = logging.getLogger(__name__)

# Supported backend identifiers
BACKEND_SQLITE = "sqlite"
BACKEND_POSTGRESQL = "postgresql"
_SUPPORTED_BACKENDS = {BACKEND_SQLITE, BACKEND_POSTGRESQL}

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


def create_backend(backend_type: str | None = None) -> DatabaseBackend:
    """
    Create a database backend instance based on configuration.

    Args:
        backend_type: Explicit backend type override. If None, reads from
            the AUS_ELE_DB_BACKEND environment variable (default: 'sqlite').

    Returns:
        A DatabaseBackend instance (SQLiteBackend or PostgreSQLBackend).

    Raises:
        ValueError: If the backend type is not supported.
        ConnectionError: If the backend cannot establish a connection
            after retry attempts.
        ImportError: If required dependencies are not installed
            (e.g., psycopg2 for PostgreSQL).
    """
    if backend_type is None:
        backend_type = os.environ.get("AUS_ELE_DB_BACKEND", BACKEND_SQLITE).lower().strip()

    if backend_type not in _SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported database backend: '{backend_type}'. "
            f"Supported backends: {sorted(_SUPPORTED_BACKENDS)}"
        )

    if backend_type == BACKEND_SQLITE:
        return _create_sqlite_backend()
    else:
        return _create_postgresql_backend()


def _create_sqlite_backend() -> DatabaseBackend:
    """Create and return a SQLite backend instance."""
    from db_sqlite_backend import SQLiteBackend

    db_path = os.environ.get(
        "AUS_ELE_DB_PATH",
        str((_REPO_ROOT / "data" / "aemo_data.db").resolve()),
    )
    logger.info("Creating SQLite backend with path: %s", db_path)
    return SQLiteBackend(db_path)


def _create_postgresql_backend() -> DatabaseBackend:
    """Create and return a PostgreSQL backend instance."""
    from db_postgres_backend import PostgreSQLBackend

    logger.info("Creating PostgreSQL backend")
    return PostgreSQLBackend()


@lru_cache(maxsize=1)
def get_backend() -> DatabaseBackend:
    """
    Return the singleton database backend instance.

    This function is intended for use in the dependency injection layer
    (deps.py) to provide a single shared backend across the application.

    The backend type is determined by the AUS_ELE_DB_BACKEND environment
    variable at first call time.
    """
    backend = create_backend()
    logger.info("Database backend singleton created: %s", backend.backend_type)
    return backend
