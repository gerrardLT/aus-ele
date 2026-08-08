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

import asyncio
import contextvars
import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)


# =============================================================================
# Per-run usage scope (A4)
# =============================================================================

# 适配器是跨并发运行共享的单例，无隔离时 token 累加器互相污染。
# 编排器在 run 开始时用 execution_id 绑定作用域，结束时解绑。
_USAGE_SCOPE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_usage_scope", default=None
)


def _zero_usage() -> Dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "request_count": 0}


# =============================================================================
# Retry utilities (exponential backoff with jitter)
# =============================================================================

_T = TypeVar("_T")

# We retry transient errors: 429 Too Many Requests, 5xx server errors, and
# connection failures (timeouts/network). Permanent errors (401/403) are NOT retried.
_RETRYABLE_CODES = frozenset([429, 408]) | set(range(500, 600))
_RETRYABLE_EXCEPTIONS = (asyncio.TimeoutError, ConnectionError, ConnectionResetError)


async def _retry_with_backoff(
    func: Callable[..., _T],
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    jitter_factor: float = 0.3,
    is_retryable: Optional[Callable[[Exception, Any], bool]] = None,
) -> _T:
    """Execute an async function with exponential backoff retries.

    Args:
        func: Async callable to execute.
        max_retries: Maximum number of retries (total attempts = max_retries + 1).
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay cap (floor at base_delay).
        jitter_factor: Jitter range [0, jitter_factor * current_delay].
        is_retryable: Optional predicate(exc, attempt) -> True to force retry.

    Returns:
        The result of func on success.

    Raises:
        The last exception if all attempts fail.
    """
    import httpx

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as exc:
            # Check permanent failures first — never retry these.
            err_str = str(exc).lower()
            if any(perma in err_str for perma in ("unauthorized", "forbidden", "permission denied", "invalid api key")):
                logger.warning("LLM request permanent failure (no retry): %s", exc)
                raise

            # Check retryable status codes (if we have a response).
            if isinstance(exc, httpx.HTTPStatusError):
                if exc.response.status_code not in _RETRYABLE_CODES:
                    raise  # Not retryable code

            # Check retryable exceptions.
            if not isinstance(exc, _RETRYABLE_EXCEPTIONS):
                raise  # Wrong exception type

            last_exc = exc

            # Final attempt exhausted?
            if attempt == max_retries:
                break

            # Exponential backoff with jitter.
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = delay * jitter_factor * (random.random() * 2 - 1)  # [-factor, +factor]
            actual_delay = max(delay + jitter, 0.1)  # floor at 100ms

            logger.info(
                "LLM request failed, retrying attempt=%d in %.1fs (exc=%s)",
                attempt + 1, actual_delay, type(exc).__name__,
            )
            await asyncio.sleep(actual_delay)

    # All retries exhausted — raise the last exception.
    assert last_exc is not None
    raise last_exc


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

    # Retry configuration (applied on transient failures)
    max_retries: int = 2
    retry_base_delay: float = 1.0
    retry_max_delay: float = 10.0

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

        # Retry configuration
        try:
            max_retries = int(os.environ.get("AUS_ELE_AGENT_LLM_MAX_RETRIES", "2"))
        except (TypeError, ValueError):
            max_retries = 2

        try:
            retry_base_delay = float(os.environ.get("AUS_ELE_AGENT_LLM_RETRY_BASE_DELAY", "1.0"))
        except (TypeError, ValueError):
            retry_base_delay = 1.0

        try:
            retry_max_delay = float(os.environ.get("AUS_ELE_AGENT_LLM_RETRY_MAX_DELAY", "10.0"))
        except (TypeError, ValueError):
            retry_max_delay = 10.0

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
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
        # B3: 熔断三态（closed/open/half-open）。连续探测失败进 open（跳过
        # 探测直降模板，省探测 token 与延迟），冷却后转 half-open 单发探测恢复。
        self._breaker_state: str = "closed"
        self._breaker_consecutive_failures: int = 0
        self._breaker_opened_at: float = 0.0
        self._breaker_open_after: int = 2
        self._breaker_cooldown_s: float = 120.0
        # Retry configuration (retried only on transient failures: 429/5xx/timeouts)
        self._max_retries: int = self.config.max_retries if hasattr(self.config, 'max_retries') else 2
        self._retry_base_delay: float = self.config.retry_base_delay if hasattr(self.config, 'retry_base_delay') else 1.0
        self._retry_max_delay: float = self.config.retry_max_delay if hasattr(self.config, 'retry_max_delay') else 10.0
        # Token usage accumulator (cost visibility). NOTE: adapter is a singleton
        # shared across concurrent runs, so per-run figures are approximate unless
        # the orchestrator calls reset_usage() at run start (which it does).
        self._usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "request_count": 0,
        }
        # A4: 按 run_id 隔离的用量作用域（并发安全）
        self._scoped_usage: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Token usage tracking (P1: cost visibility)
    # ------------------------------------------------------------------

    def _accumulate_usage(self, usage: Dict[str, Any]) -> None:
        """Add a response's token usage to the running accumulator."""
        if not usage:
            return
        scope = _USAGE_SCOPE.get()
        if scope is not None:
            target = self._scoped_usage.setdefault(scope, _zero_usage())
        else:
            target = self._usage
        try:
            target["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            target["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
            target["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
            target["request_count"] += 1
        except (TypeError, ValueError):
            pass

    def reset_usage(self, run_id: Optional[str] = None) -> None:
        """Zero the usage accumulator (call at the start of an agent run).

        With ``run_id``: bind an isolated per-run scope (A4) so concurrent
        runs on the shared singleton adapter don't contaminate each other.
        """
        if run_id is not None:
            self._scoped_usage[run_id] = _zero_usage()
            _USAGE_SCOPE.set(run_id)
            # 防御性上限：清理最旧的作用域（编排器正常会解绑）
            if len(self._scoped_usage) > 128:
                for stale in list(self._scoped_usage)[: len(self._scoped_usage) - 128]:
                    self._scoped_usage.pop(stale, None)
            return
        self._usage = _zero_usage()

    def get_usage_snapshot(self, run_id: Optional[str] = None) -> Dict[str, int]:
        """Return a copy of the accumulated token usage (call at end of a run)."""
        if run_id is not None:
            return dict(self._scoped_usage.get(run_id) or _zero_usage())
        scope = _USAGE_SCOPE.get()
        if scope is not None and scope in self._scoped_usage:
            return dict(self._scoped_usage[scope])
        return dict(self._usage)

    def end_usage_scope(self, run_id: Optional[str] = None) -> None:
        """Unbind the per-run usage scope (call at the end of an agent run)."""
        _USAGE_SCOPE.set(None)
        if run_id is not None:
            self._scoped_usage.pop(run_id, None)

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
        # Config-only gate first: no key/url means definitely unavailable.
        if not self.is_available():
            self._health_ok = False
            self.last_health_error = "LLM provider not configured"
            return False

        import time as _time

        now = _time.perf_counter()

        # B3 熔断：open 状态跳过探测直降降级；冷却期过后转 half-open 试探恢复
        if self._breaker_state == "open" and not force:
            if now - self._breaker_opened_at < self._breaker_cooldown_s:
                return False
            self._breaker_state = "half-open"

        # Serve cached probe result within TTL (仅 closed 状态、非强制且为
        # 正结果时；负结果不走缓存，否则连续失败计数无法触发熔断)。
        if (
            not force
            and self._health_ok is True
            and self._breaker_state == "closed"
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
            # B3: 探测成功→闭合熔断（half-open 恢复路径也在此收敛）
            self._breaker_state = "closed"
            self._breaker_consecutive_failures = 0
        except Exception as exc:  # noqa: BLE001 - probe must never raise
            self._health_ok = False
            self.last_health_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("LLM health probe failed: %s", self.last_health_error)
            # B3: 连续失败计数；达阈或 half-open 试探失败→进 open
            self._breaker_consecutive_failures += 1
            if (
                self._breaker_state == "half-open"
                or self._breaker_consecutive_failures >= self._breaker_open_after
            ):
                self._breaker_state = "open"
                self._breaker_opened_at = time.perf_counter()
                logger.warning(
                    "LLM breaker OPEN after %d consecutive probe failures",
                    self._breaker_consecutive_failures,
                )
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
            # Request token usage in the final streaming chunk so the ReAct
            # loop's token cost is tracked (OpenAI-compatible; ignored otherwise).
            payload["stream_options"] = {"include_usage": True}
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
            LLMRequestError: If the API call fails after retries.
        """
        if not self.is_available():
            raise LLMUnavailableError("LLM provider is not configured")

        client = await self._get_client()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, tools)

        # Wrap the request in retry with exponential backoff
        async def _make_request() -> LLMResponse:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)

        try:
            return await _retry_with_backoff(
                _make_request,
                max_retries=self._max_retries,
                base_delay=self._retry_base_delay,
                max_delay=self._retry_max_delay,
            )
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
        Retries transient failures (429/5xx/timeouts) with exponential backoff.
        """
        if not self.is_available():
            raise LLMUnavailableError("LLM provider is not configured")

        client = await self._get_client()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, tools, stream=True)

        # Internal stream consumer (yields chunks from a single response)
        async def _consume_stream() -> AsyncIterator[str]:
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

        # 流式消费不包 _retry_with_backoff（bug 修复 2026-08-06，live 回放发现）：
        # 1) 该 helper 对 func() 做 await，而 _consume_stream() 是 async 生成器，
        #    会得到 coroutine 而非 __aiter__ 对象，'async for' 直接报错；
        # 2) 即便修复等待方式，流中途失败后重试会重复 yield 已产出的事件，
        #    污染 ReAct 轨迹。流级故障向上抛，由编排层统一降级/终止。
        try:
            async for chunk in _consume_stream():
                yield chunk
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

        Retries transient failures (429/5xx/timeouts) with exponential backoff.

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

        # Internal stream consumer: yields raw events from a single response.
        # Accumulates tool-call fragments keyed by their streaming index.
        async def _consume_stream_events() -> AsyncIterator[Dict[str, Any]]:
            acc: Dict[int, Dict[str, Any]] = {}
            finish_reason = "stop"
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
                    # Capture token usage from the final streaming chunk
                    # (present when stream_options.include_usage=True). This
                    # chunk typically has empty choices, so read it before the
                    # `if not choices` skip below.
                    chunk_usage = chunk.get("usage")
                    if chunk_usage:
                        self._accumulate_usage(chunk_usage)
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
            # After streaming completes, emit accumulated tool_calls
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

        # 同 chat_stream：流式路径不包重试（见上方 bug 修复注释）
        try:
            async for event in _consume_stream_events():
                yield event
        except Exception as exc:
            logger.error("LLM stream(events) request failed: %s", exc)
            raise LLMRequestError(f"LLM stream failed: {exc}") from exc

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
        # Accumulate token usage for cost visibility (P1).
        self._accumulate_usage(usage)

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
