"""Agent 基线计量脚本（交叉验证修正行动 P0，2026-08-06）。

回答独立质疑代理的元问题："在没有失败模式分布、token/延迟基线的情况下，
如何排除真正瓶颈不在调研结论针对的位置？"

采集三类基线数据（全部只读，不改任何业务数据）：
1. 静态上下文体积：system prompt / schema 目录 / 工具 schema 的字符数与
   估算 token 数 —— 这是每个 ReAct 步都要重复预付的固定成本；
2. 执行日志统计（agent_execution_log）：状态分布、模式分布、降级触发率、
   时延百分位、工具调用数、失败原因分桶；
3. Observation 体积分布：历史轨迹中工具结果原始大小 vs 3000 字符回灌上限，
   量化"不可逆压缩"的实际发生频率。

产出：控制台报告 + output/agent_baseline_<date>.json
用法：python scripts/agent_baseline_measurement.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.support import ensure_repo_import_paths  # noqa: E402

ensure_repo_import_paths()

# 中英混合文本的粗估系数（字符/token）。中文约 1.5-2 字符/token，英文约 4；
# 取 2.5 作保守中值。所有 token 数字均为估算，报告中标注。
CHARS_PER_TOKEN = 2.5


def est_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


def percentiles(values, ps=(50, 90, 99)):
    if not values:
        return {}
    s = sorted(values)
    out = {"min": s[0], "max": s[-1], "mean": round(statistics.mean(s), 1)}
    for p in ps:
        idx = min(len(s) - 1, int(len(s) * p / 100))
        out[f"p{p}"] = s[idx]
    return out


# =============================================================================
# 1. 静态上下文体积
# =============================================================================


def measure_static_context() -> dict:
    from agent.prompts import SYSTEM_PROMPT, DATABASE_SCHEMA_CONTEXT
    from agent.tools import get_tool_registry

    registry = get_tool_registry()
    tools_json = json.dumps(registry.to_openai_tools(), ensure_ascii=False)
    n_tools = len(registry.list_definitions())

    sys_prompt_chars = len(SYSTEM_PROMPT)
    schema_ctx_chars = len(DATABASE_SCHEMA_CONTEXT)

    return {
        "system_prompt_chars": sys_prompt_chars,
        "system_prompt_est_tokens": est_tokens(SYSTEM_PROMPT),
        "db_schema_context_chars": schema_ctx_chars,
        "db_schema_context_est_tokens": est_tokens(DATABASE_SCHEMA_CONTEXT),
        "fixed_prefix_total_chars": sys_prompt_chars + schema_ctx_chars,
        "fixed_prefix_est_tokens": est_tokens(SYSTEM_PROMPT + DATABASE_SCHEMA_CONTEXT),
        "tool_count": n_tools,
        "tool_schema_json_chars": len(tools_json),
        "tool_schema_est_tokens": est_tokens(tools_json),
        "per_turn_fixed_overhead_est_tokens": est_tokens(
            SYSTEM_PROMPT + DATABASE_SCHEMA_CONTEXT + tools_json
        ),
        "note": f"token 为估算（{CHARS_PER_TOKEN} 字符/token 假设）；"
        "该固定开销在每个 ReAct 步随历史累积重复预付，是 KV-cache/预算优化的直接标的",
    }


# =============================================================================
# 2.5 工具子集 profile 测量（PoC：按阶段暴露的静态收益估算）
# =============================================================================


def measure_tool_profiles() -> list:
    from agent.tool_profiles import TOOL_PROFILES, profile_tools
    from agent.tools import get_tool_registry

    registry = get_tool_registry()
    schemas = {
        d["function"]["name"]: json.dumps(d, ensure_ascii=False)
        for d in registry.to_openai_tools()
    }
    full_chars = sum(len(s) for s in schemas.values())

    rows = [{
        "profile": "full",
        "tool_count": len(schemas),
        "schema_chars": full_chars,
        "est_tokens": int(full_chars / CHARS_PER_TOKEN),
        "saved_vs_full_pct": 0.0,
    }]
    for name in TOOL_PROFILES:
        visible = profile_tools(name)
        chars = sum(len(s) for n, s in schemas.items() if n in visible)
        rows.append({
            "profile": name,
            "tool_count": len([n for n in schemas if n in visible]),
            "schema_chars": chars,
            "est_tokens": int(chars / CHARS_PER_TOKEN),
            "saved_vs_full_pct": round((full_chars - chars) / full_chars * 100, 1),
        })
    return rows


# =============================================================================
# 2. 执行日志统计
# =============================================================================


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    return cursor.fetchone() is not None


def analyze_execution_log() -> dict:
    from deps import get_db

    db = get_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if not _table_exists(cursor, "agent_execution_log"):
            return {"available": False, "note": "agent_execution_log 表不存在（尚无执行历史）"}

        cursor.execute(
            "SELECT id, query, workflow_type, status, total_duration_ms, "
            "steps_json, report_json, created_at FROM agent_execution_log "
            "ORDER BY created_at DESC LIMIT 1000"
        )
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

    n = len(rows)
    if n == 0:
        return {"available": True, "total_runs": 0, "note": "表存在但无记录"}

    status_dist: dict = {}
    workflow_dist: dict = {}
    mode_dist: dict = {}
    degraded_count = 0
    durations = []
    tool_calls_per_run = []
    tool_status_dist: dict = {}
    failure_buckets: dict = {"timeout": [], "no_data": [], "unknown_tool": [], "other": []}
    observation_sizes = []
    oversized_observations = 0  # >3000 字符（回灌截断阈值）
    usage_totals = []

    for row in rows:
        status_dist[row.get("status")] = status_dist.get(row.get("status"), 0) + 1
        workflow_dist[row.get("workflow_type")] = workflow_dist.get(row.get("workflow_type"), 0) + 1
        if row.get("total_duration_ms"):
            durations.append(float(row["total_duration_ms"]))

        report = {}
        try:
            report = json.loads(row.get("report_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        meta = report.get("metadata", {}) if isinstance(report, dict) else {}
        mode = meta.get("mode", "unknown")
        mode_dist[mode] = mode_dist.get(mode, 0) + 1
        if meta.get("llm_degraded"):
            degraded_count += 1
        usage = meta.get("llm_usage")
        if isinstance(usage, dict) and usage.get("total_tokens"):
            usage_totals.append(usage["total_tokens"])

        steps = []
        try:
            steps = json.loads(row.get("steps_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            pass
        run_tool_calls = 0
        for step in steps if isinstance(steps, list) else []:
            action = step.get("action")
            if not action:
                continue
            run_tool_calls += 1
            obs = step.get("observation") or {}
            obs_status = obs.get("status", "unknown")
            tool_status_dist[obs_status] = tool_status_dist.get(obs_status, 0) + 1

            if obs_status != "success":
                err = (obs.get("error_message") or "").lower()
                name = obs.get("tool_name", "?")
                if "timeout" in err or obs_status == "timeout":
                    failure_buckets["timeout"].append(name)
                elif "no_data" in err or "no data" in err:
                    failure_buckets["no_data"].append(name)
                elif "unknown tool" in err:
                    failure_buckets["unknown_tool"].append(name)
                else:
                    failure_buckets["other"].append(f"{name}: {(obs.get('error_message') or '')[:80]}")

            data = obs.get("data")
            if isinstance(data, dict) and data:
                size = len(json.dumps(data, ensure_ascii=False, default=str))
                observation_sizes.append(size)
                if size > 3000:
                    oversized_observations += 1

        if run_tool_calls:
            tool_calls_per_run.append(run_tool_calls)

    failure_summary = {k: {"count": len(v), "samples": v[:5]} for k, v in failure_buckets.items()}

    return {
        "available": True,
        "total_runs": n,
        "status_distribution": status_dist,
        "workflow_type_distribution": workflow_dist,
        "mode_distribution": mode_dist,
        "degradation_rate_pct": round(degraded_count / n * 100, 1),
        "degraded_runs": degraded_count,
        "duration_ms": percentiles(durations),
        "tool_calls_per_run": percentiles(tool_calls_per_run),
        "tool_observation_status_distribution": tool_status_dist,
        "failure_buckets": failure_summary,
        "observation_size_chars": percentiles(observation_sizes),
        "observations_over_3000_chars": oversized_observations,
        "observation_over_3000_pct": (
            round(oversized_observations / len(observation_sizes) * 100, 1)
            if observation_sizes else 0
        ),
        "llm_usage_total_tokens": percentiles(usage_totals),
        "llm_usage_sample_count": len(usage_totals),
    }


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    print("=" * 72)
    print("Agent 基线计量（只读）", datetime.now(timezone.utc).isoformat())
    print("=" * 72)

    ctx = measure_static_context()
    print("\n[1] 静态上下文体积（每 ReAct 步的固定预付成本）")
    for k, v in ctx.items():
        print(f"  {k}: {v}")

    print("\n[1.5] 工具子集 profile 测量（PoC：按阶段暴露）")
    profiles = measure_tool_profiles()
    for row in profiles:
        print(
            f"  {row['profile']:<24} tools={row['tool_count']:>2}  "
            f"~{row['est_tokens']:>5} token/步  省 {row['saved_vs_full_pct']:>5}%"
        )

    print("\n[2] 执行日志统计（agent_execution_log）")
    try:
        log = analyze_execution_log()
    except Exception as exc:  # 数据库不可达时仍输出静态部分
        log = {"available": False, "note": f"数据库不可达: {exc}"}
    print(json.dumps(log, ensure_ascii=False, indent=2))

    out_dir = os.path.join(_REPO_ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"agent_baseline_{datetime.now().strftime('%Y%m%d')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"measured_at": datetime.now(timezone.utc).isoformat(),
             "static_context": ctx, "tool_profiles": profiles,
             "execution_log": log},
            f, ensure_ascii=False, indent=2,
        )
    print(f"\n已保存: {out_path}")


if __name__ == "__main__":
    main()
