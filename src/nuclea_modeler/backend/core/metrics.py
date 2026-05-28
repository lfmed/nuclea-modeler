"""Lightweight in-process metrics collection.

This is NOT a Prometheus replacement. It's a small middleware + endpoint that
tracks per-route request counts and latency p50/p95 in memory, exposed via
GET /api/metrics for quick health checks and demo dashboards.

For real production monitoring, plug into Databricks Lakehouse Monitoring or
export to Sentry/Datadog — that's a separate sprint.

Design:
- Counters: `requests_total` keyed by (route_pattern, status_class) where
  status_class is "2xx" / "3xx" / "4xx" / "5xx".
- Latency: a bounded ring of last N=512 durations per route, used to compute
  p50/p95 on read.
- Reset on process restart. Per-worker.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from statistics import median
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_BOOT_TIME = time.monotonic()
_LATENCY_RING_SIZE = 512

# (route_pattern, status_class) -> count
_counters: dict[tuple[str, str], int] = defaultdict(int)
# route_pattern -> deque[duration_ms]
_latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_LATENCY_RING_SIZE))


def _status_class(status: int) -> str:
    return f"{status // 100}xx"


def _route_key(request: Request) -> str:
    """Return the matched route pattern (e.g. `/api/entities/{entity_id}`) when
    available, otherwise the raw path. Using the pattern keeps cardinality
    bounded — a million entity ids don't explode the counter table."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    return request.url.path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Time every request and bump the in-memory counters."""

    async def dispatch(self, request: Request, call_next) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            key = _route_key(request)
            _latencies[key].append(duration_ms)
            _counters[(key, "5xx")] += 1
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        key = _route_key(request)
        _latencies[key].append(duration_ms)
        _counters[(key, _status_class(response.status_code))] += 1
        return response


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    if pct == 50:
        return round(median(values), 2)
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(pct / 100 * (len(s) - 1))))
    return round(s[k], 2)


def snapshot() -> dict[str, Any]:
    """Return a JSON-friendly snapshot of current metrics."""
    now = time.monotonic()
    by_route: dict[str, dict[str, Any]] = {}
    # Aggregate counters
    for (route, klass), count in _counters.items():
        entry = by_route.setdefault(
            route,
            {"counts": {}, "latency_ms": {"count": 0}},
        )
        entry["counts"][klass] = count
    # Aggregate latencies
    for route, ring in _latencies.items():
        values = list(ring)
        entry = by_route.setdefault(route, {"counts": {}, "latency_ms": {}})
        entry["latency_ms"] = {
            "count": len(values),
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
            "max": round(max(values), 2) if values else None,
        }

    return {
        "uptime_seconds": round(now - _BOOT_TIME, 1),
        "routes": by_route,
    }


def reset() -> None:
    """Test/debug helper: clear all counters and latencies."""
    _counters.clear()
    _latencies.clear()
