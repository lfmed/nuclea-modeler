"""Tests para extractions/service.compute_diff_against_catalog.

Função pura que compara snapshot extraído vs catálogo atual.
Mocka delta.fetch_all_params (entities) e delta.fetch_all (attributes)
para focar na lógica de comparação:
- add (entity nova no snapshot)
- remove (entity sumida do snapshot)
- change (mesma key, campos diferentes ou attrs diff)
- Summary counters consistentes
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.extractions import service as esvc
from nuclea_modeler.backend.extractions.models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractionSnapshot,
)


@pytest.fixture
def state(monkeypatch):
    """Patcha delta.fetch_all_params (entities) + delta.fetch_all (attrs)."""
    captured = {
        "entity_rows": [],   # list[list] — schema: [eid, schema, tech, etype, comment, rowct, logical, desc]
        "attr_rows": [],     # list[list] — schema: [eid, name, dtype, nullable, default, pk, comment, ord]
    }

    def fake_fetch_all_params(sql, query, params=None):
        return list(captured["entity_rows"])

    def fake_fetch_all(sql, query):
        return list(captured["attr_rows"])

    def fake_param(name, value):
        return (name, value)

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "fetch_all_params", fake_fetch_all_params)
    monkeypatch.setattr(delta, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(delta, "param", fake_param)

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(esvc, "get_settings", lambda: fake_settings)

    return captured


def _snapshot(entities: list[ExtractedEntity]) -> ExtractionSnapshot:
    return ExtractionSnapshot(
        source_kind="LAKEBASE",
        system_id="sys-1",
        captured_at=datetime(2026, 5, 28, 12, 0, 0),
        schemas=[],
        entities=entities,
    )


def _entity(schema: str, name: str, *, attrs: list[ExtractedAttribute] = None, **extra) -> ExtractedEntity:
    return ExtractedEntity(
        schema_name=schema,
        technical_name=name,
        attributes=attrs or [],
        **extra,
    )


def _attr(name: str, dtype: str = "varchar(50)", *, pk: bool = False) -> ExtractedAttribute:
    return ExtractedAttribute(technical_name=name, native_data_type=dtype, is_primary_key=pk)


# ─── Empty cases ────────────────────────────────────────────────────────────


def test_diff_empty_snapshot_and_empty_catalog(state):
    snap = _snapshot([])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary == {"found": 0, "new": 0, "changed": 0, "removed": 0}
    assert diff.entities == []


def test_diff_empty_catalog_all_additions(state):
    """Snapshot com 2 entities, catálogo vazio → 2 adds."""
    state["entity_rows"] = []
    snap = _snapshot([
        _entity("public", "cliente", attrs=[_attr("id", "bigint", pk=True)]),
        _entity("public", "pedido"),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["found"] == 2
    assert summary["new"] == 2
    assert summary["changed"] == 0
    assert summary["removed"] == 0
    assert len(diff.entities) == 2
    assert all(e.op == "add" for e in diff.entities)


def test_diff_empty_snapshot_with_catalog_all_removals(state):
    """Catálogo com 2 entities, snapshot vazio → 2 removes."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
        ["e2", "public", "pedido", "VIEW", None, None, None, None],
    ]
    snap = _snapshot([])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["removed"] == 2
    assert summary["new"] == 0
    removes = [e for e in diff.entities if e.op == "remove"]
    assert len(removes) == 2
    # entity_type preservado do catálogo
    types = {r.entity_type for r in removes}
    assert types == {"TABLE", "VIEW"}


# ─── Change detection ──────────────────────────────────────────────────────


def test_diff_native_comment_change(state):
    """Mesma key, comment diferente → 1 change."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", "old comment", None, None, None],
    ]
    snap = _snapshot([
        _entity("public", "cliente", native_comment="new comment"),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["changed"] == 1
    chg = diff.entities[0]
    assert chg.op == "change"
    assert chg.field_changes is not None
    field_names = {fc["field"] for fc in chg.field_changes}
    assert "native_comment" in field_names


def test_diff_row_count_change(state):
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, 100, None, None],
    ]
    snap = _snapshot([
        _entity("public", "cliente", row_count_approx=200),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["changed"] == 1
    field_changes = diff.entities[0].field_changes
    rc_change = next(fc for fc in field_changes if fc["field"] == "row_count_approx")
    assert rc_change["before"] == 100
    assert rc_change["after"] == 200


def test_diff_no_change_when_fields_identical(state):
    """Mesma key, mesmos campos → 0 changes."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", "comment", 100, None, None],
    ]
    snap = _snapshot([
        _entity("public", "cliente", native_comment="comment", row_count_approx=100),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary == {"found": 1, "new": 0, "changed": 0, "removed": 0}
    assert diff.entities == []


# ─── Attribute-level changes ───────────────────────────────────────────────


def test_diff_attribute_added(state):
    """Entity igual, attr nova no snapshot → field_change 'attribute_add:nome'."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "id", "bigint", False, None, True, None, 1],
    ]
    snap = _snapshot([
        _entity("public", "cliente", attrs=[
            _attr("id", "bigint", pk=True),
            _attr("nome", "varchar(200)"),  # nova
        ]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["changed"] == 1
    field_changes = diff.entities[0].field_changes
    field_names = {fc["field"] for fc in field_changes}
    assert "attribute_add:nome" in field_names


def test_diff_attribute_removed(state):
    """Snapshot perdeu attr que existe no catálogo → 'attribute_remove:X'."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "id", "bigint", False, None, True, None, 1],
        ["e1", "obsoleto", "varchar(100)", True, None, False, None, 2],
    ]
    snap = _snapshot([
        _entity("public", "cliente", attrs=[_attr("id", "bigint", pk=True)]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    field_changes = diff.entities[0].field_changes
    field_names = {fc["field"] for fc in field_changes}
    assert "attribute_remove:obsoleto" in field_names


def test_diff_attribute_type_changed(state):
    """varchar(50) → varchar(100): field_change 'attribute:nome.native_data_type'."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "nome", "varchar(50)", True, None, False, None, 1],
    ]
    snap = _snapshot([
        _entity("public", "cliente", attrs=[_attr("nome", "varchar(100)")]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    field_changes = diff.entities[0].field_changes
    type_change = next(
        fc for fc in field_changes if fc["field"] == "attribute:nome.native_data_type"
    )
    assert type_change["before"] == "varchar(50)"
    assert type_change["after"] == "varchar(100)"


def test_diff_attribute_type_case_insensitive(state):
    """VARCHAR(50) vs varchar(50) NÃO conta como change (case-insensitive)."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "nome", "VARCHAR(50)", True, None, False, None, 1],
    ]
    snap = _snapshot([
        _entity("public", "cliente", attrs=[_attr("nome", "varchar(50)")]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    # Sem field_changes → 0 changes total
    assert summary["changed"] == 0


def test_diff_attribute_pk_change(state):
    """Coluna virou PK ou deixou de ser PK → field_change 'attribute:X.is_primary_key'."""
    state["entity_rows"] = [
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "id", "bigint", False, None, False, None, 1],  # era não-PK
    ]
    snap = _snapshot([
        _entity("public", "cliente", attrs=[_attr("id", "bigint", pk=True)]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    field_changes = diff.entities[0].field_changes
    pk_change = next(
        fc for fc in field_changes if fc["field"] == "attribute:id.is_primary_key"
    )
    assert pk_change["before"] is False
    assert pk_change["after"] is True


# ─── Realistic mixed scenario ──────────────────────────────────────────────


def test_diff_realistic_mixed(state):
    """1 add + 1 remove + 1 change-com-attr-novo."""
    state["entity_rows"] = [
        # cliente vai mudar (PK adicionada)
        ["e1", "public", "cliente", "TABLE", None, None, None, None],
        # legado vai sumir
        ["e2", "old", "legado", "TABLE", None, None, None, None],
    ]
    state["attr_rows"] = [
        ["e1", "id", "bigint", False, None, False, None, 1],
        ["e2", "x", "int", True, None, False, None, 1],
    ]
    snap = _snapshot([
        # cliente continua, mas id virou PK
        _entity("public", "cliente", attrs=[_attr("id", "bigint", pk=True)]),
        # pedido é novo
        _entity("public", "pedido", attrs=[_attr("pid", "bigint", pk=True)]),
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert summary["found"] == 2
    assert summary["new"] == 1     # pedido
    assert summary["changed"] == 1  # cliente
    assert summary["removed"] == 1  # legado

    ops = {(e.op, e.schema_name, e.technical_name) for e in diff.entities}
    assert ("add", "public", "pedido") in ops
    assert ("change", "public", "cliente") in ops
    assert ("remove", "old", "legado") in ops


def test_diff_counters_match_diff_entities_length(state):
    """Sanity: somar additions+removals+changes = len(diff.entities)."""
    state["entity_rows"] = [
        ["e1", "public", "a", "TABLE", None, None, None, None],
        ["e2", "public", "b", "TABLE", "old", None, None, None],
    ]
    snap = _snapshot([
        _entity("public", "b", native_comment="new"),  # change
        _entity("public", "c"),                          # add
    ])
    diff, summary = esvc.compute_diff_against_catalog(MagicMock(), "sys-1", snap)

    assert len(diff.entities) == summary["new"] + summary["changed"] + summary["removed"]
    assert diff.additions == summary["new"]
    assert diff.removals == summary["removed"]
    assert diff.changes == summary["changed"]


# ─── _quote_id helper ──────────────────────────────────────────────────────


def test_quote_id_escapes_single_quotes():
    """_quote_id deve dobrar apóstrofos (proteção mesmo p/ trusted IDs)."""
    assert esvc._quote_id("normal-id") == "'normal-id'"
    assert esvc._quote_id("with'quote") == "'with''quote'"
    assert esvc._quote_id("") == "''"


def test_quote_id_handles_none():
    """None vira string vazia (defensive)."""
    assert esvc._quote_id(None) == "''"
