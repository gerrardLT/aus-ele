"""
Regional Timing Engine for Forward-Looking Investment Scoring.

扩展现有 RegionalRanking，加入前瞻性因素计算区域投资时机评分。

评分维度:
- coal_retirement_impact: 煤电退役带来的波动率增加预期
- pipeline_growth_rate: 管道容量年增长率（负面因素，增长越快竞争越激烈）
- renewable_penetration: 可再生能源渗透率趋势（负价频率代理）
- revenue_trajectory: 历史收入变化方向

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from database import DatabaseManager
from models.capacity_models import CapacityDataLoader
from models.outlook_models import (
    CoalRetirementSchedule,
    MarketExample,
    RegionalTimingResponse,
    RegionTimingScore,
)

logger = logging.getLogger(__name__)

# NEM regions
NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# Default dimension weights
DEFAULT_WEIGHTS = {
    "coal_retirement": 0.30,
    "pipeline_growth": 0.25,
    "renewable_penetration": 0.20,
    "revenue_trajectory": 0.25,
}

# Project root for data file paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RegionalTimingEngine:
    """扩展现有 RegionalRanking，加入前瞻性因素计算区域投资时机评分。

    评分维度:
    - coal_retirement_impact: 煤电退役带来的波动率增加预期 (0-1)
    - pipeline_growth_rate: 管道容量年增长率（负面因素，增长越快分数越低）(0-1)
    - renewable_penetration: 可再生能源渗透率趋势（负价频率代理）(0-1)
    - revenue_trajectory: 历史收入变化方向 (0-1)
    """

    def __init__(
        self,
        db: DatabaseManager,
        capacity_loader: CapacityDataLoader,
        coal_schedule: Optional[CoalRetirementSchedule] = None,
    ):
        self.db = db
        self.capacity_loader = capacity_loader
        self.coal_schedule = coal_schedule

    def score_regions(
        self,
        target_year: int,
        weights: Optional[dict[str, float]] = None,
    ) -> RegionalTimingResponse:
        """计算各区域的前瞻性投资吸引力评分。

        Args:
            target_year: 目标投资年份（当前年 ~ 当前年+5）
            weights: 各维度权重覆盖（可选），键为维度名，值为权重

        Returns:
            RegionalTimingResponse 包含排名、市场案例和结论
        """
        current_year = datetime.now().year

        # Validate target year range
        if target_year < current_year:
            target_year = current_year
        elif target_year > current_year + 5:
            target_year = current_year + 5

        # Resolve weights
        used_weights = dict(DEFAULT_WEIGHTS)
        if weights:
            used_weights.update(weights)

        # Determine if coal data is available
        coal_data_available = self.coal_schedule is not None and len(
            self.coal_schedule.retirements
        ) > 0

        # If coal data unavailable, redistribute weight to other dimensions
        effective_weights = dict(used_weights)
        if not coal_data_available:
            coal_weight = effective_weights.pop("coal_retirement", 0.0)
            remaining_keys = [k for k in effective_weights if k != "coal_retirement"]
            if remaining_keys:
                redistribution = coal_weight / len(remaining_keys)
                for k in remaining_keys:
                    effective_weights[k] += redistribution
            effective_weights["coal_retirement"] = 0.0

        # Score each region
        rankings: list[RegionTimingScore] = []

        for region in NEM_REGIONS:
            dimensions = {}

            # 1. Coal retirement impact
            if coal_data_available:
                dimensions["coal_retirement"] = self.estimate_coal_retirement_impact(
                    region, target_year
                )
            else:
                dimensions["coal_retirement"] = 0.0

            # 2. Pipeline growth (inverted: lower growth = higher score)
            pipeline_growth_rate = self.project_pipeline_growth(region, years_forward=3)
            dimensions["pipeline_growth"] = self._invert_pipeline_score(pipeline_growth_rate)

            # 3. Renewable penetration (negative price frequency as proxy)
            dimensions["renewable_penetration"] = self._compute_renewable_penetration_score(
                region
            )

            # 4. Revenue trajectory
            dimensions["revenue_trajectory"] = self._compute_revenue_trajectory_score(
                region
            )

            # Compute weighted total score
            total_score = sum(
                dimensions[dim] * effective_weights.get(dim, 0.0)
                for dim in dimensions
            )

            # Collect key events for this region
            key_events = self._get_key_events(region, target_year)

            rankings.append(
                RegionTimingScore(
                    region=region,
                    rank=0,  # Will be assigned after sorting
                    total_score=round(total_score, 4),
                    dimensions={k: round(v, 4) for k, v in dimensions.items()},
                    key_events=key_events,
                )
            )

        # Sort by total_score descending and assign ranks
        rankings.sort(key=lambda r: r.total_score, reverse=True)
        for i, score in enumerate(rankings):
            score.rank = i + 1

        # Load market examples
        market_examples = self._load_market_examples()

        # Generate conclusion
        conclusion = self._generate_conclusion(rankings, target_year, coal_data_available)

        return RegionalTimingResponse(
            metadata={
                "market": "NEM",
                "region": "NEM-wide",
                "timezone": "Australia/Sydney",
                "currency": "AUD",
                "methodology_version": "1.0",
                "model": "forward_looking_timing_scorer",
                "dimensions": list(DEFAULT_WEIGHTS.keys()),
            },
            target_year=target_year,
            weights_used=used_weights,
            rankings=rankings,
            coal_data_available=coal_data_available,
            market_examples=market_examples,
            conclusion=conclusion,
        )

    def estimate_coal_retirement_impact(
        self,
        region: str,
        target_year: int,
    ) -> float:
        """估算煤电退役对区域波动率的影响（0-1 分）。

        基于退役容量和 volatility_impact_estimate 计算。
        更多退役 = 更高波动率 = 更多 BESS 套利机会 = 更高分。

        Args:
            region: NEM 区域代码
            target_year: 目标投资年份

        Returns:
            0-1 之间的评分，1 表示最大正面影响
        """
        if self.coal_schedule is None:
            return 0.0

        target_date = date(target_year, 12, 31)
        retirements = self.coal_schedule.get_retirements_before(region, target_date)

        if not retirements:
            return 0.0

        # Weighted impact: sum of (capacity_mw * volatility_impact_estimate)
        # Normalize by a reference value (e.g., 3000 MW * 0.4 = 1200 as max expected)
        weighted_impact = sum(
            r.capacity_mw * r.volatility_impact_estimate for r in retirements
        )

        # Normalize to 0-1 range
        # Reference: Eraring (2880MW * 0.4 = 1152) is a major event
        # Cap at 2000 weighted units for normalization
        max_reference = 2000.0
        score = min(weighted_impact / max_reference, 1.0)

        return score

    def project_pipeline_growth(
        self,
        region: str,
        years_forward: int = 3,
    ) -> float:
        """预测管道容量年增长率。

        基于 capacity_data.json 中 committed/construction/planning 项目
        在未来 years_forward 年内的预期投产容量，计算年化增长率。

        Args:
            region: NEM 区域代码
            years_forward: 前瞻年数，默认 3

        Returns:
            年化增长率（如 0.5 表示 50% 年增长）。无数据时返回 0.0。
        """
        try:
            capacity_data = self.capacity_loader.load()
        except Exception as e:
            logger.warning(f"Failed to load capacity data: {e}")
            return 0.0

        region_projects = [p for p in capacity_data.projects if p.region == region]

        # Current registered capacity
        registered_mw = sum(
            p.capacity_mw for p in region_projects if p.status == "registered"
        )

        if registered_mw <= 0:
            # No registered base - use a small default to avoid division by zero
            registered_mw = 50.0

        # Pipeline capacity expected within years_forward
        current_year = datetime.now().year
        cutoff_year = current_year + years_forward
        pipeline_statuses = {"committed", "construction", "planning"}

        pipeline_mw = 0.0
        for p in region_projects:
            if p.status in pipeline_statuses:
                if p.expected_commissioning_date is not None:
                    if p.expected_commissioning_date.year <= cutoff_year:
                        pipeline_mw += p.capacity_mw
                else:
                    # No date specified - assume it comes within the window
                    # with a discount factor
                    pipeline_mw += p.capacity_mw * 0.5

        # Annual growth rate = (pipeline_mw / registered_mw) / years_forward
        if years_forward > 0:
            annual_growth_rate = (pipeline_mw / registered_mw) / years_forward
        else:
            annual_growth_rate = 0.0

        return annual_growth_rate

    def _invert_pipeline_score(self, growth_rate: float) -> float:
        """将管道增长率转换为 0-1 评分（增长越低分数越高）。

        逻辑：增长率越高意味着竞争越激烈，对现有投资者不利。
        使用反向映射：score = max(0, 1 - growth_rate / max_growth)

        Args:
            growth_rate: 年化增长率

        Returns:
            0-1 评分
        """
        # Reference: 100% annual growth is considered maximum (score = 0)
        max_growth = 1.0
        score = max(0.0, 1.0 - growth_rate / max_growth)
        return min(score, 1.0)

    def _compute_renewable_penetration_score(self, region: str) -> float:
        """计算可再生能源渗透率评分（使用负价频率作为代理指标）。

        负价越多 = 可再生渗透越高 = 波动性越大 = BESS 机会越多 = 分数越高。

        从现有价格数据中计算负价天数占总天数的比例。

        Args:
            region: NEM 区域代码

        Returns:
            0-1 评分
        """
        negative_price_ratio = self._get_negative_price_frequency(region)

        # Scale: 0% negative prices = 0 score, 20%+ negative prices = 1.0 score
        # Most NEM regions have 5-15% negative price intervals
        max_ratio = 0.20
        score = min(negative_price_ratio / max_ratio, 1.0)
        return max(score, 0.0)

    def _get_negative_price_frequency(self, region: str) -> float:
        """从数据库查询负价频率（负价天数/总天数）。

        查询最近可用年份的 trading_price 表。

        Args:
            region: NEM 区域代码

        Returns:
            负价频率比例 (0-1)
        """
        current_year = datetime.now().year

        # Try current year, then previous years
        for year_offset in range(3):
            year = current_year - year_offset
            table_name = f"trading_price_{year}"

            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()

                    # Check if table exists
                    cursor.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,),
                    )
                    if not cursor.fetchone():
                        continue

                    # Count total intervals and negative price intervals
                    cursor.execute(
                        f"""
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN rrp_aud_mwh < 0 THEN 1 ELSE 0 END) as negative
                        FROM {table_name}
                        WHERE region_id = ?
                        """,
                        (region,),
                    )
                    row = cursor.fetchone()
                    if row and row[0] and row[0] > 0:
                        total = row[0]
                        negative = row[1] or 0
                        return negative / total

            except Exception as e:
                logger.warning(
                    f"Failed to query negative prices for {region} in {year}: {e}"
                )
                continue

        # No data available - return moderate default
        return 0.05

    def _compute_revenue_trajectory_score(self, region: str) -> float:
        """计算历史收入变化方向评分。

        比较最近两年的平均价格 spread（peak - trough），
        上升趋势 = 高分，下降趋势 = 低分。

        Args:
            region: NEM 区域代码

        Returns:
            0-1 评分
        """
        current_year = datetime.now().year
        spreads: list[float] = []

        # Try to get average daily spread for recent years
        for year_offset in range(3):
            year = current_year - year_offset
            spread = self._get_average_daily_spread(region, year)
            if spread is not None:
                spreads.append(spread)

        if len(spreads) < 2:
            # Insufficient data - return neutral score
            return 0.5

        # Compare most recent year to earlier years
        recent_spread = spreads[0]
        earlier_spread = sum(spreads[1:]) / len(spreads[1:])

        if earlier_spread <= 0:
            return 0.5

        # Growth ratio: how much has the spread improved
        growth_ratio = (recent_spread - earlier_spread) / earlier_spread

        # Map growth ratio to 0-1 score
        # -50% decline = 0.0, 0% change = 0.5, +50% growth = 1.0
        score = 0.5 + (growth_ratio / 1.0)  # ±50% maps to 0-1
        return max(0.0, min(1.0, score))

    def _get_average_daily_spread(self, region: str, year: int) -> Optional[float]:
        """获取某区域某年的平均日价差（peak - trough）。

        Args:
            region: NEM 区域代码
            year: 年份

        Returns:
            平均日价差 (AUD/MWh)，无数据时返回 None
        """
        table_name = f"trading_price_{year}"

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Check if table exists
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                if not cursor.fetchone():
                    return None

                # Calculate average daily spread (max - min per day)
                cursor.execute(
                    f"""
                    SELECT AVG(daily_spread) FROM (
                        SELECT
                            DATE(settlement_date) as day,
                            MAX(rrp_aud_mwh) - MIN(rrp_aud_mwh) as daily_spread
                        FROM {table_name}
                        WHERE region_id = ?
                        GROUP BY DATE(settlement_date)
                        HAVING COUNT(*) > 10
                    )
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return float(row[0])

        except Exception as e:
            logger.warning(
                f"Failed to query daily spread for {region} in {year}: {e}"
            )

        return None

    def _get_key_events(self, region: str, target_year: int) -> list[str]:
        """获取区域的关键事件描述。

        Args:
            region: NEM 区域代码
            target_year: 目标投资年份

        Returns:
            关键事件描述列表
        """
        events: list[str] = []

        # Coal retirements
        if self.coal_schedule:
            target_date = date(target_year, 12, 31)
            retirements = self.coal_schedule.get_retirements_before(region, target_date)
            for r in retirements:
                events.append(
                    f"{r.plant_name} ({r.capacity_mw:.0f}MW {r.fuel_type}) "
                    f"closure by {r.expected_closure_date.isoformat()} "
                    f"[{r.confidence}]"
                )

        # Pipeline projects
        try:
            capacity_data = self.capacity_loader.load()
            region_projects = [p for p in capacity_data.projects if p.region == region]
            pipeline_statuses = {"committed", "construction"}

            for p in region_projects:
                if p.status in pipeline_statuses:
                    commission_str = (
                        p.expected_commissioning_date.isoformat()
                        if p.expected_commissioning_date
                        else "TBD"
                    )
                    events.append(
                        f"{p.project_name} ({p.capacity_mw:.0f}MW) "
                        f"[{p.status}] expected {commission_str}"
                    )
        except Exception as e:
            logger.warning(f"Failed to load pipeline events for {region}: {e}")

        return events

    def _load_market_examples(self) -> list[MarketExample]:
        """从 market_examples.json 加载区域时机相关的市场示例。"""
        data_path = os.path.join(_PROJECT_ROOT, "data", "market_examples.json")

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load market_examples.json: {e}")
            return []

        examples: list[MarketExample] = []
        timing_examples = data.get("examples", {}).get("regional_timing", [])

        for ex in timing_examples:
            examples.append(
                MarketExample(
                    region=ex.get("region", ""),
                    description=ex.get("description", ""),
                    data_year=ex.get("data_year", 2024),
                    actual_value=ex.get("revenue_premium_pct", 0.0),
                    label=ex.get("label", "actual"),
                )
            )

        return examples

    def _generate_conclusion(
        self,
        rankings: list[RegionTimingScore],
        target_year: int,
        coal_data_available: bool,
    ) -> str:
        """生成推荐区域和时机结论。

        Args:
            rankings: 已排序的区域评分列表
            target_year: 目标投资年份
            coal_data_available: 煤电退役数据是否可用

        Returns:
            纯文本结论字符串（中英双语）
        """
        if not rankings:
            return "Insufficient data to generate regional timing recommendation."

        top = rankings[0]
        second = rankings[1] if len(rankings) > 1 else None

        # Identify the strongest dimension for the top region
        strongest_dim = max(top.dimensions, key=lambda k: top.dimensions[k])
        dim_labels = {
            "coal_retirement": "coal retirement impact",
            "pipeline_growth": "moderate pipeline competition",
            "renewable_penetration": "high renewable penetration",
            "revenue_trajectory": "positive revenue trajectory",
        }
        strongest_label = dim_labels.get(strongest_dim, strongest_dim)

        # English conclusion
        en_parts = [
            f"{top.region} is projected to be the most attractive region "
            f"for BESS investment targeting {target_year} "
            f"(score: {top.total_score:.2f}), "
            f"primarily due to {strongest_label}.",
        ]

        if second:
            en_parts.append(
                f" {second.region} ranks second (score: {second.total_score:.2f})."
            )

        if not coal_data_available:
            en_parts.append(
                " Note: Coal retirement data unavailable — "
                "analysis excludes coal retirement impact dimension."
            )

        # Chinese conclusion
        dim_labels_zh = {
            "coal_retirement": "煤电退役影响",
            "pipeline_growth": "适度的管道竞争",
            "renewable_penetration": "高可再生能源渗透率",
            "revenue_trajectory": "正向收入趋势",
        }
        strongest_label_zh = dim_labels_zh.get(strongest_dim, strongest_dim)

        zh_parts = [
            f"\n\n{top.region} 预计是 {target_year} 年 BESS 投资最具吸引力的区域"
            f"（评分：{top.total_score:.2f}），"
            f"主要得益于{strongest_label_zh}。",
        ]

        if second:
            zh_parts.append(
                f"{second.region} 排名第二（评分：{second.total_score:.2f}）。"
            )

        if not coal_data_available:
            zh_parts.append(
                "注意：煤电退役数据不可用——分析排除了煤电退役影响维度。"
            )

        return "".join(en_parts) + "".join(zh_parts)
