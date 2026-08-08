"""Lightweight in-process session memory for multi-turn agent conversations.

Stores compacted tool results within a session so follow-up questions
can reuse prior analysis without re-executing tools.

Design constraints:
- Pure in-memory (no Redis dependency)
- TTL 30 minutes per session
- Max 50 entries per session
- Thread-safe via GIL (single async event loop)
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from agent.schemas import SessionMemoryEntry


class SessionMemory:
    """In-process session memory with TTL-based expiry."""

    def __init__(self, ttl_seconds: float = 1800, max_entries_per_session: int = 50):
        self._ttl = ttl_seconds
        self._max_entries = max_entries_per_session
        # session_id -> (last_access_time, entries list)
        self._store: Dict[str, tuple] = {}

    def put(self, session_id: str, tool_name: str, args: Dict[str, Any], summary: str,
            data_version: str = "unknown") -> None:
        """Store a compacted tool result for the session.

        Args:
            session_id: Conversation session ID.
            tool_name: Name of the tool.
            args: Tool arguments (will be hashed).
            summary: Result summary (truncated to 500 chars).
            data_version: Current data version (e.g. '2026'). Cache entries with different
                versions are treated as separate entries (prevents stale cache after data sync).
        """
        if not session_id:
            return

        self._evict_expired()

        # Hash includes both args AND data_version to invalidate on data sync
        hash_input = json.dumps({"args": args, "data_version": data_version}, sort_keys=True, default=str)
        args_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

        entry = SessionMemoryEntry(
            tool_name=tool_name,
            arguments_hash=args_hash,
            result_summary=summary[:500],  # Cap summary length
        )

        if session_id not in self._store:
            self._store[session_id] = (time.time(), [])

        ts, entries = self._store[session_id]
        # Deduplicate: replace existing entry with same tool+args
        entries = [e for e in entries if not (e.tool_name == tool_name and e.arguments_hash == args_hash)]
        entries.append(entry)

        # Enforce max entries
        if len(entries) > self._max_entries:
            entries = entries[-self._max_entries:]

        self._store[session_id] = (time.time(), entries)

    def get_context_block(self, session_id: str) -> str:
        """Return a compact text block of prior results for LLM context injection."""
        if not session_id or session_id not in self._store:
            return ""

        ts, entries = self._store[session_id]
        if time.time() - ts > self._ttl:
            del self._store[session_id]
            return ""

        if not entries:
            return ""

        lines = ["## 本次会话已完成的分析（无需重复执行）"]
        for e in entries:
            lines.append(f"- {e.tool_name}: {e.result_summary}")
        return "\n".join(lines)

    def has_result(self, session_id: str, tool_name: str, args: Dict[str, Any],
                   data_version: str = "unknown") -> bool:
        """Check if a tool result already exists in the session (version-aware)."""
        if not session_id or session_id not in self._store:
            return False

        hash_input = json.dumps({"args": args, "data_version": data_version}, sort_keys=True, default=str)
        args_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

        _, entries = self._store[session_id]
        return any(e.tool_name == tool_name and e.arguments_hash == args_hash for e in entries)

    def get_summary(self, session_id: str, tool_name: str, args: Dict[str, Any],
                    data_version: str = "unknown") -> str:
        """Return the cached summary for a matching entry (A5 强制消费用)."""
        if not session_id or session_id not in self._store:
            return ""

        hash_input = json.dumps({"args": args, "data_version": data_version}, sort_keys=True, default=str)
        args_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

        _, entries = self._store[session_id]
        for e in entries:
            if e.tool_name == tool_name and e.arguments_hash == args_hash:
                return e.result_summary
        return ""

    def clear(self, session_id: str) -> None:
        """Clear all entries for a session."""
        self._store.pop(session_id, None)

    def _evict_expired(self) -> None:
        """Remove sessions that have exceeded TTL."""
        now = time.time()
        expired = [sid for sid, (ts, _) in self._store.items() if now - ts > self._ttl]
        for sid in expired:
            del self._store[sid]


# =============================================================================
# Redis-backed session memory (B6：多 gunicorn worker 一致性)
# =============================================================================


class RedisSessionMemory:
    """Redis 后端的会话记忆，接口与 SessionMemory 完全一致。

    Redis 不可用时逐方法回落内存实现（单 worker 内仍可用）。
    条目存为单个 JSON list（会话上限 50 条×500 字符，体积可控），
    TTL 由 Redis setex 管理。
    """

    _KEY_PREFIX = "agent_sess:"

    def __init__(self, ttl_seconds: float = 1800, max_entries_per_session: int = 50):
        self._ttl = int(ttl_seconds)
        self._max_entries = max_entries_per_session
        self._fallback = SessionMemory(ttl_seconds, max_entries_per_session)

    @staticmethod
    def _hash(args: Dict[str, Any], data_version: str) -> str:
        hash_input = json.dumps(
            {"args": args, "data_version": data_version}, sort_keys=True, default=str
        )
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    def _client(self):
        try:
            from deps import get_cache
            return get_cache()._get_client()
        except Exception:
            return None

    def _load(self, client, session_id: str) -> List[Dict[str, Any]]:
        raw = client.get(self._KEY_PREFIX + session_id)
        if not raw:
            return []
        try:
            entries = json.loads(raw)
            return entries if isinstance(entries, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _save(self, client, session_id: str, entries: List[Dict[str, Any]]) -> None:
        client.setex(
            self._KEY_PREFIX + session_id, self._ttl,
            json.dumps(entries, ensure_ascii=False),
        )

    def put(self, session_id: str, tool_name: str, args: Dict[str, Any], summary: str,
            data_version: str = "unknown") -> None:
        if not session_id:
            return
        client = self._client()
        if client is None:
            return self._fallback.put(session_id, tool_name, args, summary, data_version)
        try:
            entries = self._load(client, session_id)
            h = self._hash(args, data_version)
            entries = [
                e for e in entries
                if not (e.get("tool_name") == tool_name and e.get("arguments_hash") == h)
            ]
            entries.append({
                "tool_name": tool_name,
                "arguments_hash": h,
                "result_summary": summary[:500],
                "timestamp": time.time(),
            })
            self._save(client, session_id, entries[-self._max_entries:])
        except Exception:
            self._fallback.put(session_id, tool_name, args, summary, data_version)

    def _entries(self, session_id: str):
        """返回 (entries, from_redis)；Redis 不可达时回落内存。"""
        client = self._client()
        if client is None:
            return None, False
        try:
            return self._load(client, session_id), True
        except Exception:
            return None, False

    def get_context_block(self, session_id: str) -> str:
        if not session_id:
            return ""
        entries, ok = self._entries(session_id)
        if not ok:
            return self._fallback.get_context_block(session_id)
        if not entries:
            return ""
        lines = ["## 本次会话已完成的分析（无需重复执行）"]
        for e in entries:
            lines.append(f"- {e.get('tool_name')}: {e.get('result_summary', '')}")
        return "\n".join(lines)

    def has_result(self, session_id: str, tool_name: str, args: Dict[str, Any],
                   data_version: str = "unknown") -> bool:
        if not session_id:
            return False
        entries, ok = self._entries(session_id)
        if not ok:
            return self._fallback.has_result(session_id, tool_name, args, data_version)
        h = self._hash(args, data_version)
        return any(
            e.get("tool_name") == tool_name and e.get("arguments_hash") == h
            for e in entries
        )

    def get_summary(self, session_id: str, tool_name: str, args: Dict[str, Any],
                    data_version: str = "unknown") -> str:
        if not session_id:
            return ""
        entries, ok = self._entries(session_id)
        if not ok:
            return self._fallback.get_summary(session_id, tool_name, args, data_version)
        h = self._hash(args, data_version)
        for e in entries:
            if e.get("tool_name") == tool_name and e.get("arguments_hash") == h:
                return e.get("result_summary", "")
        return ""

    def clear(self, session_id: str) -> None:
        self._fallback.clear(session_id)
        client = self._client()
        if client is not None:
            try:
                client.delete(self._KEY_PREFIX + session_id)
            except Exception:
                pass


# =============================================================================
# Factory（编排器用：自动选 Redis 后端，不可用时内部回落内存）
# =============================================================================

_session_memory_instance = None


def get_session_memory():
    """Get or create the shared session memory (Redis-backed with fallback)."""
    global _session_memory_instance
    if _session_memory_instance is None:
        _session_memory_instance = RedisSessionMemory()
    return _session_memory_instance
