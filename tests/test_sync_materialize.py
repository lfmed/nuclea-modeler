"""Materialização em Delta (pedido do cliente #9).

- _build_create_table_sql: monta CREATE TABLE ... USING DELTA com type-mapping
  Spark e NOT NULL, ou None quando a entidade não tem colunas.
- run_sync(materialize=True): quando a tabela destino não existe, CRIA a tabela,
  aplica comentários, e marca a entity como materializada (UPDATE entities).
- run_sync(materialize=False): tabela inexistente continua SKIPPED (clássico M9).
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.sync import service as svc
from nuclea_modeler.backend.sync.models import SyncRunRequest


class _FakeSettings:
    def fq_table(self, t: str) -> str:
        return f"cat.sch.{t}"


@pytest.fixture
def patch_settings(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(svc.delta, "param", lambda k, v: (k, v))
    monkeypatch.setattr(svc.delta, "new_id", lambda prefix: f"{prefix}test")


# ─── _build_create_table_sql ────────────────────────────────────────────────


def test_build_create_table_sql_structure(monkeypatch, patch_settings):
    monkeypatch.setattr(
        svc.delta,
        "fetch_all_params",
        lambda *a, **k: [
            ("id", "int", False),
            ("nome", "varchar(100)", True),
            ("total", "decimal(10,2)", None),
        ],
    )
    out = svc._build_create_table_sql(object(), "cat.sch.pedido", "ent-1")
    assert out is not None
    assert out.startswith("CREATE TABLE IF NOT EXISTS cat.sch.pedido (")
    assert "USING DELTA" in out
    for col in ("id", "nome", "total"):
        assert col in out
    # só a coluna NOT NULL (id) recebe a cláusula; nullable e None não recebem
    assert out.count("NOT NULL") == 1


def test_build_create_table_sql_none_without_columns(monkeypatch, patch_settings):
    monkeypatch.setattr(svc.delta, "fetch_all_params", lambda *a, **k: [])
    assert svc._build_create_table_sql(object(), "cat.sch.x", "ent-1") is None


def test_build_create_table_sql_skips_invalid_identifier(monkeypatch, patch_settings):
    monkeypatch.setattr(
        svc.delta,
        "fetch_all_params",
        lambda *a, **k: [("ok_col", "int", True), ("bad col", "int", True)],
    )
    out = svc._build_create_table_sql(object(), "cat.sch.t", "ent-1")
    assert out is not None
    assert "ok_col" in out
    assert "bad col" not in out


# ─── run_sync(materialize=...) ──────────────────────────────────────────────


def _fake_fetch_factory():
    def fake_fetch(sql, query, params):
        if "FROM cat.sch.entities" in query:
            return [
                ("ent-1", "vendas", "pedido", "Pedido", "desc do pedido",
                 None, "Vendas", "HIGH", "owner@x.com"),
            ]
        if "native_data_type" in query:  # _build_create_table_sql
            return [("id", "int", False), ("nome", "varchar(100)", True)]
        return [("id", "ID", None, None), ("nome", "Nome", None, None)]  # comentários
    return fake_fetch


def _install_recorder(monkeypatch):
    executed: list[str] = []
    monkeypatch.setattr(svc.delta, "fetch_all_params", _fake_fetch_factory())
    monkeypatch.setattr(svc.delta, "run", lambda sql, q: executed.append(q))
    monkeypatch.setattr(svc.delta, "run_params", lambda sql, q, p=None: executed.append(q))
    monkeypatch.setattr(svc.delta, "insert", lambda sql, table, row: executed.append(f"INSERT {table}"))
    return executed


def test_run_sync_materialize_creates_and_flags(monkeypatch, patch_settings):
    executed = _install_recorder(monkeypatch)
    monkeypatch.setattr(svc, "_target_table_exists", lambda sql, t: False)

    req = SyncRunRequest(
        system_id="sys-1", target_catalog="cliente_cat", materialize=True
    )
    result = svc.run_sync(object(), req, "tester@x.com")

    assert result.materialize is True
    assert result.objects_created == 1
    assert result.objects_synced == 1
    assert result.status == "SUCCESS"
    # criou a tabela e marcou a entity como materializada
    assert any("CREATE TABLE IF NOT EXISTS" in q for q in executed)
    assert any("UPDATE cat.sch.entities" in q for q in executed)
    assert result.objects[0].status == "OK"


def test_run_sync_without_materialize_skips_missing(monkeypatch, patch_settings):
    executed = _install_recorder(monkeypatch)
    monkeypatch.setattr(svc, "_target_table_exists", lambda sql, t: False)

    req = SyncRunRequest(
        system_id="sys-1", target_catalog="cliente_cat", materialize=False
    )
    result = svc.run_sync(object(), req, "tester@x.com")

    assert result.objects_created == 0
    assert result.objects[0].status == "SKIPPED"
    assert not any("CREATE TABLE" in q for q in executed)


def test_run_sync_dry_run_materialize_returns_ddl(monkeypatch, patch_settings):
    """Preview (dry-run) com materialize devolve o DDL de CREATE TABLE, sem tocar
    no Unity Catalog destino."""
    monkeypatch.setattr(svc.delta, "fetch_all_params", _fake_fetch_factory())
    # No dry-run nada é executado/persistido; guardas contra chamadas acidentais.
    monkeypatch.setattr(svc.delta, "run", lambda sql, q: pytest.fail("dry-run não deve executar SQL"))
    monkeypatch.setattr(svc.delta, "run_params", lambda sql, q, p=None: pytest.fail("dry-run não deve executar SQL"))

    req = SyncRunRequest(
        system_id="sys-1", target_catalog="cliente_cat",
        materialize=True, dry_run=True,
    )
    result = svc.run_sync(object(), req, "tester@x.com")

    assert result.dry_run is True
    obj = result.objects[0]
    assert obj.ddl is not None
    assert "CREATE TABLE IF NOT EXISTS cliente_cat.vendas.pedido" in obj.ddl
    assert "USING DELTA" in obj.ddl


def test_run_sync_dry_run_no_columns_fails(monkeypatch, patch_settings):
    """Dry-run materialize de entidade SEM colunas → ERROR (não dá pra criar),
    nunca aparece como sucesso."""
    def fetch(sql, query, params):
        if "FROM cat.sch.entities" in query:
            return [("ent-1", "vendas", "vazia", "Vazia", None, None, None, None, None)]
        return []  # sem atributos

    monkeypatch.setattr(svc.delta, "fetch_all_params", fetch)
    monkeypatch.setattr(svc.delta, "run", lambda sql, q: pytest.fail("dry-run não executa SQL"))
    monkeypatch.setattr(svc.delta, "run_params", lambda sql, q, p=None: pytest.fail("dry-run não executa SQL"))

    req = SyncRunRequest(
        system_id="sys-1", target_catalog="cliente_cat",
        materialize=True, dry_run=True,
    )
    result = svc.run_sync(object(), req, "tester@x.com")

    assert result.objects[0].status == "ERROR"
    assert result.objects[0].ddl is None
    assert result.objects_failed == 1
    assert result.objects_synced == 0
    assert result.status == "FAILED"
