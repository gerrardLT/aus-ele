"""跨 worker 共享的运行期状态（P0.7，2026-09-05）。

为什么这是容量前提而不是优化：部署以 GUNICORN_WORKERS>1 运行，而原先六处状态
存放在模块级 dict 里 —— 每个 worker 各持一份。后果是可量化的：

- 限流窗口按 worker 数线性放大（"5 次/分钟" 在 8 worker 下实际是 40 次）；
- in-flight 去重跨 worker 完全失效（同一份昂贵 MILP 会被并发算 N 次）；
- 无 TTL 的缓存（``_COOPT_CACHE`` max 50 且永不失效、``pipeline_knowledge._cache``
  改 JSON 必须重启）各 worker 不一致，运维改数据后无从判断谁用的是新版。

降级策略（关键取舍）：所有原语在 Redis 不可用时**回落到进程内实现**，而不是放行、
也不是报错。理由 —— 限流挂掉时「没有跨进程限流」严格优于「整站 500」，且行为不劣于
外置之前。容错不新造一套：熔断直接复用 ``response_cache.RedisResponseCache`` 已有的
circuit breaker（``_CIRCUIT_BREAKER_COOLDOWN_SECONDS``），这里只借它的客户端；唯一
新增的防护是把「取客户端」这一步也纳入降级（见 ``_redis``），因为既有实现只保护了
命令执行、没保护构造。
"""

from __future__ import annotations

import collections
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from response_cache import RedisResponseCache

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = os.environ.get("AUS_ELE_STATE_PREFIX", "aemo_state")

# 进程内回落窗口的键上限：原实现在失败路径上从不回收键，恶意/轮换邮箱会把内存吃满
_FALLBACK_MAX_KEYS = 4096
# 进程内影子缓存的条目上限：对齐 _COOPT_CACHE 原有的 50 条边界（不放大内存footprint）
_LOCAL_CACHE_MAX_ENTRIES = int(os.environ.get("AUS_ELE_LOCAL_CACHE_MAX_ENTRIES", "256"))

_store: "SharedStateStore | None" = None
_store_lock = threading.Lock()


class SlidingWindowLimiter:
    """进程内滑动窗口限流 —— Redis 不可用时的回落实现。

    刻意不共用一个全局 dict：每个 store 实例一份，测试可独立构造。
    """

    def __init__(self, max_keys: int = _FALLBACK_MAX_KEYS):
        self._max_keys = max_keys
        self._windows: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def register(self, key: str, *, limit: int, window_seconds: int, now: float | None = None) -> tuple[bool, float]:
        """记录一次尝试并返回 ``(是否放行, 建议重试秒数)``。

        超限路径**不追加**时间戳：否则持续撞限会把窗口无限期往后推，
        变成"越限越罚得久"的不可预测行为。
        """
        moment = time.time() if now is None else now
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= self._max_keys:
                    # 按最早时间戳淘汰，而不是 dict 插入序（插入序可能是热键）
                    oldest = min(self._windows.items(), key=lambda item: item[1][0] if item[1] else 0)[0]
                    self._windows.pop(oldest, None)
                window = collections.deque()
                self._windows[key] = window
            cutoff = moment - window_seconds
            while window and window[0] <= cutoff:
                window.popleft()
            if limit > 0 and len(window) >= limit:
                retry_after = max(0.0, window[0] + window_seconds - moment) if window else float(window_seconds)
                return False, retry_after
            window.append(moment)
            return True, 0.0

    def clear(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class SharedStateStore:
    """限流 / 短查询缓存 / 认领锁的统一切口。

    Redis 后端与进程内后端在此收敛为一组语义稳定的方法，调用方不需要知道用了哪个。
    """

    def __init__(self, cache: RedisResponseCache | None = None):
        self._cache = cache if cache is not None else RedisResponseCache(prefix=REDIS_KEY_PREFIX)
        self._limiter = SlidingWindowLimiter()
        # 进程内影子缓存：Redis 不可用时 recall 仍有读侧命中（写侧退化为单 worker）
        self._local_cache: dict[str, tuple[Any, float]] = {}
        self._local_cache_guard = threading.Lock()
        # 认领锁的进程内影子：同 worker 的第二个请求也必须让位，否则外置后
        # 单 worker 场景反而比原先更容易重复计算
        self._local_locks: dict[str, str] = {}
        self._local_lock_guard = threading.Lock()

    # --- 基础设施 -----------------------------------------------------------

    def _redis(self):
        """拿带熔断保护的客户端；**永不抛异常**，None 表示当前不可用（调用方走回落）。

        构造客户端这一步本身就会失败：``redis.Redis.from_url`` 在 URL 拼错时抛
        ValueError，且抛在 ``_record_failure`` 之前 → 既有熔断器永远不会打开，
        结果是"REDIS_URL 写错"演变成每个被限流的请求都 500。本方法是全部调用点
        的唯一收口，所以防护放在这里而不是散到各处 try。
        """
        try:
            return self._cache._get_client()  # noqa: SLF001 — 复用既有熔断，不复制一份
        except Exception as exc:  # noqa: BLE001 — 降级为进程内实现，绝不冒到请求链路
            self._fail("client", exc)
            return None

    def _fail(self, op: str, exc: Exception) -> None:
        logger.warning("shared_state redis %s failed: %s", op, exc)
        self._cache._record_failure()  # noqa: SLF001 — 同上，唯一记录点

    @staticmethod
    def _full_key(scope: str, key: str) -> str:
        return f"{scope}:{key}"

    # --- 滑动窗口限流 -------------------------------------------------------

    def register_attempt(self, scope: str, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        """一次尝试计数。返回 ``(是否放行, 建议重试秒数)``。limit<=0 表示不限流。"""
        if limit <= 0:
            return True, 0.0
        full_key = self._full_key(scope, key)
        client = self._redis()
        if client is not None:
            moment = time.time()
            try:
                pipe = client.pipeline()
                pipe.zadd(full_key, {f"{moment:.6f}-{uuid.uuid4().hex[:8]}": moment})
                pipe.zremrangebyscore(full_key, 0, moment - window_seconds)
                pipe.zcard(full_key)
                pipe.expire(full_key, window_seconds * 2)
                count = pipe.execute()[2]
                if int(count) > limit:
                    # 超限的这次尝试要撤出计数，否则它会继续占用下一个窗口
                    self._zremold(client, full_key, moment, window_seconds)
                    oldest = client.zrange(full_key, 0, 0, withscores=True)
                    retry_after = float(window_seconds)
                    if oldest:
                        retry_after = max(0.0, oldest[0][1] + window_seconds - moment)
                    return False, retry_after
                return True, 0.0
            except Exception as exc:  # noqa: BLE001 — 降级为进程内限流，不放行
                self._fail("register_attempt", exc)
        return self._limiter.register(full_key, limit=limit, window_seconds=window_seconds)

    @staticmethod
    def _zremold(client, full_key: str, moment: float, window_seconds: int) -> None:
        """删除本次刚写入、但已判定超限的成员（按时间戳边界近似撤销）。"""
        try:
            members = client.zrangebyscore(full_key, moment, moment)
            for member in members:
                client.zrem(full_key, member)
        except Exception:  # noqa: BLE001 — 撤销失败只多算一次，不影响判定
            logger.debug("shared_state limiter rollback failed", exc_info=True)

    def clear_attempts(self, scope: str, key: str) -> None:
        full_key = self._full_key(scope, key)
        client = self._redis()
        if client is not None:
            try:
                client.delete(full_key)
            except Exception as exc:  # noqa: BLE001
                self._fail("clear_attempts", exc)
        self._limiter.clear(full_key)

    # --- 带 TTL 的 JSON 缓存 ------------------------------------------------

    def remember(self, scope: str, key: str, value: Any, ttl_seconds: int) -> None:
        """写缓存：Redis 与进程内影子都写。

        影子不是冗余：Redis 中途故障时读侧仍能命中，避免「缓存层一挂就全部回源」。
        代价是本 worker 可能读到比 Redis 更新的值 —— 对秒级限流/用量缓存可接受。
        """
        self._cache.set_json(scope, key, value, ttl_seconds)
        self._remember_local(scope, key, value, ttl_seconds)

    def _remember_local(self, scope: str, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = time.time() + max(float(ttl_seconds), 1.0)
        with self._local_cache_guard:
            self._evict_local_locked(time.time())
            self._local_cache[self._full_key(scope, key)] = (value, expires_at)

    def recall(self, scope: str, key: str, ttl_seconds: int | None = None) -> Any:
        """读缓存。Redis 未命中时读进程内影子（按 full_key + 到期时间判定）。

        ``ttl_seconds`` 只用于文档与调用方语义对齐；影子自身记录了写入时刻，
        过期判定以它为准 —— 让调用方传 TTL 来判过期会出现「同一个 key 两种答案」。
        """
        payload = self._cache.get_json(scope, key)
        if payload is not None:
            return payload
        with self._local_cache_guard:
            entry = self._local_cache.get(self._full_key(scope, key))
            if not entry:
                return None
            value, expires_at = entry
            if time.time() >= expires_at:
                del self._local_cache[self._full_key(scope, key)]
                return None
            return value

    def keys(self, scope: str) -> list[str]:
        """列出该 scope 下仍在有效期内的键（运维/测试可观测性，也供后续清缓存端点用）。"""
        prefix = self._full_key(scope, "")
        client = self._redis()
        if client is not None:
            # Redis 侧的键带 RedisResponseCache 的前缀（prefix:scope:key），
            # 与影子缓存的 scope:key 不同命名空间 —— 两边都要各自剥对前缀
            redis_prefix = f"{self._cache.prefix}:{scope}:"
            try:
                found = list(client.scan_iter(match=f"{redis_prefix}*", count=200))
            except Exception as exc:  # noqa: BLE001
                self._fail("keys", exc)
            else:
                return [item[len(redis_prefix):] for item in found]
        moment = time.time()
        with self._local_cache_guard:
            return [
                full[len(prefix):]
                for full, (_, expires_at) in self._local_cache.items()
                if full.startswith(prefix) and moment < expires_at
            ]

    def forget(self, scope: str, key: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.delete(self._cache._full_key(scope, key))  # noqa: SLF001
            except Exception as exc:  # noqa: BLE001
                self._fail("forget", exc)
        with self._local_cache_guard:
            self._local_cache.pop(self._full_key(scope, key), None)

    def consume(self, scope: str, key: str) -> Any:
        """一次性读取并删除（OAuth state 这类一次性凭据专用）。

        为什么不能写成 ``recall`` + ``forget`` 两步：那是 check-then-act —— 两步之间
        同一个 state 可以被并发的第二次回调读走，一次性凭据实际变成了两次性。Redis 侧
        用 ``GETDEL`` 单命令原子完成；``GETDEL`` 不存在（Redis < 6.2）时退到
        ``MULTI`` 事务，仍比裸 get+del 强。

        两侧都要**删**，但只有 Redis 不可用时才准**读**影子。区别是安全性的关键：
        worker A 发起 /start 时把 state 写进自己的影子与 Redis；回调落在 B 上被消费掉。
        如果 A 后来读到自己的影子就等于「同一个 state 在 A 上还能用一次」—— CSRF 防线
        按 worker 数退回多次性。所以 Redis 活着时它以 Redis 的答案为准，影子只负责清掉。
        """
        payload: Any = None
        client = self._redis()
        redis_authoritative = client is not None
        if client is not None:
            full_key = self._cache._full_key(scope, key)  # noqa: SLF001
            try:
                raw = client.getdel(full_key)
            except Exception as exc:  # noqa: BLE001 — 老版本 Redis 无 GETDEL，走事务
                self._fail("consume_getdel", exc)
                try:
                    pipe = client.pipeline(transaction=True)
                    pipe.get(full_key)
                    pipe.delete(full_key)
                    raw = pipe.execute()[0]
                except Exception as second_exc:  # noqa: BLE001
                    self._fail("consume", second_exc)
                    raw = None
                    # 命令彻底失败：这次连 Redis 自己都说不好有没有删掉，才允许回落影子
                    redis_authoritative = False
            if raw:
                try:
                    payload = json.loads(raw)
                except ValueError:
                    logger.warning("shared_state consume: undecodable payload in scope=%s", scope)
                    payload = None
        with self._local_cache_guard:
            entry = self._local_cache.pop(self._full_key(scope, key), None)
        if payload is None and not redis_authoritative and entry is not None:
            value, expires_at = entry
            if time.time() < expires_at:
                payload = value
        return payload

    def _evict_local_locked(self, moment: float) -> None:
        """调用者须持 ``_local_cache_guard``。先清过期，再按到期时间淘汰到上限。

        按 ``expires_at`` 而非插入序淘汰：原 ``_COOPT_CACHE`` 用 ``next(iter(dict))``
        赶最旧插入项，会把刚被读热的那条踢掉（LRU 语义名不副实）。
        """
        expired = [k for k, (_, exp) in self._local_cache.items() if moment >= exp]
        for k in expired:
            del self._local_cache[k]
        if len(self._local_cache) < _LOCAL_CACHE_MAX_ENTRIES:
            return
        ordered = sorted(self._local_cache.items(), key=lambda item: item[1][1])
        for k, _ in ordered[: len(self._local_cache) - _LOCAL_CACHE_MAX_ENTRIES + 1]:
            del self._local_cache[k]

    # --- 认领锁（in-flight 去重的跨 worker 半边）----------------------------

    def acquire_claim(self, scope: str, key: str, ttl_seconds: int) -> str | None:
        """尝试成为该 key 的计算属主。返回 token（成功）或 None（已有人在算）。

        必须带 TTL：worker 在计算中途被 kill 时锁不能留在 Redis 里，
        否则这个 key 会永久无人敢算。
        """
        token = uuid.uuid4().hex
        full_key = self._full_key(scope, key)
        claimed_locally = False
        with self._local_lock_guard:
            if full_key not in self._local_locks:
                self._local_locks[full_key] = token
                claimed_locally = True
        if not claimed_locally:
            return None
        client = self._redis()
        if client is not None:
            try:
                ok = client.set(full_key, token, nx=True, ex=max(int(ttl_seconds), 1))
            except Exception as exc:  # noqa: BLE001
                self._fail("acquire_claim", exc)
                return token  # Redis 挂了退回单 worker 语义：本地已认领
            if not ok:
                with self._local_lock_guard:
                    if self._local_locks.get(full_key) == token:
                        del self._local_locks[full_key]
                return None
        return token

    def release_claim(self, scope: str, key: str, token: str) -> None:
        """只释放自己持有的认领 —— 属主超时后锁可能已属于别人，无条件删是 bug。"""
        full_key = self._full_key(scope, key)
        client = self._redis()
        if client is not None:
            try:
                script = (
                    "if redis.call('get', KEYS[1]) == ARGV[1] "
                    "then return redis.call('del', KEYS[1]) else return 0 end"
                )
                client.eval(script, 1, full_key, token)
            except Exception as exc:  # noqa: BLE001
                self._fail("release_claim", exc)
        with self._local_lock_guard:
            if self._local_locks.get(full_key) == token:
                del self._local_locks[full_key]

    def is_claimed(self, scope: str, key: str) -> bool:
        client = self._redis()
        if client is None:
            with self._local_lock_guard:
                return self._full_key(scope, key) in self._local_locks
        try:
            return bool(client.exists(self._full_key(scope, key)))
        except Exception as exc:  # noqa: BLE001
            self._fail("is_claimed", exc)
            with self._local_lock_guard:
                return self._full_key(scope, key) in self._local_locks

    def wait_for_result(self, scope: str, key: str, result_scope: str, *, timeout_seconds: float, poll_seconds: float = 0.5) -> Any:
        """轮等属主公布的结果（跨 worker 的 waiter 路径）。超时返回 None。"""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            payload = self._cache.get_json(result_scope, key)
            if payload is not None:
                return payload
            if not self.is_claimed(scope, key):
                # 属主已离场（崩溃/完成）：不再干等，让调用方自己算
                return self._cache.get_json(result_scope, key)
            time.sleep(poll_seconds)
        return self._cache.get_json(result_scope, key)

    def publish_result(self, result_scope: str, key: str, value: Any, ttl_seconds: int) -> None:
        self._cache.set_json(result_scope, key, value, ttl_seconds)

    def reset_for_tests(self) -> None:
        """清空进程内状态（不动 Redis），供测试 setUp 使用。"""
        self._limiter.reset()
        with self._local_cache_guard:
            self._local_cache.clear()
        with self._local_lock_guard:
            self._local_locks.clear()


def get_state_store() -> SharedStateStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SharedStateStore()
    return _store


def reset_state_store_for_tests(store: SharedStateStore | None = None) -> SharedStateStore:
    """替换全局单例并返回它，测试可注入自己的实例。"""
    global _store
    with _store_lock:
        _store = store if store is not None else SharedStateStore()
    return _store


__all__ = [
    "SharedStateStore",
    "SlidingWindowLimiter",
    "get_state_store",
    "reset_state_store_for_tests",
]
