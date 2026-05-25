import json
import logging
import os
import time

try:
    import redis
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    redis = None


logger = logging.getLogger(__name__)

# Circuit breaker: after a connection failure, skip Redis for this many seconds
_CIRCUIT_BREAKER_COOLDOWN_SECONDS = 60


class RedisResponseCache:
    def __init__(self, url: str | None = None, prefix: str = "aemo_api"):
        self.url = url or os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.prefix = prefix
        self._client = None
        self._last_failure_time: float = 0

    def _is_circuit_open(self) -> bool:
        """Return True if Redis recently failed and we should skip attempts."""
        if self._last_failure_time == 0:
            return False
        return (time.monotonic() - self._last_failure_time) < _CIRCUIT_BREAKER_COOLDOWN_SECONDS

    def _record_failure(self):
        """Record a failure timestamp for circuit breaker."""
        self._last_failure_time = time.monotonic()
        self._client = None

    def _get_client(self):
        if redis is None:
            return None
        if self._is_circuit_open():
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
                retry_on_timeout=False,
            )
        return self._client

    def _full_key(self, scope: str, cache_key: str) -> str:
        return f"{self.prefix}:{scope}:{cache_key}"

    def get_json(self, scope: str, cache_key: str):
        client = self._get_client()
        if client is None:
            return None

        try:
            payload = client.get(self._full_key(scope, cache_key))
            return json.loads(payload) if payload else None
        except Exception as exc:  # pragma: no cover - depends on external Redis availability
            logger.warning("Redis get failed for %s: %s", scope, exc)
            self._record_failure()
            return None

    def set_json(self, scope: str, cache_key: str, value, ttl_seconds: int):
        client = self._get_client()
        if client is None:
            return

        try:
            client.set(
                self._full_key(scope, cache_key),
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=max(int(ttl_seconds), 1),
            )
        except Exception as exc:  # pragma: no cover - depends on external Redis availability
            logger.warning("Redis set failed for %s: %s", scope, exc)
            self._record_failure()
