"""Agent tools with SQL whitelist guard.

Replaces the _exec_data_query tool with a safe version that only allows
queries against analysis tables (not system/auth tables).
"""
import re as _re
from typing import Any, Dict

from agent.schemas import AgentContext, ToolResult, ToolStatus


# Whitelist: tables allowed in data_query tool
_ANALYSIS_TABLES = frozenset([
    "trading_price_2020", "trading_price_2021", "trading_price_2022",
    "trading_price_2023", "trading_price_2024", "trading_price_2025",
    "trading_price_2026",
    "wem_ess_market_price", "wem_ess_capability", "wem_ess_constraint_summary",
    "operational_demand_actual_hh", "operational_demand_forecast_hh",
    "rooftop_pv_actual_measurement", "rooftop_pv_forecast",
    "dispatch_region_summary", "dispatch_interconnector_flow",
    "du_detail_summary", "grid_event_raw", "grid_event_state",
    "grid_event_sync_state", "pdpasa_duid_availability",
    "bom_weather_observation", "data_quality_snapshot", "data_quality_issue",
])

_SQL_FORBIDDEN_PATTERNS = [
    # Block multi-statement injection and modification operations
    r";(?![\s]*[\"'])(?![\s]*--)",           # Not allowed ; without comment/quote after
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|CALL)\b",
]

FORBIDDEN_PAT_RE = _re.compile("|".join(_SQL_FORBIDDEN_PATTERNS), _re.IGNORECASE)


def _exec_data_query_safe(params: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    """Execute a safe read-only SQL query against allowed tables only."""
    import sqlite3 as _sqlite3
    from deps import get_db

    sql = params.get("sql", "").strip()
    if not sql:
        return {"status": "error", "error": "未提供 SQL 查询"}

    # Block obviously dangerous patterns
    if FORBIDDEN_PAT_RE.search(sql):
        return {"status": "error", "error": "SQL 包含禁止关键词或语句"}

    # Only allow SELECT statements
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return {"status": "error", "error": "只允许 SELECT 查询"}

    # Extract table name(s) from FROM clause (very simple parser)
    from_match = _re.search(r"FROM\s+(\w+)", stripped, _re.IGNORECASE | _re.DOTALL)
    if not from_match:
        return {"status": "error", "error": "无法识别的 FROM 子句"}

    table_name = from_match.group(1)
    if table_name not in _ANALYSIS_TABLES:
        return {
            "status": "error",
            "error": f"表 {table_name} 不在允许查询列表中",
            "allowed_tables": list(_ANALYSIS_TABLES)[:10],  # Truncate for brevity
        }

    # Force LIMIT 500
    if "LIMIT" not in stripped:
        sql = sql.rstrip(";") + " LIMIT 500"
    else:
        limit_match = _re.search(r"LIMIT\s+(\d+)", stripped, _re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > 500:
            sql = _re.sub(r"LIMIT\s+\d+", "LIMIT 500", sql, flags=_re.IGNORECASE)

    db = get_db()
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            data = [dict(zip(columns, row)) for row in rows[:500]]
            return {
                "status": "success",
                "table": table_name,
                "columns": columns,
                "row_count": len(data),
                "data": data,
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "sql": sql}
