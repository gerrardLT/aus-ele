import sqlite3
import os
import contextlib
import logging
import json
from datetime import datetime, timedelta, timezone

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
    FINGRID_DATASET_TABLE = "fingrid_dataset_catalog"
    FINGRID_TIMESERIES_TABLE = "fingrid_timeseries"
    FINGRID_SYNC_STATE_TABLE = "fingrid_sync_state"
    DATA_QUALITY_SNAPSHOT_TABLE = "data_quality_snapshot"
    DATA_QUALITY_ISSUE_TABLE = "data_quality_issue"
    ALERT_RULE_TABLE = "alert_rule"
    ALERT_STATE_TABLE = "alert_state"
    ALERT_DELIVERY_LOG_TABLE = "alert_delivery_log"
    JOB_TABLE = "job_run"
    JOB_EVENT_TABLE = "job_event_log"
    API_CLIENT_TABLE = "external_api_client"
    API_USAGE_TABLE = "external_api_usage"
    ORGANIZATION_TABLE = "organization"
    WORKSPACE_TABLE = "workspace"
    PRINCIPAL_TABLE = "principal_identity"
    AUTH_IDENTITY_TABLE = "auth_identity"
    ORGANIZATION_MEMBERSHIP_TABLE = "organization_membership"
    WORKSPACE_MEMBERSHIP_TABLE = "workspace_membership"
    ACCESS_TOKEN_TABLE = "access_token"
    AUTH_SESSION_TABLE = "auth_session"
    AUDIT_LOG_TABLE = "audit_log"
    WORKSPACE_POLICY_TABLE = "workspace_policy"
    WORKSPACE_INVITE_TABLE = "workspace_invite"
    MEMBERSHIP_INVITE_TABLE = "membership_invite"
    OIDC_PROVIDER_TABLE = "oidc_provider"
    ORGANIZATION_DOMAIN_TABLE = "organization_domain"

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
                organization_id TEXT,
                workspace_id TEXT,
                response_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scope, cache_key, data_version, organization_id, workspace_id)
            )
        """)
        columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.ANALYSIS_CACHE_TABLE})").fetchall()}
        if "organization_id" not in columns:
            cursor.execute(f"ALTER TABLE {self.ANALYSIS_CACHE_TABLE} ADD COLUMN organization_id TEXT")
        if "workspace_id" not in columns:
            cursor.execute(f"ALTER TABLE {self.ANALYSIS_CACHE_TABLE} ADD COLUMN workspace_id TEXT")
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ANALYSIS_CACHE_TABLE}_lookup
            ON {self.ANALYSIS_CACHE_TABLE} (scope, cache_key, data_version, organization_id, workspace_id)
        """)
        conn.commit()

    def ensure_fingrid_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_DATASET_TABLE} (
                dataset_id TEXT PRIMARY KEY,
                dataset_code TEXT,
                name TEXT NOT NULL,
                description TEXT,
                unit TEXT NOT NULL,
                frequency TEXT NOT NULL,
                timezone TEXT NOT NULL,
                value_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_TIMESERIES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                series_key TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                timestamp_local TEXT NOT NULL,
                value REAL,
                unit TEXT NOT NULL,
                quality_flag TEXT,
                source_updated_at TEXT,
                ingested_at TEXT NOT NULL,
                extra_json TEXT NOT NULL DEFAULT '{{}}',
                UNIQUE(dataset_id, series_key, timestamp_utc)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_SYNC_STATE_TABLE} (
                dataset_id TEXT PRIMARY KEY,
                last_success_at TEXT,
                last_attempt_at TEXT,
                last_cursor TEXT,
                last_synced_timestamp_utc TEXT,
                sync_status TEXT NOT NULL,
                last_error TEXT,
                backfill_started_at TEXT,
                backfill_completed_at TEXT
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.FINGRID_TIMESERIES_TABLE}_dataset_time
            ON {self.FINGRID_TIMESERIES_TABLE} (dataset_id, timestamp_utc)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.FINGRID_TIMESERIES_TABLE}_dataset_series_time
            ON {self.FINGRID_TIMESERIES_TABLE} (dataset_id, series_key, timestamp_utc)
        """)
        conn.commit()

    def ensure_data_quality_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.DATA_QUALITY_SNAPSHOT_TABLE} (
                scope TEXT NOT NULL,
                market TEXT NOT NULL,
                dataset_key TEXT NOT NULL,
                data_grade TEXT NOT NULL,
                quality_score REAL,
                coverage_ratio REAL,
                freshness_minutes REAL,
                issues_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                computed_at TEXT NOT NULL,
                PRIMARY KEY (scope, market, dataset_key)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.DATA_QUALITY_ISSUE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                market TEXT NOT NULL,
                dataset_key TEXT NOT NULL,
                issue_code TEXT NOT NULL,
                severity TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{{}}',
                detected_at TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.DATA_QUALITY_ISSUE_TABLE}_market_lookup
            ON {self.DATA_QUALITY_ISSUE_TABLE} (scope, market, dataset_key, issue_code)
        """)
        conn.commit()

    def ensure_alert_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ALERT_RULE_TABLE} (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                market TEXT NOT NULL,
                region_or_zone TEXT,
                config_json TEXT NOT NULL DEFAULT '{{}}',
                channel_type TEXT NOT NULL,
                channel_target TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                organization_id TEXT,
                workspace_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ALERT_STATE_TABLE} (
                rule_id TEXT PRIMARY KEY,
                current_status TEXT NOT NULL,
                last_evaluated_at TEXT,
                last_triggered_at TEXT,
                last_delivery_at TEXT,
                organization_id TEXT,
                workspace_id TEXT,
                last_value_json TEXT NOT NULL DEFAULT '{{}}',
                FOREIGN KEY(rule_id) REFERENCES {self.ALERT_RULE_TABLE}(rule_id),
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ALERT_DELIVERY_LOG_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                target TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}',
                response_code INTEGER,
                response_text TEXT,
                organization_id TEXT,
                workspace_id TEXT,
                delivered_at TEXT NOT NULL,
                FOREIGN KEY(rule_id) REFERENCES {self.ALERT_RULE_TABLE}(rule_id),
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        rule_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.ALERT_RULE_TABLE})").fetchall()}
        if "organization_id" not in rule_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_RULE_TABLE} ADD COLUMN organization_id TEXT")
        if "workspace_id" not in rule_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_RULE_TABLE} ADD COLUMN workspace_id TEXT")
        state_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.ALERT_STATE_TABLE})").fetchall()}
        if "organization_id" not in state_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_STATE_TABLE} ADD COLUMN organization_id TEXT")
        if "workspace_id" not in state_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_STATE_TABLE} ADD COLUMN workspace_id TEXT")
        log_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.ALERT_DELIVERY_LOG_TABLE})").fetchall()}
        if "organization_id" not in log_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_DELIVERY_LOG_TABLE} ADD COLUMN organization_id TEXT")
        if "workspace_id" not in log_columns:
            cursor.execute(f"ALTER TABLE {self.ALERT_DELIVERY_LOG_TABLE} ADD COLUMN workspace_id TEXT")
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ALERT_RULE_TABLE}_market_type
            ON {self.ALERT_RULE_TABLE} (market, rule_type, enabled)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ALERT_RULE_TABLE}_workspace_scope
            ON {self.ALERT_RULE_TABLE} (workspace_id, enabled, created_at)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ALERT_DELIVERY_LOG_TABLE}_rule_time
            ON {self.ALERT_DELIVERY_LOG_TABLE} (rule_id, delivered_at DESC)
        """)
        conn.commit()

    def ensure_job_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.JOB_TABLE} (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                source_key TEXT NOT NULL,
                organization_id TEXT,
                workspace_id TEXT,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}',
                result_json TEXT NOT NULL DEFAULT '{{}}',
                error_text TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                progress_pct INTEGER NOT NULL DEFAULT 0,
                progress_message TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                next_run_after TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                locked_by TEXT,
                locked_at TEXT,
                artifact_path TEXT
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.JOB_EVENT_TABLE} (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES {self.JOB_TABLE}(job_id)
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.JOB_TABLE}_queue_status
            ON {self.JOB_TABLE} (status, next_run_after, priority, created_at)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.JOB_TABLE}_source_status
            ON {self.JOB_TABLE} (source_key, status, created_at)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.JOB_EVENT_TABLE}_job_time
            ON {self.JOB_EVENT_TABLE} (job_id, created_at)
        """)
        conn.commit()

    def ensure_external_api_tables(self, conn: sqlite3.Connection):
        self.ensure_access_control_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.API_CLIENT_TABLE} (
                client_id TEXT PRIMARY KEY,
                api_key TEXT NOT NULL UNIQUE,
                client_name TEXT NOT NULL,
                plan TEXT NOT NULL,
                organization_id TEXT,
                workspace_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.API_USAGE_TABLE} (
                usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                http_method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                request_units INTEGER NOT NULL DEFAULT 1,
                latency_ms INTEGER,
                api_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(client_id) REFERENCES {self.API_CLIENT_TABLE}(client_id)
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.API_USAGE_TABLE}_client_time
            ON {self.API_USAGE_TABLE} (client_id, created_at DESC)
        """)
        conn.commit()

    def ensure_access_control_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ORGANIZATION_TABLE} (
                organization_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WORKSPACE_TABLE} (
                workspace_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.PRINCIPAL_TABLE} (
                principal_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT,
                password_salt TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        principal_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.PRINCIPAL_TABLE})").fetchall()}
        if "password_hash" not in principal_columns:
            cursor.execute(f"ALTER TABLE {self.PRINCIPAL_TABLE} ADD COLUMN password_hash TEXT")
        if "password_salt" not in principal_columns:
            cursor.execute(f"ALTER TABLE {self.PRINCIPAL_TABLE} ADD COLUMN password_salt TEXT")
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.AUTH_IDENTITY_TABLE} (
                auth_identity_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                subject TEXT,
                email TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(provider_type, provider_key, subject),
                FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ORGANIZATION_MEMBERSHIP_TABLE} (
                organization_membership_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(organization_id, principal_id),
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WORKSPACE_MEMBERSHIP_TABLE} (
                membership_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, principal_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id),
                FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ACCESS_TOKEN_TABLE} (
                token_id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                principal_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.AUTH_SESSION_TABLE} (
                session_id TEXT PRIMARY KEY,
                session_token TEXT NOT NULL UNIQUE,
                principal_id TEXT NOT NULL,
                organization_id TEXT,
                workspace_id TEXT NOT NULL,
                auth_identity_id TEXT,
                auth_method TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                expires_at TEXT,
                revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        session_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({self.AUTH_SESSION_TABLE})").fetchall()}
        if "organization_id" not in session_columns:
            cursor.execute(f"ALTER TABLE {self.AUTH_SESSION_TABLE} ADD COLUMN organization_id TEXT")
        if "auth_identity_id" not in session_columns:
            cursor.execute(f"ALTER TABLE {self.AUTH_SESSION_TABLE} ADD COLUMN auth_identity_id TEXT")
        if "auth_method" not in session_columns:
            cursor.execute(f"ALTER TABLE {self.AUTH_SESSION_TABLE} ADD COLUMN auth_method TEXT")
        if "last_seen_at" not in session_columns:
            cursor.execute(f"ALTER TABLE {self.AUTH_SESSION_TABLE} ADD COLUMN last_seen_at TEXT")
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.AUDIT_LOG_TABLE} (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_principal_id TEXT,
                workspace_id TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WORKSPACE_POLICY_TABLE} (
                workspace_id TEXT PRIMARY KEY,
                allowed_regions_json TEXT NOT NULL DEFAULT '[]',
                allowed_markets_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.OIDC_PROVIDER_TABLE} (
                provider_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                issuer TEXT NOT NULL,
                discovery_url TEXT NOT NULL,
                client_id TEXT NOT NULL,
                client_secret_encrypted TEXT NOT NULL,
                scopes_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(organization_id, provider_key),
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.ORGANIZATION_DOMAIN_TABLE} (
                domain_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                domain TEXT NOT NULL UNIQUE,
                verified_at TEXT,
                join_mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.MEMBERSHIP_INVITE_TABLE} (
                invite_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                workspace_id TEXT,
                target_scope_type TEXT NOT NULL,
                email TEXT NOT NULL,
                target_role TEXT NOT NULL,
                invite_token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                invited_by_principal_id TEXT NOT NULL,
                accepted_by_principal_id TEXT,
                revoked_by_principal_id TEXT,
                expires_at TEXT,
                accepted_at TEXT,
                revoked_at TEXT,
                revoke_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES {self.ORGANIZATION_TABLE}(organization_id),
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id),
                FOREIGN KEY(invited_by_principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id),
                FOREIGN KEY(accepted_by_principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id),
                FOREIGN KEY(revoked_by_principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.WORKSPACE_INVITE_TABLE} (
                invite_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                invite_token TEXT NOT NULL UNIQUE,
                invited_by_principal_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                accepted_at TEXT,
                FOREIGN KEY(workspace_id) REFERENCES {self.WORKSPACE_TABLE}(workspace_id),
                FOREIGN KEY(invited_by_principal_id) REFERENCES {self.PRINCIPAL_TABLE}(principal_id)
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.AUDIT_LOG_TABLE}_workspace_time
            ON {self.AUDIT_LOG_TABLE} (workspace_id, created_at DESC)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.AUTH_SESSION_TABLE}_principal_workspace
            ON {self.AUTH_SESSION_TABLE} (principal_id, workspace_id, created_at DESC)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.AUTH_IDENTITY_TABLE}_principal
            ON {self.AUTH_IDENTITY_TABLE} (principal_id, provider_type, provider_key)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.ORGANIZATION_MEMBERSHIP_TABLE}_org_status
            ON {self.ORGANIZATION_MEMBERSHIP_TABLE} (organization_id, status, created_at)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.OIDC_PROVIDER_TABLE}_organization
            ON {self.OIDC_PROVIDER_TABLE} (organization_id, provider_key)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.MEMBERSHIP_INVITE_TABLE}_org_email
            ON {self.MEMBERSHIP_INVITE_TABLE} (organization_id, email, status, created_at DESC)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.WORKSPACE_INVITE_TABLE}_workspace_email
            ON {self.WORKSPACE_INVITE_TABLE} (workspace_id, email, created_at DESC)
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
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ):
        with self.get_connection() as conn:
            self.ensure_analysis_cache_table(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ANALYSIS_CACHE_TABLE} (
                    scope,
                    cache_key,
                    data_version,
                    organization_id,
                    workspace_id,
                    response_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scope, cache_key, data_version, organization_id, workspace_id) DO UPDATE SET
                    response_json=excluded.response_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    scope,
                    cache_key,
                    data_version,
                    organization_id,
                    workspace_id,
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
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_analysis_cache_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT organization_id, workspace_id, response_json
                FROM {self.ANALYSIS_CACHE_TABLE}
                WHERE scope = ? AND cache_key = ? AND data_version = ?
                  AND ((organization_id IS NULL AND ? IS NULL) OR organization_id = ?)
                  AND ((workspace_id IS NULL AND ? IS NULL) OR workspace_id = ?)
                """,
                (scope, cache_key, data_version, organization_id, organization_id, workspace_id, workspace_id),
            )
            row = cursor.fetchone()

        if not row:
            return None
        return {
            "organization_id": row[0],
            "workspace_id": row[1],
            "response_payload": json.loads(row[2]),
        }

    def upsert_fingrid_dataset_catalog(self, records: list[dict]):
        if not records:
            return 0

        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.executemany(
                f"""
                INSERT INTO {self.FINGRID_DATASET_TABLE} (
                    dataset_id,
                    dataset_code,
                    name,
                    description,
                    unit,
                    frequency,
                    timezone,
                    value_kind,
                    source_url,
                    enabled,
                    metadata_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    dataset_code=excluded.dataset_code,
                    name=excluded.name,
                    description=excluded.description,
                    unit=excluded.unit,
                    frequency=excluded.frequency,
                    timezone=excluded.timezone,
                    value_kind=excluded.value_kind,
                    source_url=excluded.source_url,
                    enabled=excluded.enabled,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        record["dataset_id"],
                        record.get("dataset_code"),
                        record["name"],
                        record.get("description"),
                        record["unit"],
                        record["frequency"],
                        record["timezone"],
                        record["value_kind"],
                        record["source_url"],
                        int(record.get("enabled", 1)),
                        json.dumps(record.get("metadata_json") or {}),
                        record["updated_at"],
                    )
                    for record in records
                ],
            )
            conn.commit()
        return len(records)

    def upsert_fingrid_timeseries(self, records: list[dict]):
        if not records:
            return 0

        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.executemany(
                f"""
                INSERT INTO {self.FINGRID_TIMESERIES_TABLE} (
                    dataset_id,
                    series_key,
                    timestamp_utc,
                    timestamp_local,
                    value,
                    unit,
                    quality_flag,
                    source_updated_at,
                    ingested_at,
                    extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, series_key, timestamp_utc) DO UPDATE SET
                    timestamp_local=excluded.timestamp_local,
                    value=excluded.value,
                    unit=excluded.unit,
                    quality_flag=excluded.quality_flag,
                    source_updated_at=excluded.source_updated_at,
                    ingested_at=excluded.ingested_at,
                    extra_json=excluded.extra_json
                """,
                [
                    (
                        record["dataset_id"],
                        record["series_key"],
                        record["timestamp_utc"],
                        record["timestamp_local"],
                        record.get("value"),
                        record["unit"],
                        record.get("quality_flag"),
                        record.get("source_updated_at"),
                        record["ingested_at"],
                        json.dumps(record.get("extra_json") or {}),
                    )
                    for record in records
                ],
            )
            conn.commit()
        return len(records)

    def upsert_fingrid_sync_state(
        self,
        *,
        dataset_id: str,
        last_success_at,
        last_attempt_at,
        last_cursor,
        last_synced_timestamp_utc,
        sync_status: str,
        last_error,
        backfill_started_at,
        backfill_completed_at,
    ):
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.FINGRID_SYNC_STATE_TABLE} (
                    dataset_id,
                    last_success_at,
                    last_attempt_at,
                    last_cursor,
                    last_synced_timestamp_utc,
                    sync_status,
                    last_error,
                    backfill_started_at,
                    backfill_completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    last_success_at=excluded.last_success_at,
                    last_attempt_at=excluded.last_attempt_at,
                    last_cursor=excluded.last_cursor,
                    last_synced_timestamp_utc=excluded.last_synced_timestamp_utc,
                    sync_status=excluded.sync_status,
                    last_error=excluded.last_error,
                    backfill_started_at=excluded.backfill_started_at,
                    backfill_completed_at=excluded.backfill_completed_at
                """,
                (
                    dataset_id,
                    last_success_at,
                    last_attempt_at,
                    last_cursor,
                    last_synced_timestamp_utc,
                    sync_status,
                    last_error,
                    backfill_started_at,
                    backfill_completed_at,
                ),
            )
            conn.commit()

    def fetch_fingrid_dataset_catalog(self, enabled_only: bool = True) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            query = f"""
                SELECT dataset_id, dataset_code, name, description, unit, frequency, timezone,
                       value_kind, source_url, enabled, metadata_json, updated_at
                FROM {self.FINGRID_DATASET_TABLE}
            """
            if enabled_only:
                query += " WHERE enabled = 1"
            query += " ORDER BY dataset_id ASC"
            cursor.execute(query)
            rows = cursor.fetchall()

        return [
            {
                "dataset_id": row[0],
                "dataset_code": row[1],
                "name": row[2],
                "description": row[3],
                "unit": row[4],
                "frequency": row[5],
                "timezone": row[6],
                "value_kind": row[7],
                "source_url": row[8],
                "enabled": row[9],
                "metadata_json": json.loads(row[10]),
                "updated_at": row[11],
            }
            for row in rows
        ]

    def fetch_fingrid_series(
        self,
        *,
        dataset_id: str,
        start_utc: str | None = None,
        end_utc: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            clauses = ["dataset_id = ?"]
            params = [dataset_id]
            if start_utc:
                clauses.append("timestamp_utc >= ?")
                params.append(start_utc)
            if end_utc:
                clauses.append("timestamp_utc <= ?")
                params.append(end_utc)

            query = f"""
                SELECT dataset_id, series_key, timestamp_utc, timestamp_local, value, unit,
                       quality_flag, source_updated_at, ingested_at, extra_json
                FROM {self.FINGRID_TIMESERIES_TABLE}
                WHERE {' AND '.join(clauses)}
                ORDER BY timestamp_utc ASC
            """
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            {
                "dataset_id": row[0],
                "series_key": row[1],
                "timestamp_utc": row[2],
                "timestamp_local": row[3],
                "value": row[4],
                "unit": row[5],
                "quality_flag": row[6],
                "source_updated_at": row[7],
                "ingested_at": row[8],
                "extra_json": json.loads(row[9]),
            }
            for row in rows
        ]

    def fetch_fingrid_sync_state(self, dataset_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT dataset_id, last_success_at, last_attempt_at, last_cursor,
                       last_synced_timestamp_utc, sync_status, last_error,
                       backfill_started_at, backfill_completed_at
                FROM {self.FINGRID_SYNC_STATE_TABLE}
                WHERE dataset_id = ?
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "dataset_id": row[0],
            "last_success_at": row[1],
            "last_attempt_at": row[2],
            "last_cursor": row[3],
            "last_synced_timestamp_utc": row[4],
            "sync_status": row[5],
            "last_error": row[6],
            "backfill_started_at": row[7],
            "backfill_completed_at": row[8],
        }

    def fetch_fingrid_dataset_coverage(self, dataset_id: str) -> dict:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT MIN(timestamp_utc), MAX(timestamp_utc), COUNT(*)
                FROM {self.FINGRID_TIMESERIES_TABLE}
                WHERE dataset_id = ?
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()

        return {
            "dataset_id": dataset_id,
            "coverage_start_utc": row[0],
            "coverage_end_utc": row[1],
            "record_count": row[2] or 0,
        }

    def _normalize_data_quality_issue_rows(
        self,
        scope: str,
        market: str,
        dataset_key: str,
        issues: list,
        computed_at: str,
    ) -> list[tuple]:
        normalized_issue_rows = []
        for issue in issues:
            if isinstance(issue, str):
                issue_code = issue
                severity = "info"
                detail_json = {}
                detected_at = computed_at
            else:
                issue_code = issue.get("issue_code") or "unknown"
                severity = issue.get("severity") or "info"
                detail_json = issue.get("detail_json") or {}
                detected_at = issue.get("detected_at") or computed_at

            normalized_issue_rows.append(
                (
                    scope,
                    market,
                    dataset_key,
                    issue_code,
                    severity,
                    json.dumps(detail_json, ensure_ascii=False),
                    detected_at,
                )
            )
        return normalized_issue_rows

    def _upsert_data_quality_snapshot(self, conn: sqlite3.Connection, record: dict):
        scope = record["scope"]
        market = record["market"]
        dataset_key = record["dataset_key"]
        computed_at = record["computed_at"]
        issues = record.get("issues_json") or []

        conn.execute(
            f"""
            INSERT INTO {self.DATA_QUALITY_SNAPSHOT_TABLE} (
                scope,
                market,
                dataset_key,
                data_grade,
                quality_score,
                coverage_ratio,
                freshness_minutes,
                issues_json,
                metadata_json,
                computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, market, dataset_key) DO UPDATE SET
                data_grade=excluded.data_grade,
                quality_score=excluded.quality_score,
                coverage_ratio=excluded.coverage_ratio,
                freshness_minutes=excluded.freshness_minutes,
                issues_json=excluded.issues_json,
                metadata_json=excluded.metadata_json,
                computed_at=excluded.computed_at
            """,
            (
                scope,
                market,
                dataset_key,
                record["data_grade"],
                record.get("quality_score"),
                record.get("coverage_ratio"),
                record.get("freshness_minutes"),
                json.dumps(issues, ensure_ascii=False),
                json.dumps(record.get("metadata_json") or {}, ensure_ascii=False),
                computed_at,
            ),
        )
        conn.execute(
            f"""
            DELETE FROM {self.DATA_QUALITY_ISSUE_TABLE}
            WHERE scope = ? AND market = ? AND dataset_key = ?
            """,
            (scope, market, dataset_key),
        )
        normalized_issue_rows = self._normalize_data_quality_issue_rows(
            scope=scope,
            market=market,
            dataset_key=dataset_key,
            issues=issues,
            computed_at=computed_at,
        )
        if normalized_issue_rows:
            conn.executemany(
                f"""
                INSERT INTO {self.DATA_QUALITY_ISSUE_TABLE} (
                    scope,
                    market,
                    dataset_key,
                    issue_code,
                    severity,
                    detail_json,
                    detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                normalized_issue_rows,
            )

    def upsert_data_quality_snapshot(self, record: dict):
        with self.get_connection() as conn:
            self.ensure_data_quality_tables(conn)
            self._upsert_data_quality_snapshot(conn, record)
            conn.commit()

    def replace_data_quality_snapshots(self, records: list[dict]) -> int:
        with self.get_connection() as conn:
            try:
                self.ensure_data_quality_tables(conn)
                conn.execute("BEGIN")
                conn.execute(f"DELETE FROM {self.DATA_QUALITY_ISSUE_TABLE}")
                conn.execute(f"DELETE FROM {self.DATA_QUALITY_SNAPSHOT_TABLE}")
                for record in records:
                    self._upsert_data_quality_snapshot(conn, record)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return len(records)

    def fetch_data_quality_snapshots(
        self,
        scope: str | None = None,
        market: str | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_data_quality_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.DATA_QUALITY_SNAPSHOT_TABLE} WHERE 1=1"
            params = []
            if scope:
                query += " AND scope = ?"
                params.append(scope)
            if market:
                query += " AND market = ?"
                params.append(market)
            query += " ORDER BY market ASC, dataset_key ASC"
            rows = conn.execute(query, params).fetchall()

        return [
            {
                **dict(row),
                "issues_json": json.loads(row["issues_json"]),
                "metadata_json": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def fetch_data_quality_issues(
        self,
        scope: str | None = None,
        market: str | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_data_quality_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.DATA_QUALITY_ISSUE_TABLE} WHERE 1=1"
            params = []
            if scope:
                query += " AND scope = ?"
                params.append(scope)
            if market:
                query += " AND market = ?"
                params.append(market)
            query += " ORDER BY market ASC, dataset_key ASC, issue_code ASC"
            rows = conn.execute(query, params).fetchall()

        return [
            {
                **dict(row),
                "detail_json": json.loads(row["detail_json"]),
            }
            for row in rows
        ]

    def upsert_alert_rule(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ALERT_RULE_TABLE} (
                    rule_id, name, rule_type, market, region_or_zone, config_json,
                    channel_type, channel_target, enabled, organization_id, workspace_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name=excluded.name,
                    rule_type=excluded.rule_type,
                    market=excluded.market,
                    region_or_zone=excluded.region_or_zone,
                    config_json=excluded.config_json,
                    channel_type=excluded.channel_type,
                    channel_target=excluded.channel_target,
                    enabled=excluded.enabled,
                    organization_id=excluded.organization_id,
                    workspace_id=excluded.workspace_id,
                    updated_at=excluded.updated_at
                """,
                (
                    record["rule_id"],
                    record["name"],
                    record["rule_type"],
                    record["market"],
                    record.get("region_or_zone"),
                    json.dumps(record.get("config") or {}, ensure_ascii=False),
                    record["channel_type"],
                    record["channel_target"],
                    int(record.get("enabled", True)),
                    record.get("organization_id"),
                    record.get("workspace_id"),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_alert_rule(record["rule_id"])

    def fetch_alert_rule(self, rule_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM {self.ALERT_RULE_TABLE} WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["config"] = json.loads(data.pop("config_json"))
        data["enabled"] = bool(data["enabled"])
        return data

    def fetch_alert_rules(self, enabled_only: bool = False, workspace_id: str | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.ALERT_RULE_TABLE}"
            params = []
            clauses = []
            if enabled_only:
                clauses.append("enabled = 1")
            if workspace_id is not None:
                clauses.append("workspace_id = ?")
                params.append(workspace_id)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at ASC, rule_id ASC"
            rows = conn.execute(query, params).fetchall()
        items = []
        for row in rows:
            data = dict(row)
            data["config"] = json.loads(data.pop("config_json"))
            data["enabled"] = bool(data["enabled"])
            items.append(data)
        return items

    def upsert_alert_state(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ALERT_STATE_TABLE} (
                    rule_id, current_status, last_evaluated_at, last_triggered_at,
                    last_delivery_at, organization_id, workspace_id, last_value_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    current_status=excluded.current_status,
                    last_evaluated_at=excluded.last_evaluated_at,
                    last_triggered_at=excluded.last_triggered_at,
                    last_delivery_at=excluded.last_delivery_at,
                    organization_id=excluded.organization_id,
                    workspace_id=excluded.workspace_id,
                    last_value_json=excluded.last_value_json
                """,
                (
                    record["rule_id"],
                    record["current_status"],
                    record.get("last_evaluated_at"),
                    record.get("last_triggered_at"),
                    record.get("last_delivery_at"),
                    record.get("organization_id"),
                    record.get("workspace_id"),
                    json.dumps(record.get("last_value") or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.fetch_alert_state(record["rule_id"])

    def fetch_alert_state(self, rule_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM {self.ALERT_STATE_TABLE} WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["last_value"] = json.loads(data.pop("last_value_json"))
        return data

    def fetch_alert_states(self, workspace_id: str | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.ALERT_STATE_TABLE}"
            params = []
            if workspace_id is not None:
                query += " WHERE workspace_id = ?"
                params.append(workspace_id)
            query += " ORDER BY last_evaluated_at DESC, rule_id ASC"
            rows = conn.execute(query, params).fetchall()
        items = []
        for row in rows:
            data = dict(row)
            data["last_value"] = json.loads(data.pop("last_value_json"))
            items.append(data)
        return items

    def insert_alert_delivery_log(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            cursor = conn.execute(
                f"""
                INSERT INTO {self.ALERT_DELIVERY_LOG_TABLE} (
                    rule_id, delivery_status, target, payload_json, response_code,
                    response_text, organization_id, workspace_id, delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["rule_id"],
                    record["delivery_status"],
                    record["target"],
                    json.dumps(record.get("payload") or {}, ensure_ascii=False),
                    record.get("response_code"),
                    record.get("response_text"),
                    record.get("organization_id"),
                    record.get("workspace_id"),
                    record["delivered_at"],
                ),
            )
            row_id = cursor.lastrowid
            conn.commit()
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM {self.ALERT_DELIVERY_LOG_TABLE} WHERE id = ?",
                (row_id,),
            ).fetchone()
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def fetch_alert_delivery_logs(self, limit: int = 100, workspace_id: str | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_alert_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.ALERT_DELIVERY_LOG_TABLE}"
            params = []
            if workspace_id is not None:
                query += " WHERE workspace_id = ?"
                params.append(workspace_id)
            query += " ORDER BY delivered_at DESC, id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        items = []
        for row in rows:
            data = dict(row)
            data["payload"] = json.loads(data.pop("payload_json"))
            items.append(data)
        return items

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

    def set_system_status(self, key: str, value):
        payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO system_status (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, payload),
            )
            conn.commit()

    def get_system_status(self, key: str, default=None, *, parse_json: bool = False):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_status WHERE key = ?", (key,))
            row = cursor.fetchone()
        if not row:
            return default
        if not parse_json:
            return row[0]
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default

    def create_job(
        self,
        *,
        job_id: str,
        job_type: str,
        queue_name: str,
        source_key: str,
        payload: dict,
        priority: int,
        max_attempts: int,
        next_run_after: str | None,
        created_at: str,
    ) -> dict:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.JOB_TABLE} (
                    job_id, job_type, queue_name, source_key, organization_id, workspace_id, status, payload_json, result_json,
                    priority, progress_pct, progress_message, attempt_count, max_attempts,
                    created_at, next_run_after, cancel_requested, locked_by, locked_at, artifact_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL)
                """,
                (
                    job_id,
                    job_type,
                    queue_name,
                    source_key,
                    payload.get("organization_id"),
                    payload.get("workspace_id"),
                    "queued",
                    json.dumps(payload or {}),
                    json.dumps({}),
                    priority,
                    0,
                    None,
                    0,
                    max_attempts,
                    created_at,
                    next_run_after,
                ),
            )
            conn.commit()
        return self.fetch_job(job_id)

    def append_job_event(self, job_id: str, event_type: str, detail: dict | None, created_at: str):
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.JOB_EVENT_TABLE} (job_id, event_type, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, event_type, json.dumps(detail or {}), created_at),
            )
            conn.commit()

    def list_jobs(self, *, status: str | None = None, queue_name: str | None = None, limit: int = 100) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            clauses = []
            params = []
            if status:
                clauses.append("status = ?")
                params.append(status)
            if queue_name:
                clauses.append("queue_name = ?")
                params.append(queue_name)
            query = f"SELECT * FROM {self.JOB_TABLE}"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        return [self._decode_job_row(dict(zip(columns, row))) for row in rows]

    def fetch_job(self, job_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.JOB_TABLE} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            columns = [desc[0] for desc in cursor.description] if row else []
        if not row:
            return None
        return self._decode_job_row(dict(zip(columns, row)))

    def _decode_job_row(self, row: dict) -> dict:
        row["payload_json"] = json.loads(row["payload_json"] or "{}")
        row["result_json"] = json.loads(row["result_json"] or "{}")
        row["cancel_requested"] = bool(row.get("cancel_requested"))
        return row

    def claim_next_job(self, *, worker_id: str, now_iso: str, runnable_job_ids: list[str] | None = None) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            clauses = [
                "status = 'queued'",
                "(next_run_after IS NULL OR next_run_after <= ?)",
                "cancel_requested = 0",
            ]
            params = [now_iso]
            if runnable_job_ids is not None:
                if not runnable_job_ids:
                    conn.rollback()
                    return None
                placeholders = ",".join("?" for _ in runnable_job_ids)
                clauses.append(f"job_id IN ({placeholders})")
                params.extend(runnable_job_ids)

            cursor.execute(
                f"""
                SELECT job_id
                FROM {self.JOB_TABLE}
                WHERE {' AND '.join(clauses)}
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return None

            job_id = row[0]
            cursor.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, ?),
                    locked_by = ?,
                    locked_at = ?,
                    progress_pct = CASE WHEN progress_pct > 0 THEN progress_pct ELSE 1 END,
                    progress_message = COALESCE(progress_message, 'started')
                WHERE job_id = ?
                """,
                (now_iso, worker_id, now_iso, job_id),
            )
            conn.commit()
        return self.fetch_job(job_id)

    def update_job_progress(self, job_id: str, *, progress_pct: int, progress_message: str | None):
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET progress_pct = ?, progress_message = ?
                WHERE job_id = ?
                """,
                (progress_pct, progress_message, job_id),
            )
            conn.commit()

    def complete_job(self, job_id: str, *, finished_at: str, result: dict, artifact_path: str | None):
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET status = 'succeeded',
                    finished_at = ?,
                    result_json = ?,
                    error_text = NULL,
                    progress_pct = 100,
                    progress_message = 'completed',
                    locked_by = NULL,
                    locked_at = NULL,
                    artifact_path = ?
                WHERE job_id = ?
                """,
                (finished_at, json.dumps(result or {}), artifact_path, job_id),
            )
            conn.commit()

    def reschedule_job_retry(self, job_id: str, *, next_run_after: str, error_text: str):
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET status = 'queued',
                    next_run_after = ?,
                    error_text = ?,
                    locked_by = NULL,
                    locked_at = NULL,
                    progress_message = 'retry_waiting'
                WHERE job_id = ?
                """,
                (next_run_after, error_text, job_id),
            )
            conn.commit()

    def fail_job(self, job_id: str, *, finished_at: str, error_text: str):
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            conn.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET status = 'failed',
                    finished_at = ?,
                    error_text = ?,
                    locked_by = NULL,
                    locked_at = NULL,
                    progress_message = 'failed'
                WHERE job_id = ?
                """,
                (finished_at, error_text, job_id),
            )
            conn.commit()

    def cancel_job(self, job_id: str) -> bool:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            cursor.execute(f"SELECT status FROM {self.JOB_TABLE} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return False
            status = row[0]
            if status == "queued":
                cursor.execute(
                    f"""
                    UPDATE {self.JOB_TABLE}
                    SET status = 'cancelled',
                        cancel_requested = 1,
                        finished_at = CURRENT_TIMESTAMP,
                        progress_message = 'cancelled'
                    WHERE job_id = ?
                    """,
                    (job_id,),
                )
                cursor.execute(
                    f"""
                    INSERT INTO {self.JOB_EVENT_TABLE} (job_id, event_type, detail_json, created_at)
                    VALUES (?, 'cancelled', '{{}}', CURRENT_TIMESTAMP)
                    """,
                    (job_id,),
                )
            elif status == "running":
                cursor.execute(
                    f"""
                    UPDATE {self.JOB_TABLE}
                    SET cancel_requested = 1,
                        progress_message = 'cancel_requested'
                    WHERE job_id = ?
                    """,
                    (job_id,),
                )
                cursor.execute(
                    f"""
                    INSERT INTO {self.JOB_EVENT_TABLE} (job_id, event_type, detail_json, created_at)
                    VALUES (?, 'cancel_requested', '{{}}', CURRENT_TIMESTAMP)
                    """,
                    (job_id,),
                )
            else:
                return False
            conn.commit()
        return True

    def retry_job(self, job_id: str, *, next_run_after: str) -> bool:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            cursor.execute(f"SELECT status, attempt_count, max_attempts FROM {self.JOB_TABLE} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return False
            status, attempt_count, max_attempts = row
            if status not in {"failed", "cancelled"}:
                return False
            cursor.execute(
                f"""
                UPDATE {self.JOB_TABLE}
                SET status = 'queued',
                    error_text = NULL,
                    result_json = ?,
                    next_run_after = ?,
                    cancel_requested = 0,
                    finished_at = NULL,
                    locked_by = NULL,
                    locked_at = NULL,
                    progress_pct = 0,
                    progress_message = 'retry_queued',
                    attempt_count = CASE WHEN ? >= ? THEN 0 ELSE attempt_count END
                WHERE job_id = ?
                """,
                (json.dumps({}), next_run_after, attempt_count, max_attempts, job_id),
            )
            conn.commit()
        return True

    def list_job_events(self, job_id: str) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_job_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT event_id, job_id, event_type, detail_json, created_at
                FROM {self.JOB_EVENT_TABLE}
                WHERE job_id = ?
                ORDER BY event_id ASC
                """,
                (job_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "event_id": row[0],
                "job_id": row[1],
                "event_type": row[2],
                "detail_json": json.loads(row[3] or "{}"),
                "created_at": row[4],
            }
            for row in rows
        ]

    def upsert_external_api_client(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.API_CLIENT_TABLE} (
                    client_id, api_key, client_name, plan, organization_id, workspace_id, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    api_key=excluded.api_key,
                    client_name=excluded.client_name,
                    plan=excluded.plan,
                    organization_id=excluded.organization_id,
                    workspace_id=excluded.workspace_id,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    record["client_id"],
                    record["api_key"],
                    record["client_name"],
                    record["plan"],
                    record.get("organization_id"),
                    record.get("workspace_id"),
                    int(record.get("enabled", 1)),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_external_api_client(record["client_id"])

    def fetch_external_api_client(self, client_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT client_id, api_key, client_name, plan, organization_id, workspace_id, enabled, created_at, updated_at
                FROM {self.API_CLIENT_TABLE}
                WHERE client_id = ?
                """,
                (client_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "client_id": row[0],
            "api_key": row[1],
            "client_name": row[2],
            "plan": row[3],
            "organization_id": row[4],
            "workspace_id": row[5],
            "enabled": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }

    def fetch_external_api_client_by_key(self, api_key: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT client_id, api_key, client_name, plan, organization_id, workspace_id, enabled, created_at, updated_at
                FROM {self.API_CLIENT_TABLE}
                WHERE api_key = ?
                """,
                (api_key,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "client_id": row[0],
            "api_key": row[1],
            "client_name": row[2],
            "plan": row[3],
            "organization_id": row[4],
            "workspace_id": row[5],
            "enabled": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }

    def insert_external_api_usage(
        self,
        *,
        client_id: str,
        endpoint: str,
        http_method: str,
        status_code: int,
        request_units: int,
        latency_ms: int | None,
        api_version: str,
        created_at: str,
    ):
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.API_USAGE_TABLE} (
                    client_id, endpoint, http_method, status_code, request_units, latency_ms, api_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_id, endpoint, http_method, status_code, request_units, latency_ms, api_version, created_at),
            )
            conn.commit()

    def fetch_external_api_usage(self, *, client_id: str | None = None, limit: int = 100) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            cursor = conn.cursor()
            params = []
            query = f"""
                SELECT usage_id, client_id, endpoint, http_method, status_code, request_units, latency_ms, api_version, created_at
                FROM {self.API_USAGE_TABLE}
            """
            if client_id:
                query += " WHERE client_id = ?"
                params.append(client_id)
            query += " ORDER BY usage_id DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [
            {
                "usage_id": row[0],
                "client_id": row[1],
                "endpoint": row[2],
                "http_method": row[3],
                "status_code": row[4],
                "request_units": row[5],
                "latency_ms": row[6],
                "api_version": row[7],
                "created_at": row[8],
            }
            for row in rows
        ]

    def sum_external_api_usage_units(self, *, client_id: str, created_at_from: str) -> int:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(request_units), 0)
                FROM {self.API_USAGE_TABLE}
                WHERE client_id = ? AND created_at >= ?
                """,
                (client_id, created_at_from),
            )
            row = cursor.fetchone()
        return int((row or [0])[0] or 0)

    def summarize_external_api_usage(
        self,
        *,
        created_at_from: str,
        client_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_external_api_tables(conn)
            cursor = conn.cursor()
            clauses = ["u.created_at >= ?"]
            params: list[object] = [created_at_from]
            if client_id:
                clauses.append("u.client_id = ?")
                params.append(client_id)
            params.append(limit)
            cursor.execute(
                f"""
                SELECT
                    c.client_id,
                    c.client_name,
                    c.plan,
                    c.organization_id,
                    c.workspace_id,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(u.request_units), 0) AS request_units,
                    COALESCE(AVG(u.latency_ms), 0) AS avg_latency_ms,
                    SUM(CASE WHEN u.status_code >= 200 AND u.status_code < 300 THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN u.status_code < 200 OR u.status_code >= 300 THEN 1 ELSE 0 END) AS non_success_count
                FROM {self.API_USAGE_TABLE} u
                JOIN {self.API_CLIENT_TABLE} c
                  ON c.client_id = u.client_id
                WHERE {" AND ".join(clauses)}
                GROUP BY c.client_id, c.client_name, c.plan, c.organization_id, c.workspace_id
                ORDER BY request_units DESC, request_count DESC
                LIMIT ?
                """,
                params,
            )
            rows = cursor.fetchall()
        return [
            {
                "client_id": row[0],
                "client_name": row[1],
                "plan": row[2],
                "organization_id": row[3],
                "workspace_id": row[4],
                "request_count": int(row[5] or 0),
                "request_units": int(row[6] or 0),
                "avg_latency_ms": round(float(row[7] or 0), 2),
                "success_count": int(row[8] or 0),
                "non_success_count": int(row[9] or 0),
            }
            for row in rows
        ]

    def upsert_organization(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ORGANIZATION_TABLE} (organization_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(organization_id) DO UPDATE SET
                    name=excluded.name,
                    updated_at=excluded.updated_at
                """,
                (record["organization_id"], record["name"], record["created_at"], record["updated_at"]),
            )
            conn.commit()
        return self.fetch_organization(record["organization_id"])

    def fetch_organization(self, organization_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT organization_id, name, created_at, updated_at FROM {self.ORGANIZATION_TABLE} WHERE organization_id = ?",
                (organization_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"organization_id": row[0], "name": row[1], "created_at": row[2], "updated_at": row[3]}

    def list_organizations(self) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            rows = conn.execute(
                f"SELECT organization_id, name, created_at, updated_at FROM {self.ORGANIZATION_TABLE} ORDER BY created_at ASC"
            ).fetchall()
        return [{"organization_id": row[0], "name": row[1], "created_at": row[2], "updated_at": row[3]} for row in rows]

    def upsert_workspace(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.WORKSPACE_TABLE} (workspace_id, organization_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    name=excluded.name,
                    updated_at=excluded.updated_at
                """,
                (record["workspace_id"], record["organization_id"], record["name"], record["created_at"], record["updated_at"]),
            )
            conn.commit()
        return self.fetch_workspace(record["workspace_id"])

    def fetch_workspace(self, workspace_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT workspace_id, organization_id, name, created_at, updated_at FROM {self.WORKSPACE_TABLE} WHERE workspace_id = ?",
                (workspace_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "workspace_id": row[0],
            "organization_id": row[1],
            "name": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }

    def list_workspaces(self, *, organization_id: str | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            params = []
            query = f"SELECT workspace_id, organization_id, name, created_at, updated_at FROM {self.WORKSPACE_TABLE}"
            if organization_id:
                query += " WHERE organization_id = ?"
                params.append(organization_id)
            query += " ORDER BY created_at ASC"
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "workspace_id": row[0],
                "organization_id": row[1],
                "name": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]

    def upsert_principal(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.PRINCIPAL_TABLE} (
                    principal_id, email, display_name, password_hash, password_salt, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    email=excluded.email,
                    display_name=excluded.display_name,
                    password_hash=excluded.password_hash,
                    password_salt=excluded.password_salt,
                    updated_at=excluded.updated_at
                """,
                (
                    record["principal_id"],
                    record["email"],
                    record["display_name"],
                    record.get("password_hash"),
                    record.get("password_salt"),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_principal(record["principal_id"])

    def fetch_principal(self, principal_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT principal_id, email, display_name, password_hash, password_salt, created_at, updated_at
                FROM {self.PRINCIPAL_TABLE}
                WHERE principal_id = ?
                """,
                (principal_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "principal_id": row[0],
            "email": row[1],
            "display_name": row[2],
            "password_hash": row[3],
            "password_salt": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def fetch_principal_by_email(self, email: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT principal_id, email, display_name, password_hash, password_salt, created_at, updated_at
                FROM {self.PRINCIPAL_TABLE}
                WHERE email = ?
                """,
                (email,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "principal_id": row[0],
            "email": row[1],
            "display_name": row[2],
            "password_hash": row[3],
            "password_salt": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def upsert_auth_identity(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.AUTH_IDENTITY_TABLE} (
                    auth_identity_id, principal_id, provider_type, provider_key,
                    subject, email, email_verified, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(auth_identity_id) DO UPDATE SET
                    principal_id=excluded.principal_id,
                    provider_type=excluded.provider_type,
                    provider_key=excluded.provider_key,
                    subject=excluded.subject,
                    email=excluded.email,
                    email_verified=excluded.email_verified,
                    updated_at=excluded.updated_at
                """,
                (
                    record["auth_identity_id"],
                    record["principal_id"],
                    record["provider_type"],
                    record["provider_key"],
                    record.get("subject"),
                    record.get("email"),
                    int(record.get("email_verified", 0)),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_auth_identity(record["auth_identity_id"])

    def fetch_auth_identity(self, auth_identity_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT auth_identity_id, principal_id, provider_type, provider_key,
                       subject, email, email_verified, created_at, updated_at
                FROM {self.AUTH_IDENTITY_TABLE}
                WHERE auth_identity_id = ?
                """,
                (auth_identity_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "auth_identity_id": row[0],
            "principal_id": row[1],
            "provider_type": row[2],
            "provider_key": row[3],
            "subject": row[4],
            "email": row[5],
            "email_verified": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }

    def fetch_auth_identity_by_subject(self, provider_type: str, provider_key: str, subject: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT auth_identity_id, principal_id, provider_type, provider_key,
                       subject, email, email_verified, created_at, updated_at
                FROM {self.AUTH_IDENTITY_TABLE}
                WHERE provider_type = ? AND provider_key = ? AND subject = ?
                """,
                (provider_type, provider_key, subject),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "auth_identity_id": row[0],
            "principal_id": row[1],
            "provider_type": row[2],
            "provider_key": row[3],
            "subject": row[4],
            "email": row[5],
            "email_verified": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }

    def upsert_workspace_membership(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.WORKSPACE_MEMBERSHIP_TABLE} (membership_id, workspace_id, principal_id, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, principal_id) DO UPDATE SET
                    role=excluded.role,
                    updated_at=excluded.updated_at
                """,
                (
                    record["membership_id"],
                    record["workspace_id"],
                    record["principal_id"],
                    record["role"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_workspace_membership(record["workspace_id"], record["principal_id"])

    def fetch_workspace_membership(self, workspace_id: str, principal_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT membership_id, workspace_id, principal_id, role, created_at, updated_at
                FROM {self.WORKSPACE_MEMBERSHIP_TABLE}
                WHERE workspace_id = ? AND principal_id = ?
                """,
                (workspace_id, principal_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "membership_id": row[0],
            "workspace_id": row[1],
            "principal_id": row[2],
            "role": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def list_workspace_memberships(self, workspace_id: str) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            rows = conn.execute(
                f"""
                SELECT membership_id, workspace_id, principal_id, role, created_at, updated_at
                FROM {self.WORKSPACE_MEMBERSHIP_TABLE}
                WHERE workspace_id = ?
                ORDER BY created_at ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [
            {
                "membership_id": row[0],
                "workspace_id": row[1],
                "principal_id": row[2],
                "role": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

    def upsert_organization_membership(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ORGANIZATION_MEMBERSHIP_TABLE} (
                    organization_membership_id, organization_id, principal_id, role, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, principal_id) DO UPDATE SET
                    role=excluded.role,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    record["organization_membership_id"],
                    record["organization_id"],
                    record["principal_id"],
                    record["role"],
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_organization_membership(record["organization_id"], record["principal_id"])

    def fetch_organization_membership(self, organization_id: str, principal_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            row = conn.execute(
                f"""
                SELECT organization_membership_id, organization_id, principal_id, role, status, created_at, updated_at
                FROM {self.ORGANIZATION_MEMBERSHIP_TABLE}
                WHERE organization_id = ? AND principal_id = ?
                """,
                (organization_id, principal_id),
            ).fetchone()
        if not row:
            return None
        return {
            "organization_membership_id": row[0],
            "organization_id": row[1],
            "principal_id": row[2],
            "role": row[3],
            "status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def list_organization_memberships(
        self,
        organization_id: str,
        *,
        status: str | None = None,
        role: str | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            query = f"""
                SELECT organization_membership_id, organization_id, principal_id, role, status, created_at, updated_at
                FROM {self.ORGANIZATION_MEMBERSHIP_TABLE}
                WHERE organization_id = ?
            """
            params: list[object] = [organization_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            if role:
                query += " AND role = ?"
                params.append(role)
            query += " ORDER BY created_at ASC"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "organization_membership_id": row[0],
                "organization_id": row[1],
                "principal_id": row[2],
                "role": row[3],
                "status": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def upsert_access_token(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ACCESS_TOKEN_TABLE} (token_id, token, principal_id, workspace_id, created_at, expires_at, revoked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token_id) DO UPDATE SET
                    token=excluded.token,
                    principal_id=excluded.principal_id,
                    workspace_id=excluded.workspace_id,
                    expires_at=excluded.expires_at,
                    revoked=excluded.revoked
                """,
                (
                    record["token_id"],
                    record["token"],
                    record["principal_id"],
                    record["workspace_id"],
                    record["created_at"],
                    record.get("expires_at"),
                    int(record.get("revoked", 0)),
                ),
            )
            conn.commit()
        return self.fetch_access_token_by_value(record["token"])

    def fetch_access_token_by_value(self, token: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT token_id, token, principal_id, workspace_id, created_at, expires_at, revoked
                FROM {self.ACCESS_TOKEN_TABLE}
                WHERE token = ?
                """,
                (token,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "token_id": row[0],
            "token": row[1],
            "principal_id": row[2],
            "workspace_id": row[3],
            "created_at": row[4],
            "expires_at": row[5],
            "revoked": bool(row[6]),
        }

    def list_access_tokens_for_principal(self, principal_id: str, *, workspace_ids: list[str] | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            query = f"""
                SELECT token_id, token, principal_id, workspace_id, created_at, expires_at, revoked
                FROM {self.ACCESS_TOKEN_TABLE}
                WHERE principal_id = ?
            """
            params: list[object] = [principal_id]
            if workspace_ids:
                placeholders = ",".join("?" for _ in workspace_ids)
                query += f" AND workspace_id IN ({placeholders})"
                params.extend(workspace_ids)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "token_id": row[0],
                "token": row[1],
                "principal_id": row[2],
                "workspace_id": row[3],
                "created_at": row[4],
                "expires_at": row[5],
                "revoked": bool(row[6]),
            }
            for row in rows
        ]

    def upsert_auth_session(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.AUTH_SESSION_TABLE} (
                    session_id, session_token, principal_id, organization_id, workspace_id,
                    auth_identity_id, auth_method, created_at, last_seen_at, expires_at, revoked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    session_token=excluded.session_token,
                    principal_id=excluded.principal_id,
                    organization_id=excluded.organization_id,
                    workspace_id=excluded.workspace_id,
                    auth_identity_id=excluded.auth_identity_id,
                    auth_method=excluded.auth_method,
                    last_seen_at=excluded.last_seen_at,
                    expires_at=excluded.expires_at,
                    revoked=excluded.revoked
                """,
                (
                    record["session_id"],
                    record["session_token"],
                    record["principal_id"],
                    record.get("organization_id"),
                    record["workspace_id"],
                    record.get("auth_identity_id"),
                    record.get("auth_method"),
                    record["created_at"],
                    record.get("last_seen_at"),
                    record.get("expires_at"),
                    int(record.get("revoked", 0)),
                ),
            )
            conn.commit()
        return self.fetch_auth_session_by_token(record["session_token"])

    def fetch_auth_session_by_token(self, session_token: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT session_id, session_token, principal_id, organization_id, workspace_id,
                       auth_identity_id, auth_method, created_at, last_seen_at, expires_at, revoked
                FROM {self.AUTH_SESSION_TABLE}
                WHERE session_token = ?
                """,
                (session_token,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "session_id": row[0],
            "session_token": row[1],
            "principal_id": row[2],
            "organization_id": row[3],
            "workspace_id": row[4],
            "auth_identity_id": row[5],
            "auth_method": row[6],
            "created_at": row[7],
            "last_seen_at": row[8],
            "expires_at": row[9],
            "revoked": bool(row[10]),
        }

    def fetch_auth_session_by_id(self, session_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT session_id, session_token, principal_id, organization_id, workspace_id,
                       auth_identity_id, auth_method, created_at, last_seen_at, expires_at, revoked
                FROM {self.AUTH_SESSION_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "session_id": row[0],
            "session_token": row[1],
            "principal_id": row[2],
            "organization_id": row[3],
            "workspace_id": row[4],
            "auth_identity_id": row[5],
            "auth_method": row[6],
            "created_at": row[7],
            "last_seen_at": row[8],
            "expires_at": row[9],
            "revoked": bool(row[10]),
        }

    def list_auth_sessions_for_principal(
        self,
        principal_id: str,
        *,
        organization_id: str | None = None,
        workspace_ids: list[str] | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            query = f"""
                SELECT session_id, session_token, principal_id, organization_id, workspace_id,
                       auth_identity_id, auth_method, created_at, last_seen_at, expires_at, revoked
                FROM {self.AUTH_SESSION_TABLE}
                WHERE principal_id = ?
            """
            params: list[object] = [principal_id]
            if organization_id:
                query += " AND organization_id = ?"
                params.append(organization_id)
            if workspace_ids:
                placeholders = ",".join("?" for _ in workspace_ids)
                query += f" AND workspace_id IN ({placeholders})"
                params.extend(workspace_ids)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "session_id": row[0],
                "session_token": row[1],
                "principal_id": row[2],
                "organization_id": row[3],
                "workspace_id": row[4],
                "auth_identity_id": row[5],
                "auth_method": row[6],
                "created_at": row[7],
                "last_seen_at": row[8],
                "expires_at": row[9],
                "revoked": bool(row[10]),
            }
            for row in rows
        ]

    def upsert_membership_invite(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.MEMBERSHIP_INVITE_TABLE} (
                    invite_id, organization_id, workspace_id, target_scope_type, email, target_role,
                    invite_token, status, invited_by_principal_id, accepted_by_principal_id,
                    revoked_by_principal_id, expires_at, accepted_at, revoked_at, revoke_reason,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(invite_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    workspace_id=excluded.workspace_id,
                    target_scope_type=excluded.target_scope_type,
                    email=excluded.email,
                    target_role=excluded.target_role,
                    invite_token=excluded.invite_token,
                    status=excluded.status,
                    invited_by_principal_id=excluded.invited_by_principal_id,
                    accepted_by_principal_id=excluded.accepted_by_principal_id,
                    revoked_by_principal_id=excluded.revoked_by_principal_id,
                    expires_at=excluded.expires_at,
                    accepted_at=excluded.accepted_at,
                    revoked_at=excluded.revoked_at,
                    revoke_reason=excluded.revoke_reason,
                    updated_at=excluded.updated_at
                """,
                (
                    record["invite_id"],
                    record["organization_id"],
                    record.get("workspace_id"),
                    record["target_scope_type"],
                    record["email"],
                    record["target_role"],
                    record["invite_token"],
                    record["status"],
                    record["invited_by_principal_id"],
                    record.get("accepted_by_principal_id"),
                    record.get("revoked_by_principal_id"),
                    record.get("expires_at"),
                    record.get("accepted_at"),
                    record.get("revoked_at"),
                    record.get("revoke_reason"),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_membership_invite(record["invite_id"])

    def fetch_membership_invite(self, invite_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            row = conn.execute(
                f"""
                SELECT invite_id, organization_id, workspace_id, target_scope_type, email, target_role,
                       invite_token, status, invited_by_principal_id, accepted_by_principal_id,
                       revoked_by_principal_id, expires_at, accepted_at, revoked_at, revoke_reason,
                       created_at, updated_at
                FROM {self.MEMBERSHIP_INVITE_TABLE}
                WHERE invite_id = ?
                """,
                (invite_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "invite_id": row[0],
            "organization_id": row[1],
            "workspace_id": row[2],
            "target_scope_type": row[3],
            "email": row[4],
            "target_role": row[5],
            "invite_token": row[6],
            "status": row[7],
            "invited_by_principal_id": row[8],
            "accepted_by_principal_id": row[9],
            "revoked_by_principal_id": row[10],
            "expires_at": row[11],
            "accepted_at": row[12],
            "revoked_at": row[13],
            "revoke_reason": row[14],
            "created_at": row[15],
            "updated_at": row[16],
        }

    def fetch_membership_invite_by_token(self, invite_token: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            row = conn.execute(
                f"""
                SELECT invite_id, organization_id, workspace_id, target_scope_type, email, target_role,
                       invite_token, status, invited_by_principal_id, accepted_by_principal_id,
                       revoked_by_principal_id, expires_at, accepted_at, revoked_at, revoke_reason,
                       created_at, updated_at
                FROM {self.MEMBERSHIP_INVITE_TABLE}
                WHERE invite_token = ?
                """,
                (invite_token,),
            ).fetchone()
        if not row:
            return None
        return {
            "invite_id": row[0],
            "organization_id": row[1],
            "workspace_id": row[2],
            "target_scope_type": row[3],
            "email": row[4],
            "target_role": row[5],
            "invite_token": row[6],
            "status": row[7],
            "invited_by_principal_id": row[8],
            "accepted_by_principal_id": row[9],
            "revoked_by_principal_id": row[10],
            "expires_at": row[11],
            "accepted_at": row[12],
            "revoked_at": row[13],
            "revoke_reason": row[14],
            "created_at": row[15],
            "updated_at": row[16],
        }

    def list_membership_invites(
        self,
        organization_id: str,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        email: str | None = None,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            query = f"""
                SELECT invite_id, organization_id, workspace_id, target_scope_type, email, target_role,
                       invite_token, status, invited_by_principal_id, accepted_by_principal_id,
                       revoked_by_principal_id, expires_at, accepted_at, revoked_at, revoke_reason,
                       created_at, updated_at
                FROM {self.MEMBERSHIP_INVITE_TABLE}
                WHERE organization_id = ?
            """
            params: list[str | None] = [organization_id]
            if workspace_id is None:
                query += " AND workspace_id IS NULL"
            else:
                query += " AND workspace_id = ?"
                params.append(workspace_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            if email:
                query += " AND email = ?"
                params.append(email.strip().lower())
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "invite_id": row[0],
                "organization_id": row[1],
                "workspace_id": row[2],
                "target_scope_type": row[3],
                "email": row[4],
                "target_role": row[5],
                "invite_token": row[6],
                "status": row[7],
                "invited_by_principal_id": row[8],
                "accepted_by_principal_id": row[9],
                "revoked_by_principal_id": row[10],
                "expires_at": row[11],
                "accepted_at": row[12],
                "revoked_at": row[13],
                "revoke_reason": row[14],
                "created_at": row[15],
                "updated_at": row[16],
            }
            for row in rows
        ]

    def upsert_workspace_invite(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.WORKSPACE_INVITE_TABLE} (
                    invite_id, workspace_id, email, role, invite_token, invited_by_principal_id,
                    created_at, updated_at, revoked, accepted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(invite_id) DO UPDATE SET
                    workspace_id=excluded.workspace_id,
                    email=excluded.email,
                    role=excluded.role,
                    invite_token=excluded.invite_token,
                    invited_by_principal_id=excluded.invited_by_principal_id,
                    updated_at=excluded.updated_at,
                    revoked=excluded.revoked,
                    accepted_at=excluded.accepted_at
                """,
                (
                    record["invite_id"],
                    record["workspace_id"],
                    record["email"],
                    record["role"],
                    record["invite_token"],
                    record["invited_by_principal_id"],
                    record["created_at"],
                    record["updated_at"],
                    int(record.get("revoked", 0)),
                    record.get("accepted_at"),
                ),
            )
            conn.commit()
        return self.fetch_workspace_invite(record["invite_id"])

    def fetch_workspace_invite(self, invite_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT invite_id, workspace_id, email, role, invite_token, invited_by_principal_id,
                       created_at, updated_at, revoked, accepted_at
                FROM {self.WORKSPACE_INVITE_TABLE}
                WHERE invite_id = ?
                """,
                (invite_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "invite_id": row[0],
            "workspace_id": row[1],
            "email": row[2],
            "role": row[3],
            "invite_token": row[4],
            "invited_by_principal_id": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "revoked": bool(row[8]),
            "accepted_at": row[9],
        }

    def fetch_workspace_invite_by_token(self, invite_token: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT invite_id, workspace_id, email, role, invite_token, invited_by_principal_id,
                       created_at, updated_at, revoked, accepted_at
                FROM {self.WORKSPACE_INVITE_TABLE}
                WHERE invite_token = ?
                """,
                (invite_token,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "invite_id": row[0],
            "workspace_id": row[1],
            "email": row[2],
            "role": row[3],
            "invite_token": row[4],
            "invited_by_principal_id": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "revoked": bool(row[8]),
            "accepted_at": row[9],
        }

    def upsert_oidc_provider(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.OIDC_PROVIDER_TABLE} (
                    provider_id, organization_id, provider_key, issuer, discovery_url,
                    client_id, client_secret_encrypted, scopes_json, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    provider_key=excluded.provider_key,
                    issuer=excluded.issuer,
                    discovery_url=excluded.discovery_url,
                    client_id=excluded.client_id,
                    client_secret_encrypted=excluded.client_secret_encrypted,
                    scopes_json=excluded.scopes_json,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    record["provider_id"],
                    record["organization_id"],
                    record["provider_key"],
                    record["issuer"],
                    record["discovery_url"],
                    record["client_id"],
                    record["client_secret_encrypted"],
                    json.dumps(record.get("scopes_json") or []),
                    int(record.get("enabled", 1)),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_oidc_provider(record["provider_id"])

    def fetch_oidc_provider(self, provider_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT provider_id, organization_id, provider_key, issuer, discovery_url,
                       client_id, client_secret_encrypted, scopes_json, enabled, created_at, updated_at
                FROM {self.OIDC_PROVIDER_TABLE}
                WHERE provider_id = ?
                """,
                (provider_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "provider_id": row[0],
            "organization_id": row[1],
            "provider_key": row[2],
            "issuer": row[3],
            "discovery_url": row[4],
            "client_id": row[5],
            "client_secret_encrypted": row[6],
            "scopes_json": json.loads(row[7] or "[]"),
            "enabled": bool(row[8]),
            "created_at": row[9],
            "updated_at": row[10],
        }

    def fetch_oidc_provider_by_key(self, organization_id: str, provider_key: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT provider_id, organization_id, provider_key, issuer, discovery_url,
                       client_id, client_secret_encrypted, scopes_json, enabled, created_at, updated_at
                FROM {self.OIDC_PROVIDER_TABLE}
                WHERE organization_id = ? AND provider_key = ?
                """,
                (organization_id, provider_key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "provider_id": row[0],
            "organization_id": row[1],
            "provider_key": row[2],
            "issuer": row[3],
            "discovery_url": row[4],
            "client_id": row[5],
            "client_secret_encrypted": row[6],
            "scopes_json": json.loads(row[7] or "[]"),
            "enabled": bool(row[8]),
            "created_at": row[9],
            "updated_at": row[10],
        }

    def upsert_organization_domain(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.ORGANIZATION_DOMAIN_TABLE} (
                    domain_id, organization_id, domain, verified_at, join_mode, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    domain=excluded.domain,
                    verified_at=excluded.verified_at,
                    join_mode=excluded.join_mode,
                    updated_at=excluded.updated_at
                """,
                (
                    record["domain_id"],
                    record["organization_id"],
                    record["domain"],
                    record.get("verified_at"),
                    record["join_mode"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_organization_domain(record["domain_id"])

    def fetch_organization_domain(self, domain_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT domain_id, organization_id, domain, verified_at, join_mode, created_at, updated_at
                FROM {self.ORGANIZATION_DOMAIN_TABLE}
                WHERE domain_id = ?
                """,
                (domain_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "domain_id": row[0],
            "organization_id": row[1],
            "domain": row[2],
            "verified_at": row[3],
            "join_mode": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def fetch_organization_domain_by_name(self, domain: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT domain_id, organization_id, domain, verified_at, join_mode, created_at, updated_at
                FROM {self.ORGANIZATION_DOMAIN_TABLE}
                WHERE domain = ?
                """,
                (domain,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "domain_id": row[0],
            "organization_id": row[1],
            "domain": row[2],
            "verified_at": row[3],
            "join_mode": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def insert_audit_log(self, record: dict):
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.AUDIT_LOG_TABLE} (
                    actor_principal_id, workspace_id, action, target_type, target_id, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("actor_principal_id"),
                    record.get("workspace_id"),
                    record["action"],
                    record["target_type"],
                    record["target_id"],
                    json.dumps(record.get("detail_json") or {}),
                    record["created_at"],
                ),
            )
            conn.commit()

    def fetch_audit_logs(
        self,
        *,
        workspace_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        actor_principal_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            params: list[object] = []
            query = f"""
                SELECT audit_id, actor_principal_id, workspace_id, action, target_type, target_id, detail_json, created_at
                FROM {self.AUDIT_LOG_TABLE}
            """
            clauses = []
            if workspace_id:
                clauses.append("workspace_id = ?")
                params.append(workspace_id)
            if action:
                clauses.append("action = ?")
                params.append(action)
            if target_type:
                clauses.append("target_type = ?")
                params.append(target_type)
            if actor_principal_id:
                clauses.append("actor_principal_id = ?")
                params.append(actor_principal_id)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY audit_id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "audit_id": row[0],
                "actor_principal_id": row[1],
                "workspace_id": row[2],
                "action": row[3],
                "target_type": row[4],
                "target_id": row[5],
                "detail_json": json.loads(row[6] or "{}"),
                "created_at": row[7],
            }
            for row in rows
        ]

    def upsert_workspace_policy(self, record: dict) -> dict:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.WORKSPACE_POLICY_TABLE} (workspace_id, allowed_regions_json, allowed_markets_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    allowed_regions_json=excluded.allowed_regions_json,
                    allowed_markets_json=excluded.allowed_markets_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record["workspace_id"],
                    json.dumps(record.get("allowed_regions_json") or []),
                    json.dumps(record.get("allowed_markets_json") or []),
                    record["updated_at"],
                ),
            )
            conn.commit()
        return self.fetch_workspace_policy(record["workspace_id"])

    def fetch_workspace_policy(self, workspace_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_access_control_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT workspace_id, allowed_regions_json, allowed_markets_json, updated_at
                FROM {self.WORKSPACE_POLICY_TABLE}
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "workspace_id": row[0],
            "allowed_regions_json": json.loads(row[1] or "[]"),
            "allowed_markets_json": json.loads(row[2] or "[]"),
            "updated_at": row[3],
        }

    def acquire_system_lock(
        self,
        name: str,
        *,
        owner: str,
        ttl_seconds: int,
        now_utc: datetime | None = None,
    ) -> bool:
        lock_key = f"lock:{name}"
        now_utc = now_utc or datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(seconds=ttl_seconds)
        payload = json.dumps(
            {
                "owner": owner,
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            },
            sort_keys=True,
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT value FROM system_status WHERE key = ?", (lock_key,))
            row = cursor.fetchone()

            if row:
                try:
                    current = json.loads(row[0])
                except json.JSONDecodeError:
                    current = {}
                current_expires_at = current.get("expires_at")

                expired = True
                if current_expires_at:
                    try:
                        current_expiry_dt = datetime.fromisoformat(current_expires_at.replace("Z", "+00:00"))
                        expired = current_expiry_dt <= now_utc
                    except ValueError:
                        expired = True

                if not expired:
                    conn.rollback()
                    return False

                cursor.execute(
                    "UPDATE system_status SET value = ? WHERE key = ?",
                    (payload, lock_key),
                )
            else:
                cursor.execute(
                    "INSERT INTO system_status (key, value) VALUES (?, ?)",
                    (lock_key, payload),
                )

            conn.commit()
            return True

    def release_system_lock(self, name: str, *, owner: str) -> bool:
        lock_key = f"lock:{name}"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT value FROM system_status WHERE key = ?", (lock_key,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return False

            try:
                current = json.loads(row[0])
            except json.JSONDecodeError:
                current = {}

            if current.get("owner") != owner:
                conn.rollback()
                return False

            cursor.execute("DELETE FROM system_status WHERE key = ?", (lock_key,))
            conn.commit()
            return True
