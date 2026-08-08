"""扩样本 A/B 批跑（PoC：按阶段工具子集暴露，2026-08-07）。

对 5 组用例各跑 基线(全量) + 实验(阶段子集) 两臂，结果落盘到
output/replay_results/，供 agent_ab_judge.py 评分与汇总。

用例矩阵（含一个"子集缺工具"反例 G07，验证降级体验）：
    G01 SA1 负电价分析        → stage1_screening
    G11 SA1 日均价 SQL 查询    → data_exploration
    G06 WEM ESS 收入潜力       → stage2_revenue
    G07 WEM NPV 分析（反例）   → stage1_screening（无投资工具，应诚实说明）
    G09 三区域 NPV 对比        → multi_region_decision

用法：python scripts/run_agent_ab_batch.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.join(_REPO_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

from tests.support import ensure_repo_import_paths  # noqa: E402

ensure_repo_import_paths()

from run_agent_golden_replay import _load_case, replay, save_result  # noqa: E402

AB_MATRIX = [
    ("G11", "data_exploration"),
    ("G06", "stage2_revenue"),
    ("G07", "stage1_screening"),
    ("G01", "stage1_screening"),
    ("G09", "multi_region_decision"),
]


async def main() -> None:
    summary = []
    for case_id, profile in AB_MATRIX:
        case = _load_case(case_id)
        for arm_profile in (None, profile):
            label = f"{case_id}/{arm_profile or 'full'}"
            print(f"\n=== 回放 {label} ===", flush=True)
            t0 = time.perf_counter()
            try:
                result = await replay(case, arm_profile)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! 回放异常: {exc}", flush=True)
                summary.append({"run": label, "error": str(exc)})
                continue
            if not result.get("healthy"):
                print(f"  !! LLM 不可用: {result.get('error')}", flush=True)
                summary.append({"run": label, "error": result.get("error")})
                break  # LLM 挂了后续无意义
            path = save_result(result, case_id, arm_profile)
            usage = result.get("llm_usage") or {}
            print(
                f"  status={result.get('status')} tools={result.get('tool_call_count')} "
                f"tokens={usage.get('total_tokens')} "
                f"wall={round(time.perf_counter() - t0)}s -> {os.path.basename(path)}",
                flush=True,
            )
            summary.append({
                "run": label,
                "status": result.get("status"),
                "tool_call_count": result.get("tool_call_count"),
                "total_tokens": usage.get("total_tokens"),
                "duration_ms": result.get("duration_ms"),
            })

    out_path = os.path.join(_REPO_ROOT, "output", "replay_results", "ab_batch_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n批跑完成，汇总: {out_path}", flush=True)
    for row in summary:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
