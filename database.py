import sqlite3
import os
import contextlib
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "aemo_data.db"):
        self.db_path = db_path
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Enable WAL globally once
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_status (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()
            
        # Keep track of initialized tables to avoid redundant PRAGMA and CREATE queries
        self.initialized_tables = set()

    @contextlib.contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_table_exists(self, year: int, conn: sqlite3.Connection):
        """Dynamic table sharding: create a table for a specific year if it doesn't exist."""
        table_name = f"trading_price_{year}"
        if table_name in self.initialized_tables:
            return table_name

        cursor = conn.cursor()
        
        # Create table. Note that we use a composite UNIQUE constraint to avoid duplicate inserts 
        # for exactly the same 5-minute/30-minute block.
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL,
                UNIQUE(settlement_date, region_id)
            )
        """)
        
        # Create index on region_id and settlement_date for fast querying
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_search 
            ON {table_name} (region_id, settlement_date)
        """)
        
        conn.commit()
        self.initialized_tables.add(table_name)
        return table_name

    def batch_insert(self, records: list[dict]):
        """
        Groups records by year, creates necessary tables, and bulk inserts them.
        Uses INSERT OR IGNORE to gracefully handle duplicates (re-runs).
        Records expected: [{'settlement_date': '2025/01/01 00:05:00', 'region_id': 'NSW1', 'rrp_aud_mwh': 50.5}, ...]
        """
        if not records:
            return

        # Group by year based on the settlement_date string (AEMO format is usually 'YYYY/MM/DD HH:MM:SS')
        by_year = {}
        for row in records:
            # Assuming format 'YYYY/MM/DD...' or 'YYYY-MM-DD...'
            # Extract the first 4 characters for the year
            year_str = str(row['settlement_date'])[:4]
            if not year_str.isdigit():
                continue
            year = int(year_str)
            if year not in by_year:
                by_year[year] = []
            
            # Reformat settlement_date to ISO-8601 string so Lexical sorting in SQLite works correctly: 'YYYY-MM-DD HH:MM:SS'
            raw_date = row['settlement_date']
            # Sometimes parsing '2025/01/01 00:05:00' to '2025-01-01 00:05:00'
            iso_date = raw_date.replace('/', '-') 
            
            by_year[year].append((
                iso_date,
                row['region_id'],
                row['rrp_aud_mwh']
            ))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Begin a transaction
                cursor.execute("BEGIN TRANSACTION")
                
                for year, rows in by_year.items():
                    table_name = self._ensure_table_exists(year, conn)
                    # Use execute many for high performance
                    cursor.executemany(f"""
                        INSERT OR IGNORE INTO {table_name} (settlement_date, region_id, rrp_aud_mwh)
                        VALUES (?, ?, ?)
                    """, rows)
                    
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Database insertion error: {e}")
                raise

    def get_summary(self) -> dict:
        """Fetch summary data for dashboard across all tables"""
        # Read the sqlite_master to find all dynamic tables
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%'")
            tables = [r[0] for r in cursor.fetchall()]
            
            if not tables:
                return {"status": "empty"}
                
            summary_stats = []
            for t in tables:
                cursor.execute(f"SELECT MIN(settlement_date), MAX(settlement_date), COUNT(*) FROM {t}")
                res = cursor.fetchone()
                if res and res[2] > 0:
                     summary_stats.append({
                         "table": t,
                         "min_date": res[0],
                         "max_date": res[1],
                         "count": res[2]
                     })
            return {"tables": summary_stats}

    def set_last_update_time(self, timestamp_str: str):
        """Record the physical time when the latest sync was completed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_status (key, value) 
                VALUES ('last_update', ?) 
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (timestamp_str,))
            conn.commit()

    def get_last_update_time(self) -> str:
        """Fetch the physical time of the latest sync."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_status WHERE key='last_update'")
            row = cursor.fetchone()
            return row[0] if row else None
