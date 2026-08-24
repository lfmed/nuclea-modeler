"""Tests para os endpoints de flags de relacionamentos (Bloco 5).

Espelha test_flags_batch.py mas para relacionamentos. Documentam o
comportamento esperado da aplicação/remoção de flags em lote a
relacionamentos:

- aplicar N flags a N relacionamentos numa chamada (produto cartesiano);
- idempotência (reaplicar flag já presente não falha nem duplica insert);
- erro parcial por item (flag inválida/sem justificativa não aborta o lote);
- SEM propagação LGPD (não é conceitual para relacionamentos).

Estratégia: monkeypatch delta/settings/email como em test_flags_batch.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.flags import router as frouter
from nuclea_modeler.backend.flags.models import (
    BatchFlagApplyIn,
    BatchFlagRemoveIn,
    BatchFlagSpec,
)


def _flag_row(flag_id: str, *, category: str = "USE", requires_just: bool = False):
    """Monta uma linha de catálogo no formato de _FLAG_COLS."""
    return [
        flag_id,             # flag_id
        f"{flag_id}-key",    # flag_key
        category,            # category
        f"Flag {flag_id}",   # display_name
        None,                # description
        "#123456",           # color_hex
        requires_just,       # requires_justification
        False,               # is_system
        True,                # is_active
        None,                # uc_tag_key
    ]


@pytest.fixture
def state(monkeypatch):
    """Captura chamadas em delta para testar os endpoints de relationship flags."""
    captured: dict = {
        "inserts": [],
        "runs": [],
        "flags": {},
        # set de (target_id, flag_id) já aplicados → idempotência
        "already_applied": set(),
        "new_id_counter": 0,
    }

    def fake_fetch_one_params(sql, query, params=None):
        pdict = dict(params or [])
        # _fetch_flag: SELECT ... FROM flags WHERE flag_id = :flag_id
        if "FROM cat.sch.flags" in query and "flag_id = :flag_id" in query:
            fid = pdict.get("flag_id")
            return captured["flags"].get(fid)
        # idempotência no apply: SELECT relationship_flag_id ... WHERE rel+flag
        if "relationship_flag_id FROM cat.sch.relationship_flags" in query:
            key = (pdict.get("relationship_id"), pdict.get("flag_id"))
            return ["existing-rf"] if key in captured["already_applied"] else None
        return None

    def fake_insert(sql, table, row):
        captured["inserts"].append((table, dict(row)))

    def fake_run_params(sql, query, params=None):
        captured["runs"].append((query, dict(params or [])))

    def fake_new_id(prefix=""):
        captured["new_id_counter"] += 1
        return f"{prefix}fake{captured['new_id_counter']}"

    monkeypatch.setattr(frouter.delta, "fetch_one_params", fake_fetch_one_params)
    monkeypatch.setattr(frouter.delta, "insert", fake_insert)
    monkeypatch.setattr(frouter.delta, "run_params", fake_run_params)
    monkeypatch.setattr(frouter.delta, "new_id", fake_new_id)
    monkeypatch.setattr(frouter.delta, "param", lambda name, value: (name, value))

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(frouter, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(frouter, "_current_email", lambda user_ws: "leandro")

    return captured


# ─── Relacionamentos: aplicar N flags a N alvos ──────────────────────────────


def test_batch_apply_relationship_flags_cartesian(state):
    """2 flags × 3 relacionamentos = 6 itens, todos ok, 6 inserts."""
    state["flags"] = {"f1": _flag_row("f1"), "f2": _flag_row("f2")}
    payload = BatchFlagApplyIn(
        target_ids=["r1", "r2", "r3"],
        flags=[BatchFlagSpec(flag_id="f1"), BatchFlagSpec(flag_id="f2")],
    )
    result = frouter.batch_apply_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.action == "apply"
    assert result.total == 6
    assert result.succeeded == 6
    assert result.failed == 0
    rf_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.relationship_flags"]
    assert len(rf_inserts) == 6


def test_batch_apply_relationship_flags_idempotent(state):
    """Reaplicar flag já presente num relacionamento conta como sucesso e NÃO
    insere de novo."""
    state["flags"] = {"f1": _flag_row("f1")}
    state["already_applied"] = {("r1", "f1")}  # r1 já tem f1
    payload = BatchFlagApplyIn(
        target_ids=["r1", "r2"], flags=[BatchFlagSpec(flag_id="f1")],
    )
    result = frouter.batch_apply_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 2  # ambos ok
    rf_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.relationship_flags"]
    assert len(rf_inserts) == 1  # só r2 inseriu; r1 reaproveitou


def test_batch_apply_relationship_flags_justification_optional(state):
    """v1.0035: justificativa opcional — aplicar flag requires_justification sem
    texto SUCEDE em todos os alvos (antes falhava)."""
    state["flags"] = {
        "f1": _flag_row("f1"),
        "fj": _flag_row("fj", category="LGPD", requires_just=True),
    }
    payload = BatchFlagApplyIn(
        target_ids=["r1", "r2"],
        flags=[
            BatchFlagSpec(flag_id="f1"),           # ok
            BatchFlagSpec(flag_id="fj"),           # requires_justification, sem texto → agora OK
        ],
    )
    result = frouter.batch_apply_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.total == 4
    assert result.succeeded == 4  # justificativa opcional → todos aplicam
    assert result.failed == 0


def test_batch_apply_relationship_flags_missing_flag_fails_all_targets(state):
    """Flag inexistente no catálogo → falha para todos os alvos, sem exception."""
    state["flags"] = {}  # nenhuma flag existe
    payload = BatchFlagApplyIn(
        target_ids=["r1", "r2"], flags=[BatchFlagSpec(flag_id="ghost")],
    )
    result = frouter.batch_apply_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 0
    assert result.failed == 2


# ─── Remoção em lote ────────────────────────────────────────────────────────


def test_batch_remove_relationship_flags_runs_deletes(state):
    """Remover 1 flag de 2 relacionamentos dispara 2 DELETEs; idempotente."""
    payload = BatchFlagRemoveIn(target_ids=["r1", "r2"], flag_ids=["f1"])
    result = frouter.batch_remove_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.action == "remove"
    assert result.total == 2
    assert result.succeeded == 2
    deletes = [q for q, _ in state["runs"] if "DELETE" in q and "relationship_flags" in q]
    assert len(deletes) == 2


def test_batch_remove_relationship_flags_multiple_flags_and_targets(state):
    """Remover 2 flags de 3 relacionamentos = 6 DELETEs, todos ok."""
    payload = BatchFlagRemoveIn(
        target_ids=["r1", "r2", "r3"],
        flag_ids=["f1", "f2"],
    )
    result = frouter.batch_remove_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.total == 6
    assert result.succeeded == 6
    deletes = [q for q, _ in state["runs"] if "DELETE" in q and "relationship_flags" in q]
    assert len(deletes) == 6


def test_batch_apply_relationship_flags_with_justification(state):
    """Aplicar flag que exige justificativa COM texto funciona normal."""
    state["flags"] = {"lg": _flag_row("lg", category="LGPD", requires_just=True)}
    payload = BatchFlagApplyIn(
        target_ids=["r1"],
        flags=[BatchFlagSpec(flag_id="lg", justification="Relacionamento crítico")],
    )
    result = frouter.batch_apply_relationship_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 1
    rf_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.relationship_flags"]
    assert len(rf_inserts) == 1
    assert rf_inserts[0][1]["justification"] == "Relacionamento crítico"
