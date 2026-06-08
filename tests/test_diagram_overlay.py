"""Tests do overlay editorial em DiagramView.

Cobre ``apply_session_overlay`` em isolamento — função pura, sem deps de
Delta/SDK. Validamos os 3 paths: add (entity virtual), change (mesclando
field_changes), remove (badge na entity existente).
"""
from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from nuclea_modeler.backend.diagram.models import DiagramAttribute, DiagramEntity
from nuclea_modeler.backend.diagram.overlay import apply_session_overlay


def _ent(eid: str = "ent-1", schema: str = "public", name: str = "cliente") -> DiagramEntity:
    return DiagramEntity(
        entity_id=eid,
        system_id="sys-1",
        schema_name=schema,
        technical_name=name,
        entity_type="TABLE",
        attributes=[
            DiagramAttribute(
                attribute_id="attr-id", technical_name="id",
                is_primary_key=True, has_lgpd_flag=False,
                ordinal_position=1, native_data_type="BIGINT",
                is_nullable=False,
            ),
        ],
        has_lgpd_flag=False,
    )


def _diff(entries: list[dict]) -> dict:
    return {"entities": entries, "additions": 0, "removals": 0, "changes": 0}


# ─── op=add cria entity virtual ──────────────────────────────────────────────


def test_overlay_creates_virtual_entity_for_add():
    out = apply_session_overlay(
        entities=[],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "add",
                "schema_name": "public",
                "technical_name": "novo",
                "entity_type": "TABLE",
                "payload": {"logical_name": "Tabela Nova"},
                "attributes": [
                    {"technical_name": "id", "is_primary_key": True, "native_data_type": "BIGINT"},
                ],
            },
        ]),
    )
    assert len(out) == 1
    assert out[0].technical_name == "novo"
    assert out[0].pending_op == "add"
    assert out[0].pending_ticket_id == "tkt-1"
    assert out[0].logical_name == "Tabela Nova"
    # entity_id virtual quando não há pre_allocated
    assert out[0].entity_id.startswith("pending-ent-")
    assert len(out[0].attributes) == 1
    assert out[0].attributes[0].pending_op == "add"


def test_overlay_uses_pre_allocated_entity_id_when_present():
    """Crítico pra FKs entre entities virtuais batirem após apply."""
    out = apply_session_overlay(
        entities=[],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "add",
                "schema_name": "public",
                "technical_name": "novo",
                "entity_type": "TABLE",
                "payload": {"pre_allocated_entity_id": "ent-preallocated-42"},
                "attributes": [],
            },
        ]),
    )
    assert out[0].entity_id == "ent-preallocated-42"


# ─── op=remove marca entity existente ────────────────────────────────────────


def test_overlay_marks_existing_entity_for_remove():
    out = apply_session_overlay(
        entities=[_ent()],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "remove",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
            },
        ]),
    )
    assert len(out) == 1
    assert out[0].pending_op == "remove"
    assert out[0].pending_ticket_id == "tkt-1"


# ─── op=change mescla field_changes ──────────────────────────────────────────


def test_overlay_applies_entity_field_changes():
    out = apply_session_overlay(
        entities=[_ent()],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "change",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
                "field_changes": [
                    {"field": "logical_name", "before": None, "after": "Cliente PJ"},
                    {"field": "domain", "before": None, "after": "Financeiro"},
                ],
            },
        ]),
    )
    assert out[0].pending_op == "change"
    assert out[0].logical_name == "Cliente PJ"
    assert out[0].domain == "Financeiro"


def test_overlay_adds_attribute_via_change():
    out = apply_session_overlay(
        entities=[_ent()],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "change",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
                "field_changes": [
                    {
                        "field": "attribute_add:email",
                        "before": None,
                        "after": {
                            "technical_name": "email",
                            "native_data_type": "VARCHAR(255)",
                            "is_nullable": True,
                            "is_primary_key": False,
                        },
                    },
                ],
            },
        ]),
    )
    # Manteve o id original + adicionou email virtual com pending_op=add
    names = {a.technical_name for a in out[0].attributes}
    assert names == {"id", "email"}
    email = next(a for a in out[0].attributes if a.technical_name == "email")
    assert email.pending_op == "add"
    assert email.native_data_type == "VARCHAR(255)"


# ─── Multi-entity: alguns têm overlay, outros não ─────────────────────────────


def test_overlay_leaves_untouched_entities_alone():
    ent1 = _ent(eid="ent-1", name="cliente")
    ent2 = _ent(eid="ent-2", name="pedido")
    out = apply_session_overlay(
        entities=[ent1, ent2],
        system_id="sys-1",
        session_ticket_id="tkt-1",
        session_diff=_diff([
            {
                "op": "change",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
                "field_changes": [
                    {"field": "logical_name", "before": None, "after": "Cliente PJ"},
                ],
            },
        ]),
    )
    cliente = next(e for e in out if e.technical_name == "cliente")
    pedido = next(e for e in out if e.technical_name == "pedido")
    assert cliente.pending_op == "change"
    assert pedido.pending_op is None
    assert cliente.logical_name == "Cliente PJ"
