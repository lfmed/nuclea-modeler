"""HTTP security middleware + in-memory rate limiting.

Two middlewares applied at app composition time:

1. SecurityHeadersMiddleware
   Adds defensive headers on every response:
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY              (block clickjacking)
   - Referrer-Policy: strict-origin-when-cross-origin
   - Permissions-Policy: minimal — no camera/mic/geo
   - Strict-Transport-Security: 1y      (only when behind HTTPS)

2. RateLimitMiddleware
   In-memory sliding window rate limit, per (client_ip, route_pattern).
   Tuned for the hot endpoints (search, extraction, sync). Sized small —
   the app runs behind Databricks Apps which already provides DDoS
   protection at the edge; this is defence-in-depth, not the primary.

Both are deliberately dependency-free. For multi-instance deployments a
Redis-backed limiter would be the right next step.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_DEFAULT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamp defensive headers on every response."""

    def __init__(self, app, *, hsts_max_age: int = 31_536_000):
        super().__init__(app)
        self._hsts = f"max-age={hsts_max_age}; includeSubDomains"

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for k, v in _DEFAULT_HEADERS.items():
            response.headers.setdefault(k, v)
        # Only set HSTS when the request was actually HTTPS — otherwise it can
        # confuse local dev over plain HTTP.
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        if proto == "https":
            response.headers.setdefault("Strict-Transport-Security", self._hsts)
        return response


# ─── Rate limiting ──────────────────────────────────────────────────────────

# Map: (client_key, bucket_name) -> deque[timestamp_seconds]
_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


class RateLimitRule:
    """Per-route limit. `path_prefix` matches via startswith on the request URL path."""

    __slots__ = ("path_prefix", "max_requests", "window_seconds", "bucket_name")

    def __init__(self, path_prefix: str, max_requests: int, window_seconds: float):
        self.path_prefix = path_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.bucket_name = path_prefix


DEFAULT_RULES: tuple[RateLimitRule, ...] = (
    # Hot endpoints — search + extraction + sync. Limits chosen to be generous
    # for a single user but still rein in scripted abuse.
    RateLimitRule("/api/search", max_requests=60, window_seconds=60),
    RateLimitRule("/api/extractions/lakebase/run", max_requests=20, window_seconds=300),
    RateLimitRule("/api/extractions/ddl/run", max_requests=20, window_seconds=300),
    RateLimitRule("/api/extractions/embarcadero/run", max_requests=20, window_seconds=300),
    RateLimitRule("/api/sync/run", max_requests=10, window_seconds=300),
    RateLimitRule("/api/diagram/", max_requests=120, window_seconds=60),
)


def _client_key(request: Request) -> str:
    """Best-effort client identifier — IP from X-Forwarded-For or the socket."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit per (client_ip, route_pattern)."""

    def __init__(self, app, rules: Iterable[RateLimitRule] | None = None):
        super().__init__(app)
        self._rules: tuple[RateLimitRule, ...] = tuple(rules or DEFAULT_RULES)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rule = next((r for r in self._rules if path.startswith(r.path_prefix)), None)
        if rule is not None:
            client = _client_key(request)
            now = time.monotonic()
            bucket = _BUCKETS[(client, rule.bucket_name)]
            # Drop timestamps outside the window
            cutoff = now - rule.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= rule.max_requests:
                retry_after = max(1, int(rule.window_seconds - (now - bucket[0])))
                return JSONResponse(
                    status_code=429,
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(rule.max_requests),
                        "X-RateLimit-Window": str(int(rule.window_seconds)),
                    },
                    content={
                        "detail": (
                            f"Rate limit exceeded for {rule.path_prefix}: "
                            f"{rule.max_requests} requests per {int(rule.window_seconds)}s. "
                            f"Retry in {retry_after}s."
                        ),
                    },
                )
            bucket.append(now)
        return await call_next(request)
