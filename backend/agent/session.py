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

    def put(self, session_id: str, tool_name: str, args: Dict[str, Any], summary: str) -> None:
        """Store a compacted tool result for the session."""
        if not session_id:
            return

        self._evict_expired()

        args_hash = hashlib.md5(
            json.dumps(args, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]

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

    def has_result(self, session_id: str, tool_name: str, args: Dict[str, Any]) -> bool:
        """Check if a tool result already exists in the session."""
        if not session_id or session_id not in self._store:
            return False

        args_hash = hashlib.md5(
            json.dumps(args, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]

        _, entries = self._store[session_id]
        return any(e.tool_name == tool_name and e.arguments_hash == args_hash for e in entries)

    def clear(self, session_id: str) -> None:
        """Clear all entries for a session."""
        self._store.pop(session_id, None)

    def _evict_expired(self) -> None:
        """Remove sessions that have exceeded TTL."""
        now = time.time()
        expired = [sid for sid, (ts, _) in self._store.items() if now - ts > self._ttl]
        for sid in expired:
            del self._store[sid]
