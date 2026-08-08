"""黄金轨迹 live 回放 harness（PoC A/B 验证用，2026-08-06）。

对 tests/agent_golden_cases.json 中指定用例走真实 orchestrator.run_stream
（真实 LLM + 真实 PG 数据），采集 PoC 对比所需指标：
状态、耗时、工具调用序列、llm_usage、降级标记、可见工具数。

用法：
    python scripts/run_agent_golden_replay.py --case G01
    python scripts/run_agent_golden_replay.py --case G01 --profile stage1_screening

对比示例（工具子集暴露 A/B）：
    先跑不带 --profile（基线），再带 --profile（实验），对比 llm_usage/耗时/工具序列。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.support import ensure_repo_import_paths  # noqa: E402

ensure_repo_import_paths()

_SPEC_PATH = os.path.join(_REPO_ROOT, "tests", "agent_golden_cases.json")


def _load_case(case_id: str) -> dict:
    with open(_SPEC_PATH, "r", encoding="utf-8") as f:
        spec = json.load(f)
    for case in spec["cases"]:
        if case["id"] == case_id:
            return case
    raise SystemExit(f"用例 {case_id} 不存在")


async def replay(case: dict, profile: str | None, enable_routing: bool = False) -> dict:
    from agent.orchestrator import get_orchestrator
    from agent.schemas import AgentContext, MarketType

    orch = get_orchestrator()

    # 健康探测先行（历史教训：403 代理配置存在但不可用）
    healthy = await orch.llm.health_check()
    if not healthy:
        return {"healthy": False, "error": orch.llm.last_health_error}

    ctx = AgentContext(
        market=MarketType(case.get("market", "NEM")),
        region=case.get("region") or None,
        year=case.get("year"),
        tool_profile=profile,
        enable_tool_routing=enable_routing,
        session_id=None,
    )

    tool_calls = []
    tool_statuses = []
    report_meta = {}
    status = None
    answer = ""
    start = time.perf_counter()

    async for ev in orch.run_stream(query=case["query"], context=ctx):
        etype = ev.get("type")
        if etype == "tool_call":
            tool_calls.append(ev.get("name"))
        elif etype == "tool_result":
            tool_statuses.append(f"{ev.get('name')}:{ev.get('status')}")
        elif etype == "report":
            rep = ev.get("report", {})
            report_meta = rep.get("metadata", {})
            status = rep.get("status")
            answer = ev.get("answer", "") or ""

    return {
        "healthy": True,
        "case_id": case["id"],
        "query": case["query"],
        "profile": profile or "full",
        "status": status,
        "duration_ms": round((time.perf_counter() - start) * 1000),
        "tool_call_count": len(tool_calls),
        "tool_sequence": tool_calls,
        "tool_statuses": tool_statuses,
        "llm_usage": report_meta.get("llm_usage"),
        "visible_tool_count": report_meta.get("visible_tool_count"),
        "tool_profile": report_meta.get("tool_profile"),
        "tool_profile_source": report_meta.get("tool_profile_source"),
        "llm_degraded": report_meta.get("llm_degraded", False),
        "mode": report_meta.get("mode"),
        "answer": answer,
    }


def save_result(result: dict, case_id: str, profile: str | None) -> str:
    """将回放结果落盘到 output/replay_results/，返回路径。"""
    out_dir = os.path.join(_REPO_ROOT, "output", "replay_results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{case_id}_{profile or 'full'}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="黄金轨迹 live 回放")
    parser.add_argument("--case", required=True, help="黄金用例 id，如 G01")
    parser.add_argument("--profile", default=None,
                        help="工具子集 profile（PoC 实验组）；缺省=全量基线")
    parser.add_argument("--route", action="store_true",
                        help="开启意图路由（无显式 profile 时自动分类）")
    args = parser.parse_args()

    case = _load_case(args.case)
    result = asyncio.run(replay(case, args.profile, args.route))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 结果落盘（供 LLM-as-Judge 与 A/B 汇总使用；route 模式独立命名防覆盖基线）
    if result.get("healthy"):
        label = args.profile or ("routed" if args.route else "full")
        print(f"[saved] {save_result(result, args.case, label)}", file=sys.stderr)


if __name__ == "__main__":
    main()
