"""Round 6 — pt 16: criação manual de tabela/coluna já com descrição + flags.

O apply (materialização + aplicação das flags) roda contra o Delta e é validado no
app deployado. Aqui garantimos, em CI, o WIRING do payload: `quick_add_entity`
carrega `description_md` + `flag_keys` (tabela) e `description_md`/`check_constraint`/
`flag_keys` por coluna no entry do ticket — que o apply consome (tickets/service
`_apply_op_add` + `_apply_flag_keys_to_target`).
"""
from __future__ import annotations

from nuclea_modeler.backend.diagram import router as diag
from nuclea_modeler.backend.diagram.models import QuickEntityIn


def test_quick_add_entity_carries_description_and_flags(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(diag, "get_or_create_session_ticket", lambda *a, **k: ("tk-1", {}))

    def fake_stage(sql, ticket_id, diff, entry):
        captured["entry"] = entry
        return diff

    monkeypatch.setattr(diag, "stage_entity_change", fake_stage)
    monkeypatch.setattr(diag, "_current_email", lambda ws: "tester@x.com")

    payload = QuickEntityIn(
        system_id="sys-1",
        schema_name="public",
        technical_name="pessoa",
        description_md="Cadastro de pessoas",
        flag_keys=["dados-pessoais"],
        initial_attributes=[
            {
                "technical_name": "cpf",
                "native_data_type": "VARCHAR(11)",
                "description_md": "CPF do titular",
                "check_constraint": "length(cpf) = 11",
                "flag_keys": ["titular-identificado"],
            }
        ],
    )
    diag.quick_add_entity("sys-1", payload, sql=object(), user_ws=object())

    entry = captured["entry"]
    # tabela: descrição + flags carregadas no payload do op=add
    assert entry["op"] == "add"
    assert entry["payload"]["description_md"] == "Cadastro de pessoas"
    assert entry["payload"]["flag_keys"] == ["dados-pessoais"]
    # coluna: descrição + CHECK + flags carregados
    attr = entry["attributes"][0]
    assert attr["technical_name"] == "cpf"
    assert attr["description_md"] == "CPF do titular"
    assert attr["check_constraint"] == "length(cpf) = 11"
    assert attr["flag_keys"] == ["titular-identificado"]


def test_quick_add_entity_defaults_no_flags(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(diag, "get_or_create_session_ticket", lambda *a, **k: ("tk-1", {}))
    monkeypatch.setattr(diag, "stage_entity_change",
                        lambda sql, tid, diff, entry: captured.setdefault("entry", entry) or diff)
    monkeypatch.setattr(diag, "_current_email", lambda ws: "tester@x.com")

    payload = QuickEntityIn(
        system_id="s", schema_name="public", technical_name="t",
        initial_attributes=[{"technical_name": "id", "is_primary_key": True}],
    )
    diag.quick_add_entity("s", payload, sql=object(), user_ws=object())
    entry = captured["entry"]
    assert entry["payload"]["flag_keys"] == []
    assert entry["payload"]["description_md"] is None
    assert entry["attributes"][0]["flag_keys"] == []
