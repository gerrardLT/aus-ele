import sqlite3

conn = sqlite3.connect('aemo_data.db')
c = conn.cursor()

for year in [2025, 2026]:
    t = f'trading_price_{year}'
    c.execute(f"PRAGMA table_info([{t}])")
    cols = [r[1] for r in c.fetchall()]
    fcas_cols = [col for col in cols if 'raise' in col.lower() or 'lower' in col.lower()]
    
    total = 0
    fcas_total = 0
    if fcas_cols:
        c.execute(f"SELECT COUNT(*) FROM [{t}]")
        total = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM [{t}] WHERE [{fcas_cols[0]}] IS NOT NULL AND [{fcas_cols[0]}] != 0")
        fcas_total = c.fetchone()[0]
    
    print(f"\n{t}:")
    print(f"  Total records: {total}")
    print(f"  FCAS columns: {fcas_cols}")
    print(f"  FCAS data records: {fcas_total}")
    
    if fcas_cols and fcas_total > 0:
        c.execute(f"SELECT MIN(settlement_date), MAX(settlement_date) FROM [{t}] WHERE [{fcas_cols[0]}] IS NOT NULL AND [{fcas_cols[0]}] != 0")
        row = c.fetchone()
        print(f"  FCAS date range: {row[0]} ~ {row[1]}")

conn.close()
