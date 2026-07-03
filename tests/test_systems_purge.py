"""Purge/limpeza de sistema (retendo histórico) + registro de schema no apply.

- purge_system_model: apaga o modelo na ordem child→parent (filhos que usam
  subquery nas tabelas pai vêm antes; entities por último).
- _ensure_schema: registra o schema de 1ª classe (navegador M6) no apply,
  idempotente.
"""
from __future__ import annotations

from datetime import datetime

from nuclea_modeler.backend.systems import service as sysv
from nuclea_modeler.backend.tickets import service as tsv


class _S:
    def fq_table(self, t: str) -> str:
        return f"c.s.{t}"


# ─── purge_system_model ──────────────────────────────────────────────────────


def test_purge_order_and_coverage(monkeypatch):
    monkeypatch.setattr(sysv, "get_settings", lambda: _S())
    monkeypatch.setattr(sysv.delta, "param", lambda k, v: (k, v))
    executed: list[str] = []
    monkeypatch.setattr(sysv.delta, "run_params", lambda sql, stmt, p: executed.append(stmt))

    sysv.purge_system_model(object(), "sys-1")

    # entities é o ÚLTIMO delete (pais depois dos filhos)
    assert executed[-1] == "DELETE FROM c.s.entities WHERE system_id = :sid"

    def idx(fragment: str) -> int:
        return next(i for i, sql in enumerate(executed) if fragment in sql)

    # attribute_flags → antes de attributes → antes de entities
    assert idx("c.s.attribute_flags") < idx("FROM c.s.attributes")
    assert idx("FROM c.s.attributes") < idx("c.s.entities WHERE")

    # cobertura das tabelas de modelo (histórico NÃO entra aqui)
    joined = "\n".join(executed)
    for t in (
        "relationships", "schemas", "diagrams", "diagram_entities", "der_layouts",
        "views_catalog", "procedures_catalog", "triggers_catalog", "sequences_catalog",
        "entity_flags", "entity_indexes", "entity_partitioning",
        "lineage_upstream", "lineage_downstream", "glossary_mappings",
    ):
        assert f"c.s.{t}" in joined, f"faltou purgar {t}"

    # histórico NÃO é apagado
    for keep in ("model_versions", "reconciliation_tickets", "sync_log", "audit_log", "systems"):
        assert f"c.s.{keep}" not in joined, f"não deveria apagar {keep}"


# ─── _ensure_schema ──────────────────────────────────────────────────────────


def test_ensure_schema_inserts_when_missing(monkeypatch):
    monkeypatch.setattr(tsv, "get_settings", lambda: _S())
    monkeypatch.setattr(tsv.delta, "param", lambda k, v: (k, v))
    monkeypatch.setattr(tsv.delta, "fetch_one_params", lambda *a, **k: None)
    monkeypatch.setattr(tsv.delta, "new_id", lambda p: f"{p}x")
    ins: dict = {}
    monkeypatch.setattr(tsv.delta, "insert", lambda sql, table, row: ins.update(table=table, row=row))

    tsv._ensure_schema(object(), "sys-1", "streaming", "a@x.com", datetime(2026, 1, 1))

    assert ins["table"] == "c.s.schemas"
    assert ins["row"]["schema_name"] == "streaming"
    assert ins["row"]["system_id"] == "sys-1"


def test_ensure_schema_noop_when_exists(monkeypatch):
    monkeypatch.setattr(tsv, "get_settings", lambda: _S())
    monkeypatch.setattr(tsv.delta, "param", lambda k, v: (k, v))
    monkeypatch.setattr(tsv.delta, "fetch_one_params", lambda *a, **k: ["sch-existing"])
    called = {"insert": False}
    monkeypatch.setattr(tsv.delta, "insert", lambda *a, **k: called.update(insert=True))

    tsv._ensure_schema(object(), "sys-1", "streaming", "a@x.com", datetime(2026, 1, 1))

    assert called["insert"] is False


def test_ensure_schema_noop_empty_name(monkeypatch):
    called = {"fetch": False}
    monkeypatch.setattr(tsv.delta, "fetch_one_params", lambda *a, **k: called.update(fetch=True))
    tsv._ensure_schema(object(), "sys-1", "", "a@x.com", datetime(2026, 1, 1))
    assert called["fetch"] is False
