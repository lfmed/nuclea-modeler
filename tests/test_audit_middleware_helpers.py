"""Tests para helpers pure de audit/middleware.py.

Foca em _parse_object (path → (object_type, object_id)) e
_extract_client_ip (Request → IP string).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.audit.middleware import _extract_client_ip, _parse_object


# ─── _parse_object ──────────────────────────────────────────────────────────


# _ID_RE = ^[a-zA-Z0-9_-]{6,}$ — heurística que aceita 6+ chars alfanuméricos.
# Significa que actions com nome longo ("approve", "attributes") também batem.
# Tests refletem comportamento atual.
@pytest.mark.parametrize(
    "path,expected",
    [
        # Listings — object_type sem id
        ("/api/entities", ("entities", None)),
        ("/api/tickets", ("tickets", None)),
        ("/api/flags", ("flags", None)),
        # Detail — id 6+ chars bate
        ("/api/entities/ent-abc123", ("entities", "ent-abc123")),
        ("/api/tickets/tk-xyz789", ("tickets", "tk-xyz789")),
        # IDs curtos (<6 chars) NÃO batem o regex
        ("/api/entities/ent-1", ("entities", None)),
        # Action sub-paths — heurística aceita action 6+ chars como "id"
        ("/api/tickets/tk-1/approve", ("tickets", "approve")),     # heurística
        ("/api/entities/ent-1/attributes", ("entities", "attributes")),  # idem
        ("/api/entities/ent-abc/attr-9", ("entities", None)),       # 5 chars, não bate
        # Query strings são strippadas antes do parse
        ("/api/entities?domain=Comercial", ("entities", None)),
        ("/api/entities/ent-abc123?refresh=true", ("entities", "ent-abc123")),
        # Edge cases
        ("/", (None, None)),
        ("/api", (None, None)),
        ("/api/", (None, None)),
        ("/health", (None, None)),  # não bate prefix /api/
        ("/static/index.html", (None, None)),
    ],
)
def test_parse_object(path, expected):
    assert _parse_object(path) == expected


def test_parse_object_truncates_long_id():
    """ID muito longo é truncado a 128 chars."""
    long_id = "ent-" + ("a" * 200)
    object_type, object_id = _parse_object(f"/api/entities/{long_id}")
    assert object_type == "entities"
    assert object_id is not None
    assert len(object_id) <= 128


# ─── _extract_client_ip ─────────────────────────────────────────────────────


class _Headers:
    """Mimics Starlette's Headers — case-insensitive .get() but immutable."""
    def __init__(self, items: dict[str, str]):
        # Normaliza para case-insensitive
        self._d = {k.lower(): v for k, v in items.items()}

    def get(self, key: str, default=None):
        return self._d.get(key.lower(), default)


def _mock_request(*, xff: str | None = None, client_host: str | None = None):
    """Mock minimal de Starlette Request com headers + client.host."""
    req = MagicMock()
    headers_dict = {}
    if xff is not None:
        headers_dict["X-Forwarded-For"] = xff
    req.headers = _Headers(headers_dict)
    if client_host:
        req.client = SimpleNamespace(host=client_host)
    else:
        req.client = None
    return req


def test_extract_ip_from_xff_takes_first_hop():
    req = _mock_request(xff="203.0.113.42, 198.51.100.1, 10.0.0.1")
    assert _extract_client_ip(req) == "203.0.113.42"


def test_extract_ip_from_xff_single():
    req = _mock_request(xff="203.0.113.42")
    assert _extract_client_ip(req) == "203.0.113.42"


def test_extract_ip_strips_whitespace():
    req = _mock_request(xff="  203.0.113.42  ,  198.51.100.1")
    assert _extract_client_ip(req) == "203.0.113.42"


def test_extract_ip_falls_back_to_client_host():
    req = _mock_request(xff=None, client_host="192.168.0.1")
    assert _extract_client_ip(req) == "192.168.0.1"


def test_extract_ip_returns_none_when_no_info():
    req = _mock_request(xff=None, client_host=None)
    assert _extract_client_ip(req) is None


def test_extract_ip_truncates_64_chars():
    """IPv6 + comments podem ser longos. 64 chars é o cap."""
    long_ip = "x" * 200
    req = _mock_request(xff=long_ip)
    out = _extract_client_ip(req)
    assert out is not None
    assert len(out) <= 64


def test_extract_ip_xff_wins_over_client():
    """X-Forwarded-For (vindo do load balancer) tem precedência sobre client.host."""
    req = _mock_request(xff="203.0.113.42", client_host="10.0.0.1")
    assert _extract_client_ip(req) == "203.0.113.42"
