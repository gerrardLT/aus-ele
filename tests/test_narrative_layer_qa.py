"""Investment Narrative Layer — 综合 QA 测试用例。

覆盖模块：
1. narrative_models.py — Pydantic 模型验证
2. risk_stratification_engine.py — 风险分层引擎
3. narrative_engine.py — 因果归因引擎
4. event_annotation_service.py — 事件标注服务
5. cross_validation_service.py — 交叉验证服务
6. forward_price_engine.py — 燃料敏感性 + 网络增强
7. narrative_routes.py — API 路由层
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import pytest

# Ensure import paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pydantic import ValidationError

from models.narrative_models import (
    AssetConfiguration,
    CausalAttribution,
    CausalFactor,
    ConfidenceLevel,
    CrossValidationEntry,
    CrossValidationResponse,
    DriverType,
    EventAnnotation,
    EventCluster,
    FuelSensitivityResult,
    FuelSensitivityScenario,
    GasPriceAssumptions,
    LayerDiscountRates,
    LayerWeightedNPV,
    NetworkAugmentationEvent,
    NetworkImpactComparison,
    RevenueLayer,
    AnnualStratifiedRevenue,
    StratifiedRevenue,
)
from models.forward_price_models import (
    EventConfidence,
    EventRegistry,
    EventType,
    ScenarioType,
    SupplyDemandEvent,
    AnnualRevenueProjection,
    ScenarioProjection,
)
from models.financial_params import BatterySpecs

from engines.risk_stratification_engine import RiskStratificationEngine
from engines.narrative_engine import NarrativeEngine
from engines.event_annotation_service import EventAnnotationService
from engines.cross_validation_service import CrossValidationService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_events() -> List[SupplyDemandEvent]:
    """创建测试用供需事件列表。"""
    return [
        SupplyDemandEvent(
            event_type=EventType.COAL_CLOSURE,
            name="Eraring",
            region="NSW1",
            expected_date=date(2027, 8, 1),
            capacity_mw=2880.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=1.15,
        ),
        SupplyDemandEvent(
            event_type=EventType.BESS_COMMISSIONING,
            name="Waratah Super Battery",
            region="NSW1",
            expected_date=date(2026, 6, 1),
            capacity_mw=850.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=0.94,
        ),
        SupplyDemandEvent(
            event_type=EventType.NETWORK_AUGMENTATION,
            name="HumeLink",
            region="NSW1",
            expected_date=date(2028, 12, 1),
            capacity_mw=2000.0,
            confidence=EventConfidence.ANNOUNCED,
            spread_impact_factor=0.88,
        ),
        SupplyDemandEvent(
            event_type=EventType.COAL_CLOSURE,
            name="Yallourn",
            region="VIC1",
            expected_date=date(2028, 6, 1),
            capacity_mw=1480.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=1.10,
        ),
    ]


@pytest.fixture
def event_registry(sample_events) -> EventRegistry:
    """创建测试用事件注册表。"""
    return EventRegistry(events=sample_events, last_updated=date(2025, 1, 15))


@pytest.fixture
def empty_registry() -> EventRegistry:
    """空事件注册表（用于降级策略测试）。"""
    return EventRegistry(events=[], last_updated=date(2025, 1, 15))


@pytest.fixture
def battery() -> BatterySpecs:
    """标准电池规格。"""
    return BatterySpecs(
        power_mw=100.0,
        duration_hours=4.0,
        round_trip_efficiency=0.87,
        calendar_degradation_rate=0.015,
    )


@pytest.fixture
def sample_annual_layers() -> List[AnnualStratifiedRevenue]:
    """创建 3 年分层收入数据用于 NPV 测试。"""
    layers = []
    for i, year in enumerate([2026, 2027, 2028]):
        layers.append(
            AnnualStratifiedRevenue(
                year=year,
                layer1=RevenueLayer(
                    layer_number=1,
                    name="Base Arbitrage",
                    confidence=ConfidenceLevel.HIGH,
                    discount_rate=0.08,
                    amount=100000.0,
                    percentage=50.0,
                ),
                layer2=RevenueLayer(
                    layer_number=2,
                    name="FCAS",
                    confidence=ConfidenceLevel.MEDIUM,
                    discount_rate=0.10,
                    amount=60000.0,
                    percentage=30.0,
                ),
                layer3=RevenueLayer(
                    layer_number=3,
                    name="Extreme",
                    confidence=ConfidenceLevel.LOW,
                    discount_rate=0.12,
                    amount=40000.0,
                    percentage=20.0,
                ),
                total_revenue=200000.0,
            )
        )
    return layers


# =============================================================================
# 1. 模型层测试 (narrative_models.py)
# =============================================================================


class TestNarrativeModels:
    """Pydantic 模型验证测试。"""

    def test_causal_attribution_json_roundtrip(self):
        """CausalAttribution JSON 序列化/反序列化往返。"""
        original = CausalAttribution(
            metric_name="mean_spread",
            metric_value=120.5,
            metric_unit="$/MWh",
            narrative_text="NSW1 2027年价差为 120.5 $/MWh",
            causal_factors=[
                CausalFactor(
                    driver_name="Eraring closure",
                    driver_type=DriverType.COAL_CLOSURE,
                    contribution_amount=15.0,
                    contribution_pct=60.0,
                    source_reference="coal_retirement_schedule.json",
                )
            ],
            region="NSW1",
            year=2027,
            scenario="central",
        )
        json_str = original.model_dump_json()
        restored = CausalAttribution.model_validate_json(json_str)
        assert restored.metric_name == original.metric_name
        assert restored.metric_value == original.metric_value
        assert restored.narrative_text == original.narrative_text
        assert len(restored.causal_factors) == 1
        assert restored.causal_factors[0].driver_name == "Eraring closure"
        assert restored.region == "NSW1"
        assert restored.year == 2027

    def test_stratified_revenue_json_roundtrip(self, sample_annual_layers):
        """StratifiedRevenue 完整对象序列化往返。"""
        original = StratifiedRevenue(
            region="NSW1",
            scenario="central",
            spread_threshold=300.0,
            discount_rates=LayerDiscountRates(),
            annual_layers=sample_annual_layers,
            layer_weighted_npv=450000.0,
            standard_npv=480000.0,
            npv_difference=-30000.0,
        )
        json_str = original.model_dump_json()
        restored = StratifiedRevenue.model_validate_json(json_str)
        assert restored.region == "NSW1"
        assert restored.scenario == "central"
        assert len(restored.annual_layers) == 3
        assert restored.layer_weighted_npv == 450000.0
        assert restored.npv_difference == -30000.0

    def test_asset_configuration_capacity_mwh(self):
        """AssetConfiguration.capacity_mwh 计算正确性。"""
        config = AssetConfiguration(
            region="NSW1",
            power_mw=200.0,
            duration_hours=2.0,
            round_trip_efficiency=0.85,
            mlf=0.95,
        )
        assert config.capacity_mwh == 400.0  # 200 * 2

    def test_asset_configuration_label_contains_key_info(self):
        """AssetConfiguration.label 包含 power_mw、duration_hours、region。"""
        config = AssetConfiguration(
            region="SA1",
            power_mw=150.0,
            duration_hours=4.0,
            round_trip_efficiency=0.85,
            mlf=0.95,
        )
        label = config.label
        assert "150" in label
        assert "4" in label
        assert "SA1" in label

    def test_pydantic_validation_power_mw_out_of_range(self):
        """power_mw 超出范围应抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            AssetConfiguration(
                region="NSW1",
                power_mw=0.5,  # < 1.0
                duration_hours=4.0,
                round_trip_efficiency=0.85,
                mlf=0.95,
            )
        with pytest.raises(ValidationError):
            AssetConfiguration(
                region="NSW1",
                power_mw=3000.0,  # > 2000
                duration_hours=4.0,
                round_trip_efficiency=0.85,
                mlf=0.95,
            )

    def test_pydantic_validation_rte_out_of_range(self):
        """round_trip_efficiency 超出范围应抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            AssetConfiguration(
                region="NSW1",
                power_mw=100.0,
                duration_hours=4.0,
                round_trip_efficiency=0.50,  # < 0.70
                mlf=0.95,
            )

    def test_layer_discount_rates_defaults(self):
        """LayerDiscountRates 默认值正确（0.08, 0.10, 0.12）。"""
        rates = LayerDiscountRates()
        assert rates.layer1 == 0.08
        assert rates.layer2 == 0.10
        assert rates.layer3 == 0.12

    def test_gas_price_assumptions_defaults(self):
        """GasPriceAssumptions 默认值正确。"""
        gas = GasPriceAssumptions()
        assert gas.base_price_per_gj == 10.0
        assert gas.annual_escalation_rate == 0.02
        assert gas.pass_through_coefficient == 9.5

    def test_network_augmentation_event_convergence_factor_range(self):
        """NetworkAugmentationEvent convergence_factor 范围验证 [0.05, 0.30]。"""
        # 有效值
        event = NetworkAugmentationEvent(
            name="HumeLink",
            from_region="NSW1",
            to_region="VIC1",
            capacity_mw=2000.0,
            expected_date=date(2028, 12, 1),
            convergence_factor=0.15,
            spread_impact_factor=0.85,
        )
        assert event.convergence_factor == 0.15

        # 超出下限
        with pytest.raises(ValidationError):
            NetworkAugmentationEvent(
                name="Test",
                from_region="NSW1",
                to_region="VIC1",
                capacity_mw=1000.0,
                expected_date=date(2028, 1, 1),
                convergence_factor=0.01,  # < 0.05
                spread_impact_factor=0.99,
            )

        # 超出上限
        with pytest.raises(ValidationError):
            NetworkAugmentationEvent(
                name="Test",
                from_region="NSW1",
                to_region="VIC1",
                capacity_mw=1000.0,
                expected_date=date(2028, 1, 1),
                convergence_factor=0.50,  # > 0.30
                spread_impact_factor=0.50,
            )

    def test_revenue_layer_validation(self):
        """RevenueLayer 验证约束。"""
        # amount 不能为负
        with pytest.raises(ValidationError):
            RevenueLayer(
                layer_number=1,
                name="Test",
                confidence=ConfidenceLevel.HIGH,
                discount_rate=0.08,
                amount=-100.0,
                percentage=50.0,
            )
        # percentage 不能超过 100
        with pytest.raises(ValidationError):
            RevenueLayer(
                layer_number=1,
                name="Test",
                confidence=ConfidenceLevel.HIGH,
                discount_rate=0.08,
                amount=100.0,
                percentage=150.0,
            )


# =============================================================================
# 2. RiskStratificationEngine 测试
# =============================================================================


class TestRiskStratificationEngine:
    """风险分层引擎测试。"""

    def test_layer_sum_equals_total(self, battery):
        """Layer1 + Layer2 + Layer3 = Total（收入分区完备性）。"""
        engine = RiskStratificationEngine(spread_threshold=300.0)
        price_data = [
            {"price": 100.0, "interval_hours": 0.5},
            {"price": 200.0, "interval_hours": 0.5},
            {"price": 500.0, "interval_hours": 0.5},
            {"price": 1000.0, "interval_hours": 0.5},
        ]
        result = engine.stratify_historical_revenue(
            price_data=price_data,
            fcas_revenue=50000.0,
            battery=battery,
        )
        layer_sum = result.layer1.amount + result.layer2.amount + result.layer3.amount
        assert abs(layer_sum - result.total_revenue) < 0.01

    def test_layer2_independent_of_threshold(self, battery):
        """Layer 2 独立于 spread_threshold（改变阈值不影响 FCAS 收入）。"""
        price_data = [
            {"price": 150.0, "interval_hours": 0.5},
            {"price": 500.0, "interval_hours": 0.5},
        ]
        fcas_revenue = 75000.0

        engine_low = RiskStratificationEngine(spread_threshold=100.0)
        engine_high = RiskStratificationEngine(spread_threshold=1000.0)

        result_low = engine_low.stratify_historical_revenue(
            price_data=price_data, fcas_revenue=fcas_revenue, battery=battery
        )
        result_high = engine_high.stratify_historical_revenue(
            price_data=price_data, fcas_revenue=fcas_revenue, battery=battery
        )

        assert result_low.layer2.amount == result_high.layer2.amount
        assert result_low.layer2.amount == fcas_revenue

    def test_npv_calculation_correctness(self, sample_annual_layers):
        """NPV 计算正确性（手动计算对比）。"""
        engine = RiskStratificationEngine(spread_threshold=300.0)
        npv_result = engine.calculate_layer_weighted_npv(sample_annual_layers)

        # 手动计算 Layer 1 NPV: 100000/(1.08)^1 + 100000/(1.08)^2 + 100000/(1.08)^3
        expected_l1 = (
            100000 / 1.08 + 100000 / (1.08**2) + 100000 / (1.08**3)
        )
        assert abs(npv_result.layer1_npv - expected_l1) < 0.01

        # 手动计算 Layer 2 NPV: 60000/(1.10)^1 + 60000/(1.10)^2 + 60000/(1.10)^3
        expected_l2 = (
            60000 / 1.10 + 60000 / (1.10**2) + 60000 / (1.10**3)
        )
        assert abs(npv_result.layer2_npv - expected_l2) < 0.01

        # 手动计算 Layer 3 NPV: 40000/(1.12)^1 + 40000/(1.12)^2 + 40000/(1.12)^3
        expected_l3 = (
            40000 / 1.12 + 40000 / (1.12**2) + 40000 / (1.12**3)
        )
        assert abs(npv_result.layer3_npv - expected_l3) < 0.01

        # Total = L1 + L2 + L3
        expected_total = expected_l1 + expected_l2 + expected_l3
        assert abs(npv_result.total_layer_weighted_npv - expected_total) < 0.01

    def test_spread_threshold_range_validation(self):
        """spread_threshold 范围验证 [0, 16600]。"""
        # 有效边界值
        engine_zero = RiskStratificationEngine(spread_threshold=0.0)
        assert engine_zero.spread_threshold == 0.0

        engine_max = RiskStratificationEngine(spread_threshold=16600.0)
        assert engine_max.spread_threshold == 16600.0

        # 超出范围
        with pytest.raises(ValueError):
            RiskStratificationEngine(spread_threshold=-1.0)
        with pytest.raises(ValueError):
            RiskStratificationEngine(spread_threshold=16601.0)

    def test_empty_price_data(self, battery):
        """空价格数据处理。"""
        engine = RiskStratificationEngine(spread_threshold=300.0)
        result = engine.stratify_historical_revenue(
            price_data=[],
            fcas_revenue=50000.0,
            battery=battery,
        )
        # Layer 1 和 Layer 3 应为 0，Layer 2 = FCAS
        assert result.layer1.amount == 0.0
        assert result.layer3.amount == 0.0
        assert result.layer2.amount == 50000.0
        assert result.total_revenue == 50000.0


# =============================================================================
# 3. NarrativeEngine 测试
# =============================================================================


class TestNarrativeEngine:
    """因果归因引擎测试。"""

    def test_empty_registry_generates_generic_text(self, empty_registry):
        """事件注册表为空时生成通用归因文本（降级策略）。"""
        engine = NarrativeEngine(empty_registry)
        result = engine.generate_spread_attribution(
            region="NSW1",
            year=2027,
            scenario=ScenarioType.CENTRAL,
            current_spread=120.0,
            base_spread=100.0,
        )
        assert isinstance(result, CausalAttribution)
        assert result.causal_factors == []
        assert "基于历史价格分布参数计算" in result.narrative_text

    def test_events_generate_named_attribution(self, event_registry):
        """有事件时生成包含事件名称的归因文本。"""
        engine = NarrativeEngine(event_registry)
        result = engine.generate_spread_attribution(
            region="NSW1",
            year=2028,
            scenario=ScenarioType.CENTRAL,
            current_spread=135.0,
            base_spread=120.0,
        )
        assert isinstance(result, CausalAttribution)
        assert len(result.causal_factors) > 0
        # 归因文本应包含事件相关信息
        assert "NSW1" in result.narrative_text

    def test_generate_spread_attribution_structure(self, event_registry):
        """generate_spread_attribution 返回正确的 CausalAttribution 结构。"""
        engine = NarrativeEngine(event_registry)
        result = engine.generate_spread_attribution(
            region="NSW1",
            year=2027,
            scenario=ScenarioType.CENTRAL,
            current_spread=130.0,
            base_spread=120.0,
        )
        assert result.metric_name == "mean_spread"
        assert result.metric_value == 130.0
        assert result.metric_unit == "$/MWh"
        assert result.region == "NSW1"
        assert result.year == 2027
        assert result.scenario == "central"

    def test_revenue_change_attribution_increase(self, event_registry):
        """generate_revenue_change_attribution 正确区分 increase。"""
        engine = NarrativeEngine(event_registry)
        result = engine.generate_revenue_change_attribution(
            region="NSW1",
            year_from=2026,
            year_to=2028,
            revenue_from=100000.0,
            revenue_to=130000.0,
            scenario=ScenarioType.CENTRAL,
        )
        assert result.metric_name == "revenue_change"
        assert result.metric_value == 30000.0
        # 增长时叙事文本应包含"增长"
        assert "增长" in result.narrative_text or "+" in result.narrative_text

    def test_revenue_change_attribution_decrease(self, event_registry):
        """generate_revenue_change_attribution 正确区分 decrease。"""
        engine = NarrativeEngine(event_registry)
        result = engine.generate_revenue_change_attribution(
            region="NSW1",
            year_from=2026,
            year_to=2028,
            revenue_from=150000.0,
            revenue_to=100000.0,
            scenario=ScenarioType.CENTRAL,
        )
        assert result.metric_value == -50000.0
        assert "下降" in result.narrative_text or "-" in result.narrative_text

    def test_revenue_change_attribution_stable(self, event_registry):
        """generate_revenue_change_attribution 正确区分 stable。"""
        engine = NarrativeEngine(event_registry)
        result = engine.generate_revenue_change_attribution(
            region="NSW1",
            year_from=2026,
            year_to=2027,
            revenue_from=100000.0,
            revenue_to=100500.0,  # < 2% change
            scenario=ScenarioType.CENTRAL,
        )
        assert "稳定" in result.narrative_text

    def test_module_conclusion_selects_primary_metric(self, event_registry):
        """generate_module_conclusion 选择正确的主要指标。"""
        engine = NarrativeEngine(event_registry)

        # npv 优先
        result = engine.generate_module_conclusion(
            module_name="financial_model",
            region="NSW1",
            metrics={"npv": 5000000.0, "irr": 0.12, "revenue": 150000.0},
        )
        assert result.metric_name == "npv"
        assert result.metric_value == 5000000.0

        # 无 npv 时选 irr
        result2 = engine.generate_module_conclusion(
            module_name="financial_model",
            region="NSW1",
            metrics={"irr": 0.15, "revenue": 150000.0},
        )
        assert result2.metric_name == "irr"


# =============================================================================
# 4. EventAnnotationService 测试
# =============================================================================


class TestEventAnnotationService:
    """事件标注服务测试。"""

    def test_region_filter(self, event_registry):
        """区域过滤正确性（只返回匹配区域的事件）。"""
        service = EventAnnotationService(event_registry)
        annotations = service.get_annotations(
            region="NSW1", start_year=2025, end_year=2030
        )
        for ann in annotations:
            assert ann.region == "NSW1"

    def test_year_range_filter(self, event_registry):
        """年份范围过滤正确性。"""
        service = EventAnnotationService(event_registry)
        annotations = service.get_annotations(
            region="NSW1", start_year=2027, end_year=2027
        )
        for ann in annotations:
            assert ann.date.year == 2027

    def test_event_type_filter(self, event_registry):
        """事件类型过滤正确性。"""
        service = EventAnnotationService(event_registry)
        annotations = service.get_annotations(
            region="NSW1",
            start_year=2025,
            end_year=2030,
            event_types=[EventType.COAL_CLOSURE],
        )
        for ann in annotations:
            assert ann.event_type == EventType.COAL_CLOSURE

    def test_empty_region_returns_empty_list(self, event_registry):
        """空区域返回空列表（不报错）。"""
        service = EventAnnotationService(event_registry)
        annotations = service.get_annotations(
            region="TAS1", start_year=2025, end_year=2030
        )
        assert annotations == []

    def test_clustering_preserves_total_count(self, event_registry):
        """聚类后总事件数不变。"""
        service = EventAnnotationService(event_registry)
        annotations = service.get_annotations(
            region="NSW1", start_year=2025, end_year=2030
        )
        clustered = service.cluster_annotations(annotations, pixel_threshold=20)

        # 计算聚类后的总事件数
        total_after = 0
        for item in clustered:
            if isinstance(item, EventCluster):
                total_after += item.event_count
            else:
                total_after += 1

        assert total_after == len(annotations)

    def test_single_event_not_clustered(self):
        """单个事件不聚类。"""
        single_event = EventAnnotation(
            event_name="Test",
            event_type=EventType.COAL_CLOSURE,
            region="NSW1",
            date=date(2027, 1, 1),
            capacity_mw=1000.0,
            confidence=EventConfidence.CONFIRMED,
            spread_impact_factor=1.1,
        )
        registry = EventRegistry(events=[], last_updated=date.today())
        service = EventAnnotationService(registry)
        clustered = service.cluster_annotations([single_event])
        assert len(clustered) == 1
        assert isinstance(clustered[0], EventAnnotation)


# =============================================================================
# 5. CrossValidationService 测试
# =============================================================================


class TestCrossValidationService:
    """交叉验证服务测试。"""

    def test_missing_file_graceful_degradation(self, event_registry):
        """外部文件不存在时降级（返回平台数据）。"""
        service = CrossValidationService(
            evidence_path=Path("/nonexistent/path/financial_evidence.json"),
            event_registry=event_registry,
        )
        # 不应抛出异常
        assert service.evidence == {}

        # compare_revenue_benchmarks 应返回仅平台数据
        entries = service.compare_revenue_benchmarks(
            region="NSW1", model_revenue=148000.0
        )
        assert len(entries) == 1  # 仅平台条目
        assert entries[0].source_name == "Platform Model"

    def test_is_stale_flag(self):
        """is_stale 标志正确性（超过 12 个月为 True）。"""
        today = date.today()
        # 13 个月前
        old_date = today.replace(year=today.year - 1) - timedelta(days=60)
        assert CrossValidationService._is_stale(old_date) is True

        # 6 个月前
        recent_date = today - timedelta(days=180)
        assert CrossValidationService._is_stale(recent_date) is False

    def test_compare_coal_retirements_structure(self, event_registry):
        """compare_coal_retirements 返回正确结构。"""
        service = CrossValidationService(
            evidence_path=Path("/nonexistent/path.json"),
            event_registry=event_registry,
        )
        entries = service.compare_coal_retirements()
        # 应有平台条目（来自 event_registry 中的 COAL_CLOSURE 事件）
        for entry in entries:
            assert entry.category == "coal_retirements"
            assert entry.source_name == "Platform Model"
            assert entry.discrepancy_pct == 0.0

    def test_compare_revenue_benchmarks_discrepancy(self, event_registry):
        """compare_revenue_benchmarks 计算差异百分比。"""
        # 创建带有外部数据的 evidence 文件
        evidence_data = {
            "cross_validation": {
                "revenue_benchmarks": [
                    {
                        "source_name": "Modo Energy",
                        "source_date": date.today().isoformat(),
                        "revenue_per_mw": 160000,
                        "region": "NSW1",
                    }
                ]
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(evidence_data, f)
            tmp_path = Path(f.name)

        try:
            service = CrossValidationService(
                evidence_path=tmp_path,
                event_registry=event_registry,
            )
            entries = service.compare_revenue_benchmarks(
                region="NSW1", model_revenue=148000.0
            )
            # 应有 2 个条目：平台 + Modo Energy
            assert len(entries) == 2
            modo_entry = entries[1]
            assert modo_entry.source_name == "Modo Energy"
            # 差异 = (160000 - 148000) / 148000 * 100 ≈ 8.1%
            expected_discrepancy = round(
                ((160000 - 148000) / 148000) * 100, 1
            )
            assert modo_entry.discrepancy_pct == expected_discrepancy
        finally:
            os.unlink(tmp_path)

    def test_compare_price_forecasts_structure(self, event_registry):
        """compare_price_forecasts 返回正确结构。"""
        service = CrossValidationService(
            evidence_path=Path("/nonexistent/path.json"),
            event_registry=event_registry,
        )
        entries = service.compare_price_forecasts(
            region="NSW1", scenario=ScenarioType.CENTRAL
        )
        assert len(entries) >= 1
        assert entries[0].category == "price_forecasts"
        assert entries[0].source_name == "Platform Model"


# =============================================================================
# 6. ForwardPriceEngine 扩展测试（燃料敏感性 + 网络增强）
# =============================================================================


class TestForwardPriceEngineExtensions:
    """燃料敏感性和网络增强方法测试。"""

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        """设置 ForwardPriceEngine（需要数据文件存在）。"""
        from engines.forward_price_engine import ForwardPriceEngine

        try:
            self.engine = ForwardPriceEngine()
            self.engine_available = True
        except FileNotFoundError:
            self.engine_available = False

    def test_fuel_sensitivity_outputs_5_scenarios(self, battery):
        """calculate_fuel_sensitivity 输出 5 个情景。"""
        if not self.engine_available:
            pytest.skip("数据文件不可用")

        result = self.engine.calculate_fuel_sensitivity(
            region="NSW1",
            scenario=ScenarioType.CENTRAL,
            battery=battery,
            gas_base_price=10.0,
            pass_through_coefficient=9.5,
        )
        assert isinstance(result, FuelSensitivityResult)
        assert len(result.scenarios) == 5
        # 验证 5 个情景的 gas_price_change_pct
        change_pcts = [s.gas_price_change_pct for s in result.scenarios]
        assert change_pcts == [-20.0, -10.0, 0.0, 10.0, 20.0]

    def test_pass_through_coefficient_zero_raises(self, battery):
        """pass_through_coefficient <= 0 抛出 ValueError。"""
        if not self.engine_available:
            pytest.skip("数据文件不可用")

        with pytest.raises(ValueError, match="pass_through_coefficient"):
            self.engine.calculate_fuel_sensitivity(
                region="NSW1",
                scenario=ScenarioType.CENTRAL,
                battery=battery,
                gas_base_price=10.0,
                pass_through_coefficient=0.0,
            )
        with pytest.raises(ValueError, match="pass_through_coefficient"):
            self.engine.calculate_fuel_sensitivity(
                region="NSW1",
                scenario=ScenarioType.CENTRAL,
                battery=battery,
                gas_base_price=10.0,
                pass_through_coefficient=-5.0,
            )

    def test_peak_price_impact_linear(self, battery):
        """peak_price_impact = delta_gas × coefficient（线性传导）。"""
        if not self.engine_available:
            pytest.skip("数据文件不可用")

        coefficient = 9.5
        gas_base = 10.0
        result = self.engine.calculate_fuel_sensitivity(
            region="NSW1",
            scenario=ScenarioType.CENTRAL,
            battery=battery,
            gas_base_price=gas_base,
            pass_through_coefficient=coefficient,
        )
        # +10% 情景: delta_gas = 10 * 0.1 = 1.0, impact = 1.0 * 9.5 = 9.5
        ten_pct = next(
            s for s in result.scenarios if s.gas_price_change_pct == 10.0
        )
        expected_impact = (gas_base * 0.1) * coefficient
        assert abs(ten_pct.peak_price_impact - expected_impact) < 0.01

        # -20% 情景: delta_gas = 10 * (-0.2) = -2.0, impact = -2.0 * 9.5 = -19.0
        neg_20 = next(
            s for s in result.scenarios if s.gas_price_change_pct == -20.0
        )
        expected_neg = (gas_base * (-0.2)) * coefficient
        assert abs(neg_20.peak_price_impact - expected_neg) < 0.01

    def test_network_impact_convergence_factor_validation(self):
        """calculate_network_impact convergence_factor 范围验证。"""
        if not self.engine_available:
            pytest.skip("数据文件不可用")

        with pytest.raises(ValueError, match="convergence_factor"):
            self.engine.calculate_network_impact(
                region="NSW1", convergence_factor=0.01
            )
        with pytest.raises(ValueError, match="convergence_factor"):
            self.engine.calculate_network_impact(
                region="NSW1", convergence_factor=0.50
            )

    def test_network_impact_spread_reduction(self):
        """网络增强后价差 <= 增强前价差。"""
        if not self.engine_available:
            pytest.skip("数据文件不可用")

        result = self.engine.calculate_network_impact(region="NSW1")
        # 如果有互联线项目，增强后价差应 <= 增强前
        if result.project_name != "No interconnector projects":
            for before, after in zip(result.spread_before, result.spread_after):
                assert after["spread"] <= before["spread"]


# =============================================================================
# 7. API 路由层测试 (narrative_routes.py)
# =============================================================================


class TestNarrativeRoutes:
    """API 路由层测试（使用 FastAPI TestClient）。"""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """设置 TestClient。"""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from routes.narrative_routes import router

            app = FastAPI()
            app.include_router(router)
            self.client = TestClient(app)
            self.client_available = True
        except (ImportError, FileNotFoundError) as e:
            self.client_available = False
            self.skip_reason = str(e)

    def test_get_attribution_normal(self):
        """GET /api/v1/narrative/attribution/{region} 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get("/api/v1/narrative/attribution/NSW1")
        assert response.status_code == 200
        data = response.json()
        assert "metric_name" in data
        assert "narrative_text" in data
        assert data["region"] == "NSW1"

    def test_get_stratification_normal(self):
        """GET /api/v1/narrative/stratification/{region} 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get("/api/v1/narrative/stratification/NSW1")
        assert response.status_code == 200
        data = response.json()
        assert "annual_layers" in data
        assert data["region"] == "NSW1"

    def test_get_events_normal(self):
        """GET /api/v1/narrative/events/{region} 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get("/api/v1/narrative/events/NSW1")
        assert response.status_code == 200
        data = response.json()
        assert "annotations" in data
        assert "total_count" in data
        assert data["region"] == "NSW1"

    def test_get_cross_validation_normal(self):
        """GET /api/v1/narrative/cross-validation/{category} 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get(
            "/api/v1/narrative/cross-validation/coal_retirements"
        )
        assert response.status_code == 200
        data = response.json()
        assert "category" in data
        assert data["category"] == "coal_retirements"
        assert "entries" in data

    def test_get_asset_config_normal(self):
        """GET /api/v1/narrative/asset-config 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get("/api/v1/narrative/asset-config")
        assert response.status_code == 200
        data = response.json()
        assert "power_mw" in data
        assert "region" in data

    def test_post_asset_config_normal(self):
        """POST /api/v1/narrative/asset-config 正常响应。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        payload = {
            "region": "SA1",
            "power_mw": 200.0,
            "duration_hours": 2.0,
            "round_trip_efficiency": 0.85,
            "mlf": 0.95,
            "connection_point": "test-point",
        }
        response = self.client.post(
            "/api/v1/narrative/asset-config", json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "SA1"
        assert data["power_mw"] == 200.0

    def test_invalid_region_returns_422(self):
        """无效区域返回 422。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get("/api/v1/narrative/attribution/INVALID")
        assert response.status_code == 422

    def test_invalid_category_returns_422(self):
        """无效类别返回 422。"""
        if not self.client_available:
            pytest.skip(f"TestClient 不可用: {self.skip_reason}")

        response = self.client.get(
            "/api/v1/narrative/cross-validation/invalid_category"
        )
        assert response.status_code == 422
