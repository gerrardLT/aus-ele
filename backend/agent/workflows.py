"""Predefined Workflow Templates.

Provides deterministic workflow templates that execute when:
1. The LLM is unavailable (graceful degradation)
2. The user explicitly requests a specific workflow template
3. The query clearly matches a known workflow pattern

Each template defines an ordered sequence of tool calls with optional
parallel execution groups for performance optimization.
"""

from __future__ import annotations

from typing import Dict, List

from agent.schemas import WorkflowTemplate


# =============================================================================
# Workflow Template Definitions
# =============================================================================

WORKFLOW_TEMPLATES: Dict[str, WorkflowTemplate] = {
    "full_investment_feasibility": WorkflowTemplate(
        id="full_investment_feasibility",
        name="完整投资可行性分析",
        description="完整 7 阶段 BESS 投资可行性分析：市场筛选 → 收入深潜（含尖峰与基准）→ 饱和竞争 → 投资前景 → 联合优化回测 → 财务建模 → 风险分层",
        steps=[
            "data_quality_check",
            "market_screening",
            "price_trend_analysis",
            "peak_analysis",
            "fcas_analysis",
            # 收入深潜扩容（2026-08-13）：尖峰捕获 + 市场基准锚定并入并行组
            "spike_profit_analysis",
            "bess_revenue_benchmark",
            "saturation_check",
            "forward_spread_projection",
            "merchant_risk_simulate",
            "co_optimized_backtest",
            "investment_analysis",
            "risk_stratification",
        ],
        parallel_groups=[
            [0, 1],           # data_quality + market_screening in parallel
            [2, 3, 4, 5, 6],  # 收入深潜五工具并行：price_trend/peak/fcas/spike/benchmark
            [7, 8, 9],        # saturation + forward_spread + merchant_risk in parallel
            [10],             # co-optimized backtest alone (heavy)
            [11, 12],         # investment + risk_stratification in parallel
        ],
        default_params={
            "power_mw": 100.0,
            "duration_hours": 4.0,
        },
    ),
    "quick_market_overview": WorkflowTemplate(
        id="quick_market_overview",
        name="快速市场概览",
        description="快速了解当前市场状况：数据质量、价格趋势、电网预测、区域排名",
        steps=[
            "data_quality_check",
            "price_trend_analysis",
            "grid_forecast",
            "regional_ranking",
        ],
        parallel_groups=[
            [0, 1],      # data_quality + price_trend in parallel
            [2, 3],      # grid_forecast + ranking in parallel
        ],
        default_params={},
    ),
    "fcas_opportunity": WorkflowTemplate(
        id="fcas_opportunity",
        name="FCAS 机会评估",
        description="聚焦 FCAS 收入机会评估：当前 FCAS 价格、崩溃风险、饱和影响",
        steps=[
            "fcas_analysis",
            "fcas_collapse_forecast",
            "saturation_check",
            "cannibalization_forecast",
        ],
        parallel_groups=[
            [0, 1],      # fcas_analysis + collapse_forecast in parallel
            [2, 3],      # saturation + cannibalization in parallel
        ],
        default_params={
            "capacity_mw": 100.0,
        },
    ),
    "revenue_deep_dive": WorkflowTemplate(
        id="revenue_deep_dive",
        name="收入结构深潜",
        description="深入分析收入结构：价差分析、尖峰利润、FCAS 拆分、联合优化回测",
        steps=[
            "price_trend_analysis",
            "peak_analysis",
            "spike_profit_analysis",
            "fcas_analysis",
            "co_optimized_backtest",
        ],
        parallel_groups=[
            [0, 1, 2, 3],  # All price-based analyses in parallel
            [4],            # Backtest after understanding revenue structure
        ],
        default_params={
            "power_mw": 100.0,
            "duration_hours": 4.0,
        },
    ),
    "risk_assessment": WorkflowTemplate(
        id="risk_assessment",
        name="风险评估",
        description="综合风险评估：商户风险蒙特卡洛模拟、自蚀预测、FCAS 崩溃风险、收入分层",
        steps=[
            "merchant_risk_simulate",
            "cannibalization_forecast",
            "fcas_collapse_forecast",
            "risk_stratification",
            "cross_validation",
        ],
        parallel_groups=[
            [0, 1, 2],   # Monte Carlo + cannibalization + FCAS collapse in parallel
            [3, 4],       # stratification + cross-validation in parallel
        ],
        default_params={
            "power_mw": 100.0,
            "duration_hours": 4.0,
            "n_simulations": 500,
        },
    ),
    "regional_comparison": WorkflowTemplate(
        id="regional_comparison",
        name="区域对比分析",
        description="跨区域投资潜力对比：筛选评分、价差水平、时机评分综合比较",
        steps=[
            "market_screening",
            "regional_ranking",
            "regional_timing_score",
        ],
        parallel_groups=[
            [0, 1],      # screening + ranking in parallel
            [2],          # timing score
        ],
        default_params={},
    ),
    # U6: Investment screening — quick multi-region NPV comparison + decision
    "investment_screening": WorkflowTemplate(
        id="investment_screening",
        name="投资筛选",
        description="快速多区域投资筛选：compare_regions NPV 排名 → 蚕食检查 → 决策建议",
        steps=[
            "compare_regions",
            "cannibalization_forecast",
            "investment_analysis",
        ],
        parallel_groups=[
            [0],          # compare_regions first
            [1],          # cannibalization check
            [2],          # detailed analysis on best region
        ],
        default_params={
            "regions": ["SA1", "QLD1", "NSW1", "VIC1"],
            "power_mw": 100.0,
            "duration_hours": 4.0,
        },
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================


def get_workflow_template(template_id: str) -> WorkflowTemplate | None:
    """Get a workflow template by ID."""
    return WORKFLOW_TEMPLATES.get(template_id)


def list_workflow_templates() -> List[WorkflowTemplate]:
    """List all available workflow templates."""
    return list(WORKFLOW_TEMPLATES.values())


def match_workflow_from_query(query: str) -> str | None:
    """Attempt to match a user query to a predefined workflow template.

    Uses simple keyword matching as a heuristic. Returns template ID or None.
    This is used when LLM is unavailable to still provide intelligent routing.
    """
    query_lower = query.lower()

    # Full investment feasibility
    if any(kw in query_lower for kw in ["完整", "可行性", "full", "feasibility", "全面分析", "投资分析"]):
        return "full_investment_feasibility"

    # Quick market overview
    if any(kw in query_lower for kw in ["概览", "overview", "快速", "quick", "市场情况", "current"]):
        return "quick_market_overview"

    # FCAS opportunity
    if any(kw in query_lower for kw in ["fcas", "调频", "辅助服务", "ancillary"]):
        return "fcas_opportunity"

    # Revenue deep dive
    if any(kw in query_lower for kw in ["收入", "revenue", "价差", "spread", "套利", "arbitrage"]):
        return "revenue_deep_dive"

    # Risk assessment
    if any(kw in query_lower for kw in ["风险", "risk", "monte carlo", "蒙特卡洛", "cannibalization"]):
        return "risk_assessment"

    # Regional comparison
    if any(kw in query_lower for kw in ["对比", "compare", "排名", "ranking", "哪个区域"]):
        return "regional_comparison"

    return None
