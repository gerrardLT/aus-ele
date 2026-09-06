"""MCP 网关与适配层测试（2026-08-15，纯离线）。

覆盖：config 启用判定（三层开关）、URL 模板解析、profile 并入逻辑、
executor 包装（data_grade 标记）、降级观察值、健康状态机（连续失败→
degraded 短路→半开恢复）、工具名前缀规范。不触网、不起子进程。
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from agent.mcp import adapter, config  # noqa: E402
from agent.mcp.client import (  # noqa: E402
    _DEGRADED_COOLDOWN_SECONDS,
    _FAILURE_THRESHOLD,
    McpGateway,
    McpGatewayError,
    STATUS_DEGRADED,
    STATUS_HEALTHY,
)
from agent.mcp.config import McpServerConfig  # noqa: E402
from agent.tools import ToolRegistry  # noqa: E402


class McpConfigTests(unittest.TestCase):
    def test_global_switch_disables_all(self):
        with mock.patch.dict(os.environ, {"AUS_ELE_MCP_ENABLED": "false"}, clear=False):
            self.assertEqual(config.enabled_servers(), [])

    def test_per_server_flag(self):
        env = {"AUS_ELE_MCP_ENABLED": "true", "AUS_ELE_MCP_AEMO_ENABLED": "false"}
        with mock.patch.dict(os.environ, env, clear=False):
            keys = {cfg.key for cfg in config.enabled_servers()}
            self.assertNotIn("aemo", keys)

    def test_missing_required_env_disables_server(self):
        env = {k: v for k, v in os.environ.items() if k != "TAVILY_API_KEY"}
        env["AUS_ELE_MCP_ENABLED"] = "true"
        with mock.patch.dict(os.environ, env, clear=True):
            tavily = config.server_by_key("tavily")
            self.assertFalse(config.is_server_enabled(tavily))
            # 无 env 依赖的 server 不受影响
            aemo = config.server_by_key("aemo")
            self.assertTrue(config.is_server_enabled(aemo))

    def test_resolve_url_injects_env(self):
        tavily = config.server_by_key("tavily")
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-abc"}, clear=False):
            url = config.resolve_url(tavily)
        self.assertIn("tvly-abc", url)
        self.assertNotIn("{TAVILY_API_KEY}", url)

    def test_six_servers_configured(self):
        keys = {cfg.key for cfg in config.MCP_SERVERS}
        self.assertEqual(keys, {"aemo", "au_weather", "tavily", "rba", "abs", "yfinance"})


class FakeGateway:
    """测试替身：按脚本返回 payload 或抛 McpGatewayError。"""

    def __init__(self, payload=None, error=None):
        self.payload = payload or {"value": 42}
        self.error = error
        self.calls = []

    async def call_tool(self, key, tool_name, arguments):
        self.calls.append((key, tool_name, arguments))
        if self.error:
            raise McpGatewayError(self.error)
        return dict(self.payload)


class AdapterExecutorTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_executor_wraps_payload_with_data_grade(self):
        fake = FakeGateway(payload={"records": [{"value": 88.1}]})
        with mock.patch.object(adapter, "get_gateway", return_value=fake):
            executor = adapter._make_executor("aemo", "get_data")
            result = self._run(executor({"dataset_id": "dispatch_price"}, None))
        self.assertEqual(result["source"], "mcp:aemo")
        self.assertEqual(result["data_grade"], "official_live")
        self.assertEqual(result["tool"], "get_data")
        self.assertEqual(result["records"][0]["value"], 88.1)

    def test_executor_degrades_to_observation_on_error(self):
        fake = FakeGateway(error="MCP server 'aemo' degraded, circuit open")
        with mock.patch.object(adapter, "get_gateway", return_value=fake):
            executor = adapter._make_executor("aemo", "get_data")
            result = self._run(executor({}, None))
        self.assertEqual(result["data_grade"], "unavailable")
        self.assertIn("error", result)
        self.assertIn("hint", result)

    def test_tool_name_prefix_convention(self):
        self.assertEqual(adapter._tool_name("rba", "get_series"), "mcp_rba_get_series")

    def test_mcp_tools_for_profile_mapping(self):
        adapter.MCP_SERVER_TOOLS.clear()
        adapter.MCP_SERVER_TOOLS["aemo"] = {"mcp_aemo_get_data", "mcp_aemo_latest"}
        adapter.MCP_SERVER_TOOLS["rba"] = {"mcp_rba_get_series"}
        try:
            stage1 = adapter.mcp_tools_for_profile("stage1_screening")
            self.assertIn("mcp_aemo_get_data", stage1)
            self.assertNotIn("mcp_rba_get_series", stage1)
            stage6 = adapter.mcp_tools_for_profile("stage6_financial")
            self.assertIn("mcp_rba_get_series", stage6)
            self.assertNotIn("mcp_aemo_get_data", stage6)
        finally:
            adapter.MCP_SERVER_TOOLS.clear()


class ProfileMergeTests(unittest.TestCase):
    def test_profile_tools_merges_mcp_tools(self):
        from agent import tool_profiles

        adapter.MCP_SERVER_TOOLS.clear()
        adapter.MCP_SERVER_TOOLS["au_weather"] = {"mcp_au_weather_forecast"}
        try:
            visible = tool_profiles.profile_tools("stage1_screening")
            self.assertIn("mcp_au_weather_forecast", visible)
            self.assertIn("data_quality_check", visible)  # ALWAYS_VISIBLE 不受影响
            self.assertIn("market_screening", visible)   # 静态工具不受影响
        finally:
            adapter.MCP_SERVER_TOOLS.clear()

    def test_unknown_profile_returns_none(self):
        from agent import tool_profiles

        self.assertIsNone(tool_profiles.profile_tools("nonexistent_profile"))


class CircuitBreakerTests(unittest.TestCase):
    def _make_gateway(self):
        cfg = McpServerConfig(key="fake", transport="stdio", command="nonexistent-cmd")
        return McpGateway([cfg])

    def test_consecutive_failures_open_circuit(self):
        gw = self._make_gateway()
        state = gw._states["fake"]
        for i in range(_FAILURE_THRESHOLD):
            gw._mark_failure(state, RuntimeError(f"boom {i}"))
        self.assertEqual(state.status, STATUS_DEGRADED)
        with self.assertRaises(McpGatewayError):
            gw._check_circuit(state)

    def test_half_open_after_cooldown(self):
        import time as _time

        gw = self._make_gateway()
        state = gw._states["fake"]
        for i in range(_FAILURE_THRESHOLD):
            gw._mark_failure(state, RuntimeError("boom"))
        # 快进冷却期
        state.cooldown_until = _time.monotonic() - 1
        gw._check_circuit(state)  # 半开：不再抛错
        # 成功一次即恢复 healthy
        gw._mark_success(state)
        self.assertEqual(state.status, STATUS_HEALTHY)
        self.assertEqual(state.fail_count, 0)

    def test_below_threshold_stays_operational(self):
        gw = self._make_gateway()
        state = gw._states["fake"]
        for i in range(_FAILURE_THRESHOLD - 1):
            gw._mark_failure(state, RuntimeError("boom"))
        gw._check_circuit(state)  # 未达阈值不短路

    def test_extract_payload_json_text(self):
        class _Item:
            def __init__(self, text):
                self.text = text

        class _Result:
            content = [_Item('{"value": 1}')]
            structuredContent = None

        payload = McpGateway._extract_payload(_Result())
        self.assertEqual(payload, {"value": 1})

    def test_extract_payload_plain_text(self):
        class _Item:
            def __init__(self, text):
                self.text = text

        class _Result:
            content = [_Item("hello world")]
            structuredContent = None

        payload = McpGateway._extract_payload(_Result())
        self.assertEqual(payload, {"text": "hello world"})


if __name__ == "__main__":
    unittest.main()
