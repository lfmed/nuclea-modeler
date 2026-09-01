"""Tests para versions/service.compute_diff (Módulo 8) — função pura crítica.

Mocka _load_snapshot para evitar Sql real. Foca em validar:
- entity_added / entity_removed / entity_changed
- attribute_added / attribute_removed / attribute_changed
- Totals corretos
- Snapshot vazio → diff vazio
- Snapshot idêntico → diff vazio
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.versions import service as vsvc
from nuclea_modeler.backend.versions.service import (
    _entity_key,
    _index_attrs,
    _index_entities,
    compute_diff,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _snapshot(entities=None, attributes_by_entity=None):
    """Build a fake snapshot dict matching build_snapshot's shape."""
    return {
        "entities": entities or [],
        "attributes_by_entity": attributes_by_entity or {},
    }


def _entity(eid: str, schema: str, name: str, **extra):
    """Minimal entity for diff input."""
    base = {
        "entity_id": eid,
        "schema_name": schema,
        "technical_name": name,
        "logical_name": None,
        "description_md": None,
        "domain": None,
        "criticality": None,
        "business_owner": None,
        "entity_type": "TABLE",
        "native_comment": None,
    }
    base.update(extra)
    return base


def _attr(name: str, **extra):
    base = {
        "technical_name": name,
        "native_data_type": "varchar(50)",
        "is_nullable": True,
        "default_value": None,
        "is_primary_key": False,
        "logical_name": None,
        "description_md": None,
    }
    base.update(extra)
    return base


@pytest.fixture
def patch_load(monkeypatch):
    """Patcha _load_snapshot para retornar dicts injetados via state."""
    state = {"from": None, "to": None}

    def fake_load(sql, version_id):
        return state["from"] if version_id == "v-from" else state["to"]

    monkeypatch.setattr(vsvc, "_load_snapshot", fake_load)
    return state


# ─── Index helpers ──────────────────────────────────────────────────────────


def test_entity_key_combines_schema_and_name():
    assert _entity_key({"schema_name": "public", "technical_name": "cliente"}) == "public.cliente"


def test_entity_key_handles_missing_fields():
    assert _entity_key({}) == "."


def test_index_entities_returns_dict_by_key():
    snap = _snapshot(
        entities=[
            _entity("e1", "public", "cliente"),
            _entity("e2", "vendas", "pedido"),
        ]
    )
    idx = _index_entities(snap)
    assert "public.cliente" in idx
    assert "vendas.pedido" in idx
    assert idx["public.cliente"]["entity_id"] == "e1"


def test_index_attrs_returns_dict_by_name():
    snap = _snapshot(
        attributes_by_entity={
            "e1": [_attr("id"), _attr("nome")],
        }
    )
    idx = _index_attrs(snap, "e1")
    assert set(idx.keys()) == {"id", "nome"}


def test_index_attrs_empty_for_unknown_entity():
    assert _index_attrs(_snapshot(), "no-entity") == {}


# ─── compute_diff — entity-level ────────────────────────────────────────────


def test_diff_empty_when_snapshots_identical(patch_load):
    entities = [_entity("e1", "public", "cliente")]
    patch_load["from"] = _snapshot(entities=entities)
    patch_load["to"] = _snapshot(entities=entities)

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals == {"additions": 0, "removals": 0, "changes": 0}


def test_diff_entity_added(patch_load):
    patch_load["from"] = _snapshot(entities=[])
    patch_load["to"] = _snapshot(entities=[_entity("e1", "public", "cliente")])

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["additions"] == 1
    add = diff.additions[0]
    assert add.type == "entity_added"
    assert add.entity_key == "public.cliente"


def test_diff_entity_removed(patch_load):
    patch_load["from"] = _snapshot(entities=[_entity("e1", "public", "cliente")])
    patch_load["to"] = _snapshot(entities=[])

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["removals"] == 1
    rem = diff.removals[0]
    assert rem.type == "entity_removed"
    assert rem.entity_key == "public.cliente"


def test_diff_entity_logical_name_change(patch_load):
    """Mudou logical_name → 1 change."""
    patch_load["from"] = _snapshot(
        entities=[_entity("e1", "public", "cliente", logical_name="Cliente")]
    )
    patch_load["to"] = _snapshot(
        entities=[_entity("e1", "public", "cliente", logical_name="Cliente PF")]
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["changes"] == 1
    chg = diff.changes[0]
    assert chg.type == "entity_changed"
    assert chg.field == "logical_name"
    assert chg.before == "Cliente"
    assert chg.after == "Cliente PF"


def test_diff_entity_multiple_field_changes(patch_load):
    """Múltiplos campos mudaram na mesma entidade → múltiplos changes."""
    patch_load["from"] = _snapshot(
        entities=[
            _entity("e1", "public", "cliente",
                    logical_name="Cliente",
                    domain="Comercial",
                    criticality="LOW"),
        ]
    )
    patch_load["to"] = _snapshot(
        entities=[
            _entity("e1", "public", "cliente",
                    logical_name="Cliente PF",
                    domain="Cadastro",
                    criticality="HIGH"),
        ]
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["changes"] == 3
    fields_changed = {c.field for c in diff.changes}
    assert fields_changed == {"logical_name", "domain", "criticality"}


# ─── compute_diff — attribute-level ─────────────────────────────────────────


def test_diff_attribute_added_to_existing_entity(patch_load):
    """Nova coluna em entidade que existe nos dois snapshots → addition."""
    entity = _entity("e1", "public", "cliente")
    patch_load["from"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("id")]},
    )
    patch_load["to"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("id"), _attr("nome")]},
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["additions"] == 1
    add = diff.additions[0]
    assert add.type == "attribute_added"
    assert add.entity_key == "public.cliente"
    assert add.attribute_key == "nome"


def test_diff_attribute_removed_from_existing_entity(patch_load):
    entity = _entity("e1", "public", "cliente")
    patch_load["from"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("id"), _attr("nome")]},
    )
    patch_load["to"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("id")]},
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["removals"] == 1
    rem = diff.removals[0]
    assert rem.type == "attribute_removed"
    assert rem.attribute_key == "nome"


def test_diff_attribute_type_changed(patch_load):
    """varchar(50) → varchar(100) → 1 change."""
    entity = _entity("e1", "public", "cliente")
    patch_load["from"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("nome", native_data_type="varchar(50)")]},
    )
    patch_load["to"] = _snapshot(
        entities=[entity],
        attributes_by_entity={"e1": [_attr("nome", native_data_type="varchar(100)")]},
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    assert diff.totals["changes"] == 1
    chg = diff.changes[0]
    assert chg.type == "attribute_changed"
    assert chg.field == "native_data_type"
    assert chg.before == "varchar(50)"
    assert chg.after == "varchar(100)"


def test_diff_added_entity_includes_its_attributes_as_added(patch_load):
    """Quando entidade nova é adicionada, suas colunas também contam como additions."""
    patch_load["from"] = _snapshot(entities=[])
    patch_load["to"] = _snapshot(
        entities=[_entity("e1", "public", "cliente")],
        attributes_by_entity={"e1": [_attr("id"), _attr("nome"), _attr("email")]},
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    # 1 entity_added + 3 attribute_added
    assert diff.totals["additions"] == 4
    types = {a.type for a in diff.additions}
    assert types == {"entity_added", "attribute_added"}


def test_diff_removed_entity_includes_its_attributes_as_removed(patch_load):
    """Quando entidade some, suas colunas também contam como removals."""
    patch_load["from"] = _snapshot(
        entities=[_entity("e1", "public", "cliente")],
        attributes_by_entity={"e1": [_attr("id"), _attr("nome")]},
    )
    patch_load["to"] = _snapshot(entities=[])

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    # 1 entity_removed + 2 attribute_removed
    assert diff.totals["removals"] == 3


def test_diff_complex_realistic_scenario(patch_load):
    """Cenário realista: 1 nova entidade, 1 removida, 1 alterada com PK change."""
    e_kept = _entity("e1", "public", "cliente", logical_name="Cliente")
    e_kept_changed = _entity("e1", "public", "cliente", logical_name="Cliente PF")
    e_removed = _entity("e2", "old", "legado")
    e_added = _entity("e3", "vendas", "pedido")

    patch_load["from"] = _snapshot(
        entities=[e_kept, e_removed],
        attributes_by_entity={
            "e1": [_attr("id", is_primary_key=True), _attr("nome")],
            "e2": [_attr("x")],
        },
    )
    patch_load["to"] = _snapshot(
        entities=[e_kept_changed, e_added],
        attributes_by_entity={
            "e1": [_attr("id", is_primary_key=True), _attr("cpf")],  # nome → cpf
            "e3": [_attr("pedido_id")],
        },
    )

    diff = compute_diff(MagicMock(), "v-from", "v-to")
    # Additions: e3 (entity_added) + pedido_id + cpf
    assert diff.totals["additions"] >= 3
    # Removals: e2 (entity_removed) + x + nome
    assert diff.totals["removals"] >= 3
    # Changes: logical_name e1
    assert any(
        c.type == "entity_changed" and c.field == "logical_name"
        for c in diff.changes
    )


# ─── compute_diff_vs_current (round 5, pt 18) ────────────────────────────────


def test_diff_vs_current_compares_version_with_live_model(monkeypatch):
    """`to="current"`: compara a versão com o snapshot ATUAL (ao vivo).

    Valida o rótulo `to_version_id == "current"` e que o lado `to` vem de
    build_snapshot (não de _load_snapshot). Aqui o modelo atual tem uma entidade a
    mais que a versão → 1 adição.
    """
    from nuclea_modeler.backend.versions.service import compute_diff_vs_current

    snap_from = _snapshot(entities=[_entity("e1", "public", "cliente")])
    snap_current = _snapshot(
        entities=[
            _entity("e1", "public", "cliente"),
            _entity("e2", "vendas", "pedido"),  # nova no modelo atual
        ]
    )
    monkeypatch.setattr(vsvc, "_load_snapshot", lambda sql, vid: snap_from)
    monkeypatch.setattr(vsvc, "build_snapshot", lambda sql, sysid: snap_current)
    monkeypatch.setattr(vsvc.delta, "fetch_one_params", lambda *a, **k: ["sys-1"])

    diff = compute_diff_vs_current(MagicMock(), "v-from")
    assert diff.from_version_id == "v-from"
    assert diff.to_version_id == "current"
    assert diff.totals["additions"] == 1
    assert diff.additions[0].entity_key == "vendas.pedido"
