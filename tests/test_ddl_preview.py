"""Round 6 (follow-up) — PREVIEW / dry-run do import DDL.

`run_ddl_import(..., dry_run=True)` deve:
- fazer TODO o parse + diff (mesma lógica do import real),
- NÃO abrir ticket e NÃO persistir a extração (read-only),
- devolver a lista `preview` (o que mudaria por objeto).

Espelha `test_import_ddl_desc_check.py`: mocka o diff e observa que persist/ticket
não são acionados. Também testa `_build_preview` isolado (mapeamento do diff).
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.extractions import service as svc  # noqa: E402
from nuclea_modeler.backend.extractions.diff import RELATIONSHIP_SCHEMA  # noqa: E402
from nuclea_modeler.backend.tickets.models import DiffEntity, TicketDiff  # noqa: E402


# ─── _build_preview (mapeamento do diff → linhas de preview) ──────────────────


def test_build_preview_maps_add_change_remove_and_relationship():
    diff = TicketDiff(entities=[
        DiffEntity(op="add", schema_name="social", technical_name="pessoa",
                   attributes=[{"technical_name": "id"}, {"technical_name": "nome"}]),
        DiffEntity(op="change", schema_name="social", technical_name="conta",
                   field_changes=[{"field": "x"}, {"field": "y"}, {"field": "z"}]),
        DiffEntity(op="remove", schema_name="legado", technical_name="velha"),
        DiffEntity(op="add", schema_name=RELATIONSHIP_SCHEMA, technical_name="rel-abc"),
    ])
    preview = svc._build_preview(diff)
    assert len(preview) == 4
    add, change, remove, rel = preview

    assert add.op == "add" and add.schema_name == "social" and add.technical_name == "pessoa"
    assert add.change_count == 2 and "coluna" in (add.detail or "")

    assert change.op == "change" and change.change_count == 3
    assert "altera" in (change.detail or "")

    assert remove.op == "remove" and remove.technical_name == "velha"

    # relacionamento sintético é rotulado distinto (não polui a lista de tabelas)
    assert rel.entity_type == "RELATIONSHIP"
    assert rel.schema_name == "(relacionamento)"


def test_build_preview_empty_diff():
    assert svc._build_preview(TicketDiff(entities=[])) == []


def test_build_preview_tolerates_garbage():
    """Um diff torto (sem .entities) vira preview vazio, nunca exceção."""
    assert svc._build_preview(object()) == []


# ─── run_ddl_import(dry_run=True) — read-only, popula preview ─────────────────


@pytest.fixture
def spy(monkeypatch):
    """Mocka diff (retorna TicketDiff real) e espiona persist/ticket."""
    calls = {"persist": 0, "ticket": 0}

    def fake_compute_diff(sql, system_id, snapshot):
        diff = TicketDiff(entities=[
            DiffEntity(
                op="add", schema_name="public", technical_name=e.technical_name,
                attributes=[{"technical_name": a.technical_name} for a in e.attributes],
            )
            for e in snapshot.entities
        ])
        summary = {"found": len(snapshot.entities), "new": len(snapshot.entities),
                   "changed": 0, "removed": 0, "relationships": 0}
        return diff, summary

    def fake_persist(*a, **k):
        calls["persist"] += 1
        return "ext-should-not-happen"

    def fake_open_ticket(*a, **k):
        calls["ticket"] += 1
        return "tk-should-not-happen"

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "persist_extraction", fake_persist)
    monkeypatch.setattr(svc, "open_ticket", fake_open_ticket)
    return calls


_DDL = """
CREATE TABLE cliente (id INT PRIMARY KEY, nome VARCHAR(120), email VARCHAR(200));
CREATE TABLE pedido (id INT PRIMARY KEY, cliente_id INT);
"""


def test_dry_run_does_not_persist_or_open_ticket(spy):
    result = svc.run_ddl_import(
        object(), system_id="sys-1", dialect="POSTGRES", ddl_text=_DDL,
        actor="tester@x.com", open_ticket_on_diff=False, dry_run=True,
    )
    # read-only: nada persistido, nenhum ticket aberto
    assert spy["persist"] == 0
    assert spy["ticket"] == 0
    assert result.extraction_id == "(dry-run)"
    assert result.ticket_id is None
    # preview populado com as 2 tabelas
    assert result.objects_new == 2
    names = {p.technical_name for p in result.preview}
    assert names == {"cliente", "pedido"}
    assert all(p.op == "add" for p in result.preview)


def test_real_run_persists(spy):
    """Contraste: sem dry_run, persist_extraction É chamado (comportamento normal)."""
    svc.run_ddl_import(
        object(), system_id="sys-1", dialect="POSTGRES", ddl_text=_DDL,
        actor="tester@x.com", open_ticket_on_diff=True,
    )
    assert spy["persist"] == 1


def test_dry_run_empty_ddl_does_not_persist(spy):
    """DDL sem CREATE reconhecido: dry_run devolve FAILED SEM persistir."""
    result = svc.run_ddl_import(
        object(), system_id="sys-1", dialect="POSTGRES",
        ddl_text="SELECT 1;", actor="tester@x.com",
        open_ticket_on_diff=False, dry_run=True,
    )
    assert spy["persist"] == 0
    assert result.status == "FAILED"
    assert result.extraction_id == "(dry-run)"
    assert result.preview == []
