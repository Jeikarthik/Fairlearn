"""Rate limiting middleware — protects API from abuse.

Uses a simple in-memory token bucket. For production with multiple
workers, replace with Redis-backed rate limiting.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request, status


class RateLimiter:
    """In-memory token bucket rate limiter.

    Usage in main.py:
        limiter = RateLimiter(default_rpm=100)
        app.state.limiter = limiter

    Usage in routes:
        from app.core.rate_limit import check_rate_limit
        check_rate_limit(request, rpm=10)  # for expensive endpoints
    """

    def __init__(self, default_rpm: int = 100) -> None:
        self.default_rpm = default_rpm
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._max_bucket_size = 10000  # prevent memory leak

    def check(self, key: str, rpm: int | None = None) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        limit = rpm or self.default_rpm
        now = time.monotonic()
        window = 60.0  # 1 minute

        bucket = self._buckets[key]
        # Prune old entries
        cutoff = now - window
        self._buckets[key] = [t for t in bucket if t > cutoff]

        if len(self._buckets[key]) >= limit:
            return False

        self._buckets[key].append(now)

        # Prevent memory leak from too many unique keys
        if len(self._buckets) > self._max_bucket_size:
            oldest_key = min(self._buckets, key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0)
            del self._buckets[oldest_key]

        return True

    def get_remaining(self, key: str, rpm: int | None = None) -> int:
        limit = rpm or self.default_rpm
        now = time.monotonic()
        window = 60.0
        cutoff = now - window
        count = sum(1 for t in self._buckets.get(key, []) if t > cutoff)
        return max(0, limit - count)


def check_rate_limit(request: Request, *, rpm: int | None = None) -> None:
    """Check rate limit for the current request. Raises 429 if exceeded."""
    limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
    if limiter is None:
        return  # no limiter configured

    # Key by IP + path for per-endpoint limits
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
