"""Tests for MetricsMiddleware + global exception handler.

Use a minimal Starlette/FastAPI app — no Databricks deps required.
"""
from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette")
fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nuclea_modeler.backend.core.exceptions import install_exception_handlers
from nuclea_modeler.backend.core.metrics import (
    MetricsMiddleware,
    reset as reset_metrics,
    snapshot,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    reset_metrics()
    a = FastAPI()
    a.add_middleware(MetricsMiddleware)
    install_exception_handlers(a)

    @a.get("/ok")
    def ok():
        return {"ok": True}

    @a.get("/boom")
    def boom():
        raise RuntimeError("simulated failure for tests")

    @a.get("/items/{item_id}")
    def get_item(item_id: str):
        return {"id": item_id}

    return a


# ─── Metrics middleware ──────────────────────────────────────────────────────


def test_snapshot_counts_2xx(app):
    client = TestClient(app, raise_server_exceptions=False)
    for _ in range(3):
        client.get("/ok")
    snap = snapshot()
    assert "/ok" in snap["routes"]
    assert snap["routes"]["/ok"]["counts"].get("2xx") == 3
    assert snap["routes"]["/ok"]["latency_ms"]["count"] == 3


def test_snapshot_counts_5xx_on_exception(app):
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    snap = snapshot()
    assert snap["routes"]["/boom"]["counts"].get("5xx") == 1


def test_snapshot_groups_by_route_pattern_not_path(app):
    """Two different `item_id` values should aggregate under the same pattern,
    so cardinality stays bounded."""
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/items/abc")
    client.get("/items/xyz")
    snap = snapshot()
    pattern = "/items/{item_id}"
    assert pattern in snap["routes"]
    assert snap["routes"][pattern]["counts"].get("2xx") == 2


def test_snapshot_has_uptime(app):
    snap = snapshot()
    assert "uptime_seconds" in snap
    assert snap["uptime_seconds"] >= 0


def test_latency_p50_p95_present(app):
    client = TestClient(app, raise_server_exceptions=False)
    for _ in range(10):
        client.get("/ok")
    snap = snapshot()
    lat = snap["routes"]["/ok"]["latency_ms"]
    assert lat["p50"] is not None
    assert lat["p95"] is not None
    assert lat["p95"] >= lat["p50"]


# ─── Exception handler ───────────────────────────────────────────────────────


def test_uncaught_exception_returns_500_with_error_id(app):
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert "error_id" in body
    assert len(body["error_id"]) == 12  # uuid4 prefix
    # X-Error-ID header matches the body
    assert r.headers["X-Error-ID"] == body["error_id"]


def test_error_response_does_not_leak_exception_text(app):
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom")
    body = r.json()
    # The raw exception text must NOT appear in the response — only a sanitised message
    assert "simulated failure for tests" not in r.text
    assert "RuntimeError" not in r.text
    assert "Erro interno do servidor" in body["detail"]


def test_404_from_fastapi_passes_through(app):
    """FastAPI's own 404 (no matching route) must NOT be reframed as 500."""
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/no-such-route")
    assert r.status_code == 404
    # FastAPI's default 404 body has "detail" but no "error_id"
    assert "error_id" not in r.json()
