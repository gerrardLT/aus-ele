"""
Database backend protocol/ABC for the AEMO Intelligence platform.

Defines the interface that all database backends must implement,
enabling the platform to switch between SQLite and PostgreSQL
without modifying business logic.

Requirements: 12.1, 12.2
"""

from __future__ import annotations

import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Generator

logger = logging.getLogger(__name__)


class DatabaseBackend(ABC):
    """
    Abstract base class for database backends.

    All database operations in the platform should go through this interface
    to ensure business logic does not depend on a specific SQL dialect.
    """

    @abstractmethod
    def get_connection(self) -> Generator[Any, None, None]:
        """
        Context manager that yields a database connection.

        The connection object should support:
        - execute(sql, params) -> cursor
        - commit()
        - close()

        Implementations handle connection pooling and lifecycle internally.
        """
        ...

    @abstractmethod
    def execute(self, sql: str, params: tuple = ()) -> list[tuple]:
        """
        Execute a SQL query and return all rows.

        Args:
            sql: SQL statement (use ? placeholders for portability).
            params: Query parameters.

        Returns:
            List of row tuples.
        """
        ...

    @abstractmethod
    def execute_write(self, sql: str, params: tuple = ()) -> int:
        """
        Execute a write (INSERT/UPDATE/DELETE) statement.

        Args:
            sql: SQL statement (use ? placeholders for portability).
            params: Query parameters.

        Returns:
            Number of affected rows.
        """
        ...

    @abstractmethod
    def executemany(self, sql: str, params_list: list[tuple]) -> int:
        """
        Execute a SQL statement with multiple parameter sets (batch write).

        Args:
            sql: SQL statement (use ? placeholders for portability).
            params_list: List of parameter tuples.

        Returns:
            Total number of affected rows.
        """
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the database connection is healthy.

        Returns:
            True if the backend can execute queries, False otherwise.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        Close all connections and release resources.
        """
        ...

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """Return the backend type identifier: 'sqlite' or 'postgresql'."""
        ...
