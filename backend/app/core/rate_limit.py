"""Rate limiting — in-process token bucket with optional Redis-backed distributed mode.

In single-worker dev deployments the in-memory bucket is accurate.
In multi-worker production deployments (Gunicorn/uvicorn workers or Celery),
set FAIRLENS_CELERY_BROKER_URL to a Redis URL and the limiter automatically
switches to a Redis-backed sliding window so every worker shares the same
counters — preventing the N-worker bypass where each worker allows the full
limit independently.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request, status


# ── In-process token bucket ───────────────────────────────────────


class _InMemoryLimiter:
    def __init__(self, default_rpm: int = 100) -> None:
        self.default_rpm = default_rpm
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._max_bucket_size = 10_000

    def check(self, key: str, rpm: int | None = None) -> bool:
        limit = rpm or self.default_rpm
        now = time.monotonic()
        cutoff = now - 60.0
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]
        if len(self._buckets[key]) >= limit:
            return False
        self._buckets[key].append(now)
        if len(self._buckets) > self._max_bucket_size:
            oldest = min(self._buckets, key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0)
            del self._buckets[oldest]
        return True

    def get_remaining(self, key: str, rpm: int | None = None) -> int:
        limit = rpm or self.default_rpm
        now = time.monotonic()
        count = sum(1 for t in self._buckets.get(key, []) if t > now - 60.0)
        return max(0, limit - count)


# ── Redis sliding-window limiter ──────────────────────────────────


class _RedisLimiter:
    """Distributed sliding-window rate limiter backed by Redis.

    Uses a Lua script executed atomically on the Redis server so there
    are no race conditions between the ZRANGEBYSCORE and ZADD steps.
    One sorted-set key per (client-ip, endpoint) with TTL = 70 s.
    """

    _LUA = """
local key      = KEYS[1]
local now      = tonumber(ARGV[1])
local window   = tonumber(ARGV[2])
local limit    = tonumber(ARGV[3])
local cutoff   = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, now .. '-' .. math.random(1e9))
redis.call('EXPIRE', key, math.ceil(window / 1000) + 10)
return 1
"""

    def __init__(self, redis_url: str, default_rpm: int = 100) -> None:
        import redis as _redis
        self.default_rpm = default_rpm
        self._client = _redis.from_url(redis_url, decode_responses=False)
        self._script = self._client.register_script(self._LUA)

    def check(self, key: str, rpm: int | None = None) -> bool:
        limit = rpm or self.default_rpm
        try:
            now_ms = int(time.time() * 1000)
            result = self._script(keys=[key], args=[now_ms, 60_000, limit])
            return bool(result)
        except Exception:  # noqa: BLE001
            # Redis failure → fail open (don't block legitimate traffic)
            return True

    def get_remaining(self, key: str, rpm: int | None = None) -> int:
        limit = rpm or self.default_rpm
        try:
            now_ms = int(time.time() * 1000)
            count = self._client.zcount(key, now_ms - 60_000, "+inf")
            return max(0, limit - int(count))
        except Exception:  # noqa: BLE001
            return limit


# ── Public API ────────────────────────────────────────────────────

RateLimiter = _InMemoryLimiter  # backward-compat alias for existing imports


def build_limiter(
    default_rpm: int = 100,
    redis_url: str | None = None,
) -> Any:
    """Return the best available limiter for the current deployment."""
    if redis_url:
        try:
            limiter = _RedisLimiter(redis_url, default_rpm)
            # smoke-test the connection
            limiter._client.ping()
            return limiter
        except Exception:  # noqa: BLE001
            pass
    return _InMemoryLimiter(default_rpm)


def check_rate_limit(request: Request, *, rpm: int | None = None) -> None:
    """Check rate limit for the current request. Raises 429 if exceeded."""
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is None:
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"

    if not limiter.check(key, rpm):
        remaining = limiter.get_remaining(key, rpm)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before retrying.",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Remaining": str(remaining),
            },
        )
