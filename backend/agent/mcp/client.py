"""McpGateway：MCP 服务器连接管理 + 健康状态机（2026-08-15）。

设计要点：
- stdio 子进程懒启动（首次调用才连接），连接与工具列表内存缓存
- http 传输（Tavily）用 streamable HTTP，无子进程
- 健康状态机：连续 3 次失败 → degraded 并短路 60s（避免每步重试拖慢推理），
  冷却结束半开重试；成功即恢复 healthy
- 任何异常都转化为 McpGatewayError，由 adapter 层包装为工具 ERROR 观察值，
  绝不阻断 agent 运行（优雅降级）
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .config import McpServerConfig, resolve_url

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 3
_DEGRADED_COOLDOWN_SECONDS = 60.0

STATUS_UNKNOWN = "unknown"
STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_DISABLED = "disabled"


class McpGatewayError(RuntimeError):
    """网关层统一异常（连接失败/调用失败/短路中）。"""


class _ServerState:
    __slots__ = ("cfg", "status", "fail_count", "cooldown_until", "stack", "session", "tools_cache")

    def __init__(self, cfg: McpServerConfig) -> None:
        self.cfg = cfg
        self.status = STATUS_UNKNOWN
        self.fail_count = 0
        self.cooldown_until = 0.0
        self.stack: Optional[contextlib.AsyncExitStack] = None
        self.session = None
        self.tools_cache: Optional[List[Dict[str, Any]]] = None


class McpGateway:
    """按 server key 管理 MCP 连接与调用的网关单例载体。"""

    def __init__(self, servers: List[McpServerConfig]) -> None:
        self._states: Dict[str, _ServerState] = {cfg.key: _ServerState(cfg) for cfg in servers}
        self._locks: Dict[str, asyncio.Lock] = {cfg.key: asyncio.Lock() for cfg in servers}

    # ── 公共接口 ──────────────────────────────────────────────

    def keys(self) -> List[str]:
        return list(self._states.keys())

    def status(self, key: str) -> str:
        state = self._states.get(key)
        return state.status if state else STATUS_DISABLED

    def health_summary(self) -> Dict[str, str]:
        return {key: state.status for key, state in self._states.items()}

    async def list_tools(self, key: str) -> List[Dict[str, Any]]:
        """发现工具列表（缓存）。返回 [{name, description, inputSchema}]。"""
        state = self._require(key)
        if state.tools_cache is not None:
            return state.tools_cache
        session = await self._ensure_session(state)
        result = await session.list_tools()
        tools = [
            {
                "name": t.name,
                "description": getattr(t, "description", "") or "",
                "inputSchema": getattr(t, "inputSchema", None) or {"type": "object", "properties": {}},
            }
            for t in (result.tools if hasattr(result, "tools") else result)
        ]
        state.tools_cache = tools
        state.status = STATUS_HEALTHY
        return tools

    async def call_tool(self, key: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用 MCP 工具，返回解析后的 payload（dict）。"""
        state = self._require(key)
        self._check_circuit(state)
        try:
            session = await self._ensure_session(state)
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments or {}),
                timeout=state.cfg.timeout_seconds,
            )
            payload = self._extract_payload(result)
            self._mark_success(state)
            return payload
        except McpGatewayError:
            raise
        except Exception as exc:
            self._mark_failure(state, exc)
            # 连接可能已损坏：重置会话以便下次重连
            await self._reset_session(state)
            raise McpGatewayError(f"MCP call failed [{key}/{tool_name}]: {exc}") from exc

    async def shutdown(self) -> None:
        for state in self._states.values():
            await self._reset_session(state)

    # ── 内部实现 ──────────────────────────────────────────────

    def _require(self, key: str) -> _ServerState:
        state = self._states.get(key)
        if state is None:
            raise McpGatewayError(f"Unknown MCP server: {key}")
        return state

    def _check_circuit(self, state: _ServerState) -> None:
        """degraded 短路：冷却期内快速失败，冷却结束半开放行。"""
        if state.status == STATUS_DEGRADED:
            if time.monotonic() < state.cooldown_until:
                raise McpGatewayError(f"MCP server '{state.cfg.key}' degraded, circuit open")
            # 半开：允许一次尝试

    def _mark_success(self, state: _ServerState) -> None:
        state.fail_count = 0
        state.status = STATUS_HEALTHY

    def _mark_failure(self, state: _ServerState, exc: Exception) -> None:
        state.fail_count += 1
        logger.warning("MCP failure [%s] (%d/%d): %s", state.cfg.key, state.fail_count, _FAILURE_THRESHOLD, exc)
        if state.fail_count >= _FAILURE_THRESHOLD:
            state.status = STATUS_DEGRADED
            state.cooldown_until = time.monotonic() + _DEGRADED_COOLDOWN_SECONDS
            logger.warning("MCP server '%s' marked degraded for %.0fs", state.cfg.key, _DEGRADED_COOLDOWN_SECONDS)

    async def _ensure_session(self, state: _ServerState):
        if state.session is not None:
            return state.session
        async with self._locks[state.cfg.key]:
            if state.session is not None:
                return state.session
            cfg = state.cfg
            stack = contextlib.AsyncExitStack()
            try:
                if cfg.transport == "stdio":
                    from mcp import StdioServerParameters
                    from mcp.client.stdio import stdio_client

                    params = StdioServerParameters(command=cfg.command, args=list(cfg.args))
                    read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                elif cfg.transport == "http":
                    from mcp.client.streamable_http import streamablehttp_client

                    url = resolve_url(cfg)
                    read_stream, write_stream, _ = await stack.enter_async_context(streamablehttp_client(url))
                else:
                    raise McpGatewayError(f"Unsupported transport: {cfg.transport}")

                from mcp import ClientSession

                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await asyncio.wait_for(session.initialize(), timeout=cfg.timeout_seconds)
            except Exception as exc:
                await stack.aclose()
                self._mark_failure(state, exc)
                raise McpGatewayError(f"MCP connect failed [{cfg.key}]: {exc}") from exc

            state.stack = stack
            state.session = session
            state.status = STATUS_HEALTHY
            logger.info("MCP server '%s' connected (%s)", cfg.key, cfg.transport)
            return session

    async def _reset_session(self, state: _ServerState) -> None:
        state.session = None
        state.tools_cache = None
        if state.stack is not None:
            stack, state.stack = state.stack, None
            with contextlib.suppress(Exception):
                await stack.aclose()

    @staticmethod
    def _extract_payload(result: Any) -> Dict[str, Any]:
        """MCP 调用结果 → dict：优先解析 text 内容为 JSON，失败则原样带文本。"""
        content = getattr(result, "content", None)
        texts: List[str] = []
        for item in content or []:
            text = getattr(item, "text", None)
            if text:
                texts.append(text)
        combined = "\n".join(texts)
        if combined:
            try:
                parsed = json.loads(combined)
                if isinstance(parsed, dict):
                    return parsed
                return {"data": parsed}
            except (json.JSONDecodeError, ValueError):
                return {"text": combined}
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        return {"raw": str(result)[:4000]}
