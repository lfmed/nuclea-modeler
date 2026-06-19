"""Import DDL: extração de colunas (regressão) + Foreign Keys.

Regressão crítica: o parser DDL lia `stmt.expressions` (sempre vazio no sqlglot)
em vez de `stmt.this.expressions`, então NÃO extraía coluna nenhuma de CREATE
TABLE. Aqui garantimos que colunas E FKs são extraídas.

Mocka compute_diff/persist/open_ticket pra focar no parsing puro: capturamos o
ExtractionSnapshot que o run_ddl_import monta a partir do DDL.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.extractions import service as svc  # noqa: E402


@pytest.fixture
def capture_snapshot(monkeypatch):
    """Intercepta o snapshot montado pelo run_ddl_import."""
    captured = {}

    def fake_compute_diff(sql, system_id, snapshot):
        captured["snapshot"] = snapshot
        rel = len(snapshot.relationships)
        return (
            object(),  # diff (não inspecionado — open_ticket é mockado)
            {"found": len(snapshot.entities), "new": len(snapshot.entities),
             "changed": 0, "removed": 0, "relationships": rel},
        )

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "persist_extraction", lambda *a, **k: "ext-test")
    monkeypatch.setattr(svc, "open_ticket", lambda *a, **k: "tk-test")
    return captured


def _run(capture_snapshot, ddl: str, dialect: str = "POSTGRES"):
    svc.run_ddl_import(
        object(),
        system_id="sys-1",
        dialect=dialect,
        ddl_text=ddl,
        actor="tester@x.com",
        open_ticket_on_diff=True,
    )
    return capture_snapshot["snapshot"]


# ─── Regressão: colunas extraídas ──────────────────────────────────────────


def test_ddl_extracts_columns(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (
      id INT PRIMARY KEY,
      nome VARCHAR(100) NOT NULL,
      email VARCHAR(200)
    );
    """
    snap = _run(capture_snapshot, ddl)
    assert len(snap.entities) == 1
    ent = snap.entities[0]
    assert ent.technical_name == "cliente"
    names = [a.technical_name for a in ent.attributes]
    assert names == ["id", "nome", "email"]  # <- antes vinha vazio
    id_attr = next(a for a in ent.attributes if a.technical_name == "id")
    assert id_attr.is_primary_key is True
    nome_attr = next(a for a in ent.attributes if a.technical_name == "nome")
    assert nome_attr.is_nullable is False


def test_ddl_schema_qualified_table(capture_snapshot):
    ddl = "CREATE TABLE vendas.pedido (id INT PRIMARY KEY, total NUMERIC(10,2));"
    snap = _run(capture_snapshot, ddl)
    ent = snap.entities[0]
    assert ent.schema_name == "vendas"
    assert ent.technical_name == "pedido"
    assert [a.technical_name for a in ent.attributes] == ["id", "total"]


# ─── Foreign Keys ──────────────────────────────────────────────────────────


def test_ddl_table_level_fk(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY);
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT NOT NULL,
      CONSTRAINT fk_cliente FOREIGN KEY (cliente_id) REFERENCES cliente (id)
    );
    """
    snap = _run(capture_snapshot, ddl)
    assert len(snap.relationships) == 1
    rel = snap.relationships[0]
    # parent = referenciado (cliente), child = quem segura a FK (pedido)
    assert rel.parent_entity == "cliente"
    assert rel.parent_columns == ["id"]
    assert rel.child_entity == "pedido"
    assert rel.child_columns == ["cliente_id"]


def test_ddl_inline_fk(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY);
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT REFERENCES cliente (id)
    );
    """
    snap = _run(capture_snapshot, ddl)
    assert len(snap.relationships) == 1
    rel = snap.relationships[0]
    assert rel.parent_entity == "cliente"
    assert rel.child_entity == "pedido"
    assert rel.child_columns == ["cliente_id"]


def test_ddl_cross_schema_fk(capture_snapshot):
    ddl = """
    CREATE TABLE hr.depto (id INT PRIMARY KEY);
    CREATE TABLE rh.func (
      id INT PRIMARY KEY,
      depto_id INT,
      CONSTRAINT fk_d FOREIGN KEY (depto_id) REFERENCES hr.depto (id)
    );
    """
    snap = _run(capture_snapshot, ddl)
    rel = snap.relationships[0]
    assert rel.parent_schema == "hr"
    assert rel.parent_entity == "depto"
    assert rel.child_schema == "rh"
    assert rel.child_entity == "func"


def test_ddl_no_fk_no_relationships(capture_snapshot):
    ddl = "CREATE TABLE t (id INT PRIMARY KEY, x VARCHAR(10));"
    snap = _run(capture_snapshot, ddl)
    assert snap.relationships == []
