"""按阶段工具子集暴露（PoC，2026-08-06）。

基线计量发现：每 ReAct 步固定预付 ~6.8k token，其中 31 个工具的
function-calling schema 占 ~5.6k（83%），而每步实际只与少数工具相关。

本模块实现调研图谱维度 4/5 的"中间选项"：按投资漏斗阶段静态暴露工具子集。
关键设计约束（来自 Manus 反证与交叉验证）：
- **静态而非动态**：一次运行内可见集确定后不再变化，避免中途增删工具
  破坏 KV-cache 前缀、引发悬空引用幻觉；
- **默认关闭**：只有显式传入 tool_profile 才启用子集，未指定时保持
  全量动作空间（现有行为零变化）；
- **全局工具恒可见**：data_quality_check 是系统提示词规则 6 的首步要求。

解析优先级：显式 profile > 模板推导 > None（全量）。
"""

from __future__ import annotations

from typing import Collection, Optional

# 任何 profile 下都恒可见的工具（系统提示词要求始终先跑数据质量检查）
ALWAYS_VISIBLE = ["data_quality_check"]

# 阶段 → 工具子集（名称必须与 tools.py 注册名一致，测试校验）
TOOL_PROFILES = {
    "stage1_screening": [
        "market_screening", "price_trend_analysis", "regional_ranking",
        "timeseries_analysis", "market_pulse",
        # 规则知识库（2026-08-12）：常识/机制类问题的兜底入口
        "grid_knowledge_lookup",
    ],
    "stage2_revenue": [
        "spike_profit_analysis", "peak_analysis", "fcas_analysis",
        "price_trend_analysis",
        # Phase 1（2026-08-12）：收益基准锚定，回答“市场基准收益多少”类问题
        "bess_revenue_benchmark",
        # 规则知识库（2026-08-12）：FCAS/容量等机制解释带来源引用
        "grid_knowledge_lookup",
        # 事件案例库（2026-08-13）：收益异动归因的历史案例引用
        "market_event_lookup",
        # G06 教训（扩样本 A/B 2026-08-07）：收入类问题需附风险边界，
        # 缺失崩塌/饱和工具时实验组回答被 judge 判负；对齐 fcas_opportunity 模板
        "fcas_collapse_forecast", "saturation_check", "cannibalization_forecast",
    ],
    "stage3_saturation": [
        "saturation_check", "cannibalization_forecast",
        # 管线知识库（2026-08-13）：饱和/竞争判断的供给端事实基础
        "asset_pipeline_lookup",
    ],
    "stage4_outlook": [
        "cannibalization_forecast", "fcas_collapse_forecast",
        "regional_timing_score", "merchant_risk_simulate",
        "forward_spread_projection", "saturation_check",
        # 覆盖审计（§10.4-2）：G04 风险评估需 risk_stratification，对齐 risk_assessment 模板
        "risk_stratification",
        # 事件案例库（2026-08-13）：崩塌/退役/负价等情景的历史案例支撑
        "market_event_lookup",
        # 管线知识库（2026-08-13）：前瞻风险需管线供给事实
        "asset_pipeline_lookup",
    ],
    "stage5_backtest": [
        "co_optimized_backtest", "price_trend_analysis", "fcas_analysis",
    ],
    "stage6_financial": [
        "investment_analysis", "risk_stratification", "cross_validation",
        "narrative_attribution", "compare_regions", "scenario_simulation",
        "portfolio_analysis", "generate_report",
        # Phase 1（2026-08-12）：投资测算需市场基准锚定对照
        "bess_revenue_benchmark",
        # 规则知识库（2026-08-12）：CIS/PFR/注册等制度语境支撑投资结论
        "grid_knowledge_lookup",
    ],
    "data_exploration": [
        "data_query", "timeseries_analysis", "export_data",
        "generate_chart", "market_pulse",
    ],
    "multi_region_decision": [
        "compare_regions", "multi_market_analysis", "investment_analysis",
        "portfolio_analysis", "scenario_simulation",
        # 覆盖审计（§10.4-2）：G08 区域排名对比需筛选/排名工具
        "market_screening", "regional_ranking",
    ],
}


def profile_tools(profile: str) -> Optional[frozenset]:
    """返回 profile 的可见工具集（含全局工具）；未知 profile 返回 None（全量）。"""
    tools = TOOL_PROFILES.get(profile)
    if tools is None:
        return None
    return frozenset(tools) | frozenset(ALWAYS_VISIBLE)


def resolve_visible_tools(
    explicit: Optional[str] = None,
    template_id: Optional[str] = None,
    query: Optional[str] = None,
) -> Optional[frozenset]:
    """解析本次运行的可见工具集。

    Args:
        explicit: 显式指定的 profile 名（AgentContext.tool_profile）。
        template_id: 强制模板 id——以模板步骤 + 全局工具为可见集。
        query: 自由查询——先试关键词路由，命中则以对应模板步骤为可见集。

    Returns:
        可见工具名 frozenset；None 表示不做过滤（全量动作空间）。
    """
    if explicit:
        return profile_tools(explicit)

    from agent.workflows import get_workflow_template, match_workflow_from_query

    tid = template_id or (match_workflow_from_query(query) if query else None)
    if tid:
        template = get_workflow_template(tid)
        if template is not None:
            return frozenset(template.steps) | frozenset(ALWAYS_VISIBLE)

    return None


# =============================================================================
# 意图路由器（§10.4-1：子集暴露启用的前置条件）
# =============================================================================

# 关键词规则，**从具体到泛化**排序，首中即止。设计红线：
# 宁缺毋滥——不确定就返回 None 回落全量动作空间（安全网），
# 误路由牺牲完整性（G06 教训）比多花 token 更糟糕。
_ROUTING_RULES = [
    ("data_exploration", [
        "sql", "导出", "csv", "json 文件", "画图", "图表", "持续曲线",
        "日均价", "月度均价", "小时级",
    ]),
    ("multi_region_decision", [
        "对比", "比较", "哪个区域", "排名", "多市场", "nem 和 wem",
        "多个区域",
    ]),
    ("stage6_financial", [
        "npv", "irr", "投资可行性", "投资分析", "回收期", "备忘录",
        "投资 npv", "值得投资吗",
    ]),
    ("stage4_outlook", [
        "风险评估", "蒙特卡洛", "崩塌", "蚕食", "饱和", "前瞻",
        "商户风险", "管线", "在建项目", "并网",
    ]),
    ("stage2_revenue", [
        "fcas", "辅助服务", "ess", "价差套利", "收入结构", "尖峰利润",
        "收入潜力", "套利收入", "基准收益", "收益基准", "benchmark",
    ]),
    ("stage1_screening", [
        "负电价", "负价", "价格趋势", "价格结构", "市场概览", "筛选",
        "充电策略", "什么是", "规则", "机制", "政策", "制度", "常识",
        "大停电", "黑系统", "煤电退役", "历史上",
    ]),
]


def route_query_to_profile(query: str) -> Optional[str]:
    """将自由查询分类到 profile（确定性关键词规则，无 LLM 成本）。

    Returns:
        profile 名；无法归类时返回 None——调用方必须回落全量动作空间。
    """
    if not query:
        return None
    q = query.lower()
    # 深度研究类查询需要全阶段工具链（如完整可行性 11 步），
    # 直接回落全量动作空间——宁多花 token 不牺牲完整性（G06 教训）
    deep_keywords = ["完整", "全面分析", "full feasibility", "深度分析", "尽调"]
    if any(kw in q for kw in deep_keywords):
        return None
    for profile, keywords in _ROUTING_RULES:
        if any(kw in q for kw in keywords):
            return profile
    return None
