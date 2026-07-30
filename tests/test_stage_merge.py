"""Tests para stage_entity_change com merge de field_changes.

BUG fix (v1.0021): edições de campos DIFERENTES da mesma entidade devem
acumular no mesmo entry, não sobrescrever. Este módulo valida que o merge
preserva N field_changes de N campos distintos.

Cenários:
(a) 2 edições de campos DIFERENTES → ambos os field_changes acumulam
(b) 2 edições do MESMO campo → última vence, field_changes é único
(c) Edições de 2 atributos diferentes → coexistem
(d) Após merge, apply aplica TODOS os field_changes
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.tickets.session import stage_entity_change


@pytest.fixture
def state(monkeypatch):
    """Captura calls em delta e expõe state mutable pros testes."""
    captured: dict = {
        "updates": [],  # list of (table, key, key_val, fields)
    }

    def fake_update_by_id(sql, table, key, key_val, fields):
        captured["updates"].append((table, key, key_val, dict(fields)))

    def fake_param(name, value):
        return (name, value)

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "update_by_id", fake_update_by_id)
    monkeypatch.setattr(delta, "param", fake_param)

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    from nuclea_modeler.backend.tickets import session as svc
    monkeypatch.setattr(svc, "get_settings", lambda: fake_settings)

    return captured


def test_merge_two_different_fields_accumulate(state):
    """(a) Editar 2 campos DIFERENTES da mesma entidade acumula ambos."""
    # Primeira edição: muda logical_name
    diff = {"entities": []}
    entry1 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {
            "target_entity_id": "ent-123",
            "logical_name": "User",
        },
        "field_changes": [
            {"field": "logical_name", "before": "users", "after": "User"}
        ],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)

    # Verifica primeiro staging
    assert len(new_diff["entities"]) == 1
    assert new_diff["entities"][0]["field_changes"] == [
        {"field": "logical_name", "before": "users", "after": "User"}
    ]

    # Segunda edição: muda domain (CAMPO DIFERENTE)
    entry2 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {
            "target_entity_id": "ent-123",
            "domain": "Sales",
        },
        "field_changes": [
            {"field": "domain", "before": None, "after": "Sales"}
        ],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)

    # RESULTADO: ambos os field_changes acumulam
    assert len(new_diff2["entities"]) == 1
    entity = new_diff2["entities"][0]
    assert len(entity["field_changes"]) == 2

    # Verifica que ambos os fields estão presentes
    fields = {fc.get("field") for fc in entity["field_changes"]}
    assert fields == {"logical_name", "domain"}

    # Verifica que o payload tem ambas as chaves
    assert entity["payload"]["logical_name"] == "User"
    assert entity["payload"]["domain"] == "Sales"
    assert entity["payload"]["target_entity_id"] == "ent-123"


def test_merge_same_field_last_wins(state):
    """(b) Editar o MESMO campo 2x → última intenção vence."""
    diff = {"entities": []}
    entry1 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123", "logical_name": "Users"},
        "field_changes": [
            {"field": "logical_name", "before": "users", "after": "Users"}
        ],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)

    # Segunda edição: muda o MESMO field (logical_name)
    entry2 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123", "logical_name": "Clientes"},
        "field_changes": [
            {"field": "logical_name", "before": "Users", "after": "Clientes"}
        ],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)

    # RESULTADO: field_changes tem só 1 entry, a última
    assert len(new_diff2["entities"]) == 1
    entity = new_diff2["entities"][0]
    assert len(entity["field_changes"]) == 1
    assert entity["field_changes"][0] == {
        "field": "logical_name",
        "before": "Users",
        "after": "Clientes",
    }
    # Payload também reflete a última intenção
    assert entity["payload"]["logical_name"] == "Clientes"


def test_merge_two_attributes_coexist(state):
    """(c) Edições de 2 atributos DIFERENTES coexistem (não eliminam)."""
    diff = {"entities": []}
    # Primeira edição: add coluna A
    entry1 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123"},
        "field_changes": [
            {
                "field": "attribute_add:id",
                "before": None,
                "after": {"attribute_id": "attr-1", "technical_name": "id", "native_data_type": "BIGINT"},
            }
        ],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)

    # Segunda edição: add coluna B (ATRIBUTO DIFERENTE)
    entry2 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123"},
        "field_changes": [
            {
                "field": "attribute_add:name",
                "before": None,
                "after": {"attribute_id": "attr-2", "technical_name": "name", "native_data_type": "STRING"},
            }
        ],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)

    # RESULTADO: ambos os field_changes acumulam
    assert len(new_diff2["entities"]) == 1
    entity = new_diff2["entities"][0]
    assert len(entity["field_changes"]) == 2

    # Verifica que ambos os atributos estão
    fields = {fc.get("field") for fc in entity["field_changes"]}
    assert fields == {"attribute_add:id", "attribute_add:name"}


def test_merge_attribute_update_overwrites(state):
    """Editar o MESMO atributo 2x → última intenção vence."""
    diff = {"entities": []}
    # Primeira edição: update coluna name
    entry1 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123"},
        "field_changes": [
            {
                "field": "attribute:name.update",
                "before": None,
                "after": {
                    "attribute_id": "attr-2",
                    "technical_name": "name",
                    "logical_name": "Nome",
                    "native_data_type": "STRING",
                },
            }
        ],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)

    # Segunda edição: update MESMO atributo, muda logical_name
    entry2 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"target_entity_id": "ent-123"},
        "field_changes": [
            {
                "field": "attribute:name.update",
                "before": None,
                "after": {
                    "attribute_id": "attr-2",
                    "technical_name": "name",
                    "logical_name": "User Name",
                    "native_data_type": "STRING",
                },
            }
        ],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)

    # RESULTADO: só 1 field_change, a última
    assert len(new_diff2["entities"]) == 1
    entity = new_diff2["entities"][0]
    assert len(entity["field_changes"]) == 1
    fc = entity["field_changes"][0]
    assert fc["field"] == "attribute:name.update"
    assert fc["after"]["logical_name"] == "User Name"  # última intenção


def test_stage_empty_payload_still_accumulates_fields(state):
    """Se um entry tem payload vazio, merge ainda acumula field_changes."""
    diff = {"entities": []}
    entry1 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {},
        "field_changes": [{"field": "f1", "before": None, "after": "v1"}],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)

    entry2 = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"key2": "value2"},
        "field_changes": [{"field": "f2", "before": None, "after": "v2"}],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)

    entity = new_diff2["entities"][0]
    assert len(entity["field_changes"]) == 2
    assert entity["payload"] == {"key2": "value2"}


def test_add_entry_no_existing(state):
    """Novo entry (sem existente): apenas append."""
    diff = {"entities": []}
    entry = {
        "op": "add",
        "schema_name": "public",
        "technical_name": "new_table",
        "entity_type": "TABLE",
        "payload": {"logical_name": "New Table"},
        "field_changes": [],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry)

    assert len(new_diff["entities"]) == 1
    assert new_diff["entities"][0] == entry


def test_recount_after_merge(state):
    """Recount após merge está correto."""
    diff = {"entities": []}
    entry1 = {
        "op": "add",
        "schema_name": "public",
        "technical_name": "t1",
        "entity_type": "TABLE",
        "payload": {},
        "field_changes": [],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry1)
    assert new_diff["additions"] == 1

    # Merge outro op=add: não muda count (ainda é o mesmo entry por schema.tech.op)
    entry2 = {
        "op": "add",
        "schema_name": "public",
        "technical_name": "t1",
        "entity_type": "TABLE",
        "payload": {"logical_name": "T1"},
        "field_changes": [{"field": "logical_name", "before": None, "after": "T1"}],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry2)
    assert len(new_diff2["entities"]) == 1
    assert new_diff2["additions"] == 1  # still 1, não duplicou

    # Add outra entidade: count sobe
    entry3 = {
        "op": "add",
        "schema_name": "public",
        "technical_name": "t2",
        "entity_type": "TABLE",
        "payload": {},
        "field_changes": [],
    }
    new_diff3 = stage_entity_change(MagicMock(), "ticket-1", new_diff2, entry3)
    assert len(new_diff3["entities"]) == 2
    assert new_diff3["additions"] == 2


def test_mixed_ops_in_same_entity_schema(state):
    """OPs diferentes (add vs change) são treated como DISTINTOS entries."""
    diff = {"entities": []}
    entry_add = {
        "op": "add",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"logical_name": "Users"},
        "field_changes": [],
    }
    new_diff = stage_entity_change(MagicMock(), "ticket-1", diff, entry_add)

    # Depois um change da MESMA entidade (op diferente)
    entry_change = {
        "op": "change",
        "schema_name": "public",
        "technical_name": "users",
        "entity_type": "TABLE",
        "payload": {"domain": "Core"},
        "field_changes": [{"field": "domain", "before": None, "after": "Core"}],
    }
    new_diff2 = stage_entity_change(MagicMock(), "ticket-1", new_diff, entry_change)

    # RESULTADO: 2 entries distintos (schema.tech.add vs schema.tech.change)
    assert len(new_diff2["entities"]) == 2
    ops = {e.get("op") for e in new_diff2["entities"]}
    assert ops == {"add", "change"}
    assert new_diff2["additions"] == 1
    assert new_diff2["changes"] == 1
