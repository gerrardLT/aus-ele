"""Unified LLM Adapter Layer.

Provides a provider-agnostic interface for LLM interactions supporting:
- OpenAI-compatible APIs (OpenAI, vLLM, LiteLLM, etc.)
- Azure OpenAI Service
- Ollama local inference
- Custom OpenAI-compatible endpoints

Configuration via environment variables:
    AUS_ELE_AGENT_LLM_PROVIDER=openai|azure|ollama|custom
    AUS_ELE_AGENT_LLM_API_KEY=sk-xxx
    AUS_ELE_AGENT_LLM_BASE_URL=https://api.openai.com/v1
    AUS_ELE_AGENT_LLM_MODEL=gpt-4o
    AUS_ELE_AGENT_LLM_TIMEOUT=30
    AUS_ELE_AGENT_LLM_MAX_TOKENS=4096
    AUS_ELE_AGENT_LLM_TEMPERATURE=0.1
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class LLMConfig:
    """LLM provider configuration loaded from environment."""

    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    timeout: float = 30.0
    max_tokens: int = 4096
    temperature: float = 0.1

    # Azure-specific
    azure_api_version: str = "2024-02-01"
    azure_deployment: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load configuration from environment variables."""
        provider = os.environ.get("AUS_ELE_AGENT_LLM_PROVIDER", "openai").strip().lower()
        api_key = os.environ.get("AUS_ELE_AGENT_LLM_API_KEY", "").strip()
        model = os.environ.get("AUS_ELE_AGENT_LLM_MODEL", "gpt-4o").strip()

        # Default base URLs per provider
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "azure": "",  # Azure uses resource URL
            "ollama": "http://localhost:11434/v1",
            "custom": "",
        }
        base_url = os.environ.get(
            "AUS_ELE_AGENT_LLM_BASE_URL", default_urls.get(provider, "")
        ).strip().rstrip("/")

        try:
            timeout = float(os.environ.get("AUS_ELE_AGENT_LLM_TIMEOUT", "30"))
        except (TypeError, ValueError):
            timeout = 30.0

        try:
            max_tokens = int(os.environ.get("AUS_ELE_AGENT_LLM_MAX_TOKENS", "4096"))
        except (TypeError, ValueError):
            max_tokens = 4096

        try:
            temperature = float(os.environ.get("AUS_ELE_AGENT_LLM_TEMPERATURE", "0.1"))
        except (TypeError, ValueError):
            temperature = 0.1

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            azure_api_version=os.environ.get("AUS_ELE_AGENT_LLM_AZURE_API_VERSION", "2024-02-01"),
            azure_deployment=os.environ.get("AUS_ELE_AGENT_LLM_AZURE_DEPLOYMENT", model),
        )


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class LLMResponse:
    """Parsed LLM response."""

    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# =============================================================================
# LLM Adapter
# =============================================================================


class LLMAdapter:
    """Unified LLM adapter supporting multiple providers.

    Usage:
        adapter = LLMAdapter()
        if adapter.is_available():
            response = await adapter.chat(messages, tools)
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client = None
        self._available: Optional[bool] = None
        # Live health-probe state (distinct from config-only _available).
        self._health_ok: Optional[bool] = None
        self._health_checked_at: float = 0.0
        self._health_ttl: float = 300.0  # re-probe at most every 5 min
        self.last_health_error: str = ""

    def is_available(self) -> bool:
        """Check if the LLM provider is configured and reachable.

        Returns False if:
        - No API key is set (except for ollama which may not need one)
        - Provider is unknown
        """
        if self._available is not None:
            return self._available

        if self.config.provider == "ollama":
            # Ollama may work without API key
            self._available = bool(self.config.base_url)
        else:
            self._available = bool(self.config.api_key and self.config.base_url)

        if not self._available:
            logger.info(
                "Agent LLM not available (provider=%s, has_key=%s, has_url=%s)",
                self.config.provider,
                bool(self.config.api_key),
                bool(self.config.base_url),
            )
        return self._available

    async def health_check(self, force: bool = False) -> bool:
        """Actively probe LLM reachability with a minimal request.

        Unlike :meth:`is_available` (config-only, synchronous), this sends a
        tiny real request to detect auth/quota/network failures (e.g. a 403
        from a proxy that is configured but not actually usable). The result
        is cached for ``_health_ttl`` seconds to avoid probing on every run.

        Args:
            force: bypass the TTL cache and probe immediately.

        Returns:
            True if a live request succeeded recently; False otherwise.
            ``last_health_error`` holds the reason on failure.
        """
        import time as _time

        # Config-only gate first: no key/url means definitely unavailable.
        if not self.is_available():
            self._health_ok = False
            self.last_health_error = "LLM provider not configured"
            return False

        # Serve cached probe result within TTL.
        now = _time.perf_counter()
        if (
            not force
            and self._health_ok is not None
            and (now - self._health_checked_at) < self._health_ttl
        ):
            return self._health_ok

        # Minimal probe request (1 token) — cheap connectivity/auth check.
        try:
            client = await self._get_client()
            url = self._build_url()
            headers = self._build_headers()
            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0.0,
            }
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            self._health_ok = True
            self.last_health_error = ""
        except Exception as exc:  # noqa: BLE001 - probe must never raise
            self._health_ok = False
            self.last_health_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("LLM health probe failed: %s", self.last_health_error)
        finally:
            self._health_checked_at = _time.perf_counter()

        return self._health_ok

    async def _get_client(self):
        """Lazy-initialize httpx.AsyncClient."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    def _build_url(self) -> str:
        """Build the chat completions endpoint URL."""
        if self.config.provider == "azure":
            deployment = self.config.azure_deployment or self.config.model
            return (
                f"{self.config.base_url}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={self.config.azure_api_version}"
            )
        # OpenAI-compatible (openai, ollama, custom)
        return f"{self.config.base_url}/chat/completions"

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.config.provider == "azure":
            headers["api-key"] = self.config.api_key
        elif self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Build the request payload."""
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if stream:
            payload["stream"] = True
        return payload

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: Conversation messages in OpenAI format.
            tools: Optional tool definitions in OpenAI format.

        Returns:
            Parsed LLMResponse with content and/or tool_calls.

        Raises:
            LLMUnavailableError: If the provider is not configured.
            LLMRequestError: If the API call fails.
        """
        if not self.is_available():
            raise LLMUnavailableError("LLM provider is not configured")

        client = await self._get_client()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, tools)

        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)
        except Exception as exc:
            logger.error("LLM request failed: %s", exc)
            raise LLMRequestError(f"LLM request failed: {exc}") from exc

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Send a streaming chat completion request.

        Yields content chunks as they arrive.
        """
        if not self.is_available():
            raise LLMUnavailableError("LLM provider is not configured")

        client = await self._get_client()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, tools, stream=True)

        try:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.error("LLM stream request failed: %s", exc)
            raise LLMRequestError(f"LLM stream failed: {exc}") from exc

    async def chat_stream_events(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Streaming chat that surfaces BOTH content deltas and tool calls.

        Unlike :meth:`chat_stream` (content-only), this drives the ReAct loop:
        it forwards assistant reasoning tokens as they arrive and accumulates
        streamed tool-call deltas (which arrive fragmented across chunks) into
        complete calls.

        Yields dict events:
            {"type": "content", "text": <token>}
            {"type": "tool_calls", "tool_calls": [{id, name, arguments(dict)}]}
            {"type": "done", "finish_reason": <str>}
        """
        if not self.is_available():
            raise LLMUnavailableError("LLM provider is not configured")

        client = await self._get_client()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, tools, stream=True)

        # Accumulate tool-call fragments keyed by their streaming index.
        acc: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"

        try:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta", {})
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]

                    content = delta.get("content")
                    if content:
                        yield {"type": "content", "text": content}

                    for tc in delta.get("tool_calls", []) or []:
                        idx = tc.get("index", 0)
                        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        func = tc.get("function", {})
                        if func.get("name"):
                            slot["name"] = func["name"]
                        if func.get("arguments"):
                            slot["arguments"] += func["arguments"]
        except Exception as exc:
            logger.error("LLM stream(events) request failed: %s", exc)
            raise LLMRequestError(f"LLM stream failed: {exc}") from exc

        if acc:
            tool_calls = []
            for idx in sorted(acc.keys()):
                slot = acc[idx]
                try:
                    arguments = json.loads(slot["arguments"]) if slot["arguments"] else {}
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append({
                    "id": slot["id"] or f"call_{idx}",
                    "name": slot["name"],
                    "arguments": arguments,
                })
            yield {"type": "tool_calls", "tool_calls": tool_calls}

        yield {"type": "done", "finish_reason": finish_reason}

    def _parse_response(self, data: Dict[str, Any]) -> LLMResponse:
        """Parse raw API response into LLMResponse."""
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(raw=data)

        message = choices[0].get("message", {})
        content = message.get("content", "") or ""
        finish_reason = choices[0].get("finish_reason", "stop")

        # Parse tool calls
        tool_calls = []
        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            func = tc.get("function", {})
            arguments_str = func.get("arguments", "{}")
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": arguments,
            })

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            raw=data,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# Exceptions
# =============================================================================


class LLMUnavailableError(Exception):
    """Raised when the LLM provider is not configured."""
    pass


class LLMRequestError(Exception):
    """Raised when an LLM API request fails."""
    pass


# =============================================================================
# Singleton accessor
# =============================================================================

_adapter_instance: Optional[LLMAdapter] = None


def get_llm_adapter() -> LLMAdapter:
    """Get or create the singleton LLM adapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LLMAdapter()
    return _adapter_instance
