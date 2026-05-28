"""Tests for connection testers — ODBC, REST, DDL_IMPORT.

The ODBC tests stub `pyodbc.connect`; the REST tests use httpx's MockTransport
so we don't hit any real network.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

httpx = pytest.importorskip("httpx")

from nuclea_modeler.backend.connections import testers


# ─── DDL_IMPORT ──────────────────────────────────────────────────────────────


def test_ddl_import_always_succeeds():
    out = testers.test_ddl_import()
    assert out.status == "success"
    assert out.latency_ms >= 1
    assert "DDL_IMPORT" in (out.db_version or "")


# ─── REST ────────────────────────────────────────────────────────────────────


def _mock_ws(secrets: dict[str, str] | None = None):
    """Build a WorkspaceClient mock with a secrets API that returns base64-encoded values."""
    import base64

    ws = MagicMock()
    if secrets:
        def _get(scope, key):
            value = secrets.get(f"{scope}/{key}")
            resp = MagicMock()
            resp.value = base64.b64encode(value.encode()).decode() if value else None
            return resp
        ws.secrets.get_secret.side_effect = _get
    else:
        ws.secrets.get_secret.side_effect = Exception("no secrets configured")
    return ws


def test_rest_missing_base_url_fails():
    out = testers.test_rest(
        ws=_mock_ws(),
        config={},
        secret_scope=None,
        secret_key_token=None,
        secret_key_user=None,
        secret_key_pass=None,
    )
    assert out.status == "failure"
    assert "base_url" in (out.error or "")


def test_rest_2xx_is_success():
    def handler(request):
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    with patch.object(httpx, "Client", lambda *a, **kw: httpx.Client(transport=transport, **kw)):
        out = testers.test_rest(
            ws=_mock_ws(),
            config={"base_url": "https://api.example.com"},
            secret_scope=None,
            secret_key_token=None,
            secret_key_user=None,
            secret_key_pass=None,
        )
    assert out.status == "success"
    assert "HTTP 200" in (out.db_version or "")


def test_rest_5xx_is_failure():
    def handler(request):
        return httpx.Response(503, text="down")

    transport = httpx.MockTransport(handler)
    with patch.object(httpx, "Client", lambda *a, **kw: httpx.Client(transport=transport, **kw)):
        out = testers.test_rest(
            ws=_mock_ws(),
            config={"base_url": "https://api.example.com"},
            secret_scope=None,
            secret_key_token=None,
            secret_key_user=None,
            secret_key_pass=None,
        )
    assert out.status == "failure"
    assert "503" in (out.error or "")


def test_rest_bearer_requires_token_secret():
    out = testers.test_rest(
        ws=_mock_ws(),
        config={"base_url": "https://api.example.com", "auth_type": "BEARER"},
        secret_scope="myscope",
        secret_key_token="api_token",
        secret_key_user=None,
        secret_key_pass=None,
    )
    assert out.status == "failure"
    assert "BEARER" in (out.error or "")


def test_rest_bearer_sends_authorization_header():
    captured: dict = {}

    def handler(request):
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    with patch.object(httpx, "Client", lambda *a, **kw: httpx.Client(transport=transport, **kw)):
        out = testers.test_rest(
            ws=_mock_ws({"myscope/api_token": "abc123"}),
            config={"base_url": "https://api.example.com", "auth_type": "BEARER"},
            secret_scope="myscope",
            secret_key_token="api_token",
            secret_key_user=None,
            secret_key_pass=None,
        )
    assert out.status == "success"
    assert captured["auth"] == "Bearer abc123"


def test_rest_oauth2_returns_clear_unsupported_error():
    out = testers.test_rest(
        ws=_mock_ws(),
        config={"base_url": "https://api.example.com", "auth_type": "OAUTH2"},
        secret_scope=None,
        secret_key_token=None,
        secret_key_user=None,
        secret_key_pass=None,
    )
    assert out.status == "failure"
    assert "OAUTH2" in (out.error or "")


# ─── ODBC ────────────────────────────────────────────────────────────────────


def test_odbc_empty_config_fails():
    out = testers.test_odbc(
        ws=_mock_ws(),
        config={},
        secret_scope=None,
        secret_key_user=None,
        secret_key_pass=None,
    )
    # Either "pyodbc not installed" (no driver locally) or "empty ODBC config".
    # Both are acceptable failures — the point is that we don't crash.
    assert out.status == "failure"
    assert out.error is not None
