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

    # FCAS price columns that live alongside the energy RRP
    FCAS_COLUMNS = [
        "raise6sec_rrp", "raise60sec_rrp", "raise5min_rrp", "raisereg_rrp",
        "lower6sec_rrp", "lower60sec_rrp", "lower5min_rrp", "lowerreg_rrp",
    ]

    def _ensure_table_exists(self, year: int, conn: sqlite3.Connection):
        """Dynamic table sharding: create a table for a specific year if it doesn't exist."""
        table_name = f"trading_price_{year}"
        if table_name in self.initialized_tables:
            return table_name

        cursor = conn.cursor()
        
        # Create table with energy RRP + 8 FCAS price columns.
        # FCAS columns are nullable – they'll be NULL for WEM data and
        # for any NEM data that was imported before this schema upgrade.
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL,
                raise6sec_rrp REAL,
                raise60sec_rrp REAL,
                raise5min_rrp REAL,
                raisereg_rrp REAL,
                lower6sec_rrp REAL,
                lower60sec_rrp REAL,
                lower5min_rrp REAL,
                lowerreg_rrp REAL,
                UNIQUE(settlement_date, region_id)
            )
        """)
        
        # Migrate existing tables that were created before FCAS columns existed.
        # SQLite ignores ALTER TABLE ADD COLUMN if the column already exists (raises error),
        # so we catch and skip gracefully.
        self._migrate_fcas_columns(table_name, cursor)
        
        # Create index on region_id and settlement_date for fast querying
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_search 
            ON {table_name} (region_id, settlement_date)
        """)
        
        conn.commit()
        self.initialized_tables.add(table_name)
        return table_name

    def _migrate_fcas_columns(self, table_name: str, cursor):
        """Add FCAS columns to an existing table if they don't already exist."""
        # Get current columns
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        for col in self.FCAS_COLUMNS:
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} REAL")
                    logger.info(f"Migrated: added column {col} to {table_name}")
                except sqlite3.OperationalError:
                    pass  # Column already exists

    def batch_insert(self, records: list[dict]):
        """
        Groups records by year, creates necessary tables, and bulk inserts them.
        Uses INSERT OR REPLACE to update existing records with new FCAS data.
        Records expected: [{'settlement_date': '...', 'region_id': 'NSW1', 'rrp_aud_mwh': 50.5, ...fcas fields...}, ...]
        """
        if not records:
            return

        # Check if any record has FCAS data
        has_fcas = any(row.get('raise6sec_rrp') is not None for row in records)

        # Group by year based on the settlement_date string
        by_year = {}
        for row in records:
            year_str = str(row['settlement_date'])[:4]
            if not year_str.isdigit():
                continue
            year = int(year_str)
            if year not in by_year:
                by_year[year] = []
            
            # Reformat settlement_date to ISO-8601
            raw_date = row['settlement_date']
            iso_date = raw_date.replace('/', '-') 
            
            if has_fcas:
                by_year[year].append((
                    iso_date,
                    row['region_id'],
                    row['rrp_aud_mwh'],
                    row.get('raise6sec_rrp'),
                    row.get('raise60sec_rrp'),
                    row.get('raise5min_rrp'),
                    row.get('raisereg_rrp'),
                    row.get('lower6sec_rrp'),
                    row.get('lower60sec_rrp'),
                    row.get('lower5min_rrp'),
                    row.get('lowerreg_rrp'),
                ))
            else:
                by_year[year].append((
                    iso_date,
                    row['region_id'],
                    row['rrp_aud_mwh']
                ))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                for year, rows in by_year.items():
                    table_name = self._ensure_table_exists(year, conn)
                    if has_fcas:
                        # INSERT OR REPLACE: if the (settlement_date, region_id) already exists,
                        # replace the row so FCAS data overwrites the old energy-only record.
                        cursor.executemany(f"""
                            INSERT OR REPLACE INTO {table_name}
                            (settlement_date, region_id, rrp_aud_mwh,
                             raise6sec_rrp, raise60sec_rrp, raise5min_rrp, raisereg_rrp,
                             lower6sec_rrp, lower60sec_rrp, lower5min_rrp, lowerreg_rrp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, rows)
                    else:
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
