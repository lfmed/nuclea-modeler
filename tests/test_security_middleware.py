"""Tests for SecurityHeadersMiddleware and RateLimitMiddleware.

These spin up a minimal Starlette app — no real Databricks deps needed.
"""
from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette")

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from nuclea_modeler.backend.core.security import (
    RateLimitMiddleware,
    RateLimitRule,
    SecurityHeadersMiddleware,
    _BUCKETS,
)


def _build_app(rules=None) -> Starlette:
    async def ok(request):
        return PlainTextResponse("ok")

    return Starlette(
        routes=[
            Route("/api/search", ok),
            Route("/api/hello", ok),
        ],
        middleware=[
            Middleware(SecurityHeadersMiddleware),
            Middleware(RateLimitMiddleware, rules=rules) if rules is not None
            else Middleware(RateLimitMiddleware),
        ],
    )


@pytest.fixture(autouse=True)
def _reset_buckets():
    _BUCKETS.clear()
    yield
    _BUCKETS.clear()


# ─── Security headers ────────────────────────────────────────────────────────


def test_security_headers_applied_on_200():
    client = TestClient(_build_app())
    r = client.get("/api/hello")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "strict-origin" in r.headers["Referrer-Policy"]
    assert "camera=()" in r.headers["Permissions-Policy"]


def test_hsts_not_set_on_http():
    client = TestClient(_build_app())
    r = client.get("/api/hello")
    # TestClient defaults to http — no HSTS
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_set_when_xfproto_https():
    client = TestClient(_build_app())
    r = client.get("/api/hello", headers={"x-forwarded-proto": "https"})
    assert "Strict-Transport-Security" in r.headers
    assert "max-age=" in r.headers["Strict-Transport-Security"]


def test_security_headers_applied_on_429():
    rules = (RateLimitRule("/api/search", max_requests=1, window_seconds=60),)
    client = TestClient(_build_app(rules=rules))
    # First passes, second is throttled
    r1 = client.get("/api/search")
    r2 = client.get("/api/search")
    assert r1.status_code == 200
    assert r2.status_code == 429
    # Headers must be on the 429 response too
    assert r2.headers["X-Content-Type-Options"] == "nosniff"


# ─── Rate limit ──────────────────────────────────────────────────────────────


def test_rate_limit_allows_under_threshold():
    rules = (RateLimitRule("/api/search", max_requests=3, window_seconds=60),)
    client = TestClient(_build_app(rules=rules))
    for _ in range(3):
        assert client.get("/api/search").status_code == 200


def test_rate_limit_blocks_over_threshold():
    rules = (RateLimitRule("/api/search", max_requests=2, window_seconds=60),)
    client = TestClient(_build_app(rules=rules))
    assert client.get("/api/search").status_code == 200
    assert client.get("/api/search").status_code == 200
    r = client.get("/api/search")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) >= 1


def test_rate_limit_isolated_per_route():
    rules = (
        RateLimitRule("/api/search", max_requests=1, window_seconds=60),
        RateLimitRule("/api/hello", max_requests=5, window_seconds=60),
    )
    client = TestClient(_build_app(rules=rules))
    # /api/search exhausted but /api/hello still has budget
    client.get("/api/search")
    assert client.get("/api/search").status_code == 429
    for _ in range(5):
        assert client.get("/api/hello").status_code == 200


def test_rate_limit_isolated_per_client_ip():
    rules = (RateLimitRule("/api/search", max_requests=1, window_seconds=60),)
    client = TestClient(_build_app(rules=rules))
    # Client A exhausts
    assert client.get("/api/search", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
    assert client.get("/api/search", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 429
    # Client B unaffected
    assert client.get("/api/search", headers={"x-forwarded-for": "2.2.2.2"}).status_code == 200


def test_rate_limit_429_response_shape():
    rules = (RateLimitRule("/api/search", max_requests=1, window_seconds=60),)
    client = TestClient(_build_app(rules=rules))
    client.get("/api/search")
    r = client.get("/api/search")
    body = r.json()
    assert "detail" in body
    assert "Rate limit" in body["detail"]
    assert r.headers["X-RateLimit-Limit"] == "1"
    assert r.headers["X-RateLimit-Window"] == "60"
