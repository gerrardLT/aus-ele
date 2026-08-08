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

# FROM/JOIN/括号/单引号——用于扫描 SQL 引用的表名
_TABLE_REF_RE = _re.compile(r"\b(FROM|JOIN)\b|\(|\)|'", _re.IGNORECASE)


def _extract_referenced_tables(sql: str) -> list:
    """提取 SQL 中 FROM/JOIN 引用的表名（小写化）。

    规则：跳过字符串字面量；只认顶层或子查询括号（以 SELECT 开头）内的
    FROM/JOIN，函数调用括号内的 FROM（如 EXTRACT(MONTH FROM col)）不算
    表引用（bug 修复 2026-08-07：旧版正则取第一个 FROM，被 EXTRACT 等
    函数内 FROM 欺骗，导致合法查询被误杀）。
    """
    tables: list = []
    subquery_stack: list = []
    in_str = False
    for m in _TABLE_REF_RE.finditer(sql):
        raw = m.group(0)
        if raw == "'":
            in_str = not in_str
            continue
        if in_str:
            continue
        if raw == "(":
            subquery_stack.append(
                bool(_re.match(r"\s*SELECT\b", sql[m.end():], _re.IGNORECASE))
            )
            continue
        if raw == ")":
            if subquery_stack:
                subquery_stack.pop()
            continue
        # FROM / JOIN 关键字：函数调用括号内的跳过
        if subquery_stack and not subquery_stack[-1]:
            continue
        name_m = _re.match(r"\s+([\w]+)", sql[m.end():])
        if name_m:
            tables.append(name_m.group(1).lower())
    return tables


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

    # 提取 FROM/JOIN 引用的全部表名（含子查询）。
    # 从原始 sql（非大写化的 stripped）抽取并小写化后与白名单比较，
    # 避免大小写不匹配误杀合法查询（bug 修复 2026-07-29）；
    # 解析器升级：跳过 EXTRACT(MONTH FROM col) 等函数内 FROM（2026-08-07）。
    tables = _extract_referenced_tables(sql)
    if not tables:
        return {"status": "error", "error": "无法识别的 FROM 子句"}

    # 所有被引用的表（含子查询/JOIN）都必须在白名单内
    bad = [t for t in tables if t not in _ANALYSIS_TABLES]
    if bad:
        return {
            "status": "error",
            "error": f"表 {', '.join(bad)} 不在允许查询列表中",
            "allowed_tables": sorted(_ANALYSIS_TABLES)[:10],  # Truncate for brevity
        }
    table_name = tables[0]

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
