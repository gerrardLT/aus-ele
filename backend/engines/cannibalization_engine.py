"""
Cannibalization Engine for Revenue Dilution Simulation.

Simulates how future BESS capacity additions dilute existing project revenues
using a power-law model: revenue_per_mw = base_revenue / (capacity / base_capacity) ^ alpha

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from models.capacity_models import CapacityDataLoader, CapacityDataLoadError
from models.outlook_models import (
    CannibalizationResponse,
    DilutionPoint,
    MarketExample,
    YearlyProjection,
)

logger = logging.getLogger(__name__)

# Default market examples data path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MARKET_EXAMPLES_PATH = _PROJECT_ROOT / "data" / "market_examples.json"

# Default base revenue estimates per region (AUD/MW/year)
# Based on historical BESS revenue data from AEMO reports
DEFAULT_BASE_REVENUES: dict[str, float] = {
    "NSW1": 150000.0,
    "QLD1": 280000.0,
    "VIC1": 120000.0,
    "SA1": 180000.0,
    "TAS1": 90000.0,
    "WEM": 100000.0,
}


class CannibalizationEngine:
    """基于幂律模型模拟容量增长对单位收入的蚕食效应。

    核心模型: revenue_per_mw = base_revenue / (capacity_mw / base_capacity) ^ alpha
    其中 alpha ≈ 0.5-0.7 控制稀释速度。

    QLD 实际数据拟合: 容量 3x (200MW→600MW) → 收入下降 74% ($280k→$73k)
    对应 alpha ≈ 0.6
    """

    def __init__(
        self,
        capacity_loader: CapacityDataLoader,
        market_examples_path: Optional[Path] = None,
    ):
        self.capacity_loader = capacity_loader
        self.market_examples_path = market_examples_path or DEFAULT_MARKET_EXAMPLES_PATH

    def simulate(
        self,
        region: str,
        base_revenue_per_mw: Optional[float] = None,
        base_capacity_mw: Optional[float] = None,
        alpha: float = 0.6,
        projection_years: int = 3,
    ) -> CannibalizationResponse:
        """执行蚕食模拟。

        Args:
            region: NEM 区域代码 (NSW1, QLD1, VIC1, SA1, TAS1) 或 WEM。
            base_revenue_per_mw: 基准收入 (AUD/MW/year)。若为 None 则使用默认值。
            base_capacity_mw: 基准容量 (MW)。若为 None 则从已注册项目计算。
            alpha: 稀释指数，范围 [0.3, 1.0]，默认 0.6。
            projection_years: 前瞻预测年数，范围 [1, 5]，默认 3。

        Returns:
            CannibalizationResponse 包含稀释曲线、年度预测和结论。

        Raises:
            CapacityDataLoadError: 容量数据加载失败。
            ValueError: 区域无项目数据。
        """
        # Load capacity data
        capacity_data = self.capacity_loader.load()

        # Filter projects for the target region
        region_projects = [p for p in capacity_data.projects if p.region == region]
        if not region_projects:
            raise ValueError(
                f"No projects found for region '{region}'. "
                f"Check region code or add projects to capacity data."
            )

        # Calculate base capacity from registered projects
        registered_projects = [p for p in region_projects if p.status == "registered"]
        calculated_base_capacity = sum(p.capacity_mw for p in registered_projects)

        if base_capacity_mw is None:
            base_capacity_mw = calculated_base_capacity
            # Ensure non-zero base capacity
            if base_capacity_mw <= 0:
                base_capacity_mw = 100.0  # Minimum fallback

        # Use default base revenue if not provided
        if base_revenue_per_mw is None:
            base_revenue_per_mw = DEFAULT_BASE_REVENUES.get(region, 150000.0)

        # Get pipeline projects (committed, construction, planning)
        pipeline_statuses = {"committed", "construction", "planning"}
        pipeline_projects = [
            p for p in region_projects if p.status in pipeline_statuses
        ]

        # Calculate total projected capacity (registered + pipeline)
        total_pipeline_mw = sum(p.capacity_mw for p in pipeline_projects)
        max_projected_capacity = base_capacity_mw + total_pipeline_mw

        # Generate dilution curve (50 data points)
        dilution_curve = self.compute_dilution_curve(
            base_revenue=base_revenue_per_mw,
            base_capacity=base_capacity_mw,
            alpha=alpha,
            capacity_range=(base_capacity_mw, max(max_projected_capacity, base_capacity_mw * 2)),
            steps=50,
        )

        # Generate yearly projections
        current_year = datetime.now().year
        yearly_projections = self._compute_yearly_projections(
            region=region,
            base_revenue=base_revenue_per_mw,
            base_capacity=base_capacity_mw,
            alpha=alpha,
            pipeline_projects=pipeline_projects,
            current_year=current_year,
            projection_years=projection_years,
        )

        # Calculate current dilution (based on current total capacity vs base)
        current_total_capacity = base_capacity_mw
        # Include construction projects as they are likely to commission soon
        construction_mw = sum(
            p.capacity_mw for p in pipeline_projects if p.status == "construction"
        )
        current_total_capacity += construction_mw

        current_revenue = self._compute_revenue(
            base_revenue_per_mw, base_capacity_mw, current_total_capacity, alpha
        )
        current_dilution_pct = (1 - current_revenue / base_revenue_per_mw) * 100

        # Warning if dilution exceeds 50%
        warning_triggered = current_dilution_pct > 50.0

        # Load market examples
        market_examples = self._load_market_examples(region)

        # Generate conclusion
        conclusion = self._generate_conclusion(
            region=region,
            base_capacity_mw=base_capacity_mw,
            total_pipeline_mw=total_pipeline_mw,
            current_dilution_pct=current_dilution_pct,
            yearly_projections=yearly_projections,
            projection_years=projection_years,
        )

        # Build metadata
        metadata = {
            "market": "WEM" if region == "WEM" else "NEM",
            "region": region,
            "timezone": "Australia/Perth" if region == "WEM" else "Australia/Sydney",
            "currency": "AUD",
            "methodology_version": "1.0",
        }

        return CannibalizationResponse(
            metadata=metadata,
            region=region,
            alpha=alpha,
            base_capacity_mw=base_capacity_mw,
            base_revenue_per_mw=base_revenue_per_mw,
            dilution_curve=dilution_curve,
            yearly_projections=yearly_projections,
            current_dilution_pct=round(current_dilution_pct, 2),
            warning_triggered=warning_triggered,
            market_examples=market_examples,
            conclusion=conclusion,
        )

    def compute_dilution_curve(
        self,
        base_revenue: float,
        base_capacity: float,
        alpha: float,
        capacity_range: tuple[float, float],
        steps: int = 50,
    ) -> list[DilutionPoint]:
        """生成稀释曲线数据点。

        Args:
            base_revenue: 基准收入 (AUD/MW/year)。
            base_capacity: 基准容量 (MW)。
            alpha: 稀释指数。
            capacity_range: (最小容量, 最大容量) 元组。
            steps: 数据点数量，默认 50。

        Returns:
            50 个 DilutionPoint 组成的列表。
        """
        min_cap, max_cap = capacity_range
        if max_cap <= min_cap:
            max_cap = min_cap * 2

        step_size = (max_cap - min_cap) / max(steps - 1, 1)

        points: list[DilutionPoint] = []
        for i in range(steps):
            capacity = min_cap + i * step_size
            revenue_per_mw = self._compute_revenue(
                base_revenue, base_capacity, capacity, alpha
            )
            dilution_pct = (1 - revenue_per_mw / base_revenue) * 100

            points.append(
                DilutionPoint(
                    capacity_mw=round(capacity, 2),
                    revenue_per_mw=round(revenue_per_mw, 2),
                    dilution_pct=round(dilution_pct, 2),
                )
            )

        return points

    def _compute_revenue(
        self,
        base_revenue: float,
        base_capacity: float,
        target_capacity: float,
        alpha: float,
    ) -> float:
        """计算给定容量下的单位收入。

        公式: revenue_per_mw = base_revenue / (target_capacity / base_capacity) ^ alpha

        Args:
            base_revenue: 基准收入。
            base_capacity: 基准容量。
            target_capacity: 目标容量。
            alpha: 稀释指数。

        Returns:
            计算后的单位收入 (AUD/MW/year)。
        """
        if base_capacity <= 0 or target_capacity <= 0:
            return base_revenue

        ratio = target_capacity / base_capacity
        return base_revenue / (ratio ** alpha)

    def _compute_yearly_projections(
        self,
        region: str,
        base_revenue: float,
        base_capacity: float,
        alpha: float,
        pipeline_projects: list,
        current_year: int,
        projection_years: int,
    ) -> list[YearlyProjection]:
        """生成年度预测。

        基于管道项目的预期投产日期，逐年累加容量并计算稀释。

        Args:
            region: 区域代码。
            base_revenue: 基准收入。
            base_capacity: 基准容量。
            alpha: 稀释指数。
            pipeline_projects: 管道项目列表。
            current_year: 当前年份。
            projection_years: 预测年数。

        Returns:
            年度预测列表。
        """
        projections: list[YearlyProjection] = []
        cumulative_capacity = base_capacity

        for year_offset in range(projection_years):
            year = current_year + year_offset + 1

            # Find projects expected to commission in this year
            new_projects_this_year: list[str] = []
            new_capacity_this_year = 0.0

            for project in pipeline_projects:
                if project.expected_commissioning_date is not None:
                    commission_year = project.expected_commissioning_date.year
                    if commission_year == year:
                        new_projects_this_year.append(project.project_name)
                        new_capacity_this_year += project.capacity_mw

            cumulative_capacity += new_capacity_this_year

            # Calculate revenue at projected capacity
            projected_revenue = self._compute_revenue(
                base_revenue, base_capacity, cumulative_capacity, alpha
            )
            dilution_pct = (1 - projected_revenue / base_revenue) * 100

            projections.append(
                YearlyProjection(
                    year=year,
                    projected_capacity_mw=round(cumulative_capacity, 2),
                    projected_revenue_per_mw=round(projected_revenue, 2),
                    dilution_pct=round(dilution_pct, 2),
                    new_projects=new_projects_this_year,
                )
            )

        return projections

    def _load_market_examples(self, region: str) -> list[MarketExample]:
        """加载对应区域的真实市场案例注释。

        Args:
            region: 区域代码。

        Returns:
            MarketExample 列表。若数据不可用则返回空列表。
        """
        try:
            if not self.market_examples_path.exists():
                logger.warning(
                    "Market examples file not found: %s", self.market_examples_path
                )
                return []

            with open(self.market_examples_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            examples_data = data.get("examples", {}).get("cannibalization", [])
            examples: list[MarketExample] = []

            for ex in examples_data:
                # Include examples matching the region, or general examples
                ex_region = ex.get("region", "")
                if ex_region == region or ex_region == "NEM-wide":
                    examples.append(
                        MarketExample(
                            region=ex_region,
                            description=ex.get("description", ""),
                            data_year=ex.get("data_year", 2024),
                            actual_value=ex.get("after_revenue", ex.get("before_revenue", 0)),
                            label=ex.get("label", "actual"),
                        )
                    )

            return examples

        except Exception as e:
            logger.warning("Failed to load market examples: %s", e)
            return []

    def _generate_conclusion(
        self,
        region: str,
        base_capacity_mw: float,
        total_pipeline_mw: float,
        current_dilution_pct: float,
        yearly_projections: list[YearlyProjection],
        projection_years: int,
    ) -> str:
        """生成纯文本结论摘要。

        Args:
            region: 区域代码。
            base_capacity_mw: 基准容量。
            total_pipeline_mw: 管道总容量。
            current_dilution_pct: 当前稀释百分比。
            yearly_projections: 年度预测列表。
            projection_years: 预测年数。

        Returns:
            纯文本结论字符串（中英双语）。
        """
        # Find max dilution across projections
        max_dilution = current_dilution_pct
        max_dilution_year = datetime.now().year
        if yearly_projections:
            for proj in yearly_projections:
                if proj.dilution_pct > max_dilution:
                    max_dilution = proj.dilution_pct
                    max_dilution_year = proj.year

        # If no yearly projections show dilution, compute full pipeline dilution
        if max_dilution <= 0 and total_pipeline_mw > 0:
            full_capacity = base_capacity_mw + total_pipeline_mw
            full_revenue = self._compute_revenue(
                DEFAULT_BASE_REVENUES.get(region, 150000.0),
                base_capacity_mw,
                full_capacity,
                0.6,  # default alpha
            )
            base_rev = DEFAULT_BASE_REVENUES.get(region, 150000.0)
            max_dilution = (1 - full_revenue / base_rev) * 100
            # Use the last projection year or estimate from pipeline
            max_dilution_year = datetime.now().year + projection_years

        # English conclusion
        en_conclusion = (
            f"If {total_pipeline_mw:.0f}MW more BESS comes online in {region} "
            f"by {max_dilution_year}, existing project revenues are projected to "
            f"decline by {max_dilution:.0f}%."
        )

        # Chinese conclusion
        zh_conclusion = (
            f"若 {region} 区域在 {max_dilution_year} 年前新增 "
            f"{total_pipeline_mw:.0f}MW BESS 容量，现有项目收入预计将下降 "
            f"{max_dilution:.0f}%。"
        )

        # Warning addition
        if max_dilution > 50:
            en_conclusion += (
                f" WARNING: Dilution exceeds 50% threshold — "
                f"significant revenue risk for existing assets."
            )
            zh_conclusion += (
                f" 警告：稀释超过 50% 阈值——现有资产面临重大收入风险。"
            )

        return f"{en_conclusion}\n\n{zh_conclusion}"
