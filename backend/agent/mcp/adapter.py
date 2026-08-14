"""MCP 工具注册适配层（2026-08-15）。

把 McpGateway 发现的外部 MCP 工具注册进既有 ToolRegistry：
- 工具名规范：mcp_<server>_<tool>
- description 加「外部实时数据」前缀标注
- async executor 包装 gateway.call_tool，结果统一包一层
  {"source": "mcp:<server>", "data_grade": "official_live", ...}
- 任何失败（服务器不可用/降级）转化为 ERROR 观察值，不阻断 agent 运行

注册时机：server.py lifespan startup 调 register_all_mcp_tools()。
tool_profiles 通过 MCP_SERVER_TOOLS + server profiles 配置并入可见集。
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Set

from ..schemas import ToolDefinition
from ..tools import ToolRegistry
from .client import McpGateway, McpGatewayError
from .config import enabled_servers

logger = logging.getLogger(__name__)

MCP_TOOL_PREFIX = "mcp_"

# server key → 已注册工具名集合（tool_profiles 并入可见集用）
MCP_SERVER_TOOLS: Dict[str, Set[str]] = {}

_gateway: Optional[McpGateway] = None


def get_gateway() -> McpGateway:
    """网关单例（懒创建）。"""
    global _gateway
    if _gateway is None:
        _gateway = McpGateway(list(enabled_servers()))
    return _gateway


def _tool_name(server_key: str, tool_name: str) -> str:
    return f"{MCP_TOOL_PREFIX}{server_key}_{tool_name}"


def _make_executor(server_key: str, tool_name: str):
    async def executor(params: dict, ctx) -> dict:  # noqa: ARG001
        gateway = get_gateway()
        try:
            payload = await gateway.call_tool(server_key, tool_name, params)
        except McpGatewayError as exc:
            # 优雅降级：返回结构化错误观察值，LLM 可改走库内工具
            return {
                "source": f"mcp:{server_key}",
                "data_grade": "unavailable",
                "error": str(exc),
                "hint": "外部 MCP 数据源暂不可用，请改用平台内置工具（库内数据）回答或说明数据不可得。",
            }
        return {
            "source": f"mcp:{server_key}",
            "data_grade": "official_live",
            "tool": tool_name,
            **payload,
        }

    return executor


async def register_all_mcp_tools(registry: Optional[ToolRegistry] = None) -> Dict[str, int]:
    """发现并注册全部启用服务器的工具。返回 {server_key: 注册数}。

    任何服务器发现失败仅记 warning 跳过，不影响启动与其他服务器。
    """
    if registry is None:
        from ..tools import _registry_instance

        registry = _registry_instance

    gateway = get_gateway()
    registered: Dict[str, int] = {}
    for key in gateway.keys():
        try:
            tools = await gateway.list_tools(key)
        except Exception as exc:  # noqa: BLE001 — 单服务器失败不阻断
            logger.warning("MCP discovery failed [%s]: %s", key, exc)
            continue
        count = 0
        names: Set[str] = set()
        for tool in tools:
            name = _tool_name(key, tool["name"])
            if registry.get_definition(name):
                names.add(name)
                continue
            registry.register(
                ToolDefinition(
                    name=name,
                    description=f"[外部实时数据·{key}] {tool['description']}",
                    parameters=tool["inputSchema"],
                    stage=f"MCP - {key}",
                ),
                _make_executor(key, tool["name"]),
            )
            names.add(name)
            count += 1
        MCP_SERVER_TOOLS[key] = names
        registered[key] = count
        logger.info("MCP tools registered [%s]: %d", key, count)
    return registered


def mcp_tools_for_profile(profile: str) -> Set[str]:
    """返回该 profile 应可见的 MCP 工具名集合（按 server profiles 配置）。"""
    from .config import MCP_SERVERS

    visible: Set[str] = set()
    for cfg in MCP_SERVERS:
        if profile in cfg.profiles:
            visible |= MCP_SERVER_TOOLS.get(cfg.key, set())
    return visible
