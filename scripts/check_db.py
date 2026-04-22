import sqlite3
from collections import defaultdict


DB_PATH = "aemo_data.db"
TRADING_YEARS = [2025, 2026]
EVENT_TABLES = ["grid_event_raw", "grid_event_state", "grid_event_sync_state"]
FCAS_PRIORITY = [
    "raise1sec_rrp",
    "raise6sec_rrp",
    "raise60sec_rrp",
    "raise5min_rrp",
    "raisereg_rrp",
    "lower1sec_rrp",
    "lower6sec_rrp",
    "lower60sec_rrp",
    "lower5min_rrp",
    "lowerreg_rrp",
]


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone()[0] > 0


def print_header(title):
    print(f"\n=== {title} ===")


def inspect_trading_tables(cursor):
    print_header("Trading Price Tables")

    for year in TRADING_YEARS:
        table_name = f"trading_price_{year}"
        print(f"\n{table_name}:")

        if not table_exists(cursor, table_name):
            print("  status: missing")
            continue

        cursor.execute(f"PRAGMA table_info([{table_name}])")
        cols = [row[1] for row in cursor.fetchall()]
        fcas_cols = [col for col in FCAS_PRIORITY if col in cols]

        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        total_rows = cursor.fetchone()[0]

        print(f"  total_records: {total_rows}")
        print(f"  fcas_columns_present: {fcas_cols if fcas_cols else 'none'}")
        print(f"  missing_priority_fcas_columns: {[col for col in FCAS_PRIORITY if col not in cols]}")

        if not fcas_cols:
            continue

        for fcas_col in fcas_cols:
            cursor.execute(
                f"""
                SELECT COUNT(*), MIN(settlement_date), MAX(settlement_date)
                FROM [{table_name}]
                WHERE [{fcas_col}] IS NOT NULL AND [{fcas_col}] != 0
                """
            )
            count, start_time, end_time = cursor.fetchone()
            print(
                f"  {fcas_col}: records={count}, range={start_time or '-'} ~ {end_time or '-'}"
            )


def inspect_event_tables(cursor):
    print_header("Event Layer Tables")

    for table_name in EVENT_TABLES:
        if not table_exists(cursor, table_name):
            print(f"{table_name}: missing")
            continue

        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        row_count = cursor.fetchone()[0]
        print(f"{table_name}: {row_count}")

    if table_exists(cursor, "grid_event_sync_state"):
        print("\nEvent sync states:")
        cursor.execute(
            """
            SELECT source, last_success_at, last_backfill_at, sync_status
            FROM grid_event_sync_state
            ORDER BY source
            """
        )
        for source, last_success_at, last_backfill_at, sync_status in cursor.fetchall():
            print(
                f"  {source}: status={sync_status}, last_success_at={last_success_at}, "
                f"last_backfill_at={last_backfill_at}"
            )

    if table_exists(cursor, "grid_event_state"):
        print("\nEvent state coverage by market/region:")
        cursor.execute(
            """
            SELECT market, region, COUNT(*) AS state_count
            FROM grid_event_state
            GROUP BY market, region
            ORDER BY market, region
            """
        )
        for market, region, state_count in cursor.fetchall():
            print(f"  {market}/{region}: {state_count}")

        print("\nEvent state type breakdown:")
        cursor.execute(
            """
            SELECT market, region, state_type, COUNT(*) AS state_count
            FROM grid_event_state
            GROUP BY market, region, state_type
            ORDER BY market, region, state_count DESC, state_type
            """
        )
        grouped = defaultdict(list)
        for market, region, state_type, state_count in cursor.fetchall():
            grouped[(market, region)].append((state_type, state_count))

        for (market, region), rows in grouped.items():
            parts = ", ".join(f"{state_type}={state_count}" for state_type, state_count in rows)
            print(f"  {market}/{region}: {parts}")


def inspect_wem_tables(cursor):
    print_header("WEM Slim Tables")

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name LIKE 'wem\\_%' ESCAPE '\\'
        ORDER BY name
        """
    )
    table_names = [row[0] for row in cursor.fetchall()]

    if not table_names:
        print("No WEM tables found.")
        return

    for table_name in table_names:
        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        row_count = cursor.fetchone()[0]
        print(f"  {table_name}: {row_count}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        inspect_trading_tables(cursor)
        inspect_event_tables(cursor)
        inspect_wem_tables(cursor)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
