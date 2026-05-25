"""Risk Stratification Engine — 收入风险分层引擎。

将年度收入按价格阈值拆分为三层，各层独立折现计算 NPV：
- Layer 1: 基础套利收入（价格 < threshold），HIGH 置信度，8% 折现
- Layer 2: FCAS 辅助服务收入（独立于阈值），MEDIUM 置信度，10% 折现
- Layer 3: 极端事件收入（价格 > threshold），LOW 置信度，12% 折现

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import logging
from datetime import date
from math import sqrt
from typing import Any, List

from models.financial_params import BatterySpecs
from models.forward_price_models import ScenarioProjection
from models.narrative_models import (
    AnnualStratifiedRevenue,
    ConfidenceLevel,
    LayerDiscountRates,
    LayerWeightedNPV,
    RevenueLayer,
    StratifiedRevenue,
)

logger = logging.getLogger(__name__)


class RiskStratificationEngine:
    """收入风险分层引擎。

    将年度收入按价格阈值拆分为三层，各层独立折现计算 NPV。
    默认 Spread_Threshold = $300/MWh（NEM 市场价格上限 $16,600/MWh）。
    """

    def __init__(
        self,
        spread_threshold: float = 300.0,
        layer_discount_rates: LayerDiscountRates | None = None,
    ) -> None:
        """初始化风险分层引擎。

        Args:
            spread_threshold: 价差阈值（$/MWh），用于区分 Layer 1 和 Layer 3。
                有效范围 [0, 16600]。
            layer_discount_rates: 各层折现率配置。默认 Layer1=8%, Layer2=10%, Layer3=12%。
        """
        if spread_threshold < 0 or spread_threshold > 16600:
            raise ValueError(
                f"spread_threshold must be in [0, 16600], got {spread_threshold}"
            )
        self.spread_threshold = spread_threshold
        self.discount_rates = layer_discount_rates or LayerDiscountRates()

    def stratify_historical_revenue(
        self,
        price_data: list[dict[str, Any]],
        fcas_revenue: float,
        battery: BatterySpecs,
    ) -> AnnualStratifiedRevenue:
        """基于历史价格数据按阈值拆分三层收入。

        对每个价格区间计算套利收入，按价格是否超过阈值分配到 Layer 1 或 Layer 3。
        FCAS 收入独立分配到 Layer 2。

        Args:
            price_data: 价格区间列表，每个元素为 dict，包含:
                - 'price': 结算价格 ($/MWh)
                - 'interval_hours': 区间时长（小时），默认 5/60（5分钟）
            fcas_revenue: FCAS 辅助服务年收入 ($)
            battery: 电池规格参数

        Returns:
            AnnualStratifiedRevenue 包含三层收入分解。
        """
        one_way_efficiency = sqrt(battery.round_trip_efficiency)

        layer1_revenue = 0.0  # 价格 < threshold
        layer3_revenue = 0.0  # 价格 > threshold

        for record in price_data:
            price = float(record["price"])
            interval_hours = float(record.get("interval_hours", 5.0 / 60.0))

            # 计算该区间最大放电量
            max_discharge_mwh = min(
                battery.power_mw * interval_hours,
                battery.capacity_mwh,
            )

            # 仅正价格区间产生收入（简化模型：假设满放电）
            if price > 0:
                discharge_mwh = max_discharge_mwh * one_way_efficiency
                interval_revenue = discharge_mwh * price
            else:
                interval_revenue = 0.0

            # 按阈值分配到 Layer 1 或 Layer 3
            if price <= self.spread_threshold:
                layer1_revenue += interval_revenue
            else:
                layer3_revenue += interval_revenue

        # Layer 2 = FCAS 收入（独立于价格阈值）
        layer2_revenue = max(0.0, fcas_revenue)

        total_revenue = layer1_revenue + layer2_revenue + layer3_revenue

        # 计算各层百分比
        if total_revenue > 0:
            layer1_pct = (layer1_revenue / total_revenue) * 100.0
            layer2_pct = (layer2_revenue / total_revenue) * 100.0
            layer3_pct = (layer3_revenue / total_revenue) * 100.0
        else:
            layer1_pct = 0.0
            layer2_pct = 0.0
            layer3_pct = 0.0

        # 推断年份（使用当前年份）
        year = date.today().year

        return AnnualStratifiedRevenue(
            year=year,
            layer1=RevenueLayer(
                layer_number=1,
                name="Base Arbitrage",
                confidence=ConfidenceLevel.HIGH,
                discount_rate=self.discount_rates.layer1,
                amount=layer1_revenue,
                percentage=layer1_pct,
            ),
            layer2=RevenueLayer(
                layer_number=2,
                name="FCAS Ancillary Services",
                confidence=ConfidenceLevel.MEDIUM,
                discount_rate=self.discount_rates.layer2,
                amount=layer2_revenue,
                percentage=layer2_pct,
            ),
            layer3=RevenueLayer(
                layer_number=3,
                name="Extreme Price Events",
                confidence=ConfidenceLevel.LOW,
                discount_rate=self.discount_rates.layer3,
                amount=layer3_revenue,
                percentage=layer3_pct,
            ),
            total_revenue=total_revenue,
        )

    def stratify_forward_revenue(
        self,
        projection: ScenarioProjection,
        spike_frequency: float,
        fcas_annual: float,
    ) -> list[AnnualStratifiedRevenue]:
        """基于前瞻预测估算 20 年分层收入。

        使用 spike_frequency 估算 Layer 3（极端事件）占比，
        剩余为 Layer 1（基础套利），Layer 2 为固定 FCAS 收入。

        Args:
            projection: 单情景 20 年收入预测（来自 ForwardPriceEngine）。
            spike_frequency: 价格尖峰频率 (0-1)，用于估算 Layer 3 占比。
            fcas_annual: 年度 FCAS 收入 ($)。

        Returns:
            20 年分层收入列表。
        """
        annual_layers: list[AnnualStratifiedRevenue] = []

        for annual in projection.annual_projections:
            # 总收入 = revenue_per_mw × power_mw（从 projection 中推算）
            # ScenarioProjection 存储的是 per MW 收入，需要还原为总收入
            # 这里直接使用 per MW 值作为总收入的代理（调用方可传入已缩放的 projection）
            total_energy_revenue = annual.estimated_revenue_per_mw

            # Layer 3 占比 = spike_frequency（极端事件频率近似为收入占比）
            # 实际中极端事件虽然频率低但金额大，用 spike_frequency 作为收入占比的近似
            layer3_proportion = min(spike_frequency, 1.0)
            layer1_proportion = 1.0 - layer3_proportion

            layer1_revenue = total_energy_revenue * layer1_proportion
            layer3_revenue = total_energy_revenue * layer3_proportion
            layer2_revenue = max(0.0, fcas_annual)

            total_revenue = layer1_revenue + layer2_revenue + layer3_revenue

            # 计算各层百分比
            if total_revenue > 0:
                layer1_pct = (layer1_revenue / total_revenue) * 100.0
                layer2_pct = (layer2_revenue / total_revenue) * 100.0
                layer3_pct = (layer3_revenue / total_revenue) * 100.0
            else:
                layer1_pct = 0.0
                layer2_pct = 0.0
                layer3_pct = 0.0

            annual_layers.append(
                AnnualStratifiedRevenue(
                    year=annual.year,
                    layer1=RevenueLayer(
                        layer_number=1,
                        name="Base Arbitrage",
                        confidence=ConfidenceLevel.HIGH,
                        discount_rate=self.discount_rates.layer1,
                        amount=layer1_revenue,
                        percentage=layer1_pct,
                    ),
                    layer2=RevenueLayer(
                        layer_number=2,
                        name="FCAS Ancillary Services",
                        confidence=ConfidenceLevel.MEDIUM,
                        discount_rate=self.discount_rates.layer2,
                        amount=layer2_revenue,
                        percentage=layer2_pct,
                    ),
                    layer3=RevenueLayer(
                        layer_number=3,
                        name="Extreme Price Events",
                        confidence=ConfidenceLevel.LOW,
                        discount_rate=self.discount_rates.layer3,
                        amount=layer3_revenue,
                        percentage=layer3_pct,
                    ),
                    total_revenue=total_revenue,
                )
            )

        return annual_layers

    def calculate_layer_weighted_npv(
        self,
        annual_layers: list[AnnualStratifiedRevenue],
    ) -> LayerWeightedNPV:
        """各层独立折现后求和，计算分层加权 NPV。

        NPV 公式：sum(amount_i / (1 + rate)^i)，i 从 1 开始。
        同时计算标准单一折现率 NPV 用于对比。

        Args:
            annual_layers: 年度分层收入列表（通常 20 年）。

        Returns:
            LayerWeightedNPV 包含各层 NPV 和总计。
        """
        layer1_npv = 0.0
        layer2_npv = 0.0
        layer3_npv = 0.0
        standard_npv = 0.0

        # 标准单一折现率（取三层加权平均或使用常见的 8%）
        standard_rate = 0.08

        for i, annual in enumerate(annual_layers, start=1):
            # Layer 1 折现
            layer1_npv += annual.layer1.amount / (
                (1.0 + self.discount_rates.layer1) ** i
            )
            # Layer 2 折现
            layer2_npv += annual.layer2.amount / (
                (1.0 + self.discount_rates.layer2) ** i
            )
            # Layer 3 折现
            layer3_npv += annual.layer3.amount / (
                (1.0 + self.discount_rates.layer3) ** i
            )
            # 标准 NPV（所有收入用同一折现率）
            standard_npv += annual.total_revenue / ((1.0 + standard_rate) ** i)

        total_layer_weighted_npv = layer1_npv + layer2_npv + layer3_npv

        # 差异百分比
        if standard_npv != 0:
            difference_pct = (
                (total_layer_weighted_npv - standard_npv) / abs(standard_npv)
            ) * 100.0
        else:
            difference_pct = 0.0

        return LayerWeightedNPV(
            layer1_npv=layer1_npv,
            layer2_npv=layer2_npv,
            layer3_npv=layer3_npv,
            total_layer_weighted_npv=total_layer_weighted_npv,
            standard_single_rate_npv=standard_npv,
            difference_pct=difference_pct,
        )

    def generate_stratified_revenue(
        self,
        region: str,
        scenario: str,
        annual_layers: list[AnnualStratifiedRevenue],
    ) -> StratifiedRevenue:
        """生成完整分层收入结果（可序列化）。

        组合年度分层数据和 NPV 计算结果为完整响应对象。

        Args:
            region: NEM 区域或 WEM。
            scenario: 情景名称。
            annual_layers: 年度分层收入列表。

        Returns:
            StratifiedRevenue 完整结果对象。
        """
        npv_result = self.calculate_layer_weighted_npv(annual_layers)

        return StratifiedRevenue(
            region=region,
            scenario=scenario,
            spread_threshold=self.spread_threshold,
            discount_rates=self.discount_rates,
            annual_layers=annual_layers,
            layer_weighted_npv=npv_result.total_layer_weighted_npv,
            standard_npv=npv_result.standard_single_rate_npv,
            npv_difference=npv_result.total_layer_weighted_npv
            - npv_result.standard_single_rate_npv,
        )
