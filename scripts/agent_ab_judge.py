"""LLM-as-Judge：A/B 输出质量配对评分（PoC 维度 8.3 落地，2026-08-07）。

读取 output/replay_results/ 下同一用例的两臂回放结果（基线 full vs 实验 profile），
让独立 LLM 评审按 rubric 打分并裁决胜负。

偏差控制（依据调研维度 8.3 最佳实践）：
- 配对比较优于绝对打分：输出 winner + 各维度分差依据；
- 位置偏差对冲：按用例 id 哈希决定 A/B 呈现顺序，结果映射回真实臂；
- 匿名：不告知评审哪臂是基线/实验、用了多少工具，只给查询与回答；
- rubric 明确化：四维（数值可溯源/完整性/诚实性/简洁性）各 1-5 分。

用法：
    python scripts/agent_ab_judge.py --case G11 --profile data_exploration
    python scripts/agent_ab_judge.py --all   # 扫描 replay_results 自动配对
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import re
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.support import ensure_repo_import_paths  # noqa: E402

ensure_repo_import_paths()

_RESULTS_DIR = os.path.join(_REPO_ROOT, "output", "replay_results")

JUDGE_PROMPT = """你是能源投资分析平台的独立质量评审。用户提出了一个分析请求，
两个分析系统分别给出了回答（回答 X 与回答 Y）。请按以下维度各自打 1-5 分：

1. numerical_grounding 数值可溯源性：回答中的数字是否看起来来自真实计算/数据，
   是否有编造或凭空出现的数字（编造数字该维度直接给 1 分）
2. completeness 完整性：是否正面回答了用户的问题
3. honesty 诚实性：对无法完成的分析、缺失的数据是否如实声明；
   注意——若系统因能力受限而诚实说明"无法完成某分析"，这是正确行为，
   诚实性应给高分，不应因"没做"而扣分；反过来，能力不足却硬编结果应给低分
4. conciseness 简洁性：是否聚焦、无冗余

最后给出 winner（X / Y / tie）与不超过 80 字的 reason。

## 用户请求
{query}

## 回答 X
{answer_x}

## 回答 Y
{answer_y}

## 输出格式（只输出 JSON，不要其他内容）
{{"scores_x": {{"numerical_grounding": 0, "completeness": 0, "honesty": 0, "conciseness": 0}},
 "scores_y": {{"numerical_grounding": 0, "completeness": 0, "honesty": 0, "conciseness": 0}},
 "winner": "X|Y|tie", "reason": "..."}}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text


def _parse_json_loose(text: str) -> dict:
    """从评审输出中解析 JSON（容忍代码块包裹与前后杂讯）。"""
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


async def judge_pair(case_id: str, profile: str) -> dict:
    from agent.llm_adapter import get_llm_adapter

    base_path = os.path.join(_RESULTS_DIR, f"{case_id}_full.json")
    exp_path = os.path.join(_RESULTS_DIR, f"{case_id}_{profile}.json")
    for p in (base_path, exp_path):
        if not os.path.exists(p):
            return {"case_id": case_id, "error": f"缺少回放结果: {os.path.basename(p)}"}

    with open(base_path, "r", encoding="utf-8") as f:
        base = json.load(f)
    with open(exp_path, "r", encoding="utf-8") as f:
        exp = json.load(f)

    # 位置偏差对冲：按用例 id 哈希决定呈现顺序
    swap = (sum(ord(c) for c in case_id) % 2) == 1
    x, y = (exp, base) if swap else (base, exp)

    prompt = JUDGE_PROMPT.format(
        query=base.get("query", ""),
        answer_x=(x.get("answer") or "(无回答)")[:4000],
        answer_y=(y.get("answer") or "(无回答)")[:4000],
    )

    llm = get_llm_adapter()
    if not await llm.health_check():
        return {"case_id": case_id, "error": f"LLM 不可用: {llm.last_health_error}"}

    response = await llm.chat([
        {"role": "system", "content": "你是严格、公正的质量评审。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ])
    verdict = _parse_json_loose(response.content)

    # 映射回真实臂
    if swap:
        verdict["scores_baseline"], verdict["scores_experiment"] = (
            verdict.pop("scores_y"), verdict.pop("scores_x"))
        verdict["winner"] = {"X": "experiment", "Y": "baseline", "tie": "tie"}[verdict["winner"]]
    else:
        verdict["scores_baseline"], verdict["scores_experiment"] = (
            verdict.pop("scores_x"), verdict.pop("scores_y"))
        verdict["winner"] = {"X": "baseline", "Y": "experiment", "tie": "tie"}[verdict["winner"]]

    verdict.update({
        "case_id": case_id,
        "profile": profile,
        "baseline_tokens": (base.get("llm_usage") or {}).get("total_tokens"),
        "experiment_tokens": (exp.get("llm_usage") or {}).get("total_tokens"),
    })

    out_path = os.path.join(_RESULTS_DIR, f"judge_{case_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    return verdict


def _discover_pairs() -> list:
    """扫描 replay_results，自动发现可配对的 (case, profile)。"""
    pairs = []
    for path in glob.glob(os.path.join(_RESULTS_DIR, "*_full.json")):
        case_id = os.path.basename(path)[:-len("_full.json")]
        for exp in glob.glob(os.path.join(_RESULTS_DIR, f"{case_id}_*.json")):
            name = os.path.basename(exp)
            if name.endswith("_full.json") or name.startswith("judge_"):
                continue
            profile = name[len(case_id) + 1:-len(".json")]
            pairs.append((case_id, profile))
    return sorted(set(pairs))


async def main() -> None:
    parser = argparse.ArgumentParser(description="A/B 输出质量 LLM 评审")
    parser.add_argument("--case")
    parser.add_argument("--profile")
    parser.add_argument("--all", action="store_true", help="自动配对全部已有回放结果")
    args = parser.parse_args()

    pairs = _discover_pairs() if args.all else [(args.case, args.profile)]
    for case_id, profile in pairs:
        verdict = await judge_pair(case_id, profile)
        if verdict.get("error"):
            print(f"[{case_id}] 跳过: {verdict['error']}")
            continue
        print(f"\n=== {case_id} (profile={profile}) ===")
        print(f"  baseline  得分: {verdict['scores_baseline']}  tokens={verdict['baseline_tokens']}")
        print(f"  experiment得分: {verdict['scores_experiment']}  tokens={verdict['experiment_tokens']}")
        print(f"  winner: {verdict['winner']}  reason: {verdict['reason']}")


if __name__ == "__main__":
    asyncio.run(main())
