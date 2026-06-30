"""
FCAS Collapse Forecaster Engine.

基于供需比模型预测 FCAS 各服务类型的价格天花板。

核心模型: price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))
其中 beta 控制崩塌陡峭度，supply/demand > 3.0 时价格趋近于零。

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Literal, Optional

from database import DatabaseManager
from sql_safe import trading_price_table
from models.outlook_models import (
    FcasCollapseParams,
    FcasCollapseResponse,
    FcasServiceResult,
    MarketExample,
)

logger = logging.getLogger(__name__)

# 10 FCAS services in the NEM
FCAS_SERVICES = [
    "raise1sec",
    "raise6sec",
    "raise60sec",
    "raise5min",
    "raisereg",
    "lower1sec",
    "lower6sec",
    "lower60sec",
    "lower5min",
    "lowerreg",
]

# Mapping from service name to the column in trading_price_{year} table
FCAS_COLUMN_MAP = {
    "raise1sec": "raise1sec_rrp",
    "raise6sec": "raise6sec_rrp",
    "raise60sec": "raise60sec_rrp",
    "raise5min": "raise5min_rrp",
    "raisereg": "raisereg_rrp",
    "lower1sec": "lower1sec_rrp",
    "lower6sec": "lower6sec_rrp",
    "lower60sec": "lower60sec_rrp",
    "lower5min": "lower5min_rrp",
    "lowerreg": "lowerreg_rrp",
}

# Default participation rates: fraction of total BESS capacity registered for each service
DEFAULT_PARTICIPATION_RATES = {
    "raise1sec": 0.8,
    "raise6sec": 0.8,
    "raise60sec": 0.7,
    "raise5min": 0.6,
    "raisereg": 0.5,
    "lower1sec": 0.8,
    "lower6sec": 0.8,
    "lower60sec": 0.7,
    "lower5min": 0.6,
    "lowerreg": 0.5,
}

# AEMO minimum procurement volumes (MW) for each FCAS service
# Based on AEMO public data for NEM-wide requirements
MARKET_REQUIREMENT_MW = {
    "raise1sec": 180,
    "raise6sec": 200,
    "raise60sec": 300,
    "raise5min": 250,
    "raisereg": 150,
    "lower1sec": 180,
    "lower6sec": 200,
    "lower60sec": 300,
    "lower5min": 250,
    "lowerreg": 150,
}


class FcasCollapseEngine:
    """基于供需比模型预测 FCAS 各服务类型的价格天花板。

    核心模型: price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))
    其中 beta 控制崩塌陡峭度，supply/demand > 3.0 时价格趋近于零。
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def forecast(
        self,
        region: str = "NEM-wide",
        year: int = 2025,
        beta: float = 1.5,
        enablement_probability: float = 0.3,
        participation_rates: Optional[dict[str, float]] = None,
    ) -> FcasCollapseResponse:
        """计算各 FCAS 服务的供需比和价格天花板。

        Args:
            region: 区域代码（NEM-wide 表示全网）
            year: 分析年份
            beta: 崩塌陡峭度参数
            enablement_probability: FCAS 启用概率（用于加权年收入计算）
            participation_rates: 各服务参与率覆盖（可选）

        Returns:
            FcasCollapseResponse 包含各服务分析结果和总收入天花板
        """
        params = FcasCollapseParams(
            beta=beta,
            enablement_probability=enablement_probability,
        )

        rates = participation_rates or DEFAULT_PARTICIPATION_RATES

        # Load total BESS capacity from capacity_data.json
        total_bess_mw = self._load_total_bess_capacity()

        # Load historical FCAS prices from SQLite
        historical_prices = self._load_historical_fcas_prices(year)

        # Compute results for each service
        services: list[FcasServiceResult] = []
        total_ceiling_per_mw_year = 0.0

        for service in FCAS_SERVICES:
            rate = rates.get(service, 0.5)
            supply_mw = total_bess_mw * rate
            demand_mw = MARKET_REQUIREMENT_MW[service]
            ratio = supply_mw / demand_mw if demand_mw > 0 else 0.0

            classification = self.classify_service(ratio)

            # Get historical base price for this service
            base_price = historical_prices.get(service)
            if base_price is None:
                # Service data missing - exclude from total calculation
                continue

            price_ceiling = self.compute_price_ceiling(
                supply_mw=supply_mw,
                demand_mw=demand_mw,
                base_price=base_price,
                beta=beta,
            )

            service_result = FcasServiceResult(
                service_name=service,
                supply_mw=round(supply_mw, 1),
                demand_mw=demand_mw,
                supply_demand_ratio=round(ratio, 3),
                classification=classification,
                price_ceiling_per_mwh=round(price_ceiling, 4),
                historical_price_per_mwh=round(base_price, 4) if base_price else None,
            )
            services.append(service_result)

            # Accumulate total ceiling: price_ceiling * enablement_probability * 8760
            total_ceiling_per_mw_year += price_ceiling * enablement_probability * 8760

        total_ceiling_per_mw_year = round(total_ceiling_per_mw_year, 2)

        # Load market examples
        market_examples = self._load_market_examples()

        # Load historical trajectory
        historical_trajectory = self._load_historical_trajectory()

        # Generate conclusion
        conclusion = self._generate_conclusion(
            services, total_ceiling_per_mw_year, total_bess_mw
        )

        return FcasCollapseResponse(
            metadata={
                "market": "NEM",
                "region": region,
                "timezone": "Australia/Sydney",
                "currency": "AUD",
                "methodology_version": "1.0",
                "model": "supply_demand_ratio_ceiling",
                "formula": "price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))",
                "total_bess_capacity_mw": total_bess_mw,
            },
            region=region,
            year=year,
            beta=beta,
            services=services,
            total_fcas_ceiling_per_mw_year=total_ceiling_per_mw_year,
            historical_trajectory=historical_trajectory,
            market_examples=market_examples,
            conclusion=conclusion,
        )

    def compute_price_ceiling(
        self,
        supply_mw: float,
        demand_mw: float,
        base_price: float,
        beta: float,
    ) -> float:
        """计算单个服务的价格天花板。

        price = max(0, base_price * (1 - (supply/demand - 1) ^ beta))
        当 supply/demand <= 1 时返回 base_price（供不应求）。

        Args:
            supply_mw: 注册供给容量 (MW)
            demand_mw: 市场需求量 (MW)
            base_price: 历史基准价格 (AUD/MW/hr)
            beta: 崩塌陡峭度参数

        Returns:
            价格天花板 (AUD/MW/hr)，非负
        """
        if demand_mw <= 0:
            return base_price

        ratio = supply_mw / demand_mw

        if ratio <= 1.0:
            return base_price

        # price = max(0, base_price * (1 - (ratio - 1) ^ beta))
        decay = (ratio - 1.0) ** beta
        price = base_price * (1.0 - decay)
        return max(0.0, price)

    def classify_service(
        self, supply_demand_ratio: float
    ) -> Literal["healthy", "at_risk", "collapsed"]:
        """分类服务状态。

        Args:
            supply_demand_ratio: 供需比

        Returns:
            "healthy" (<1.5), "at_risk" (1.5-3.0), "collapsed" (>3.0)
        """
        if supply_demand_ratio < 1.5:
            return "healthy"
        elif supply_demand_ratio <= 3.0:
            return "at_risk"
        else:
            return "collapsed"

    def _load_total_bess_capacity(self) -> float:
        """从 capacity_data.json 加载 BESS 总注册容量。

        只计算 status 为 registered, committed, construction 的项目。
        排除 Pumped Hydro 项目（它们通常不参与 FCAS）。
        """
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "capacity_data.json",
        )

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load capacity_data.json: {e}")
            # Fallback: use a reasonable estimate based on known NEM BESS capacity
            return 2500.0

        total_mw = 0.0
        active_statuses = {"registered", "committed", "construction"}

        for project in data.get("projects", []):
            status = project.get("status", "")
            technology = project.get("technology", "")

            # Only count active BESS projects (exclude pumped hydro and planning)
            if status in active_statuses and "Pumped Hydro" not in technology:
                total_mw += project.get("capacity_mw", 0.0)

        return total_mw

    def _load_historical_fcas_prices(self, year: int) -> dict[str, Optional[float]]:
        """从 SQLite 加载历史 FCAS 平均价格数据。

        查询 trading_price_{year} 表中各 FCAS 服务的平均价格。
        缺失时返回 None。

        Args:
            year: 查询年份

        Returns:
            Dict mapping service name to average price (AUD/MW/hr), or None if unavailable
        """
        prices: dict[str, Optional[float]] = {}
        table_name = trading_price_table(year)

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Check if table exists
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                if not cursor.fetchone():
                    # Table doesn't exist - try previous year
                    table_name = trading_price_table(year - 1)
                    cursor.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,),
                    )
                    if not cursor.fetchone():
                        logger.warning(
                            f"No trading_price table found for {year} or {year - 1}"
                        )
                        return {s: None for s in FCAS_SERVICES}

                # Check which FCAS columns exist
                cursor.execute(f"PRAGMA table_info({table_name})")
                existing_cols = {row[1] for row in cursor.fetchall()}

                for service in FCAS_SERVICES:
                    col = FCAS_COLUMN_MAP[service]
                    if col not in existing_cols:
                        prices[service] = None
                        continue

                    cursor.execute(
                        f"SELECT AVG({col}) FROM {table_name} WHERE {col} IS NOT NULL AND {col} > 0"
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        prices[service] = float(row[0])
                    else:
                        prices[service] = None

        except Exception as e:
            logger.warning(f"Failed to load FCAS prices from SQLite: {e}")
            return {s: None for s in FCAS_SERVICES}

        return prices

    def _load_market_examples(self) -> list[MarketExample]:
        """从 market_examples.json 加载 FCAS 崩塌相关的市场示例。"""
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "market_examples.json",
        )

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load market_examples.json: {e}")
            return []

        examples = []
        fcas_examples = data.get("examples", {}).get("fcas_collapse", [])

        for ex in fcas_examples:
            trajectory = ex.get("trajectory", [])
            # Use the latest year's revenue as actual_value
            actual_value = trajectory[-1]["revenue_per_mw"] if trajectory else 0.0

            examples.append(
                MarketExample(
                    region=ex.get("region", "NEM-wide"),
                    description=ex.get("description", ""),
                    data_year=ex.get("data_year", trajectory[-1]["year"] if trajectory else 2025),
                    actual_value=actual_value,
                    label=ex.get("label", "actual"),
                )
            )

        return examples

    def _load_historical_trajectory(self) -> list[dict]:
        """从 market_examples.json 加载 FCAS 历史收入轨迹数据。"""
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "market_examples.json",
        )

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load market_examples.json: {e}")
            return []

        fcas_examples = data.get("examples", {}).get("fcas_collapse", [])
        if not fcas_examples:
            return []

        # Use the first example's trajectory
        trajectory = fcas_examples[0].get("trajectory", [])
        return [
            {
                "year": point["year"],
                "total_fcas_revenue_per_mw": point["revenue_per_mw"],
                "registered_bess_mw": point.get("registered_bess_mw"),
            }
            for point in trajectory
        ]

    def _generate_conclusion(
        self,
        services: list[FcasServiceResult],
        total_ceiling: float,
        total_bess_mw: float,
    ) -> str:
        """生成结论摘要（最大现实 FCAS 收入）。"""
        collapsed_count = sum(
            1 for s in services if s.classification == "collapsed"
        )
        at_risk_count = sum(
            1 for s in services if s.classification == "at_risk"
        )
        healthy_count = sum(
            1 for s in services if s.classification == "healthy"
        )

        ceiling_k = total_ceiling / 1000.0

        conclusion_parts = [
            f"Maximum realistic FCAS revenue: ${ceiling_k:.1f}k/MW/yr",
            f"(based on {total_bess_mw:.0f}MW registered BESS capacity).",
        ]

        if collapsed_count > 0:
            conclusion_parts.append(
                f"{collapsed_count} of {len(services)} services classified as collapsed"
                f" (supply/demand > 3.0)."
            )
        if at_risk_count > 0:
            conclusion_parts.append(
                f"{at_risk_count} services at risk (supply/demand 1.5-3.0)."
            )
        if healthy_count > 0:
            conclusion_parts.append(
                f"{healthy_count} services remain healthy (supply/demand < 1.5)."
            )

        conclusion_parts.append(
            "FCAS should not be relied upon as a primary revenue stream for new BESS investments."
        )

        return " ".join(conclusion_parts)
