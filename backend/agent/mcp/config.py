"""MCP 服务器配置（2026-08-15，第一批 + 第二批）。

启用判定三层：
1. 总开关 AUS_ELE_MCP_ENABLED（缺省 true，设为 false 全部停用）
2. 单服务器开关 AUS_ELE_MCP_<KEY>_ENABLED（缺省 true）
3. 必需环境变量缺失 → 自动 disabled（如 Tavily 缺 key）

URL 模板中的 {ENV_NAME} 占位符在 resolve_url 时从环境变量注入，
配置文件不落任何密钥明文。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class McpServerConfig:
    key: str
    transport: str  # "stdio" | "http"
    command: str = ""            # stdio：可执行命令（uvx 等）
    args: tuple = field(default_factory=tuple)
    url_template: str = ""       # http：含 {ENV} 占位符的 URL 模板
    env_requirements: tuple = field(default_factory=tuple)
    profiles: tuple = field(default_factory=tuple)  # 可见的 tool_profile 名
    timeout_seconds: float = 30.0


# 第一批：实时数据 + 时效；第二批：金融宏观语境（商品类用户决策暂缓）
MCP_SERVERS: tuple = (
    McpServerConfig(
        key="aemo",
        transport="stdio",
        command="uvx",
        args=("--upgrade", "aemo-mcp"),
        profiles=("stage1_screening", "stage2_revenue"),
    ),
    McpServerConfig(
        key="au_weather",
        transport="stdio",
        command="uvx",
        args=("--upgrade", "au-weather-mcp"),
        profiles=("stage1_screening",),
    ),
    McpServerConfig(
        key="tavily",
        transport="http",
        url_template="https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        env_requirements=("TAVILY_API_KEY",),
        profiles=("stage1_screening", "stage4_outlook", "stage6_financial"),
    ),
    McpServerConfig(
        key="rba",
        transport="stdio",
        command="uvx",
        args=("--upgrade", "rba-mcp"),
        profiles=("stage6_financial",),
    ),
    McpServerConfig(
        key="abs",
        transport="stdio",
        command="uvx",
        args=("--upgrade", "abs-mcp"),
        profiles=("stage6_financial",),
    ),
    McpServerConfig(
        key="yfinance",
        transport="stdio",
        command="uvx",
        args=("--upgrade", "yfinance-mcp"),
        profiles=("stage6_financial", "multi_region_decision"),
    ),
)

_ENV_PLACEHOLDER = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")


def mcp_globally_enabled() -> bool:
    return os.environ.get("AUS_ELE_MCP_ENABLED", "true").strip().lower() != "false"


def _server_flag_enabled(cfg: McpServerConfig) -> bool:
    flag = os.environ.get(f"AUS_ELE_MCP_{cfg.key.upper()}_ENABLED", "true")
    return flag.strip().lower() != "false"


def is_server_enabled(cfg: McpServerConfig) -> bool:
    """三层启用判定；必需环境变量缺失自动 disabled。"""
    if not mcp_globally_enabled():
        return False
    if not _server_flag_enabled(cfg):
        return False
    for env_name in cfg.env_requirements:
        if not os.environ.get(env_name):
            return False
    return True


def resolve_url(cfg: McpServerConfig) -> str:
    """把 URL 模板中的 {ENV} 占位符替换为环境变量值。"""

    def _sub(match: re.Match) -> str:
        return os.environ.get(match.group(1), "")

    return _ENV_PLACEHOLDER.sub(_sub, cfg.url_template)


def enabled_servers() -> list:
    return [cfg for cfg in MCP_SERVERS if is_server_enabled(cfg)]


def server_by_key(key: str) -> McpServerConfig | None:
    for cfg in MCP_SERVERS:
        if cfg.key == key:
            return cfg
    return None
