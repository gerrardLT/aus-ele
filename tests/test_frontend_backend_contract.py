"""前后端一致性测试（API 契约测试）。

验证前端组件期望的 API 接口与后端实际提供的接口完全一致：
1. URL 路径一致性 — 前端调用的 API URL 与后端路由定义完全匹配
2. 响应字段一致性 — 后端返回的 JSON 字段名与前端组件中使用的字段名一致
3. 请求参数一致性 — 前端发送的 query params 与后端期望的参数名/类型一致
4. 数据类型一致性 — 数值/字符串/数组类型匹配

测试方法：使用 FastAPI TestClient 发起真实请求到后端路由，验证响应结构。
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# 设置导入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """创建 FastAPI TestClient，挂载 narrative_routes。"""
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.narrative_routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)
    except (ImportError, FileNotFoundError) as e:
        pytest.skip(f"TestClient 不可用: {e}")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

DATA_DEPENDENCY_STATUS = 503


def _check_response(response, expected_fields: list[str], context: str) -> dict:
    """检查响应状态码并验证字段存在性。

    如果返回 503（数据依赖），标记为 skip 而非失败。
    返回响应 JSON 数据。
    """
    if response.status_code == DATA_DEPENDENCY_STATUS:
        pytest.skip(f"[数据依赖] {context}: 后端返回 503，数据文件缺失")

    assert response.status_code == 200, (
        f"[{context}] 期望 200，实际 {response.status_code}: {response.text[:200]}"
    )

    data = response.json()
    missing = [f for f in expected_fields if f not in data]
    assert not missing, (
        f"[{context}] 响应缺少前端期望的字段: {missing}\n"
        f"实际字段: {list(data.keys())}"
    )
    return data


def _check_array_item_fields(
    items: list, expected_fields: list[str], context: str
):
    """验证数组中第一个元素包含期望的字段。"""
    if not items:
        pytest.skip(f"[{context}] 数组为空，无法验证内部字段结构")

    first = items[0]
    missing = [f for f in expected_fields if f not in first]
    assert not missing, (
        f"[{context}] 数组元素缺少前端期望的字段: {missing}\n"
        f"实际字段: {list(first.keys())}"
    )


# ===========================================================================
# 1. ForwardSpreadCurve 契约测试
#    GET /api/v1/narrative/forward-spread/NSW1
#    前端期望: historical_available(bool), historical(list),
#              projection(list of {year, central_spread, high_spread, low_spread})
# ===========================================================================


class TestForwardSpreadCurveContract:
    """ForwardSpreadCurve.jsx 期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/forward-spread/NSW1"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达（非 404）。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/forward-spread/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["historical_available", "historical", "projection"],
            "ForwardSpreadCurve 顶层字段",
        )

    def test_historical_available_is_bool(self, client):
        """验证 historical_available 为 bool 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["historical_available"], bool), (
            f"historical_available 应为 bool，实际为 {type(data['historical_available']).__name__}"
        )

    def test_historical_is_list(self, client):
        """验证 historical 为 list 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["historical"], list), (
            f"historical 应为 list，实际为 {type(data['historical']).__name__}"
        )

    def test_projection_is_list(self, client):
        """验证 projection 为 list 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["projection"], list), (
            f"projection 应为 list，实际为 {type(data['projection']).__name__}"
        )

    def test_projection_item_fields(self, client):
        """验证 projection 数组元素包含 {year, central_spread, high_spread, low_spread}。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["projection"],
            ["year", "central_spread", "high_spread", "low_spread"],
            "projection 元素",
        )

    def test_projection_item_types(self, client):
        """验证 projection 元素字段类型为数值。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        if not data["projection"]:
            pytest.skip("projection 为空")
        item = data["projection"][0]
        assert isinstance(item["year"], int), "year 应为 int"
        assert isinstance(item["central_spread"], (int, float)), "central_spread 应为数值"
        assert isinstance(item["high_spread"], (int, float)), "high_spread 应为数值"
        assert isinstance(item["low_spread"], (int, float)), "low_spread 应为数值"


# ===========================================================================
# 2. Stratification 契约测试
#    GET /api/v1/narrative/stratification/NSW1
#    前端期望: annual_layers(list), layer_weighted_npv(number),
#              standard_npv(number), npv_difference(number), discount_rates(object)
# ===========================================================================


class TestStratificationContract:
    """RevenueStratificationChart.jsx 期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/stratification/NSW1"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/stratification/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["annual_layers", "layer_weighted_npv", "standard_npv", "npv_difference", "discount_rates"],
            "Stratification 顶层字段",
        )

    def test_annual_layers_is_list(self, client):
        """验证 annual_layers 为 list 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["annual_layers"], list), (
            f"annual_layers 应为 list，实际为 {type(data['annual_layers']).__name__}"
        )

    def test_npv_fields_are_numbers(self, client):
        """验证 NPV 相关字段为数值类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["layer_weighted_npv"], (int, float)), (
            f"layer_weighted_npv 应为数值，实际为 {type(data['layer_weighted_npv']).__name__}"
        )
        assert isinstance(data["standard_npv"], (int, float)), (
            f"standard_npv 应为数值，实际为 {type(data['standard_npv']).__name__}"
        )
        assert isinstance(data["npv_difference"], (int, float)), (
            f"npv_difference 应为数值，实际为 {type(data['npv_difference']).__name__}"
        )

    def test_discount_rates_is_object(self, client):
        """验证 discount_rates 为 object（dict）类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["discount_rates"], dict), (
            f"discount_rates 应为 object，实际为 {type(data['discount_rates']).__name__}"
        )


# ===========================================================================
# 3. Events 契约测试
#    GET /api/v1/narrative/events/NSW1
#    前端期望: annotations(list of {event_name, event_type, date, capacity_mw,
#              confidence, spread_impact_factor}), total_count(int)
# ===========================================================================


class TestEventsContract:
    """EventAnnotation 组件期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/events/NSW1"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/events/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["annotations", "total_count"],
            "Events 顶层字段",
        )

    def test_annotations_is_list(self, client):
        """验证 annotations 为 list 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["annotations"], list), (
            f"annotations 应为 list，实际为 {type(data['annotations']).__name__}"
        )

    def test_total_count_is_int(self, client):
        """验证 total_count 为 int 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["total_count"], int), (
            f"total_count 应为 int，实际为 {type(data['total_count']).__name__}"
        )

    def test_annotation_item_fields(self, client):
        """验证 annotations 数组元素包含前端期望的字段。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["annotations"],
            ["event_name", "event_type", "date", "capacity_mw", "confidence", "spread_impact_factor"],
            "annotations 元素",
        )


# ===========================================================================
# 4. CrossValidation 契约测试
#    GET /api/v1/narrative/cross-validation/coal_retirements
#    前端期望: entries(list of {data_point, source_name, source_date,
#              reported_value, discrepancy_pct, is_stale}), last_updated
# ===========================================================================


class TestCrossValidationContract:
    """CrossValidationTable.jsx 期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/cross-validation/coal_retirements"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/cross-validation/{category}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["entries", "last_updated"],
            "CrossValidation 顶层字段",
        )

    def test_entries_is_list(self, client):
        """验证 entries 为 list 类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["entries"], list), (
            f"entries 应为 list，实际为 {type(data['entries']).__name__}"
        )

    def test_entry_item_fields(self, client):
        """验证 entries 数组元素包含前端期望的字段。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["entries"],
            ["data_point", "source_name", "source_date", "reported_value", "discrepancy_pct", "is_stale"],
            "entries 元素",
        )

    def test_last_updated_exists(self, client):
        """验证 last_updated 字段存在且为字符串。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert "last_updated" in data, "缺少 last_updated 字段"
        # last_updated 可以是 date 字符串
        assert data["last_updated"] is not None, "last_updated 不应为 null"


# ===========================================================================
# 5. AssetConfig GET 契约测试
#    GET /api/v1/narrative/asset-config
#    前端期望: region, power_mw, duration_hours, round_trip_efficiency, mlf, connection_point
# ===========================================================================


class TestAssetConfigGetContract:
    """AssetConfigPanel.jsx GET 期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/asset-config"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/asset-config"
        )

    def test_response_fields(self, client):
        """验证响应包含前端期望的所有字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["region", "power_mw", "duration_hours", "round_trip_efficiency", "mlf", "connection_point"],
            "AssetConfig GET 字段",
        )

    def test_field_types(self, client):
        """验证字段类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["region"], str), "region 应为 str"
        assert isinstance(data["power_mw"], (int, float)), "power_mw 应为数值"
        assert isinstance(data["duration_hours"], (int, float)), "duration_hours 应为数值"
        assert isinstance(data["round_trip_efficiency"], (int, float)), "round_trip_efficiency 应为数值"
        assert isinstance(data["mlf"], (int, float)), "mlf 应为数值"
        assert isinstance(data["connection_point"], str), "connection_point 应为 str"


# ===========================================================================
# 6. AssetConfig POST 契约测试
#    POST /api/v1/narrative/asset-config
#    body: {region:"SA1", power_mw:200, duration_hours:2,
#           round_trip_efficiency:0.85, mlf:0.95, connection_point:""}
# ===========================================================================


class TestAssetConfigPostContract:
    """AssetConfigPanel.jsx POST 期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/asset-config"
    PAYLOAD = {
        "region": "SA1",
        "power_mw": 200,
        "duration_hours": 2,
        "round_trip_efficiency": 0.85,
        "mlf": 0.95,
        "connection_point": "",
    }

    def test_post_returns_200(self, client):
        """验证 POST 请求返回 200。"""
        response = client.post(self.ENDPOINT, json=self.PAYLOAD)
        assert response.status_code == 200, (
            f"POST asset-config 期望 200，实际 {response.status_code}: {response.text[:200]}"
        )

    def test_post_response_fields(self, client):
        """验证 POST 响应包含前端期望的所有字段。"""
        response = client.post(self.ENDPOINT, json=self.PAYLOAD)
        _check_response(
            response,
            ["region", "power_mw", "duration_hours", "round_trip_efficiency", "mlf", "connection_point"],
            "AssetConfig POST 响应字段",
        )

    def test_post_response_reflects_input(self, client):
        """验证 POST 响应反映输入值。"""
        response = client.post(self.ENDPOINT, json=self.PAYLOAD)
        if response.status_code != 200:
            pytest.skip(f"POST 返回 {response.status_code}")
        data = response.json()
        assert data["region"] == "SA1", f"region 应为 SA1，实际为 {data['region']}"
        assert data["power_mw"] == 200, f"power_mw 应为 200，实际为 {data['power_mw']}"
        assert data["duration_hours"] == 2, f"duration_hours 应为 2，实际为 {data['duration_hours']}"


# ===========================================================================
# 7. Attribution 契约测试
#    GET /api/v1/narrative/attribution/NSW1?module=forward_price
#    前端期望: metric_name, metric_value, metric_unit, narrative_text,
#              causal_factors(list of {driver_name, driver_type, contribution_amount,
#              contribution_pct, source_reference}), region, year
# ===========================================================================


class TestAttributionContract:
    """Attribution 组件期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/attribution/NSW1"
    PARAMS = {"module": "forward_price"}

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT, params=self.PARAMS)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/attribution/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT, params=self.PARAMS)
        _check_response(
            response,
            ["metric_name", "metric_value", "metric_unit", "narrative_text",
             "causal_factors", "region", "year"],
            "Attribution 顶层字段",
        )

    def test_field_types(self, client):
        """验证字段类型。"""
        response = client.get(self.ENDPOINT, params=self.PARAMS)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["metric_name"], str), "metric_name 应为 str"
        assert isinstance(data["metric_value"], (int, float)), "metric_value 应为数值"
        assert isinstance(data["metric_unit"], str), "metric_unit 应为 str"
        assert isinstance(data["narrative_text"], str), "narrative_text 应为 str"
        assert isinstance(data["causal_factors"], list), "causal_factors 应为 list"
        assert isinstance(data["region"], str), "region 应为 str"
        assert isinstance(data["year"], int), "year 应为 int"

    def test_causal_factor_item_fields(self, client):
        """验证 causal_factors 数组元素包含前端期望的字段。"""
        response = client.get(self.ENDPOINT, params=self.PARAMS)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["causal_factors"],
            ["driver_name", "driver_type", "contribution_amount", "contribution_pct", "source_reference"],
            "causal_factors 元素",
        )


# ===========================================================================
# 8. FuelSensitivity 契约测试
#    GET /api/v1/narrative/fuel-sensitivity/NSW1
#    前端期望: sensitivity_coefficient, base_revenue, scenario,
#              scenarios(list of {gas_price_change_pct, gas_price,
#              peak_price_impact, revenue_impact, revenue_change_pct})
# ===========================================================================


class TestFuelSensitivityContract:
    """FuelSensitivity 组件期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/fuel-sensitivity/NSW1"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/fuel-sensitivity/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["sensitivity_coefficient", "base_revenue", "scenario", "scenarios"],
            "FuelSensitivity 顶层字段",
        )

    def test_field_types(self, client):
        """验证字段类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["sensitivity_coefficient"], (int, float)), (
            f"sensitivity_coefficient 应为数值，实际为 {type(data['sensitivity_coefficient']).__name__}"
        )
        assert isinstance(data["base_revenue"], (int, float)), (
            f"base_revenue 应为数值，实际为 {type(data['base_revenue']).__name__}"
        )
        assert isinstance(data["scenario"], str), (
            f"scenario 应为 str，实际为 {type(data['scenario']).__name__}"
        )
        assert isinstance(data["scenarios"], list), (
            f"scenarios 应为 list，实际为 {type(data['scenarios']).__name__}"
        )

    def test_scenario_item_fields(self, client):
        """验证 scenarios 数组元素包含前端期望的字段。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["scenarios"],
            ["gas_price_change_pct", "gas_price", "peak_price_impact", "revenue_impact", "revenue_change_pct"],
            "scenarios 元素",
        )


# ===========================================================================
# 9. NetworkImpact 契约测试
#    GET /api/v1/narrative/network-impact/NSW1
#    前端期望: project_name, region, reduction_pct,
#              spread_before(list of {year, spread}),
#              spread_after(list of {year, spread})
# ===========================================================================


class TestNetworkImpactContract:
    """NetworkImpact 组件期望的 API 契约。"""

    ENDPOINT = "/api/v1/narrative/network-impact/NSW1"

    def test_url_path_exists(self, client):
        """验证 URL 路径可达。"""
        response = client.get(self.ENDPOINT)
        assert response.status_code != 404, (
            "路由不存在: GET /api/v1/narrative/network-impact/{region}"
        )

    def test_response_top_level_fields(self, client):
        """验证响应包含前端期望的顶层字段。"""
        response = client.get(self.ENDPOINT)
        _check_response(
            response,
            ["project_name", "region", "reduction_pct", "spread_before", "spread_after"],
            "NetworkImpact 顶层字段",
        )

    def test_field_types(self, client):
        """验证字段类型。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        assert isinstance(data["project_name"], str), "project_name 应为 str"
        assert isinstance(data["region"], str), "region 应为 str"
        assert isinstance(data["reduction_pct"], (int, float)), "reduction_pct 应为数值"
        assert isinstance(data["spread_before"], list), "spread_before 应为 list"
        assert isinstance(data["spread_after"], list), "spread_after 应为 list"

    def test_spread_before_item_fields(self, client):
        """验证 spread_before 数组元素包含 {year, spread}。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["spread_before"],
            ["year", "spread"],
            "spread_before 元素",
        )

    def test_spread_after_item_fields(self, client):
        """验证 spread_after 数组元素包含 {year, spread}。"""
        response = client.get(self.ENDPOINT)
        if response.status_code == DATA_DEPENDENCY_STATUS:
            pytest.skip("数据依赖")
        data = response.json()
        _check_array_item_fields(
            data["spread_after"],
            ["year", "spread"],
            "spread_after 元素",
        )
