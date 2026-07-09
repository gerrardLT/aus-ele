#!/usr/bin/env python3
"""
将 PostgreSQL 中的 WEM 数据同步到 SQLite（供当前 API 路由使用）。
当前 API 路由通过 DatabaseManager 读取 SQLite，而 WEM 数据已导入 PG。
本脚本桥接两者。

用法：
    python3 wem_pg_to_sqlite.py
    python3 wem_pg_to_sqlite.py --pg-host postgres --pg-port 5432
"""
import argparse
import io
import os
import sqlite3
import sys

def main():
    parser = argparse.ArgumentParser(description="WEM 数据 PG → SQLite 同步")
    parser.add_argument("--pg-host", default="localhost", help="PG 主机")
    parser.add_argument("--pg-port", type=int, default=5432, help="PG 端口")
    parser.add_argument("--pg-password", default="aemo_pg_pass_2026", help="PG 密码")
    parser.add_argument("--sqlite-db", default="/app/data/aemo_data.db", help="SQLite 路径")
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
        import psycopg2

    dsn = f"postgresql://aemo:{args.pg_password}@{args.pg_host}:{args.pg_port}/aemo_data"
    print(f"连接 PG: {args.pg_host}:{args.pg_port}")
    pg = psycopg2.connect(dsn)
    pg_cur = pg.cursor()

    sq = sqlite3.connect(args.sqlite_db)
    sq_cur = sq.cursor()
    print(f"连接 SQLite: {args.sqlite_db}")

    # ── 1. wem_ess_capabilities → wem_ess_capability ──
    # 注意：PG 表名 wem_ess_capabilities (复数)，SQLite 表名 wem_ess_capability (单数)
    pg_cur.execute("SELECT count(*) FROM wem_ess_capabilities")
    cap_count = pg_cur.fetchone()[0]
    print(f"\n═══ FCAS 能力: {cap_count} 行 ═══")

    sq_cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_capability (
            facility_code TEXT PRIMARY KEY,
            participant_code TEXT,
            participant_name TEXT,
            facility_class TEXT,
            max_accredited_regulation_raise REAL,
            max_accredited_regulation_lower REAL,
            max_accredited_contingency_raise REAL,
            max_accredited_contingency_lower REAL,
            max_accredited_rocof REAL,
            facility_speed_factor REAL,
            rocof_ride_through_capability REAL,
            extracted_at TEXT
        )
    """)

    pg_cur.execute("SELECT * FROM wem_ess_capabilities")
    rows = pg_cur.fetchall()
    if rows:
        placeholders = ",".join(["?"] * len(rows[0]))
        sq_cur.executemany(
            f"INSERT OR REPLACE INTO wem_ess_capability VALUES ({placeholders})",
            rows,
        )
        print(f"  ✓ 写入 {len(rows)} 行")
    sq.commit()

    # ── 2. wem_ess_market_price ──
    pg_cur.execute("SELECT count(*) FROM wem_ess_market_price")
    mkt_count = pg_cur.fetchone()[0]
    print(f"\n═══ 调度方案 market_price: {mkt_count} 行 ═══")

    sq_cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_market_price (
            dispatch_interval TEXT PRIMARY KEY,
            energy_price REAL,
            regulation_raise_price REAL,
            regulation_lower_price REAL,
            contingency_raise_price REAL,
            contingency_lower_price REAL,
            rocof_price REAL,
            available_regulation_raise REAL,
            available_regulation_lower REAL,
            available_contingency_raise REAL,
            available_contingency_lower REAL,
            available_rocof REAL,
            in_service_regulation_raise REAL,
            in_service_regulation_lower REAL,
            in_service_contingency_raise REAL,
            in_service_contingency_lower REAL,
            in_service_rocof REAL,
            requirement_regulation_raise REAL,
            requirement_regulation_lower REAL,
            requirement_contingency_raise REAL,
            requirement_contingency_lower REAL,
            requirement_rocof REAL,
            shortfall_regulation_raise REAL,
            shortfall_regulation_lower REAL,
            shortfall_contingency_raise REAL,
            shortfall_contingency_lower REAL,
            shortfall_rocof REAL,
            dispatch_total_regulation_raise REAL,
            dispatch_total_regulation_lower REAL,
            dispatch_total_contingency_raise REAL,
            dispatch_total_contingency_lower REAL,
            dispatch_total_rocof REAL,
            capped_regulation_raise INTEGER DEFAULT 0,
            capped_regulation_lower INTEGER DEFAULT 0,
            capped_contingency_raise INTEGER DEFAULT 0,
            capped_contingency_lower INTEGER DEFAULT 0,
            capped_rocof INTEGER DEFAULT 0
        )
    """)

    pg_cur.execute("SELECT * FROM wem_ess_market_price ORDER BY dispatch_interval")
    rows = pg_cur.fetchall()
    if rows:
        placeholders = ",".join(["?"] * len(rows[0]))
        # 分批写入避免内存问题
        batch = 10000
        for i in range(0, len(rows), batch):
            sq_cur.executemany(
                f"INSERT OR REPLACE INTO wem_ess_market_price VALUES ({placeholders})",
                rows[i:i+batch],
            )
        print(f"  ✓ 写入 {len(rows)} 行")
    sq.commit()

    # ── 3. wem_ess_constraint_summary ──
    pg_cur.execute("SELECT count(*) FROM wem_ess_constraint_summary")
    cst_count = pg_cur.fetchone()[0]
    print(f"\n═══ 调度方案 constraint: {cst_count} 行 ═══")

    sq_cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_constraint_summary (
            dispatch_interval TEXT PRIMARY KEY,
            binding_count INTEGER DEFAULT 0,
            near_binding_count INTEGER DEFAULT 0,
            binding_max_shadow_price REAL DEFAULT 0,
            near_binding_max_shadow_price REAL DEFAULT 0,
            max_formulation_shadow_price REAL DEFAULT 0,
            max_facility_shadow_price REAL DEFAULT 0,
            max_network_shadow_price REAL DEFAULT 0,
            max_generic_shadow_price REAL DEFAULT 0
        )
    """)

    pg_cur.execute("SELECT * FROM wem_ess_constraint_summary ORDER BY dispatch_interval")
    rows = pg_cur.fetchall()
    if rows:
        placeholders = ",".join(["?"] * len(rows[0]))
        for i in range(0, len(rows), batch):
            sq_cur.executemany(
                f"INSERT OR REPLACE INTO wem_ess_constraint_summary VALUES ({placeholders})",
                rows[i:i+batch],
            )
        print(f"  ✓ 写入 {len(rows)} 行")
    sq.commit()

    # ── 4. trading_price_YYYY ──
    pg_cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE tablename LIKE 'trading_price_%'
        ORDER BY tablename
    """)
    tables = [r[0] for r in pg_cur.fetchall()]
    print(f"\n═══ 交易电价表: {tables} ═══")

    for tbl in tables:
        pg_cur.execute(f"SELECT count(*) FROM {tbl}")
        cnt = pg_cur.fetchone()[0]
        print(f"  {tbl}: {cnt} 行")

        sq_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {tbl} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL,
                raise1sec_rrp REAL, raise6sec_rrp REAL,
                raise60sec_rrp REAL, raise5min_rrp REAL, raisereg_rrp REAL,
                lower1sec_rrp REAL, lower6sec_rrp REAL,
                lower60sec_rrp REAL, lower5min_rrp REAL, lowerreg_rrp REAL,
                UNIQUE(settlement_date, region_id)
            )
        """)

        pg_cur.execute(f"SELECT settlement_date, region_id, rrp_aud_mwh FROM {tbl}")
        rows = pg_cur.fetchall()
        if rows:
            for i in range(0, len(rows), batch):
                sq_cur.executemany(
                    f"INSERT OR REPLACE INTO {tbl} (settlement_date, region_id, rrp_aud_mwh) VALUES (?, ?, ?)",
                    rows[i:i+batch],
                )
            print(f"    ✓ 写入 {len(rows)} 行")
    sq.commit()

    # ── 最终统计 ──
    print("\n" + "=" * 60)
    print("同步完成！SQLite 数据统计：")
    for tbl in ["wem_ess_capability", "wem_ess_market_price", "wem_ess_constraint_summary"]:
        sq_cur.execute(f"SELECT count(*) FROM {tbl}")
        print(f"  {tbl}: {sq_cur.fetchone()[0]} 行")
    for tbl in tables:
        sq_cur.execute(f"SELECT count(*) FROM {tbl}")
        print(f"  {tbl}: {sq_cur.fetchone()[0]} 行")
    print("=" * 60)

    pg.close()
    sq.close()


if __name__ == "__main__":
    main()
