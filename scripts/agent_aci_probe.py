"""ACI 工具描述探测（B5，2026-08-08）。

让 LLM 只依据工具描述（function-calling schema）为一组代表意图选择工具，
不真正执行——审计 31 个工具描述的"模型视角可用性"（Anthropic BEA 附录 2
的 ACI 理念：工具描述需要与提示词同级别的工程投入）。

产出：每个意图的选中工具 vs 期望工具（支持多可接受答案）、误选清单、
解析失败清单。误选模式是改写工具描述的直接依据。

用法：
    python scripts/agent_aci_probe.py            # 全量意图
    python scripts/agent_aci_probe.py --limit 5  # 抽样
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.support import ensure_repo_import_paths  # noqa: E402

ensure_repo_import_paths()

# 意图 → 可接受工具集合（多个合法答案时用集合表达）
INTENTS = [
    ("SA1 2025 年的平均电价和负电价比例是多少", {"price_trend_analysis", "data_query", "timeseries_analysis"}),
    ("查询 SA1 2025 年 6 月的日均价格明细", {"data_query", "timeseries_analysis"}),
    ("对 NSW1 做投资 NPV/IRR 分析", {"investment_analysis"}),
    ("对比 SA1、QLD1、NSW1 三个区域的投资 NPV", {"compare_regions", "multi_market_analysis"}),
    ("评估 VIC1 的 FCAS 辅助服务收入机会", {"fcas_analysis"}),
    ("预测 FCAS 价格天花板崩塌风险", {"fcas_collapse_forecast"}),
    ("检查某区域 BESS 装机饱和程度", {"saturation_check"}),
    ("跑一次蒙特卡洛商户风险模拟", {"merchant_risk_simulate"}),
    ("画一张 NSW1 的价格持续曲线", {"timeseries_analysis", "generate_chart"}),
    ("把 VIC1 的月度均价导出成 CSV 文件", {"export_data"}),
    ("先检查所有市场的数据质量", {"data_quality_check"}),
    ("未来 24 小时电网风险预测", {"grid_forecast"}),
    ("分析峰谷价差套利窗口", {"peak_analysis"}),
    ("极端价格尖峰的利润机会有多大", {"spike_profit_analysis"}),
    ("哪个区域现在进入的投资时机最好", {"regional_timing_score", "regional_ranking"}),
    ("BESS 收入被新增容量蚕食的趋势", {"cannibalization_forecast"}),
    ("20 年前瞻价差情景推演", {"forward_spread_projection"}),
    ("把收入拆成基础套利/FCAS/极端事件三层", {"risk_stratification"}),
]

PROBE_SYSTEM = (
    "你是工具选择器。只根据提供的工具定义，为用户意图选择最合适的 1 个工具，"
    "并给出最小参数。只输出 JSON：{\"tool\": \"...\", \"arguments\": {...}, \"reason\": \"一句话\"}"
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text


async def probe_one(llm, tools_schema: list, intent: str) -> dict:
    try:
        response = await llm.chat(
            [
                {"role": "system", "content": PROBE_SYSTEM},
                {"role": "user", "content": f"用户意图：{intent}"},
            ],
            tools=tools_schema,
        )
    except Exception as exc:  # noqa: BLE001
        return {"intent": intent, "error": f"LLM 调用失败: {exc}"}

    # 优先从 function-calling 的 tool_calls 取；其次解析正文 JSON
    chosen = None
    if response.tool_calls:
        chosen = response.tool_calls[0].get("name")
    else:
        try:
            parsed = json.loads(_strip_fences(response.content))
            chosen = parsed.get("tool")
        except (json.JSONDecodeError, TypeError):
            m = re.search(r'"tool"\s*:\s*"([\w]+)"', response.content or "")
            chosen = m.group(1) if m else None

    return {"intent": intent, "chosen": chosen, "raw": (response.content or "")[:200]}


def _normalize_tool_name(name) -> str:
    """容忍命名空间前缀（如 functions.investment_analysis → investment_analysis）。"""
    if not name:
        return name
    return name.rsplit(".", 1)[-1]


async def main() -> None:
    parser = argparse.ArgumentParser(description="ACI 工具描述探测")
    parser.add_argument("--limit", type=int, default=0, help="只探测前 N 个意图（0=全量）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="只重跑上次报告中 PARSE-FAIL 的意图并合并结果")
    args = parser.parse_args()

    from agent.llm_adapter import get_llm_adapter
    from agent.tools import get_tool_registry

    llm = get_llm_adapter()
    if not await llm.health_check():
        print(f"LLM 不可用: {llm.last_health_error}")
        return

    registry = get_tool_registry()
    tools_schema = registry.to_openai_tools()
    registered = {d["function"]["name"] for d in tools_schema}

    out_dir = os.path.join(_REPO_ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "aci_probe_report.json")

    # --retry-failed：从上次报告取失败意图重跑，成功后从失败清单移除
    prior = {"mismatches": [], "parse_errors": []}
    retry_intents = None
    if args.retry_failed and os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            prior = json.load(f)
        retry_intents = {e["intent"] for e in prior.get("parse_errors", []) if e.get("intent")}

    intents_by_text = {text: acc for text, acc in INTENTS}
    if retry_intents is not None:
        intents = [(t, a) for t, a in INTENTS if t in retry_intents]
    else:
        intents = INTENTS[: args.limit] if args.limit else INTENTS

    mismatches, parse_errors, hits = [], [], []

    for intent, acceptable in intents:
        result = await probe_one(llm, tools_schema, intent)
        chosen = _normalize_tool_name(result.get("chosen"))
        result["chosen"] = chosen
        if chosen is None:
            parse_errors.append(result)
            mark = "PARSE-FAIL"
        elif chosen not in registered:
            parse_errors.append(result)
            mark = "HALLUCINATED-TOOL"
        elif chosen in acceptable:
            hits.append(result)
            mark = "OK"
        else:
            mismatches.append(result)
            mark = "MISMATCH"
        print(f"[{mark}] {intent}\n       chosen={chosen} acceptable={sorted(acceptable)}")

    print("\n=== 汇总 ===")
    print(f"命中 {len(hits)}/{len(intents)}，误选 {len(mismatches)}，解析/幻觉 {len(parse_errors)}")
    if mismatches:
        print("\n误选明细（工具描述改写的直接依据）：")
        for m in mismatches:
            print(f"  - {m['intent']} -> {m['chosen']}")

    # --retry-failed 模式：合并旧报告（移除已重试成功的条目）
    if retry_intents is not None:
        fixed = {h["intent"] for h in hits}
        merged_parse_errors = [
            e for e in prior.get("parse_errors", [])
            if e.get("intent") not in retry_intents or e.get("intent") not in fixed
        ]
        # 本次仍失败的保留新记录（已在 parse_errors 中）
        merged_parse_errors = [
            e for e in merged_parse_errors if e.get("intent") not in {p.get("intent") for p in parse_errors}
        ] + parse_errors
        merged = {
            "hits": prior.get("hits", 0) + len(hits),
            "mismatches": prior.get("mismatches", []) + mismatches,
            "parse_errors": merged_parse_errors,
        }
    else:
        merged = {"hits": len(hits), "mismatches": mismatches, "parse_errors": parse_errors}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
