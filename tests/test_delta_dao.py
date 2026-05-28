"""Tests para os DAO helpers de core/delta.py.

Foca em validar:
- SQL gerado é bem-formado e usa quoting correto
- Apóstrofos em strings são escapados (proteção SQL injection nos sites
  trusted-input — mesmo sendo trusted, queremos consistência)
- Datas/datetimes ganham `TIMESTAMP '...'` / `DATE '...'` prefix
- new_id gera UUIDs únicos com prefix
- run levanta ValueError em failed/cancelled state

Mock minimal Sql.execute_statement — não toca warehouse real.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from databricks.sdk.service.sql import StatementState

from nuclea_modeler.backend.core import delta


def _mock_sql_capture():
    """Retorna (mock_sql, captured_list). Cada execute_statement adiciona o
    statement na lista capturada e retorna sucesso."""
    captured = []
    sql = MagicMock()

    def execute(statement: str, wait_timeout: str = "30s", parameters=None):
        captured.append(statement)
        return SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
            result=SimpleNamespace(data_array=[]),
        )

    sql.execute_statement.side_effect = execute
    return sql, captured


# ─── new_id ─────────────────────────────────────────────────────────────────


def test_new_id_returns_hex_uuid():
    uid = delta.new_id()
    assert len(uid) == 32
    int(uid, 16)  # raises se não for hex


def test_new_id_with_prefix():
    uid = delta.new_id("ent-")
    assert uid.startswith("ent-")
    assert len(uid) == 32 + len("ent-")


def test_new_id_each_call_unique():
    ids = {delta.new_id() for _ in range(100)}
    assert len(ids) == 100


# ─── insert ─────────────────────────────────────────────────────────────────


def test_insert_generates_well_formed_sql():
    sql, captured = _mock_sql_capture()
    delta.insert(
        sql,
        "cat.sch.entities",
        {"entity_id": "e1", "name": "Cliente", "active": True, "count": 42},
    )
    assert len(captured) == 1
    stmt = captured[0]
    assert stmt.startswith("INSERT INTO cat.sch.entities")
    assert "entity_id, name, active, count" in stmt
    assert "'e1'" in stmt
    assert "'Cliente'" in stmt
    assert "true" in stmt
    assert "42" in stmt


def test_insert_escapes_apostrophes():
    """Apóstrofos no value são duplicados ('') — proteção SQL injection."""
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"name": "O'Hara"})
    stmt = captured[0]
    assert "O''Hara" in stmt
    # Não pode aparecer apóstrofo isolado (que quebraria o INSERT)
    # Quotamos por ''-doubling
    raw_count = stmt.count("'")
    assert raw_count % 2 == 0  # par = quoting balanceado


def test_insert_handles_none_as_null():
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"name": None})
    stmt = captured[0]
    assert "NULL" in stmt


def test_insert_serializes_dict_to_json():
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"config": {"foo": "bar"}})
    stmt = captured[0]
    # JSON serializado como string SQL com escape
    assert '"foo"' in stmt
    assert '"bar"' in stmt


def test_insert_serializes_list_as_array():
    """Listas viram array(...) literal do Spark SQL."""
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"tags": ["a", "b", "c"]})
    stmt = captured[0]
    assert "array('a', 'b', 'c')" in stmt


def test_insert_datetime_uses_timestamp_literal():
    """datetime → TIMESTAMP '...' literal."""
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"ts": datetime(2026, 1, 15, 10, 30, 0)})
    stmt = captured[0]
    assert "TIMESTAMP '" in stmt
    assert "2026-01-15 10:30:00" in stmt


def test_insert_date_uses_date_literal():
    sql, captured = _mock_sql_capture()
    delta.insert(sql, "cat.sch.t", {"d": date(2026, 1, 15)})
    stmt = captured[0]
    assert "DATE '2026-01-15'" in stmt


def test_insert_tz_aware_datetime_normalised_to_utc():
    """datetime tz-aware deve ser normalizado para UTC antes de serialize."""
    sql, captured = _mock_sql_capture()
    brt = timezone(timedelta(hours=-3))
    dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=brt)
    delta.insert(sql, "cat.sch.t", {"ts": dt})
    stmt = captured[0]
    # 10:30 BRT (UTC-3) = 13:30 UTC
    assert "13:30:00" in stmt


# ─── update_by_id ───────────────────────────────────────────────────────────


def test_update_by_id_well_formed():
    sql, captured = _mock_sql_capture()
    delta.update_by_id(
        sql,
        "cat.sch.t",
        "id",
        "abc",
        {"name": "new", "active": False},
    )
    stmt = captured[0]
    assert stmt.startswith("UPDATE cat.sch.t SET")
    assert "name = 'new'" in stmt
    assert "active = false" in stmt
    assert "WHERE id = 'abc'" in stmt


def test_update_by_id_no_op_when_empty():
    """Updates vazio → não dispara SQL."""
    sql, captured = _mock_sql_capture()
    delta.update_by_id(sql, "cat.sch.t", "id", "abc", {})
    assert captured == []


def test_update_by_id_escapes_pk():
    """PK com apóstrofo é escapado."""
    sql, captured = _mock_sql_capture()
    delta.update_by_id(sql, "cat.sch.t", "id", "O'Hara", {"x": 1})
    stmt = captured[0]
    assert "WHERE id = 'O''Hara'" in stmt


# ─── delete_by_id ───────────────────────────────────────────────────────────


def test_delete_by_id_well_formed():
    sql, captured = _mock_sql_capture()
    delta.delete_by_id(sql, "cat.sch.t", "id", "abc")
    assert captured[0] == "DELETE FROM cat.sch.t WHERE id = 'abc'"


def test_delete_by_id_escapes_apostrophe():
    sql, captured = _mock_sql_capture()
    delta.delete_by_id(sql, "cat.sch.t", "id", "x'or'1")
    stmt = captured[0]
    assert "x''or''1" in stmt
    # Nenhum apóstrofo isolado
    assert stmt.count("'") % 2 == 0


# ─── run / run_scalar error handling ────────────────────────────────────────


def test_run_raises_on_failed_state():
    sql = MagicMock()
    sql.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(
            state=StatementState.FAILED,
            error=SimpleNamespace(message="syntax error near 'INVALID'"),
        ),
        result=None,
    )
    with pytest.raises(ValueError) as exc_info:
        delta.run(sql, "INVALID SQL")
    assert "syntax error" in str(exc_info.value)


def test_run_returns_empty_when_no_rows():
    sql = MagicMock()
    sql.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
        result=SimpleNamespace(data_array=None),
    )
    assert delta.run(sql, "SELECT 1") == []


def test_run_scalar_returns_first_value():
    sql = MagicMock()
    sql.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
        result=SimpleNamespace(data_array=[[42, "ignored"]]),
    )
    assert delta.run_scalar(sql, "SELECT 42") == 42


def test_run_scalar_returns_none_on_empty():
    sql = MagicMock()
    sql.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
        result=SimpleNamespace(data_array=[]),
    )
    assert delta.run_scalar(sql, "SELECT") is None
