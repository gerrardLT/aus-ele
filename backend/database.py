import sqlite3
import os
import contextlib
import logging
import json

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

class DatabaseManager:
    WEM_ESS_MARKET_TABLE = "wem_ess_market_price"
    WEM_ESS_CONSTRAINT_TABLE = "wem_ess_constraint_summary"
    WEM_ESS_CAPABILITY_TABLE = "wem_ess_capability"
    GRID_EVENT_RAW_TABLE = "grid_event_raw"
    GRID_EVENT_STATE_TABLE = "grid_event_state"
    GRID_EVENT_SYNC_TABLE = "grid_event_sync_state"
    GRID_FORECAST_SNAPSHOT_TABLE = "grid_forecast_snapshot"
    GRID_FORECAST_SYNC_TABLE = "grid_forecast_sync_state"
    ANALYSIS_CACHE_TABLE = "analysis_cache"

    WEM_ESS_MARKET_COLUMNS = [
        "dispatch_interval",
        "energy_price",
        "regulation_raise_price",
        "regulation_lower_price",
        "contingency_raise_price",
        "contingency_lower_price",
        "rocof_price",
        "available_regulation_raise",
        "available_regulation_lower",
        "available_contingency_raise",
        "available_contingency_lower",
        "available_rocof",
        "in_service_regulation_raise",
        "in_service_regulation_lower",
        "in_service_contingency_raise",
        "in_service_contingency_lower",
        "in_service_rocof",
        "requirement_regulation_raise",
        "requirement_regulation_lower",
        "requirement_contingency_raise",
        "requirement_contingency_lower",
        "requirement_rocof",
        "shortfall_regulation_raise",
        "shortfall_regulation_lower",
        "shortfall_contingency_raise",
        "shortfall_contingency_lower",
        "shortfall_rocof",
        "dispatch_total_regulation_raise",
        "dispatch_total_regulation_lower",
        "dispatch_total_contingency_raise",
        "dispatch_total_contingency_lower",
        "dispatch_total_rocof",
        "capped_regulation_raise",
        "capped_regulation_lower",
        "capped_contingency_raise",
        "capped_contingency_lower",
        "capped_rocof",
    ]

    WEM_ESS_CONSTRAINT_COLUMNS = [
        "dispatch_interval",
        "binding_count",
        "near_binding_count",
        "binding_max_shadow_price",
        "near_binding_max_shadow_price",
        "max_formulation_shadow_price",
        "max_facility_shadow_price",
        "max_network_shadow_price",
        "max_generic_shadow_price",
    ]

    WEM_ESS_CAPABILITY_COLUMNS = [
        "facility_code",
        "participant_code",
        "participant_name",
        "facility_class",
        "max_accredited_regulation_raise",
        "max_accredited_regulation_lower",
        "max_accredited_contingency_raise",
        "max_accredited_contingency_lower",
        "max_accredited_rocof",
        "facility_speed_factor",
        "rocof_ride_through_capability",
        "extracted_at",
    ]

    def __init__(self, db_path: str = "../data/aemo_data.db"):
        self.db_path = db_path
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Enable WAL globally once
        conn = sqlite3.connect(self.db_path)
        try:
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
        finally:
            conn.close()
            
        # Keep track of initialized tables to avoid redundant PRAGMA and CREATE queries
        self.initialized_tables = set()

    @contextlib.contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def ensure_wem_ess_tables(self, conn: sqlite3.Connection):
        """Create slim WEM ESS tables used for the latest rolling month."""
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WEM_ESS_MARKET_TABLE} (
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
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WEM_ESS_CONSTRAINT_TABLE} (
                dispatch_interval TEXT PRIMARY KEY,
                binding_count INTEGER NOT NULL DEFAULT 0,
                near_binding_count INTEGER NOT NULL DEFAULT 0,
                binding_max_shadow_price REAL NOT NULL DEFAULT 0,
                near_binding_max_shadow_price REAL NOT NULL DEFAULT 0,
                max_formulation_shadow_price REAL NOT NULL DEFAULT 0,
                max_facility_shadow_price REAL NOT NULL DEFAULT 0,
                max_network_shadow_price REAL NOT NULL DEFAULT 0,
                max_generic_shadow_price REAL NOT NULL DEFAULT 0
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WEM_ESS_CAPABILITY_TABLE} (
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
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.WEM_ESS_MARKET_TABLE}_interval
            ON {self.WEM_ESS_MARKET_TABLE} (dispatch_interval)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.WEM_ESS_CONSTRAINT_TABLE}_interval
            ON {self.WEM_ESS_CONSTRAINT_TABLE} (dispatch_interval)
        """)
        conn.commit()

    def ensure_event_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.GRID_EVENT_RAW_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                source TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                published_at TEXT,
                effective_start TEXT,
                effective_end TEXT,
                region_scope_json TEXT NOT NULL DEFAULT '[]',
                asset_scope_json TEXT NOT NULL DEFAULT '[]',
                event_class_raw TEXT,
                severity_raw TEXT,
                source_url TEXT,
                raw_payload_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, source_event_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.GRID_EVENT_STATE_TABLE} (
                state_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                region TEXT NOT NULL,
                state_type TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                headline TEXT NOT NULL,
                impact_domains_json TEXT NOT NULL DEFAULT '[]',
                evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
                evidence_summary_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.GRID_EVENT_SYNC_TABLE} (
                source TEXT PRIMARY KEY,
                last_success_at TEXT,
                cursor TEXT,
                last_backfill_at TEXT,
                sync_status TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.GRID_EVENT_RAW_TABLE}_market_time
            ON {self.GRID_EVENT_RAW_TABLE} (market, effective_start, published_at)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.GRID_EVENT_STATE_TABLE}_market_region_time
            ON {self.GRID_EVENT_STATE_TABLE} (market, region, start_time, end_time)
        """)
        conn.commit()

    def ensure_forecast_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.GRID_FORECAST_SNAPSHOT_TABLE} (
                market TEXT NOT NULL,
                region TEXT NOT NULL,
                horizon TEXT NOT NULL,
                as_of_bucket TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                coverage_quality TEXT NOT NULL,
                response_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (market, region, horizon, as_of_bucket)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.GRID_FORECAST_SYNC_TABLE} (
                source TEXT PRIMARY KEY,
                last_success_at TEXT,
                last_attempt_at TEXT,
                sync_status TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{{}}'
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.GRID_FORECAST_SNAPSHOT_TABLE}_lookup
            ON {self.GRID_FORECAST_SNAPSHOT_TABLE} (market, region, horizon, as_of_bucket)
        """)
        conn.commit()

    def ensure_analysis_cache_table(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ANALYSIS_CACHE_TABLE} (
                scope TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                data_version TEXT NOT NULL,
                response_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scope, cache_key, data_version)
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ANALYSIS_CACHE_TABLE}_lookup
            ON {self.ANALYSIS_CACHE_TABLE} (scope, cache_key, data_version)
        """)
        conn.commit()

    def upsert_grid_event_raw(self, records: list[dict]):
        if not records:
            return []

        saved = []
        with self.get_connection() as conn:
            self.ensure_event_tables(conn)
            cursor = conn.cursor()
            for record in records:
                cursor.execute(
                    f"""
                    INSERT INTO {self.GRID_EVENT_RAW_TABLE} (
                        market,
                        source,
                        source_event_id,
                        title,
                        summary,
                        published_at,
                        effective_start,
                        effective_end,
                        region_scope_json,
                        asset_scope_json,
                        event_class_raw,
                        severity_raw,
                        source_url,
                        raw_payload_json,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source, source_event_id) DO UPDATE SET
                        market=excluded.market,
                        title=excluded.title,
                        summary=excluded.summary,
                        published_at=excluded.published_at,
                        effective_start=excluded.effective_start,
                        effective_end=excluded.effective_end,
                        region_scope_json=excluded.region_scope_json,
                        asset_scope_json=excluded.asset_scope_json,
                        event_class_raw=excluded.event_class_raw,
                        severity_raw=excluded.severity_raw,
                        source_url=excluded.source_url,
                        raw_payload_json=excluded.raw_payload_json,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        record["market"],
                        record["source"],
                        record["source_event_id"],
                        record["title"],
                        record.get("summary"),
                        record.get("published_at"),
                        record.get("effective_start"),
                        record.get("effective_end"),
                        json.dumps(record.get("region_scope") or []),
                        json.dumps(record.get("asset_scope") or []),
                        record.get("event_class_raw"),
                        record.get("severity_raw"),
                        record.get("source_url"),
                        json.dumps(record.get("raw_payload_json") or {}),
                    ),
                )
                cursor.execute(
                    f"SELECT id FROM {self.GRID_EVENT_RAW_TABLE} WHERE source = ? AND source_event_id = ?",
                    (record["source"], record["source_event_id"]),
                )
                event_id = cursor.fetchone()[0]
                saved.append({**record, "id": event_id})
            conn.commit()
        return saved

    def replace_grid_event_states(self, market: str, records: list[dict]):
        with self.get_connection() as conn:
            self.ensure_event_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {self.GRID_EVENT_STATE_TABLE} WHERE market = ?",
                (market,),
            )
            if records:
                cursor.executemany(
                    f"""
                    INSERT INTO {self.GRID_EVENT_STATE_TABLE} (
                        state_id,
                        market,
                        region,
                        state_type,
                        start_time,
                        end_time,
                        severity,
                        confidence,
                        headline,
                        impact_domains_json,
                        evidence_event_ids_json,
                        evidence_summary_json,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    [
                        (
                            record["state_id"],
                            record["market"],
                            record["region"],
                            record["state_type"],
                            record["start_time"],
                            record["end_time"],
                            record["severity"],
                            record.get("confidence", 0),
                            record["headline"],
                            json.dumps(record.get("impact_domains") or []),
                            json.dumps(record.get("evidence_event_ids") or []),
                            json.dumps(record.get("evidence_summary_json") or []),
                        )
                        for record in records
                    ],
                )
            conn.commit()
        return len(records)

    def upsert_grid_event_sync_states(self, records: list[dict]):
        if not records:
            return 0

        with self.get_connection() as conn:
            self.ensure_event_tables(conn)
            conn.executemany(
                f"""
                INSERT INTO {self.GRID_EVENT_SYNC_TABLE} (
                    source,
                    last_success_at,
                    cursor,
                    last_backfill_at,
                    sync_status
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_success_at=excluded.last_success_at,
                    cursor=excluded.cursor,
                    last_backfill_at=excluded.last_backfill_at,
                    sync_status=excluded.sync_status
                """,
                [
                    (
                        record["source"],
                        record.get("last_success_at"),
                        record.get("cursor"),
                        record.get("last_backfill_at"),
                        record.get("sync_status", "ok"),
                    )
                    for record in records
                ],
            )
            conn.commit()
        return len(records)

    def fetch_grid_event_sync_states(self) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_event_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT source, last_success_at, cursor, last_backfill_at, sync_status
                FROM {self.GRID_EVENT_SYNC_TABLE}
                ORDER BY source ASC
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "source": row[0],
                "last_success_at": row[1],
                "cursor": row[2],
                "last_backfill_at": row[3],
                "sync_status": row[4],
            }
            for row in rows
        ]

    def upsert_grid_forecast_snapshot(
        self,
        *,
        market: str,
        region: str,
        horizon: str,
        as_of_bucket: str,
        issued_at: str,
        expires_at: str,
        coverage_quality: str,
        response_payload: dict,
    ):
        with self.get_connection() as conn:
            self.ensure_forecast_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.GRID_FORECAST_SNAPSHOT_TABLE} (
                    market,
                    region,
                    horizon,
                    as_of_bucket,
                    issued_at,
                    expires_at,
                    coverage_quality,
                    response_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(market, region, horizon, as_of_bucket) DO UPDATE SET
                    issued_at=excluded.issued_at,
                    expires_at=excluded.expires_at,
                    coverage_quality=excluded.coverage_quality,
                    response_json=excluded.response_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    market,
                    region,
                    horizon,
                    as_of_bucket,
                    issued_at,
                    expires_at,
                    coverage_quality,
                    json.dumps(response_payload or {}),
                ),
            )
            conn.commit()

    def fetch_grid_forecast_snapshot(
        self,
        *,
        market: str,
        region: str,
        horizon: str,
        as_of_bucket: str,
    ) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_forecast_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT market, region, horizon, as_of_bucket, issued_at, expires_at, coverage_quality, response_json
                FROM {self.GRID_FORECAST_SNAPSHOT_TABLE}
                WHERE market = ? AND region = ? AND horizon = ? AND as_of_bucket = ?
                """,
                (market, region, horizon, as_of_bucket),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "market": row[0],
            "region": row[1],
            "horizon": row[2],
            "as_of_bucket": row[3],
            "issued_at": row[4],
            "expires_at": row[5],
            "coverage_quality": row[6],
            "response": json.loads(row[7]),
        }

    def upsert_grid_forecast_sync_state(
        self,
        *,
        source: str,
        last_success_at: str | None,
        last_attempt_at: str | None,
        sync_status: str,
        detail: dict | None = None,
    ):
        with self.get_connection() as conn:
            self.ensure_forecast_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.GRID_FORECAST_SYNC_TABLE} (
                    source,
                    last_success_at,
                    last_attempt_at,
                    sync_status,
                    detail_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_success_at=excluded.last_success_at,
                    last_attempt_at=excluded.last_attempt_at,
                    sync_status=excluded.sync_status,
                    detail_json=excluded.detail_json
                """,
                (
                    source,
                    last_success_at,
                    last_attempt_at,
                    sync_status,
                    json.dumps(detail or {}),
                ),
            )
            conn.commit()

    def upsert_analysis_cache(
        self,
        *,
        scope: str,
        cache_key: str,
        data_version: str,
        response_payload: dict,
    ):
        with self.get_connection() as conn:
            self.ensure_analysis_cache_table(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ANALYSIS_CACHE_TABLE} (
                    scope,
                    cache_key,
                    data_version,
                    response_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scope, cache_key, data_version) DO UPDATE SET
                    response_json=excluded.response_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    scope,
                    cache_key,
                    data_version,
                    json.dumps(response_payload or {}),
                ),
            )
            conn.commit()

    def fetch_analysis_cache(
        self,
        *,
        scope: str,
        cache_key: str,
        data_version: str,
    ) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_analysis_cache_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT response_json
                FROM {self.ANALYSIS_CACHE_TABLE}
                WHERE scope = ? AND cache_key = ? AND data_version = ?
                """,
                (scope, cache_key, data_version),
            )
            row = cursor.fetchone()

        if not row:
            return None
        return json.loads(row[0])

    def batch_upsert_wem_ess_market(self, records: list[dict]):
        if not records:
            return 0

        placeholders = ", ".join(["?"] * len(self.WEM_ESS_MARKET_COLUMNS))
        columns = ", ".join(self.WEM_ESS_MARKET_COLUMNS)
        updates = ", ".join(
            f"{col}=excluded.{col}" for col in self.WEM_ESS_MARKET_COLUMNS[1:]
        )
        rows = [tuple(record.get(col) for col in self.WEM_ESS_MARKET_COLUMNS) for record in records]

        with self.get_connection() as conn:
            self.ensure_wem_ess_tables(conn)
            conn.executemany(f"""
                INSERT INTO {self.WEM_ESS_MARKET_TABLE} ({columns})
                VALUES ({placeholders})
                ON CONFLICT(dispatch_interval) DO UPDATE SET {updates}
            """, rows)
            conn.commit()
        return len(rows)

    def batch_upsert_wem_ess_constraints(self, records: list[dict]):
        if not records:
            return 0

        placeholders = ", ".join(["?"] * len(self.WEM_ESS_CONSTRAINT_COLUMNS))
        columns = ", ".join(self.WEM_ESS_CONSTRAINT_COLUMNS)
        updates = ", ".join(
            f"{col}=excluded.{col}" for col in self.WEM_ESS_CONSTRAINT_COLUMNS[1:]
        )
        rows = [tuple(record.get(col) for col in self.WEM_ESS_CONSTRAINT_COLUMNS) for record in records]

        with self.get_connection() as conn:
            self.ensure_wem_ess_tables(conn)
            conn.executemany(f"""
                INSERT INTO {self.WEM_ESS_CONSTRAINT_TABLE} ({columns})
                VALUES ({placeholders})
                ON CONFLICT(dispatch_interval) DO UPDATE SET {updates}
            """, rows)
            conn.commit()
        return len(rows)

    def replace_wem_ess_capabilities(self, records: list[dict]):
        with self.get_connection() as conn:
            self.ensure_wem_ess_tables(conn)
            conn.execute(f"DELETE FROM {self.WEM_ESS_CAPABILITY_TABLE}")
            if records:
                placeholders = ", ".join(["?"] * len(self.WEM_ESS_CAPABILITY_COLUMNS))
                columns = ", ".join(self.WEM_ESS_CAPABILITY_COLUMNS)
                rows = [tuple(record.get(col) for col in self.WEM_ESS_CAPABILITY_COLUMNS) for record in records]
                conn.executemany(
                    f"INSERT INTO {self.WEM_ESS_CAPABILITY_TABLE} ({columns}) VALUES ({placeholders})",
                    rows,
                )
            conn.commit()
        return len(records)

    def prune_wem_ess_history(self, keep_from: str):
        with self.get_connection() as conn:
            self.ensure_wem_ess_tables(conn)
            conn.execute(
                f"DELETE FROM {self.WEM_ESS_MARKET_TABLE} WHERE dispatch_interval < ?",
                (keep_from,),
            )
            conn.execute(
                f"DELETE FROM {self.WEM_ESS_CONSTRAINT_TABLE} WHERE dispatch_interval < ?",
                (keep_from,),
            )
            conn.commit()

    def get_wem_ess_stats(self) -> dict:
        with self.get_connection() as conn:
            self.ensure_wem_ess_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT COUNT(*), MIN(dispatch_interval), MAX(dispatch_interval) FROM {self.WEM_ESS_MARKET_TABLE}"
            )
            market_count, market_min, market_max = cursor.fetchone()
            cursor.execute(
                f"SELECT COUNT(*), MIN(dispatch_interval), MAX(dispatch_interval) FROM {self.WEM_ESS_CONSTRAINT_TABLE}"
            )
            constraint_count, _, _ = cursor.fetchone()
            cursor.execute(f"SELECT COUNT(*) FROM {self.WEM_ESS_CAPABILITY_TABLE}")
            capability_count = cursor.fetchone()[0]
            return {
                "market_rows": market_count or 0,
                "constraint_rows": constraint_count or 0,
                "capability_rows": capability_count or 0,
                "min_interval": market_min,
                "max_interval": market_max,
            }

    # FCAS price columns that live alongside the energy RRP
    FCAS_COLUMNS = [
        "raise1sec_rrp", "raise6sec_rrp", "raise60sec_rrp", "raise5min_rrp", "raisereg_rrp",
        "lower1sec_rrp", "lower6sec_rrp", "lower60sec_rrp", "lower5min_rrp", "lowerreg_rrp",
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
                raise1sec_rrp REAL,
                raise6sec_rrp REAL,
                raise60sec_rrp REAL,
                raise5min_rrp REAL,
                raisereg_rrp REAL,
                lower1sec_rrp REAL,
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
                    row.get('raise1sec_rrp'),
                    row.get('raise6sec_rrp'),
                    row.get('raise60sec_rrp'),
                    row.get('raise5min_rrp'),
                    row.get('raisereg_rrp'),
                    row.get('lower1sec_rrp'),
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
                             raise1sec_rrp, raise6sec_rrp, raise60sec_rrp, raise5min_rrp, raisereg_rrp,
                             lower1sec_rrp, lower6sec_rrp, lower60sec_rrp, lower5min_rrp, lowerreg_rrp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            self.ensure_wem_ess_tables(conn)
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
            wem_ess = self.get_wem_ess_stats()
            return {"tables": summary_stats, "wem_ess": wem_ess}

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
