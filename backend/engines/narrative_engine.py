"""Narrative Engine — 因果归因文本生成引擎。

使用结构化模板（非 LLM）为每个分析模块的关键指标生成因果归因文本。
引用 coal_retirement_schedule.json 和 capacity_data.json 数据，
通过 EventRegistry 获取供需事件信息。

设计原则：
- 可重复性：相同输入始终产生相同输出
- 可测试性：模板输出可通过属性测试验证
- 低延迟：无需外部 API 调用
- 可审计：模板逻辑透明可追溯

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 15.1, 15.2
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from models.forward_price_models import (
    EventRegistry,
    EventType,
    ScenarioType,
    SupplyDemandEvent,
)
from models.narrative_models import (
    CausalAttribution,
    CausalFactor,
    DriverType,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Mapping from EventType to DriverType
_EVENT_TO_DRIVER: Dict[EventType, DriverType] = {
    EventType.COAL_CLOSURE: DriverType.COAL_CLOSURE,
    EventType.BESS_COMMISSIONING: DriverType.BESS_SATURATION,
    EventType.NETWORK_AUGMENTATION: DriverType.NETWORK_AUGMENTATION,
}


# =============================================================================
# Engine
# =============================================================================


class NarrativeEngine:
    """因果归因文本生成引擎。

    使用模板驱动方式为分析模块输出生成结构化因果归因，
    引用 EventRegistry 中的供需事件和数据文件中的市场数据。
    """

    def __init__(self, event_registry: EventRegistry) -> None:
        self.event_registry = event_registry
        self.templates = self._load_templates()
        self._coal_data = self._load_coal_data()
        self._capacity_data = self._load_capacity_data()

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    def _load_templates(self) -> Dict[str, Dict[str, str]]:
        """加载结构化叙事模板。

        模板按类别组织，每个模板包含可插值的文本片段。
        使用 Python str.format() 进行变量替换。
        """
        return {
            "spread_attribution": {
                "coal_closure": (
                    "{plant_name} ({capacity_mw:.0f}MW) 预计于 {closure_date} 退役，"
                    "减少 {region} 区域基荷供应，推高价差约 {contribution:.1f} $/MWh"
                ),
                "bess_saturation": (
                    "{project_name} ({capacity_mw:.0f}MW) 投运压缩峰值价差，"
                    "降低 {region} 区域价差约 {contribution:.1f} $/MWh"
                ),
                "network_augmentation": (
                    "{project_name} 互联线 ({capacity_mw:.0f}MW) 投运促进区域价格收敛，"
                    "压缩 {region} 区域价差约 {contribution:.1f} $/MWh"
                ),
                "summary": (
                    "{region} {year}年 {scenario} 情景价差为 {spread:.1f} $/MWh，"
                    "主要受{driver_summary}驱动"
                ),
                "generic": (
                    "{region} {year}年价差为 {spread:.1f} $/MWh，"
                    "基于历史价格分布参数计算"
                ),
            },
            "revenue_change": {
                "increase": (
                    "{region} 收入从 {year_from}年 ${revenue_from:,.0f}/MW "
                    "增长至 {year_to}年 ${revenue_to:,.0f}/MW "
                    "(+{change_pct:.1f}%)，主要受{driver_summary}驱动"
                ),
                "decrease": (
                    "{region} 收入从 {year_from}年 ${revenue_from:,.0f}/MW "
                    "下降至 {year_to}年 ${revenue_to:,.0f}/MW "
                    "({change_pct:.1f}%)，主要受{driver_summary}驱动"
                ),
                "stable": (
                    "{region} 收入在 {year_from}-{year_to}年间保持稳定 "
                    "(约 ${revenue_to:,.0f}/MW)，无重大供需事件影响"
                ),
                "generic": (
                    "{region} 收入从 {year_from}年 ${revenue_from:,.0f}/MW "
                    "变化至 {year_to}年 ${revenue_to:,.0f}/MW，"
                    "基于历史价格分布参数计算"
                ),
            },
            "module_conclusion": {
                "forward_price": (
                    "{region} 前瞻电价分析结论：{conclusion_text}"
                ),
                "risk_stratification": (
                    "{region} 风险分层分析结论：{conclusion_text}"
                ),
                "financial_model": (
                    "{region} 财务模型分析结论：{conclusion_text}"
                ),
                "generic": (
                    "{region} {module_name} 模块分析结论：基于历史价格分布参数计算"
                ),
            },
        }

    def _load_coal_data(self) -> List[Dict]:
        """加载煤电退役时间表数据。"""
        coal_path = DATA_DIR / "coal_retirement_schedule.json"
        if not coal_path.exists():
            logger.warning("煤电退役数据文件不存在: %s", coal_path)
            return []
        try:
            with open(coal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("retirements", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载煤电退役数据失败: %s", e)
            return []

    def _load_capacity_data(self) -> List[Dict]:
        """加载 BESS 容量数据。"""
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            logger.warning("容量数据文件不存在: %s", capacity_path)
            return []
        try:
            with open(capacity_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("projects", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载容量数据失败: %s", e)
            return []

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_events_for_region_year(
        self, region: str, year: int
    ) -> List[SupplyDemandEvent]:
        """获取指定区域和年份的相关事件。"""
        return [
            event
            for event in self.event_registry.events
            if event.region == region and event.expected_date.year == year
        ]

    def _get_events_affecting_year(
        self, region: str, year: int
    ) -> List[SupplyDemandEvent]:
        """获取在指定年份或之前发生、影响该年份价差的事件。"""
        return [
            event
            for event in self.event_registry.events
            if event.region == region and event.expected_date.year <= year
        ]

    def _get_events_in_range(
        self, region: str, year_from: int, year_to: int
    ) -> List[SupplyDemandEvent]:
        """获取指定区域和年份范围内的事件。"""
        return [
            event
            for event in self.event_registry.events
            if event.region == region
            and year_from <= event.expected_date.year <= year_to
        ]

    def _calculate_spread_contribution(
        self, event: SupplyDemandEvent, base_spread: float
    ) -> float:
        """计算单个事件对价差的贡献量。

        Coal closures (factor > 1) increase spread.
        BESS/Network (factor < 1) decrease spread.
        """
        return base_spread * (event.spread_impact_factor - 1.0)

    def _build_causal_factors_from_events(
        self, events: List[SupplyDemandEvent], base_spread: float
    ) -> List[CausalFactor]:
        """从事件列表构建因果因素列表。"""
        factors: List[CausalFactor] = []
        for event in events:
            contribution = self._calculate_spread_contribution(event, base_spread)
            driver_type = _EVENT_TO_DRIVER.get(event.event_type, DriverType.COAL_CLOSURE)

            # Determine source reference from data files
            source_ref = self._get_source_reference(event)

            factors.append(
                CausalFactor(
                    driver_name=event.name,
                    driver_type=driver_type,
                    contribution_amount=contribution,
                    contribution_pct=None,
                    source_reference=source_ref,
                )
            )
        return factors

    def _get_source_reference(self, event: SupplyDemandEvent) -> str:
        """获取事件的数据来源引用。"""
        if event.event_type == EventType.COAL_CLOSURE:
            return "coal_retirement_schedule.json"
        elif event.event_type == EventType.BESS_COMMISSIONING:
            return "capacity_data.json"
        elif event.event_type == EventType.NETWORK_AUGMENTATION:
            return "capacity_data.json (interconnectors)"
        return "event_registry"

    def _build_driver_summary(self, events: List[SupplyDemandEvent]) -> str:
        """构建驱动因素摘要文本。"""
        if not events:
            return "历史价格分布参数"

        summaries: List[str] = []
        coal_events = [e for e in events if e.event_type == EventType.COAL_CLOSURE]
        bess_events = [
            e for e in events if e.event_type == EventType.BESS_COMMISSIONING
        ]
        network_events = [
            e for e in events if e.event_type == EventType.NETWORK_AUGMENTATION
        ]

        if coal_events:
            names = "、".join(e.name for e in coal_events[:3])
            summaries.append(f"煤电退役（{names}）")
        if bess_events:
            names = "、".join(e.name for e in bess_events[:3])
            summaries.append(f"BESS 投运（{names}）")
        if network_events:
            names = "、".join(e.name for e in network_events[:3])
            summaries.append(f"网络增强（{names}）")

        return "、".join(summaries)

    def _calculate_contribution_percentages(
        self, factors: List[CausalFactor]
    ) -> List[CausalFactor]:
        """计算各因素的贡献百分比。"""
        if not factors:
            return factors

        total_abs = sum(abs(f.contribution_amount) for f in factors)
        if total_abs == 0:
            return factors

        updated: List[CausalFactor] = []
        for factor in factors:
            pct = (abs(factor.contribution_amount) / total_abs) * 100.0
            updated.append(
                CausalFactor(
                    driver_name=factor.driver_name,
                    driver_type=factor.driver_type,
                    contribution_amount=factor.contribution_amount,
                    contribution_pct=round(pct, 1),
                    source_reference=factor.source_reference,
                )
            )
        return updated

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def generate_spread_attribution(
        self,
        region: str,
        year: int,
        scenario: ScenarioType,
        current_spread: float,
        base_spread: float,
    ) -> CausalAttribution:
        """生成价差因果归因。

        解释为什么指定区域/年份/情景的价差具有当前值，
        追溯到具体的供需事件（煤电退役、BESS 投运、网络增强）。

        Args:
            region: NEM 区域或 WEM
            year: 目标年份
            scenario: 情景类型 (Central/High/Low)
            current_spread: 当前/预测价差 ($/MWh)
            base_spread: 基准价差 ($/MWh)，用于计算各事件贡献

        Returns:
            CausalAttribution 对象，包含结构化因果解释
        """
        # 降级策略：事件注册表为空时生成通用归因文本
        if not self.event_registry.events:
            template = self.templates["spread_attribution"]["generic"]
            narrative = template.format(
                region=region,
                year=year,
                spread=current_spread,
            )
            return CausalAttribution(
                metric_name="mean_spread",
                metric_value=current_spread,
                metric_unit="$/MWh",
                narrative_text=narrative,
                causal_factors=[],
                region=region,
                year=year,
                scenario=scenario.value,
            )

        # 获取影响该年份价差的事件
        events = self._get_events_affecting_year(region, year)

        # 构建因果因素
        factors = self._build_causal_factors_from_events(events, base_spread)
        factors = self._calculate_contribution_percentages(factors)

        # 构建驱动因素摘要
        driver_summary = self._build_driver_summary(events)

        # 生成叙事文本
        template = self.templates["spread_attribution"]["summary"]
        narrative = template.format(
            region=region,
            year=year,
            scenario=scenario.value,
            spread=current_spread,
            driver_summary=driver_summary,
        )

        return CausalAttribution(
            metric_name="mean_spread",
            metric_value=current_spread,
            metric_unit="$/MWh",
            narrative_text=narrative,
            causal_factors=factors,
            region=region,
            year=year,
            scenario=scenario.value,
        )

    def generate_revenue_change_attribution(
        self,
        region: str,
        year_from: int,
        year_to: int,
        revenue_from: float,
        revenue_to: float,
        scenario: ScenarioType,
    ) -> CausalAttribution:
        """生成年度收入变化归因。

        解释为什么收入在两个年份之间发生变化，
        将变化归因到具体事件（煤电退役增加波动性、BESS 饱和压缩价差等）。

        Args:
            region: NEM 区域或 WEM
            year_from: 起始年份
            year_to: 目标年份
            revenue_from: 起始年份收入 ($/MW)
            revenue_to: 目标年份收入 ($/MW)
            scenario: 情景类型

        Returns:
            CausalAttribution 对象，包含收入变化的因果解释
        """
        change = revenue_to - revenue_from
        change_pct = (change / revenue_from * 100.0) if revenue_from != 0 else 0.0

        # 降级策略：事件注册表为空时生成通用归因文本
        if not self.event_registry.events:
            template = self.templates["revenue_change"]["generic"]
            narrative = template.format(
                region=region,
                year_from=year_from,
                year_to=year_to,
                revenue_from=revenue_from,
                revenue_to=revenue_to,
            )
            return CausalAttribution(
                metric_name="revenue_change",
                metric_value=change,
                metric_unit="$/MW",
                narrative_text=narrative,
                causal_factors=[],
                region=region,
                year=year_to,
                scenario=scenario.value,
            )

        # 获取年份范围内的事件
        events = self._get_events_in_range(region, year_from, year_to)

        # 构建因果因素（使用 revenue_from 作为基准计算贡献）
        factors = self._build_revenue_factors(events, revenue_from, change)
        factors = self._calculate_contribution_percentages(factors)

        # 构建驱动因素摘要
        driver_summary = self._build_driver_summary(events)

        # 选择模板
        if abs(change_pct) < 2.0:
            template = self.templates["revenue_change"]["stable"]
            narrative = template.format(
                region=region,
                year_from=year_from,
                year_to=year_to,
                revenue_to=revenue_to,
            )
        elif change > 0:
            template = self.templates["revenue_change"]["increase"]
            narrative = template.format(
                region=region,
                year_from=year_from,
                year_to=year_to,
                revenue_from=revenue_from,
                revenue_to=revenue_to,
                change_pct=change_pct,
                driver_summary=driver_summary,
            )
        else:
            template = self.templates["revenue_change"]["decrease"]
            narrative = template.format(
                region=region,
                year_from=year_from,
                year_to=year_to,
                revenue_from=revenue_from,
                revenue_to=revenue_to,
                change_pct=change_pct,
                driver_summary=driver_summary,
            )

        return CausalAttribution(
            metric_name="revenue_change",
            metric_value=change,
            metric_unit="$/MW",
            narrative_text=narrative,
            causal_factors=factors,
            region=region,
            year=year_to,
            scenario=scenario.value,
        )

    def generate_module_conclusion(
        self,
        module_name: str,
        region: str,
        metrics: Dict[str, float],
    ) -> CausalAttribution:
        """为模块输出生成结论性归因文本。

        为指定分析模块的关键输出指标生成综合性因果解释，
        包含至少一个因果归因语句链接输出值到具体市场驱动因素。

        Args:
            module_name: 模块名称 (forward_price, risk_stratification, financial_model)
            region: NEM 区域或 WEM
            metrics: 模块输出指标字典，如 {"npv": 1234.5, "irr": 0.12}

        Returns:
            CausalAttribution 对象，包含模块结论的因果解释
        """
        # 选择主要指标作为归因目标
        primary_metric = self._select_primary_metric(metrics)
        metric_name = primary_metric[0]
        metric_value = primary_metric[1]

        # 降级策略：事件注册表为空时生成通用归因文本
        if not self.event_registry.events:
            template = self.templates["module_conclusion"].get(
                module_name, self.templates["module_conclusion"]["generic"]
            )
            narrative = template.format(
                region=region,
                module_name=module_name,
                conclusion_text="基于历史价格分布参数计算",
            )
            return CausalAttribution(
                metric_name=metric_name,
                metric_value=metric_value,
                metric_unit=self._get_metric_unit(metric_name),
                narrative_text=narrative,
                causal_factors=[],
                region=region,
                year=date.today().year,
            )

        # 获取区域内所有未来事件
        current_year = date.today().year
        events = self._get_events_affecting_year(region, current_year + 20)

        # 构建因果因素
        factors = self._build_conclusion_factors(events, module_name, metrics)
        factors = self._calculate_contribution_percentages(factors)

        # 生成结论文本
        conclusion_text = self._build_conclusion_text(
            module_name, region, metrics, events
        )

        template = self.templates["module_conclusion"].get(
            module_name, self.templates["module_conclusion"]["generic"]
        )
        narrative = template.format(
            region=region,
            module_name=module_name,
            conclusion_text=conclusion_text,
        )

        return CausalAttribution(
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=self._get_metric_unit(metric_name),
            narrative_text=narrative,
            causal_factors=factors,
            region=region,
            year=current_year,
        )

    # -------------------------------------------------------------------------
    # Private Helpers for Revenue Attribution
    # -------------------------------------------------------------------------

    def _build_revenue_factors(
        self,
        events: List[SupplyDemandEvent],
        base_revenue: float,
        total_change: float,
    ) -> List[CausalFactor]:
        """从事件列表构建收入变化因果因素。"""
        factors: List[CausalFactor] = []
        if not events:
            return factors

        # 分配贡献量：按事件影响因子的偏离程度加权
        total_weight = sum(abs(e.spread_impact_factor - 1.0) for e in events)
        if total_weight == 0:
            return factors

        for event in events:
            weight = abs(event.spread_impact_factor - 1.0) / total_weight
            contribution = total_change * weight
            driver_type = _EVENT_TO_DRIVER.get(event.event_type, DriverType.COAL_CLOSURE)
            source_ref = self._get_source_reference(event)

            factors.append(
                CausalFactor(
                    driver_name=event.name,
                    driver_type=driver_type,
                    contribution_amount=round(contribution, 2),
                    contribution_pct=None,
                    source_reference=source_ref,
                )
            )
        return factors

    # -------------------------------------------------------------------------
    # Private Helpers for Module Conclusion
    # -------------------------------------------------------------------------

    def _select_primary_metric(
        self, metrics: Dict[str, float]
    ) -> tuple[str, float]:
        """选择主要指标用于归因。优先级：npv > irr > revenue > 第一个。"""
        priority = ["npv", "irr", "revenue", "mean_spread"]
        for key in priority:
            if key in metrics:
                return (key, metrics[key])
        # 返回第一个指标
        if metrics:
            first_key = next(iter(metrics))
            return (first_key, metrics[first_key])
        return ("unknown", 0.0)

    def _get_metric_unit(self, metric_name: str) -> str:
        """获取指标的单位。"""
        units = {
            "npv": "$",
            "irr": "%",
            "revenue": "$/MW",
            "mean_spread": "$/MWh",
            "revenue_change": "$/MW",
        }
        return units.get(metric_name, "")

    def _build_conclusion_factors(
        self,
        events: List[SupplyDemandEvent],
        module_name: str,
        metrics: Dict[str, float],
    ) -> List[CausalFactor]:
        """为模块结论构建因果因素列表。

        选取影响最大的前 5 个事件作为因果因素。
        """
        if not events:
            return []

        # 按影响因子偏离程度排序，取前 5 个
        sorted_events = sorted(
            events, key=lambda e: abs(e.spread_impact_factor - 1.0), reverse=True
        )[:5]

        factors: List[CausalFactor] = []
        for event in sorted_events:
            driver_type = _EVENT_TO_DRIVER.get(event.event_type, DriverType.COAL_CLOSURE)
            source_ref = self._get_source_reference(event)

            # 使用影响因子作为贡献量的代理
            contribution = (event.spread_impact_factor - 1.0) * 100.0

            factors.append(
                CausalFactor(
                    driver_name=event.name,
                    driver_type=driver_type,
                    contribution_amount=round(contribution, 2),
                    contribution_pct=None,
                    source_reference=source_ref,
                )
            )
        return factors

    def _build_conclusion_text(
        self,
        module_name: str,
        region: str,
        metrics: Dict[str, float],
        events: List[SupplyDemandEvent],
    ) -> str:
        """构建模块结论文本。"""
        coal_events = [e for e in events if e.event_type == EventType.COAL_CLOSURE]
        bess_events = [
            e for e in events if e.event_type == EventType.BESS_COMMISSIONING
        ]

        parts: List[str] = []

        if coal_events:
            total_coal_mw = sum(e.capacity_mw for e in coal_events)
            parts.append(
                f"未来 {len(coal_events)} 座煤电站退役 "
                f"(合计 {total_coal_mw:.0f}MW) 将推高价格波动性"
            )

        if bess_events:
            total_bess_mw = sum(e.capacity_mw for e in bess_events)
            parts.append(
                f"{len(bess_events)} 个 BESS 项目投运 "
                f"(合计 {total_bess_mw:.0f}MW) 将压缩峰值价差"
            )

        if not parts:
            return "基于历史价格分布参数计算"

        return "；".join(parts)
