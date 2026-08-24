"""Tests para o apply de descrição de coluna (v1.0030, plano round 3 A2/A3).

GOTCHA corrigido: o allowlist de apply de `attribute:NAME.update` em
`_dispatch_field_change` NÃO incluía `description_md`/`business_rule`. Resultado:
a descrição editada por coluna (no modal do DER ou na tela do objeto) era staged
no ticket mas **descartada** no apply — nunca chegava ao catálogo. Estes testes
fixam o contrato: os dois campos entram no UPDATE (edição) e no INSERT (criação).

Documentação viva: se alguém remover os campos do allowlist de novo, o CI quebra.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from nuclea_modeler.backend.core import delta
from nuclea_modeler.backend.tickets import service as svc
from nuclea_modeler.backend.tickets.service import _ApplyState, _dispatch_field_change


@pytest.fixture
def captured(monkeypatch):
    """Captura UPDATE (run_params) e INSERT (insert) do apply, com deps fakeadas."""
    cap: dict = {"update_query": None, "update_params": [], "inserts": []}

    def fake_run_params(sql, query, params):
        cap["update_query"] = query
        cap["update_params"] = list(params)

    def fake_insert(sql, table, fields):
        cap["inserts"].append((table, dict(fields)))

    monkeypatch.setattr(delta, "run_params", fake_run_params)
    monkeypatch.setattr(delta, "insert", fake_insert)
    monkeypatch.setattr(delta, "param", lambda name, value: (name, value))
    monkeypatch.setattr(delta, "new_id", lambda prefix="": f"{prefix}fixed")

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(svc, "get_settings", lambda: fake_settings)

    return cap


def _state() -> _ApplyState:
    return _ApplyState(
        sql=object(),
        system_id="sys-1",
        applied_by="tester@nuclea",
        now=datetime(2026, 8, 24, 12, 0, 0),
        decisions=None,
        ws=None,
        sandbox_info=None,
    )


def test_update_carries_description_and_business_rule(captured):
    """UPDATE de atributo inclui description_md e business_rule (v1.0030)."""
    state = _state()
    new_val = {
        "attribute_id": "attr-1",
        "technical_name": "cpf",
        "description_md": "Documento do titular",
        "business_rule": "Obrigatório para PF",
    }
    _dispatch_field_change(state, "ent-1", "attribute:cpf.update", new_val, {})

    query = captured["update_query"]
    assert query is not None, "UPDATE não foi emitido"
    assert "description_md = :description_md" in query
    assert "business_rule = :business_rule" in query

    params = dict(captured["update_params"])  # [(name, value), ...] → dict
    assert params["description_md"] == "Documento do titular"
    assert params["business_rule"] == "Obrigatório para PF"
    # WHERE ainda por entity + nome técnico da coluna.
    assert params["entity_id"] == "ent-1"
    assert params["name"] == "cpf"
    assert state.applied_attributes == 1


def test_update_empty_string_description_still_written(captured):
    """String vazia zera a descrição (passa no filtro `v is not None`)."""
    state = _state()
    new_val = {"technical_name": "cpf", "description_md": ""}
    _dispatch_field_change(state, "ent-1", "attribute:cpf.update", new_val, {})

    query = captured["update_query"]
    # "" não é None → deve entrar no SET (limpa o texto).
    assert query is not None
    assert "description_md = :description_md" in query
    assert dict(captured["update_params"])["description_md"] == ""


def test_update_without_description_omits_column(captured):
    """Sem description/business_rule no payload, o UPDATE não os inclui (None filtrado)."""
    state = _state()
    new_val = {"technical_name": "cpf", "logical_name": "CPF"}
    _dispatch_field_change(state, "ent-1", "attribute:cpf.update", new_val, {})

    query = captured["update_query"]
    assert query is not None
    assert "logical_name = :logical_name" in query
    assert "description_md" not in query
    assert "business_rule" not in query


def test_attribute_add_persists_description(captured):
    """CRIAÇÃO de coluna já grava description_md/business_rule (v1.0030)."""
    state = _state()
    new_val = {
        "technical_name": "cpf",
        "native_data_type": "STRING",
        "description_md": "Documento do titular",
        "business_rule": "Obrigatório para PF",
    }
    _dispatch_field_change(state, "ent-1", "attribute_add:cpf", new_val, {})

    assert captured["inserts"], "INSERT não foi emitido"
    _table, fields = captured["inserts"][0]
    assert fields["description_md"] == "Documento do titular"
    assert fields["business_rule"] == "Obrigatório para PF"
    assert fields["technical_name"] == "cpf"
    assert state.applied_attributes == 1
