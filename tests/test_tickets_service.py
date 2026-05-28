"""Tests para tickets/service — open_ticket e apply_ticket.

Mocka delta.insert / fetch_one_params / update_by_id / new_id pra
focar na lógica de negócio: persistência do diff JSON, idempotência
de add (skip se já existe), gating de APPLY por status APPROVED,
mapping de field_changes em update_by_id.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.tickets import service as tsvc
from nuclea_modeler.backend.tickets.models import DiffEntity, TicketDiff


@pytest.fixture
def state(monkeypatch):
    """Captura calls em delta e expõe state mutable pros testes."""
    captured: dict = {
        "inserts": [],          # list of (table, row)
        "updates": [],          # list of (table, key, key_val, fields)
        "fetch_one_returns": [],  # FIFO de retornos
        "new_id_counter": 0,
    }

    def fake_insert(sql, table, row):
        captured["inserts"].append((table, dict(row)))

    def fake_update_by_id(sql, table, key, key_val, fields):
        captured["updates"].append((table, key, key_val, dict(fields)))

    def fake_fetch_one_params(sql, query, params=None):
        if captured["fetch_one_returns"]:
            return captured["fetch_one_returns"].pop(0)
        return None

    def fake_new_id(prefix=""):
        captured["new_id_counter"] += 1
        return f"{prefix}fake{captured['new_id_counter']}"

    def fake_param(name, value):
        return (name, value)

    from nuclea_modeler.backend.core import delta
    monkeypatch.setattr(delta, "insert", fake_insert)
    monkeypatch.setattr(delta, "update_by_id", fake_update_by_id)
    monkeypatch.setattr(delta, "fetch_one_params", fake_fetch_one_params)
    monkeypatch.setattr(delta, "new_id", fake_new_id)
    monkeypatch.setattr(delta, "param", fake_param)

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(tsvc, "get_settings", lambda: fake_settings)

    return captured


# ─── open_ticket ────────────────────────────────────────────────────────────


def test_open_ticket_persists_with_status_open(state):
    diff = TicketDiff(entities=[], additions=0, removals=0, changes=0)
    tid = tsvc.open_ticket(
        MagicMock(),
        title="Sync schema XYZ",
        system_id="sys-1",
        source_type="MANUAL",
        diff=diff,
        created_by="leandro",
    )

    assert tid.startswith("ticket-")
    assert len(state["inserts"]) == 1
    table, row = state["inserts"][0]
    assert table == "cat.sch.reconciliation_tickets"
    assert row["status"] == "OPEN"
    assert row["title"] == "Sync schema XYZ"
    assert row["created_by"] == "leandro"


def test_open_ticket_counts_ops_when_explicit_zero(state):
    """Quando additions/removals/changes vêm zerados, conta entities pelo op."""
    diff = TicketDiff(
        entities=[
            DiffEntity(op="add", schema_name="public", technical_name="cliente"),
            DiffEntity(op="add", schema_name="public", technical_name="pedido"),
            DiffEntity(op="remove", schema_name="legado", technical_name="velha"),
            DiffEntity(op="change", schema_name="public", technical_name="cliente_v2"),
        ],
        additions=0, removals=0, changes=0,
    )
    tsvc.open_ticket(
        MagicMock(), title="t", system_id="s",
        source_type="MANUAL", diff=diff, created_by="u",
    )
    _, row = state["inserts"][0]
    assert row["additions_count"] == 2
    assert row["removals_count"] == 1
    assert row["changes_count"] == 1


def test_open_ticket_respects_explicit_counters(state):
    """Quando counters explícitos vêm preenchidos, são preservados."""
    diff = TicketDiff(entities=[], additions=42, removals=7, changes=3)
    tsvc.open_ticket(
        MagicMock(), title="t", system_id="s",
        source_type="REVERSE_ENG", diff=diff, created_by="u",
    )
    _, row = state["inserts"][0]
    assert row["additions_count"] == 42
    assert row["removals_count"] == 7
    assert row["changes_count"] == 3


def test_open_ticket_serializes_diff_to_json(state):
    """diff_json deve ser parseable de volta para a estrutura original."""
    diff = TicketDiff(
        entities=[
            DiffEntity(op="add", schema_name="s", technical_name="t",
                       payload={"logical_name": "Teste"}),
        ],
    )
    tsvc.open_ticket(
        MagicMock(), title="t", system_id="s",
        source_type="MANUAL", diff=diff, created_by="u",
    )
    _, row = state["inserts"][0]
    parsed = json.loads(row["diff_json"])
    assert parsed["entities"][0]["op"] == "add"
    assert parsed["entities"][0]["payload"]["logical_name"] == "Teste"


def test_open_ticket_returns_unique_ids(state):
    """IDs gerados via new_id são únicos por chamada."""
    diff = TicketDiff(entities=[])
    t1 = tsvc.open_ticket(MagicMock(), title="a", system_id="s",
                          source_type="MANUAL", diff=diff, created_by="u")
    t2 = tsvc.open_ticket(MagicMock(), title="b", system_id="s",
                          source_type="MANUAL", diff=diff, created_by="u")
    assert t1 != t2


# ─── apply_ticket — gates ───────────────────────────────────────────────────


def test_apply_returns_error_when_ticket_not_found(state):
    """Ticket inexistente retorna erro sem mexer no banco."""
    state["fetch_one_returns"] = [None]  # SELECT do ticket retorna None
    result = tsvc.apply_ticket(MagicMock(), "ticket-missing", applied_by="u")
    assert result.applied_entities == 0
    assert result.applied_attributes == 0
    assert any("not found" in e for e in result.errors)
    assert state["updates"] == []  # nada mudou


def test_apply_blocks_non_approved_status(state):
    """Só tickets APPROVED podem ser aplicados — OPEN é bloqueado."""
    state["fetch_one_returns"] = [
        ('{"entities": []}', "sys-1", "OPEN"),
    ]
    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.status == "OPEN"
    assert any("must be APPROVED" in e for e in result.errors)
    assert state["updates"] == []


@pytest.mark.parametrize("status", ["REJECTED", "APPLIED", "ARCHIVED"])
def test_apply_blocks_terminal_statuses(state, status):
    state["fetch_one_returns"] = [('{"entities": []}', "sys-1", status)]
    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.status == status
    assert state["updates"] == []


def test_apply_handles_invalid_diff_json(state):
    """diff_json corrompido vira erro estruturado, não exception."""
    state["fetch_one_returns"] = [("not valid json {", "sys-1", "APPROVED")]
    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert any("invalid diff_json" in e for e in result.errors)


# ─── apply_ticket — op=add ──────────────────────────────────────────────────


def test_apply_add_inserts_entity_when_not_exists(state):
    """op=add cria entidade quando key não existe."""
    diff = {
        "entities": [
            {
                "op": "add", "schema_name": "public", "technical_name": "cliente",
                "entity_type": "TABLE",
                "payload": {"logical_name": "Cliente PF", "domain": "Cadastro"},
                "attributes": [],
            }
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),  # primeiro SELECT
        None,                                       # checagem de "existing"
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 1
    # 1 insert no entities + 1 update_by_id no ticket
    entities_inserts = [
        i for i in state["inserts"] if i[0] == "cat.sch.entities"
    ]
    assert len(entities_inserts) == 1
    inserted = entities_inserts[0][1]
    assert inserted["schema_name"] == "public"
    assert inserted["technical_name"] == "cliente"
    assert inserted["logical_name"] == "Cliente PF"
    assert inserted["domain"] == "Cadastro"


def test_apply_add_is_idempotent_when_already_exists(state):
    """op=add é skipado se entity já existe (mesma key)."""
    diff = {
        "entities": [
            {"op": "add", "schema_name": "public", "technical_name": "cliente"}
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        ("ent-existente",),  # existing — não cria
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 0
    assert not any(i[0] == "cat.sch.entities" for i in state["inserts"])


def test_apply_add_with_attributes_inserts_both(state):
    """op=add com lista de attributes insere entidade + cada coluna."""
    diff = {
        "entities": [
            {
                "op": "add", "schema_name": "public", "technical_name": "cliente",
                "attributes": [
                    {"technical_name": "id", "native_data_type": "bigint",
                     "is_primary_key": True},
                    {"technical_name": "nome", "native_data_type": "varchar(200)"},
                ],
            }
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        None,  # entity não existe
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 1
    assert result.applied_attributes == 2
    attr_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.attributes"]
    assert len(attr_inserts) == 2
    assert attr_inserts[0][1]["technical_name"] == "id"
    assert attr_inserts[0][1]["is_primary_key"] is True
    assert attr_inserts[1][1]["technical_name"] == "nome"


# ─── apply_ticket — op=remove ───────────────────────────────────────────────


def test_apply_remove_emits_error_not_implemented(state):
    """op=remove é soft-delete ainda não suportado — vira warning."""
    diff = {
        "entities": [
            {"op": "remove", "schema_name": "legado", "technical_name": "velha"}
        ]
    }
    state["fetch_one_returns"] = [(json.dumps(diff), "sys-1", "APPROVED")]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    # Ainda termina como APPLIED (op skipada), mas com erros listando
    assert result.status == "APPLIED"
    assert any("not auto-applied" in e for e in result.errors)
    assert not any(i[0] == "cat.sch.entities" for i in state["inserts"])


# ─── apply_ticket — op=change ───────────────────────────────────────────────


def test_apply_change_updates_only_allowed_fields(state):
    """op=change só atualiza campos da allowlist (logical_name, description_md, etc)."""
    diff = {
        "entities": [
            {
                "op": "change", "schema_name": "public", "technical_name": "cliente",
                "field_changes": [
                    {"field": "logical_name", "after": "Cliente PF"},
                    {"field": "domain", "after": "Cadastro"},
                    {"field": "ignored_field", "after": "x"},  # fora da allowlist
                ],
            }
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        ("ent-abc",),  # entity existe
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 1
    # Procurar update da entidade (não o do ticket no final)
    entity_updates = [
        u for u in state["updates"]
        if u[0] == "cat.sch.entities" and u[1] == "entity_id"
    ]
    assert len(entity_updates) == 1
    _, _, key_val, fields = entity_updates[0]
    assert key_val == "ent-abc"
    assert fields["logical_name"] == "Cliente PF"
    assert fields["domain"] == "Cadastro"
    assert "ignored_field" not in fields
    # Audit fields foram preenchidos
    assert "updated_at" in fields
    assert fields["updated_by"] == "u"


def test_apply_change_target_missing_emits_error(state):
    """op=change com target inexistente vira erro, não exception."""
    diff = {
        "entities": [
            {"op": "change", "schema_name": "x", "technical_name": "y",
             "field_changes": [{"field": "logical_name", "after": "Z"}]}
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        None,  # entity não existe
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 0
    assert any("change target not found" in e for e in result.errors)


def test_apply_change_with_no_allowed_field_changes_does_nothing(state):
    """Se todas field_changes estão fora da allowlist, não chama update."""
    diff = {
        "entities": [
            {"op": "change", "schema_name": "public", "technical_name": "cliente",
             "field_changes": [{"field": "weird_field", "after": "x"}]}
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        ("ent-abc",),
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 0
    entity_updates = [
        u for u in state["updates"]
        if u[0] == "cat.sch.entities" and u[1] == "entity_id"
    ]
    assert entity_updates == []


# ─── apply_ticket — finalização ─────────────────────────────────────────────


def test_apply_marks_ticket_as_applied(state):
    """Sempre que apply roda (mesmo sem entities), ticket vira APPLIED."""
    diff = {"entities": []}
    state["fetch_one_returns"] = [(json.dumps(diff), "sys-1", "APPROVED")]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="leandro")
    assert result.status == "APPLIED"

    ticket_updates = [
        u for u in state["updates"]
        if u[0] == "cat.sch.reconciliation_tickets"
    ]
    assert len(ticket_updates) == 1
    _, _, tid, fields = ticket_updates[0]
    assert tid == "ticket-1"
    assert fields["status"] == "APPLIED"
    assert fields["applied_by"] == "leandro"


def test_apply_continues_after_per_entity_error(state):
    """Erro em uma entidade não aborta o loop — segue para as outras."""
    diff = {
        "entities": [
            {"op": "change", "schema_name": "miss", "technical_name": "ing",
             "field_changes": [{"field": "logical_name", "after": "X"}]},  # vai falhar
            {"op": "add", "schema_name": "public", "technical_name": "ok"},
        ]
    }
    state["fetch_one_returns"] = [
        (json.dumps(diff), "sys-1", "APPROVED"),
        None,  # change target não existe
        None,  # add — entity não existe
    ]

    result = tsvc.apply_ticket(MagicMock(), "ticket-1", applied_by="u")
    assert result.applied_entities == 1  # só o add funcionou
    assert any("change target not found" in e for e in result.errors)
