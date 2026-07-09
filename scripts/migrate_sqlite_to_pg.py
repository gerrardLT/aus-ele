#!/usr/bin/env python3
"""
SQLite to PostgreSQL data migration script.

Reads all tables from a SQLite database and writes them to PostgreSQL.
Supports table structure mapping and data type conversion.

Type mapping:
    TEXT      → VARCHAR
    REAL      → DOUBLE PRECISION
    INTEGER   → BIGINT
    BLOB      → BYTEA
    NUMERIC   → NUMERIC

Usage:
    python scripts/migrate_sqlite_to_pg.py \
        --source-db data/aemo_data.db \
        --target-dsn "postgresql://aemo:pass@localhost:5432/aemo_data"

    # Dry run (show plan without executing):
    python scripts/migrate_sqlite_to_pg.py \
        --source-db data/aemo_data.db \
        --target-dsn "postgresql://aemo:pass@localhost:5432/aemo_data" \
        --dry-run

Requirements: 12.4
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass, field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Batch size for INSERT operations
BATCH_SIZE = 1000

# SQLite → PostgreSQL type mapping
TYPE_MAP: dict[str, str] = {
    "TEXT": "VARCHAR",
    "text": "VARCHAR",
    "INTEGER": "BIGINT",
    "integer": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "real": "DOUBLE PRECISION",
    "BLOB": "BYTEA",
    "blob": "BYTEA",
    "NUMERIC": "NUMERIC",
    "numeric": "NUMERIC",
    "BOOLEAN": "BOOLEAN",
    "boolean": "BOOLEAN",
    "DATETIME": "TIMESTAMP",
    "datetime": "TIMESTAMP",
    "DATE": "DATE",
    "date": "DATE",
    "FLOAT": "DOUBLE PRECISION",
    "float": "DOUBLE PRECISION",
    "VARCHAR": "VARCHAR",
    "varchar": "VARCHAR",
}


@dataclass
class ColumnInfo:
    """Represents a column in a SQLite table."""

    name: str
    sqlite_type: str
    not_null: bool
    default_value: str | None
    is_pk: bool

    @property
    def pg_type(self) -> str:
        """Map SQLite type to PostgreSQL type."""
        raw = self.sqlite_type.strip()
        # Handle parameterized types like VARCHAR(255)
        base_type = raw.split("(")[0].strip().upper()
        mapped = TYPE_MAP.get(base_type)
        if mapped:
            return mapped
        # Fallback: if type contains known keywords
        upper = raw.upper()
        if "INT" in upper:
            return "BIGINT"
        if "CHAR" in upper or "TEXT" in upper or "CLOB" in upper:
            return "VARCHAR"
        if "REAL" in upper or "FLOA" in upper or "DOUB" in upper:
            return "DOUBLE PRECISION"
        if "BLOB" in upper:
            return "BYTEA"
        # Default fallback
        return "VARCHAR"


@dataclass
class TableInfo:
    """Represents a SQLite table schema."""

    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    row_count: int = 0


@dataclass
class MigrationStats:
    """Tracks migration progress and statistics."""

    tables_total: int = 0
    tables_migrated: int = 0
    tables_skipped: int = 0
    tables_failed: int = 0
    rows_total: int = 0
    rows_migrated: int = 0
    start_time: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time if self.start_time else 0.0

    def summary(self) -> str:
        elapsed = self.elapsed_seconds
        return (
            f"Migration complete in {elapsed:.1f}s: "
            f"{self.tables_migrated}/{self.tables_total} tables migrated, "
            f"{self.rows_migrated}/{self.rows_total} rows transferred, "
            f"{self.tables_skipped} skipped, {self.tables_failed} failed"
        )


def get_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    """Get all user table names from SQLite database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_info(conn: sqlite3.Connection, table_name: str) -> TableInfo:
    """Get column information for a SQLite table."""
    cursor = conn.execute(f"PRAGMA table_info([{table_name}])")
    columns = []
    for row in cursor.fetchall():
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        col = ColumnInfo(
            name=row[1],
            sqlite_type=row[2] or "TEXT",
            not_null=bool(row[3]),
            default_value=row[4],
            is_pk=bool(row[5]),
        )
        columns.append(col)

    # Get row count
    count_cursor = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    row_count = count_cursor.fetchone()[0]

    return TableInfo(name=table_name, columns=columns, row_count=row_count)


def generate_create_table_sql(table: TableInfo) -> str:
    """Generate PostgreSQL CREATE TABLE statement from table info."""
    col_defs = []
    pk_columns = []

    for col in table.columns:
        parts = [f'"{col.name}"', col.pg_type]
        if col.not_null:
            parts.append("NOT NULL")
        if col.default_value is not None:
            parts.append(f"DEFAULT {col.default_value}")
        if col.is_pk:
            pk_columns.append(f'"{col.name}"')
        col_defs.append(" ".join(parts))

    if pk_columns:
        col_defs.append(f"PRIMARY KEY ({', '.join(pk_columns)})")

    columns_sql = ",\n    ".join(col_defs)
    return f'CREATE TABLE IF NOT EXISTS "{table.name}" (\n    {columns_sql}\n);'


def generate_insert_sql(table: TableInfo) -> str:
    """Generate PostgreSQL INSERT statement with %s placeholders."""
    col_names = ", ".join(f'"{col.name}"' for col in table.columns)
    placeholders = ", ".join(["%s"] * len(table.columns))
    return f'INSERT INTO "{table.name}" ({col_names}) VALUES ({placeholders})'


def _pg_table_exists(pg_cursor, table_name: str) -> bool:
    """Check if a table already exists in PostgreSQL."""
    pg_cursor.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s",
        (table_name,),
    )
    return pg_cursor.fetchone() is not None


def _pg_get_columns(pg_cursor, table_name: str) -> list[str]:
    """Get column names of an existing PG table in ordinal position order."""
    pg_cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s "
        "ORDER BY ordinal_position",
        (table_name,),
    )
    return [row[0] for row in pg_cursor.fetchall()]


def _coerce_row(row: tuple, col_pg_types: list[str]) -> tuple:
    """Coerce SQLite row values to PG-compatible types.

    Handles:
    - TEXT dates (ISO 8601) → datetime for TIMESTAMP columns
    - Boolean ints → bool
    - None stays None
    """
    from datetime import datetime as _dt

    coerced = []
    for val, pg_type in zip(row, col_pg_types):
        if val is None:
            coerced.append(None)
            continue
        upper = pg_type.upper()
        # ISO date/datetime text → datetime object for TIMESTAMP columns
        if "TIMESTAMP" in upper and isinstance(val, str):
            try:
                coerced.append(_dt.fromisoformat(val.replace("Z", "+00:00")))
            except (ValueError, TypeError):
                coerced.append(val)
        elif upper == "DATE" and isinstance(val, str):
            try:
                coerced.append(_dt.fromisoformat(val).date())
            except (ValueError, TypeError):
                coerced.append(val)
        elif upper == "BOOLEAN" and isinstance(val, int):
            coerced.append(bool(val))
        else:
            coerced.append(val)
    return tuple(coerced)


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    table: TableInfo,
    dry_run: bool,
    stats: MigrationStats,
) -> bool:
    """
    Migrate a single table from SQLite to PostgreSQL.

    Strategy:
    - If table already exists in PG (created by server with proper schema):
      TRUNCATE + INSERT using the existing PG column order.
    - If table doesn't exist in PG:
      CREATE TABLE (inferred from SQLite schema) + INSERT.

    Returns True on success, False on failure.
    """
    table_start = time.time()
    logger.info(
        "  [%d/%d] Migrating table '%s' (%d rows, %d columns)...",
        stats.tables_migrated + stats.tables_failed + stats.tables_skipped + 1,
        stats.tables_total,
        table.name,
        table.row_count,
        len(table.columns),
    )

    if dry_run:
        create_sql = generate_create_table_sql(table)
        logger.info("    [DRY RUN] Would execute:\n%s", create_sql)
        logger.info("    [DRY RUN] Would insert %d rows", table.row_count)
        stats.tables_migrated += 1
        stats.rows_migrated += table.row_count
        return True

    try:
        pg_cursor = pg_conn.cursor()

        # Decide whether to use existing PG schema or create new table
        use_existing_schema = _pg_table_exists(pg_cursor, table.name)

        if use_existing_schema:
            logger.info("    Table '%s' already exists in PG, using existing schema", table.name)
            # TRUNCATE existing data
            pg_cursor.execute(f'TRUNCATE TABLE "{table.name}" CASCADE')
            pg_cols = _pg_get_columns(pg_cursor, table.name)
            # Build INSERT using existing PG column order
            col_names = ", ".join(f'"{c}"' for c in pg_cols)
            placeholders = ", ".join(["%s"] * len(pg_cols))
            insert_sql = f'INSERT INTO "{table.name}" ({col_names}) VALUES ({placeholders})'
            # Build column type list for coercion
            pg_cursor.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "ORDER BY ordinal_position",
                (table.name,),
            )
            col_pg_types = [row[0] for row in pg_cursor.fetchall()]
            # Map PG col names → SQLite col positions (by name match)
            sqlite_col_map = {c.name: i for i, c in enumerate(table.columns)}
            col_indices = [sqlite_col_map.get(c) for c in pg_cols]
            # Detect missing columns
            missing = [c for c, idx in zip(pg_cols, col_indices) if idx is None]
            if missing:
                logger.warning(
                    "    PG table has columns not in SQLite: %s — will insert NULL",
                    missing,
                )
        else:
            # Create new table with schema inferred from SQLite
            create_sql = generate_create_table_sql(table)
            pg_cursor.execute(create_sql)
            pg_cols = [c.name for c in table.columns]
            col_pg_types = [c.pg_type for c in table.columns]
            col_indices = list(range(len(table.columns)))
            insert_sql = generate_insert_sql(table)

        if table.row_count == 0:
            pg_conn.commit()
            logger.info("    Table '%s' handled (empty, no data to transfer)", table.name)
            stats.tables_migrated += 1
            return True

        # Read and insert data in batches
        sqlite_cursor = sqlite_conn.execute(f"SELECT * FROM [{table.name}]")

        rows_inserted = 0
        while True:
            batch = sqlite_cursor.fetchmany(BATCH_SIZE)
            if not batch:
                break

            # Reorder + coerce each row
            coerced_batch = []
            for row in batch:
                reordered = tuple(
                    row[idx] if idx is not None else None for idx in col_indices
                )
                coerced_batch.append(_coerce_row(reordered, col_pg_types))

            pg_cursor.executemany(insert_sql, coerced_batch)
            rows_inserted += len(batch)

            # Progress reporting for large tables
            if table.row_count > BATCH_SIZE:
                pct = (rows_inserted / table.row_count) * 100
                logger.info(
                    "    Progress: %d/%d rows (%.1f%%)",
                    rows_inserted,
                    table.row_count,
                    pct,
                )

        pg_conn.commit()
        elapsed = time.time() - table_start
        rate = rows_inserted / elapsed if elapsed > 0 else 0
        logger.info(
            "    Table '%s' migrated: %d rows in %.1fs (%.0f rows/s)",
            table.name,
            rows_inserted,
            elapsed,
            rate,
        )
        stats.tables_migrated += 1
        stats.rows_migrated += rows_inserted
        return True

    except Exception as exc:
        pg_conn.rollback()
        logger.error("    FAILED to migrate table '%s': %s", table.name, exc)
        stats.tables_failed += 1
        return False


def run_migration(source_db: str, target_dsn: str, dry_run: bool) -> MigrationStats:
    """
    Execute the full SQLite → PostgreSQL migration.

    Args:
        source_db: Path to the SQLite database file.
        target_dsn: PostgreSQL connection string (DSN).
        dry_run: If True, show plan without executing writes.

    Returns:
        MigrationStats with final counts.
    """
    stats = MigrationStats(start_time=time.time())

    # Connect to SQLite
    logger.info("Connecting to SQLite database: %s", source_db)
    sqlite_conn = sqlite3.connect(source_db)
    sqlite_conn.row_factory = None  # Return plain tuples

    # Get all tables
    table_names = get_sqlite_tables(sqlite_conn)
    stats.tables_total = len(table_names)
    logger.info("Found %d tables to migrate", stats.tables_total)

    if stats.tables_total == 0:
        logger.warning("No tables found in source database. Nothing to migrate.")
        sqlite_conn.close()
        return stats

    # Gather table metadata
    tables: list[TableInfo] = []
    for name in table_names:
        info = get_table_info(sqlite_conn, name)
        tables.append(info)
        stats.rows_total += info.row_count

    logger.info("Total rows to migrate: %d", stats.rows_total)
    logger.info("")

    # Print migration plan
    logger.info("Migration plan:")
    for t in tables:
        col_summary = ", ".join(
            f"{c.name}({c.sqlite_type} -> {c.pg_type})" for c in t.columns[:5]
        )
        if len(t.columns) > 5:
            col_summary += f", ... (+{len(t.columns) - 5} more)"
        logger.info("  %s: %d rows [%s]", t.name, t.row_count, col_summary)
    logger.info("")

    if dry_run:
        logger.info("[DRY RUN MODE] No changes will be made to PostgreSQL.")
        logger.info("")

    # Connect to PostgreSQL
    pg_conn = None
    if not dry_run:
        try:
            import psycopg2

            logger.info("Connecting to PostgreSQL: %s", _mask_dsn(target_dsn))
            pg_conn = psycopg2.connect(target_dsn)
            logger.info("PostgreSQL connection established")
        except ImportError:
            logger.error(
                "psycopg2 is required for PostgreSQL migration. "
                "Install with: pip install psycopg2-binary"
            )
            sqlite_conn.close()
            sys.exit(1)
        except Exception as exc:
            logger.error("Failed to connect to PostgreSQL: %s", exc)
            sqlite_conn.close()
            sys.exit(1)

    # Migrate each table
    logger.info("Starting migration...")
    for table in tables:
        if table.row_count == 0 and len(table.columns) == 0:
            logger.info("  Skipping empty schema table: %s", table.name)
            stats.tables_skipped += 1
            continue

        migrate_table(sqlite_conn, pg_conn, table, dry_run, stats)

    # Cleanup
    sqlite_conn.close()
    if pg_conn is not None:
        pg_conn.close()

    logger.info("")
    logger.info(stats.summary())
    return stats


def _mask_dsn(dsn: str) -> str:
    """Mask password in DSN for safe logging."""
    # Handle postgresql://user:password@host format
    if "://" in dsn and "@" in dsn:
        prefix, rest = dsn.split("://", 1)
        if "@" in rest:
            userinfo, hostinfo = rest.rsplit("@", 1)
            if ":" in userinfo:
                user, _ = userinfo.split(":", 1)
                return f"{prefix}://{user}:***@{hostinfo}"
    # Handle key=value format (password=xxx)
    if "password=" in dsn.lower():
        parts = dsn.split()
        masked_parts = []
        for part in parts:
            if part.lower().startswith("password="):
                masked_parts.append("password=***")
            else:
                masked_parts.append(part)
        return " ".join(masked_parts)
    return dsn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --source-db data/aemo_data.db "
            '--target-dsn "postgresql://aemo:pass@localhost:5432/aemo_data"\n'
            "\n"
            "  %(prog)s --source-db data/aemo_data.db "
            '--target-dsn "postgresql://aemo:pass@localhost:5432/aemo_data" '
            "--dry-run\n"
        ),
    )
    parser.add_argument(
        "--source-db",
        required=True,
        help="Path to the source SQLite database file",
    )
    parser.add_argument(
        "--target-dsn",
        required=True,
        help=(
            "PostgreSQL connection string (DSN). "
            'Example: "postgresql://user:pass@host:5432/dbname"'
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show migration plan without executing any changes",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Number of rows per INSERT batch (default: {BATCH_SIZE})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose (DEBUG) logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    global BATCH_SIZE
    BATCH_SIZE = args.batch_size

    logger.info("=" * 60)
    logger.info("SQLite → PostgreSQL Migration")
    logger.info("=" * 60)
    logger.info("Source: %s", args.source_db)
    logger.info("Target: %s", _mask_dsn(args.target_dsn))
    logger.info("Dry run: %s", args.dry_run)
    logger.info("Batch size: %d", BATCH_SIZE)
    logger.info("")

    stats = run_migration(args.source_db, args.target_dsn, args.dry_run)

    if stats.tables_failed > 0:
        logger.warning(
            "%d table(s) failed to migrate. Check logs above for details.",
            stats.tables_failed,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
