"""Tests for the migrations runner — statement splitter, checksum, ordering.

Doesn't hit a real warehouse — uses a mock Sql client to validate the
control flow (already_applied, drift detection, ordering, idempotência).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.core import migrations


# ─── Statement splitter ──────────────────────────────────────────────────────


def test_statement_splitter_basic():
    sql = "CREATE TABLE a (x INT);\nINSERT INTO a VALUES (1);"
    stmts = migrations._statements(sql)
    assert len(stmts) == 2
    assert "CREATE TABLE" in stmts[0]
    assert "INSERT INTO" in stmts[1]


def test_statement_splitter_drops_empty_and_comment_only():
    sql = """
        -- this is a comment
        -- another
        ;
        CREATE TABLE a (x INT);
        -- trailing comment
        ;
    """
    stmts = migrations._statements(sql)
    assert len(stmts) == 1
    assert "CREATE TABLE" in stmts[0]


def test_statement_splitter_preserves_inline_comments():
    sql = """
        CREATE TABLE a (
            -- this column holds the id
            x INT
        );
    """
    stmts = migrations._statements(sql)
    assert len(stmts) == 1
    assert "-- this column" in stmts[0]


def test_statement_splitter_handles_trailing_no_semicolon():
    """Some legitimate migration files don't end with `;`."""
    sql = "CREATE TABLE a (x INT)"
    stmts = migrations._statements(sql)
    assert len(stmts) == 1


# ─── Checksum determinism ────────────────────────────────────────────────────


def test_checksum_is_stable():
    a = migrations._checksum("CREATE TABLE x;")
    b = migrations._checksum("CREATE TABLE x;")
    assert a == b
    assert len(a) == 64  # SHA-256 hex


def test_checksum_differs_with_whitespace():
    """Whitespace matters for the checksum — we want to detect any edit,
    including trivial reformat, so drift detection catches it."""
    a = migrations._checksum("CREATE TABLE x;")
    b = migrations._checksum("CREATE TABLE  x;")
    assert a != b


# ─── discover_migrations ─────────────────────────────────────────────────────


def test_discover_migrations_orders_lexicographically(tmp_path: Path):
    (tmp_path / "002_b.sql").write_text("-- b")
    (tmp_path / "001_a.sql").write_text("-- a")
    (tmp_path / "010_c.sql").write_text("-- c")
    (tmp_path / "NOT_A_MIGRATION.txt").write_text("ignore me")
    (tmp_path / "readme.md").write_text("ignore me too")
    out = migrations.discover_migrations(tmp_path)
    names = [name for name, _ in out]
    assert names == ["001_a.sql", "002_b.sql", "010_c.sql"]


def test_discover_migrations_missing_dir_returns_empty(tmp_path: Path):
    nonexistent = tmp_path / "doesnotexist"
    assert migrations.discover_migrations(nonexistent) == []


# ─── apply_migrations control flow (mocked Sql) ──────────────────────────────


def _make_mock_sql(applied: dict[str, str] | None = None):
    """Build a MagicMock Sql client that:
    - succeeds on every execute_statement
    - returns the `applied` dict when asked for already_applied
    """
    sql = MagicMock()

    def execute(statement: str, wait_timeout: str = "30s"):
        # `_already_applied` does SELECT filename, checksum FROM schema_migrations
        if "schema_migrations" in statement and "SELECT" in statement.upper():
            rows = [[k, v] for k, v in (applied or {}).items()]
            return SimpleNamespace(
                status=SimpleNamespace(state="SUCCEEDED", error=None),
                result=SimpleNamespace(data_array=rows),
            )
        # All other statements succeed silently
        return SimpleNamespace(
            status=SimpleNamespace(state="SUCCEEDED", error=None),
            result=SimpleNamespace(data_array=[]),
        )

    sql.execute_statement.side_effect = execute
    return sql


@pytest.fixture
def patched_state(monkeypatch):
    """Patch settings + the delta helpers used by migrations so we can
    drive the control flow with a mock Sql without a real Databricks env."""
    fake_settings = SimpleNamespace(
        catalog="test_cat",
        schema_="test_schema",
        warehouse_id="w-1",
    )
    fake_settings.fq_table = lambda t: f"test_cat.test_schema.{t}"

    monkeypatch.setattr(migrations, "get_settings", lambda: fake_settings)

    # delta.fetch_all just returns whatever the mocked execute_statement gives
    def fake_fetch_all(sql_dep, statement: str):
        resp = sql_dep.execute_statement(statement=statement)
        if resp.result and resp.result.data_array:
            return list(resp.result.data_array)
        return []

    def fake_run(sql_dep, statement: str, *, wait: str = "30s"):
        sql_dep.execute_statement(statement=statement, wait_timeout=wait)
        return []

    def fake_insert(sql_dep, table, row):
        cols = ", ".join(row.keys())
        sql_dep.execute_statement(statement=f"INSERT INTO {table} ({cols}) VALUES (...)")

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(delta, "run", fake_run)
    monkeypatch.setattr(delta, "insert", fake_insert)
    return fake_settings


def test_apply_migrations_idempotent_when_all_applied(tmp_path: Path, patched_state):
    """Second run with same files = all skipped."""
    (tmp_path / "001_a.sql").write_text("CREATE TABLE a;")
    (tmp_path / "002_b.sql").write_text("CREATE TABLE b;")

    content_a = (tmp_path / "001_a.sql").read_text()
    content_b = (tmp_path / "002_b.sql").read_text()
    already_applied = {
        "001_a.sql": migrations._checksum(content_a),
        "002_b.sql": migrations._checksum(content_b),
    }
    sql = _make_mock_sql(applied=already_applied)
    summary = migrations.apply_migrations(sql, tmp_path)

    assert summary["applied"] == 0
    assert summary["skipped"] == 2
    assert summary["drifted"] == 0
    assert summary["failed"] == 0


def test_apply_migrations_applies_pending(tmp_path: Path, patched_state):
    """New files (not in schema_migrations) get applied + recorded."""
    (tmp_path / "001_a.sql").write_text("CREATE TABLE a;")
    (tmp_path / "002_b.sql").write_text("CREATE TABLE b;")

    # Empty applied dict — both need to run
    sql = _make_mock_sql(applied={})
    summary = migrations.apply_migrations(sql, tmp_path)

    assert summary["applied"] == 2
    assert summary["skipped"] == 0
    assert summary["failed"] == 0


def test_apply_migrations_detects_drift_without_reapplying(tmp_path: Path, patched_state):
    """If a file's checksum differs from the stored one, it's reported as
    drifted but NOT re-applied (would risk re-creating things)."""
    (tmp_path / "001_a.sql").write_text("CREATE TABLE a;")
    drift_checksum = migrations._checksum("CREATE TABLE a_DIFFERENT_VERSION;")

    sql = _make_mock_sql(applied={"001_a.sql": drift_checksum})
    summary = migrations.apply_migrations(sql, tmp_path)

    assert summary["applied"] == 0
    assert summary["drifted"] == 1
    assert summary["skipped"] == 0


def test_apply_migrations_stops_on_first_failure(tmp_path: Path, patched_state):
    """If migration #2 fails, migration #3 should NOT be attempted (fail-fast).
    Otherwise we'd apply later DDL on a broken state."""
    (tmp_path / "001_a.sql").write_text("CREATE TABLE a;")
    (tmp_path / "002_b.sql").write_text("BROKEN_SYNTAX;")
    (tmp_path / "003_c.sql").write_text("CREATE TABLE c;")

    sql = MagicMock()

    def execute(statement: str, wait_timeout: str = "30s"):
        # Empty schema_migrations
        if "schema_migrations" in statement and "SELECT" in statement.upper():
            return SimpleNamespace(
                status=SimpleNamespace(state="SUCCEEDED", error=None),
                result=SimpleNamespace(data_array=[]),
            )
        # 002 fails
        if "BROKEN_SYNTAX" in statement:
            return SimpleNamespace(
                status=SimpleNamespace(state="FAILED", error=SimpleNamespace(message="syntax")),
                result=None,
            )
        return SimpleNamespace(
            status=SimpleNamespace(state="SUCCEEDED", error=None),
            result=SimpleNamespace(data_array=[]),
        )

    sql.execute_statement.side_effect = execute
    summary = migrations.apply_migrations(sql, tmp_path)

    assert summary["applied"] == 1  # 001 OK
    assert summary["failed"] == 1   # 002 falhou
    # 003 não chegou a ser executada — não conta como skipped nem applied
