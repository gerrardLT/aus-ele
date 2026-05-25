"""Check existing WEM data in the database."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "aemo_data.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=" * 70)
print("WEM Data Inventory")
print("=" * 70)

# 1. Check WEM price data (trading_price tables)
print("\n1. WEM Price Data (trading_price_* tables):")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%' ORDER BY name")
tables = cursor.fetchall()
for (table_name,) in tables:
    cursor.execute(f"SELECT COUNT(*), MIN(settlement_date), MAX(settlement_date) FROM {table_name} WHERE region_id='WEM'")
    row = cursor.fetchone()
    if row[0] > 0:
        print(f"  {table_name}: {row[0]:,} rows | {row[1]} → {row[2]}")

# 2. Check WEM ESS market data
print("\n2. WEM ESS Market Data (wem_ess_market_price):")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wem_ess_market_price'")
if cursor.fetchone():
    cursor.execute("SELECT COUNT(*), MIN(dispatch_interval), MAX(dispatch_interval) FROM wem_ess_market_price")
    row = cursor.fetchone()
    print(f"  Rows: {row[0]:,}")
    if row[0] > 0:
        print(f"  Range: {row[1]} → {row[2]}")
    else:
        print("  (empty - no ESS data)")
else:
    print("  Table does not exist")

# 3. Check WEM ESS constraint data
print("\n3. WEM ESS Constraint Data (wem_ess_constraint_summary):")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wem_ess_constraint_summary'")
if cursor.fetchone():
    cursor.execute("SELECT COUNT(*), MIN(dispatch_interval), MAX(dispatch_interval) FROM wem_ess_constraint_summary")
    row = cursor.fetchone()
    print(f"  Rows: {row[0]:,}")
    if row[0] > 0:
        print(f"  Range: {row[1]} → {row[2]}")
    else:
        print("  (empty - no constraint data)")
else:
    print("  Table does not exist")

# 4. Check WEM ESS capability data
print("\n4. WEM ESS Capability Data (wem_ess_capability):")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wem_ess_capability'")
if cursor.fetchone():
    cursor.execute("SELECT COUNT(*) FROM wem_ess_capability")
    row = cursor.fetchone()
    print(f"  Facilities: {row[0]}")
else:
    print("  Table does not exist")

# 5. Check sync state
print("\n5. Sync State:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aemo_source_sync_state'")
if cursor.fetchone():
    cursor.execute("SELECT source_id, last_success_at, sync_status FROM aemo_source_sync_state WHERE source_id LIKE '%wem%'")
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}: status={row[2]}, last_sync={row[1]}")
    else:
        print("  No WEM sync records")
else:
    print("  Table does not exist")

# 6. Database file size
db_size = os.path.getsize(DB_PATH)
print(f"\n6. Database file size: {db_size / 1024 / 1024:.1f} MB")

# 7. Summary of all WEM-related data
print("\n" + "=" * 70)
print("Summary:")
print("=" * 70)
cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
total_tables = cursor.fetchone()[0]
print(f"  Total tables: {total_tables}")

# Count total WEM rows across all price tables
total_wem_price_rows = 0
for (table_name,) in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE region_id='WEM'")
    total_wem_price_rows += cursor.fetchone()[0]
print(f"  Total WEM price rows: {total_wem_price_rows:,}")

conn.close()
