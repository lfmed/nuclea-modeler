"""Tests for RequestIdMiddleware + JsonFormatter."""
from __future__ import annotations

import json
import logging

import pytest

starlette = pytest.importorskip("starlette")

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from nuclea_modeler.backend.core.logging import (
    JsonFormatter,
    RequestIdMiddleware,
    get_request_id,
)


def _build_app():
    async def show_rid(request):
        return JSONResponse({"rid_in_handler": get_request_id()})

    return Starlette(
        routes=[Route("/echo", show_rid)],
        middleware=[Middleware(RequestIdMiddleware)],
    )


# ─── Middleware ──────────────────────────────────────────────────────────────


def test_generates_request_id_when_missing():
    client = TestClient(_build_app())
    r = client.get("/echo")
    rid = r.headers["X-Request-ID"]
    assert rid and len(rid) >= 8
    # the handler also saw the same id
    assert r.json()["rid_in_handler"] == rid


def test_honours_inbound_request_id():
    client = TestClient(_build_app())
    r = client.get("/echo", headers={"x-request-id": "trace-abc-123"})
    assert r.headers["X-Request-ID"] == "trace-abc-123"
    assert r.json()["rid_in_handler"] == "trace-abc-123"


def test_sanitises_inbound_request_id():
    client = TestClient(_build_app())
    # Special chars stripped; alphanumeric/-/_ kept.
    r = client.get("/echo", headers={"x-request-id": "evil;rm -rf/* abc_123"})
    rid = r.headers["X-Request-ID"]
    # rm-rf chars dropped; spaces dropped; underscore + dash kept; alphanum kept
    assert rid == "evilrm-rf_abc_123" or set(rid) <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def test_request_id_capped_at_64_chars():
    client = TestClient(_build_app())
    long = "a" * 200
    r = client.get("/echo", headers={"x-request-id": long})
    assert len(r.headers["X-Request-ID"]) == 64


def test_request_id_resets_between_requests():
    client = TestClient(_build_app())
    r1 = client.get("/echo")
    r2 = client.get("/echo")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_context_outside_request_is_none():
    """get_request_id() must be None when no request is in flight."""
    assert get_request_id() is None


# ─── JsonFormatter ───────────────────────────────────────────────────────────


def test_json_formatter_basic_fields():
    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="nuclea.test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = json.loads(fmt.format(rec))
    assert out["level"] == "INFO"
    assert out["logger"] == "nuclea.test"
    assert out["msg"] == "hello world"
    assert "ts" in out


def test_json_formatter_includes_extras():
    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x.py", lineno=1,
        msg="m", args=(), exc_info=None,
    )
    rec.system_id = "sys-42"
    rec.entity_count = 7
    out = json.loads(fmt.format(rec))
    assert out["system_id"] == "sys-42"
    assert out["entity_count"] == 7


def test_json_formatter_serialises_exc_info():
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="x.py", lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    out = json.loads(fmt.format(rec))
    assert "boom" in out["exc_info"]


def test_json_formatter_non_serialisable_extra_falls_back_to_repr():
    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x.py", lineno=1,
        msg="m", args=(), exc_info=None,
    )

    class Weird:
        def __repr__(self):
            return "<Weird>"

    rec.thing = Weird()
    out = json.loads(fmt.format(rec))
    assert out["thing"] == "<Weird>"
