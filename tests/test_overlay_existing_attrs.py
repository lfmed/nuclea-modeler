"""Overlay de edições pendentes sobre attributes de entity EXISTENTE (fix v1.0030).

BUG (code-review): `list_attributes` devolvia a linha CRUA do catálogo para
entities existentes — edições staged (PK, descrição, tipo…) NÃO apareciam. Como
a UI reconstrói o payload de update a partir desse dado, e o staging faz merge
"última intenção vence" por field-key (`attribute:NAME.update`), uma 2ª edição da
mesma coluna no mesmo ticket sobrescrevia a 1ª silenciosamente (ex.: editar
descrição e depois togglar PK perdia a descrição).

`_overlay_existing_attrs` espelha o estado staged sobre o catálogo, análogo ao
`_overlay_entity_out` que já existia para entity-level. Estes testes fixam:
(a) update pendente reflete no AttributeOut + pending_op="change";
(b) is_primary_key=False staged É aplicado (desmarcar PK aparece);
(c) sem ticket OPEN, retorna o catálogo intacto;
(d) attribute_add virtual aparece como pending "add".
"""
from __future__ import annotations

from datetime import datetime

import pytest

from nuclea_modeler.backend.entities import router as R
from nuclea_modeler.backend.entities.models import AttributeOut


def _catalog_attr(name: str, *, pk: bool = False, desc: str | None = None) -> AttributeOut:
    now = datetime(2026, 8, 24, 12, 0, 0)
    return AttributeOut(
        attribute_id=f"attr-{name}",
        entity_id="ent-1",
        technical_name=name,
        logical_name=None,
        ordinal_position=1,
        native_data_type="STRING",
        is_nullable=True,
        default_value=None,
        is_primary_key=pk,
        description_md=desc,
        business_rule=None,
        sample_value=None,
        glossary_term_id=None,
        native_comment=None,
        created_at=now, created_by="x", updated_at=now, updated_by="x",
    )


@pytest.fixture
def patch_session(monkeypatch):
    """Fakeia _resolve_entity_keys + find_open_session_ticket; testa passa o diff."""
    state: dict = {"diff": None}

    monkeypatch.setattr(
        R, "_resolve_entity_keys",
        lambda sql, eid: ("sys-1", "public", "cliente", "TABLE"),
    )

    def fake_find(sql, actor, system_id):
        if state["diff"] is None:
            return None
        return ("ticket-1", state["diff"])

    monkeypatch.setattr(R, "find_open_session_ticket", fake_find)
    return state


def _change_entry(field_after: dict) -> dict:
    return {
        "entities": [
            {
                "op": "change",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
                "payload": {"target_entity_id": "ent-1"},
                "field_changes": [
                    {"field": "attribute:cpf.update", "before": None, "after": field_after}
                ],
            }
        ]
    }


def test_overlay_reflects_staged_description_and_pk(patch_session):
    """(a) update staged aparece no AttributeOut + pending_op='change'."""
    patch_session["diff"] = _change_entry({
        "technical_name": "cpf",
        "description_md": "Documento do titular",
        "is_primary_key": True,
    })
    out = [_catalog_attr("cpf", pk=False, desc=None)]
    result = R._overlay_existing_attrs(object(), "tester@nuclea", "ent-1", out)

    cpf = next(a for a in result if a.technical_name == "cpf")
    assert cpf.description_md == "Documento do titular"
    assert cpf.is_primary_key is True
    assert cpf.pending_op == "change"


def test_overlay_applies_pk_false(patch_session):
    """(b) desmarcar PK (is_primary_key=False) É aplicado — False is not None."""
    patch_session["diff"] = _change_entry({
        "technical_name": "cpf",
        "is_primary_key": False,
    })
    out = [_catalog_attr("cpf", pk=True)]
    result = R._overlay_existing_attrs(object(), "tester@nuclea", "ent-1", out)

    cpf = next(a for a in result if a.technical_name == "cpf")
    assert cpf.is_primary_key is False
    assert cpf.pending_op == "change"


def test_overlay_no_open_ticket_returns_catalog(patch_session):
    """(c) sem ticket OPEN, o catálogo volta intacto (sem pending_op)."""
    patch_session["diff"] = None  # find_open_session_ticket → None
    out = [_catalog_attr("cpf", pk=True, desc="orig")]
    result = R._overlay_existing_attrs(object(), "tester@nuclea", "ent-1", out)

    assert result[0].is_primary_key is True
    assert result[0].description_md == "orig"
    assert result[0].pending_op is None


def test_overlay_virtual_add_appears(patch_session):
    """(d) attribute_add staged que não existe no catálogo aparece como pending 'add'."""
    patch_session["diff"] = {
        "entities": [
            {
                "op": "change",
                "schema_name": "public",
                "technical_name": "cliente",
                "entity_type": "TABLE",
                "payload": {"target_entity_id": "ent-1"},
                "field_changes": [
                    {
                        "field": "attribute_add:email",
                        "before": None,
                        "after": {"technical_name": "email", "native_data_type": "STRING",
                                  "description_md": "E-mail de contato"},
                    }
                ],
            }
        ]
    }
    out = [_catalog_attr("cpf")]
    result = R._overlay_existing_attrs(object(), "tester@nuclea", "ent-1", out)

    email = next((a for a in result if a.technical_name == "email"), None)
    assert email is not None
    assert email.pending_op == "add"
    assert email.description_md == "E-mail de contato"
