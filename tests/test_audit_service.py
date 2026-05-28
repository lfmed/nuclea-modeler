"""Tests para audit/service.py — list_audit + count_audit + filter combinations.

Mocks o delta.fetch_all_params + fetch_one_params para validar control flow
sem warehouse real. Foca em:
- Filtros opcionais não são passados quando None
- LIMIT clampado entre 1 e 1000
- OFFSET é negative-safe (clamp >= 0)
- count_audit usa mesmo where_clause que list_audit
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patched_audit(monkeypatch):
    """Patch settings + delta helpers; capture queries+params for assertion."""
    from nuclea_modeler.backend.audit import service
    from nuclea_modeler.backend.core import delta

    fake_settings = SimpleNamespace(catalog="test_cat", schema_="test_schema")
    fake_settings.fq_table = lambda t: f"test_cat.test_schema.{t}"
    monkeypatch.setattr(service, "get_settings", lambda: fake_settings)

    # Capture all queries + params
    captured: list[dict] = []

    def fake_fetch_all_params(sql_dep, query: str, params=None):
        captured.append({"q": query, "p": list(params or [])})
        # Return one row matching _COLS_SHORT shape (9 cols)
        now = datetime.now(timezone.utc)
        return [["aud-1", now, "alice", "ADMIN", "CREATE", "entity", "ent-1", "rid-1", "1.2.3.4"]]

    def fake_fetch_one_params(sql_dep, query: str, params=None):
        captured.append({"q": query, "p": list(params or [])})
        if "COUNT(*)" in query.upper():
            return [42]
        return None

    monkeypatch.setattr(delta, "fetch_all_params", fake_fetch_all_params)
    monkeypatch.setattr(delta, "fetch_one_params", fake_fetch_one_params)
    return captured


def _q(captured: list[dict]) -> str:
    """Concat all captured queries for inspection."""
    return "\n---\n".join(c["q"] for c in captured)


# ─── list_audit ──────────────────────────────────────────────────────────────


def test_list_audit_no_filters_returns_rows(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    rows = list_audit(sql, limit=10)
    assert len(rows) == 1
    assert rows[0].audit_id == "aud-1"
    assert rows[0].actor_email == "alice"


def test_list_audit_applies_each_filter(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(
        sql,
        actor_email="alice@nuclea",
        action="CREATE",
        object_type="entity",
        object_id="ent-1",
        since=datetime(2026, 1, 1),
        limit=20,
    )
    query = _q(patched_audit)
    assert "actor_email = :actor_email" in query
    assert "action = :action" in query
    assert "object_type = :object_type" in query
    assert "object_id = :object_id" in query
    assert "occurred_at >= :since" in query

    # All params bound
    params = patched_audit[0]["p"]
    names = {p.name for p in params}
    assert names == {"actor_email", "action", "object_type", "object_id", "since"}


def test_list_audit_skips_none_filters(patched_audit):
    """Filters set to None must NOT appear in the WHERE clause.

    Column names (object_type, action) aparecem no SELECT (COLS_SHORT)
    independentemente de filtros. O teste verifica apenas o WHERE.
    """
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(sql, actor_email="alice", limit=10)
    query = _q(patched_audit)
    # Extrai apenas o WHERE clause
    where_clause = ""
    if "WHERE" in query:
        where_clause = query.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "actor_email = :actor_email" in where_clause
    assert "action = :action" not in where_clause
    assert ":object_type" not in where_clause
    assert ":since" not in where_clause


def test_list_audit_clamps_limit_to_1000(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(sql, limit=99999)
    query = _q(patched_audit)
    assert "LIMIT 1000" in query


def test_list_audit_floors_limit_to_1(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(sql, limit=0)
    query = _q(patched_audit)
    assert "LIMIT 1" in query


def test_list_audit_negative_offset_floored_to_zero(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(sql, limit=10, offset=-5)
    query = _q(patched_audit)
    assert "OFFSET 0" in query


def test_list_audit_uses_offset(patched_audit):
    from nuclea_modeler.backend.audit.service import list_audit
    sql = MagicMock()
    list_audit(sql, limit=20, offset=40)
    query = _q(patched_audit)
    assert "LIMIT 20 OFFSET 40" in query


# ─── count_audit ─────────────────────────────────────────────────────────────


def test_count_audit_returns_int(patched_audit):
    from nuclea_modeler.backend.audit.service import count_audit
    sql = MagicMock()
    total = count_audit(sql, action="UPDATE")
    assert total == 42


def test_count_audit_uses_same_where_as_list(patched_audit):
    """Paginator depende disso — total e items precisam filtrar igual."""
    from nuclea_modeler.backend.audit.service import count_audit
    sql = MagicMock()
    count_audit(
        sql,
        actor_email="alice",
        action="DELETE",
        object_type="ticket",
        object_id="tk-1",
        since=datetime(2026, 1, 1),
    )
    query = _q(patched_audit)
    assert "COUNT(*)" in query.upper()
    assert "actor_email = :actor_email" in query
    assert "action = :action" in query
    assert "object_type = :object_type" in query
    assert "object_id = :object_id" in query
    assert "occurred_at >= :since" in query


def test_count_audit_no_filters_returns_total(patched_audit):
    from nuclea_modeler.backend.audit.service import count_audit
    sql = MagicMock()
    total = count_audit(sql)
    assert total == 42
    query = _q(patched_audit)
    assert "WHERE" not in query  # sem filtros, sem WHERE


def test_count_audit_handles_null_result(patched_audit, monkeypatch):
    """fetch_one_params retornando None → count = 0, não crash."""
    from nuclea_modeler.backend.audit import service
    from nuclea_modeler.backend.core import delta

    def fake(sql_dep, query, params=None):
        return None

    monkeypatch.setattr(delta, "fetch_one_params", fake)
    assert service.count_audit(MagicMock()) == 0
