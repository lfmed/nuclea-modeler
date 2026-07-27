"""Tests para os endpoints batch de flags (Blocos 3 + 6).

Documentam o comportamento esperado da aplicação/remoção de flags em lote:

- aplicar N flags a N alvos numa chamada (produto cartesiano em `results`);
- idempotência (reaplicar flag já presente não falha nem duplica insert);
- erro parcial por item (flag inválida/sem justificativa não aborta o lote);
- propagação LGPD atributo→entidade preservada no caminho batch.

Estratégia: como os endpoints são funções simples que usam `delta`, `get_settings`
e `_current_email` do módulo `flags.router`, monkeypatchamos esses três para focar
na lógica de lote sem tocar num warehouse real (mesmo padrão de test_tickets_service).
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
    """Captura chamadas em delta e permite roteirizar retornos de SELECT.

    `flags` mapeia flag_id → linha de catálogo (usada pelo _fetch_flag do router).
    `existing_apply` controla o SELECT de idempotência (True = já aplicado).
    """
    captured: dict = {
        "inserts": [],
        "runs": [],
        "flags": {},
        # set de (target_id, flag_id) já aplicados → idempotência
        "already_applied": set(),
        # set de flag_ids cuja categoria é LGPD (para SELECT category no remove)
        "lgpd_flags": set(),
        # entity_id devolvido por _entity_id_for_attribute
        "attr_entity": "ent-1",
        # controla o guard still_used no cleanup LGPD (True = ainda em uso)
        "still_used": False,
        "new_id_counter": 0,
    }

    def fake_fetch_one_params(sql, query, params=None):
        pdict = dict(params or [])
        # _fetch_flag: SELECT ... FROM flags WHERE flag_id = :flag_id
        if "FROM cat.sch.flags" in query and "flag_id = :flag_id" in query and "category FROM" not in query:
            fid = pdict.get("flag_id")
            return captured["flags"].get(fid)
        # SELECT category FROM flags (usado em _remove_attribute_flag_by_flag)
        if "SELECT category FROM cat.sch.flags" in query:
            fid = pdict.get("flag_id")
            return ["LGPD"] if fid in captured["lgpd_flags"] else ["USE"]
        # idempotência no apply: SELECT entity_flag_id/attribute_flag_id ... WHERE target+flag
        if "entity_flag_id FROM cat.sch.entity_flags" in query:
            key = (pdict.get("entity_id"), pdict.get("flag_id"))
            return ["existing-ef"] if key in captured["already_applied"] else None
        if "attribute_flag_id FROM cat.sch.attribute_flags" in query:
            key = (pdict.get("attribute_id"), pdict.get("flag_id"))
            return ["existing-af"] if key in captured["already_applied"] else None
        # _propagate_lgpd_to_entity: checa se a entidade já tem a flag
        if "SELECT entity_flag_id FROM cat.sch.entity_flags" in query:
            return None  # nunca tem → sempre propaga (idempotência testada à parte)
        # _entity_id_for_attribute
        if "entity_id FROM cat.sch.attributes" in query:
            return [captured["attr_entity"]]
        # _cleanup_propagated_entity_flag: guard still_used
        if "FROM cat.sch.attribute_flags af" in query and "LIMIT 1" in query:
            return [1] if captured["still_used"] else None
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
    # actor autenticado fixo
    monkeypatch.setattr(frouter, "_current_email", lambda user_ws: "leandro")

    return captured


# ─── Entidades: aplicar N flags a N alvos ───────────────────────────────────


def test_batch_apply_entity_flags_cartesian(state):
    """2 flags × 3 entidades = 6 itens, todos ok, 6 inserts."""
    state["flags"] = {"f1": _flag_row("f1"), "f2": _flag_row("f2")}
    payload = BatchFlagApplyIn(
        target_ids=["e1", "e2", "e3"],
        flags=[BatchFlagSpec(flag_id="f1"), BatchFlagSpec(flag_id="f2")],
    )
    result = frouter.batch_apply_entity_flags(payload, MagicMock(), MagicMock())
    assert result.action == "apply"
    assert result.total == 6
    assert result.succeeded == 6
    assert result.failed == 0
    ef_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.entity_flags"]
    assert len(ef_inserts) == 6


def test_batch_apply_entity_flags_idempotent(state):
    """Reaplicar flag já presente conta como sucesso e NÃO insere de novo."""
    state["flags"] = {"f1": _flag_row("f1")}
    state["already_applied"] = {("e1", "f1")}  # e1 já tem f1
    payload = BatchFlagApplyIn(
        target_ids=["e1", "e2"], flags=[BatchFlagSpec(flag_id="f1")],
    )
    result = frouter.batch_apply_entity_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 2  # ambos ok
    ef_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.entity_flags"]
    assert len(ef_inserts) == 1  # só e2 inseriu; e1 reaproveitou


def test_batch_apply_entity_flags_partial_error_missing_justification(state):
    """Flag que exige justificativa sem texto falha para TODOS os alvos daquela
    flag, mas o lote não aborta as demais flags."""
    state["flags"] = {
        "f1": _flag_row("f1"),
        "fj": _flag_row("fj", category="LGPD", requires_just=True),
    }
    payload = BatchFlagApplyIn(
        target_ids=["e1", "e2"],
        flags=[
            BatchFlagSpec(flag_id="f1"),           # ok
            BatchFlagSpec(flag_id="fj"),           # sem justificativa → falha
        ],
    )
    result = frouter.batch_apply_entity_flags(payload, MagicMock(), MagicMock())
    assert result.total == 4
    assert result.succeeded == 2  # só f1 nos 2 alvos
    assert result.failed == 2     # fj nos 2 alvos
    failed = [r for r in result.results if not r.ok]
    assert all(r.flag_id == "fj" for r in failed)
    assert all("justif" in (r.error or "").lower() for r in failed)


def test_batch_apply_entity_flags_missing_flag_fails_all_targets(state):
    """Flag inexistente no catálogo → falha para todos os alvos, sem exception."""
    state["flags"] = {}  # nenhuma flag existe
    payload = BatchFlagApplyIn(
        target_ids=["e1", "e2"], flags=[BatchFlagSpec(flag_id="ghost")],
    )
    result = frouter.batch_apply_entity_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 0
    assert result.failed == 2


# ─── Atributos: propagação LGPD preservada ──────────────────────────────────


def test_batch_apply_attribute_flags_propagates_lgpd(state):
    """Aplicar flag LGPD em atributo insere a linha do atributo E propaga uma
    entity_flag (is_propagated=True) na entidade-pai."""
    state["flags"] = {"lg": _flag_row("lg", category="LGPD")}
    payload = BatchFlagApplyIn(
        target_ids=["a1"], flags=[BatchFlagSpec(flag_id="lg", justification="cpf")],
    )
    result = frouter.batch_apply_attribute_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 1
    af_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.attribute_flags"]
    ef_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.entity_flags"]
    assert len(af_inserts) == 1
    assert len(ef_inserts) == 1  # propagou
    assert ef_inserts[0][1]["is_propagated"] is True
    assert ef_inserts[0][1]["entity_id"] == "ent-1"


def test_batch_apply_attribute_flags_non_lgpd_does_not_propagate(state):
    """Flag não-LGPD não gera propagação para a entidade."""
    state["flags"] = {"q1": _flag_row("q1", category="QUALITY")}
    payload = BatchFlagApplyIn(
        target_ids=["a1", "a2"], flags=[BatchFlagSpec(flag_id="q1")],
    )
    result = frouter.batch_apply_attribute_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 2
    ef_inserts = [i for i in state["inserts"] if i[0] == "cat.sch.entity_flags"]
    assert ef_inserts == []


# ─── Remoção em lote ────────────────────────────────────────────────────────


def test_batch_remove_entity_flags_runs_deletes(state):
    """Remover 1 flag de 2 entidades dispara 2 DELETEs; idempotente (sem erro se
    a flag não existir no alvo)."""
    payload = BatchFlagRemoveIn(target_ids=["e1", "e2"], flag_ids=["f1"])
    result = frouter.batch_remove_entity_flags(payload, MagicMock(), MagicMock())
    assert result.action == "remove"
    assert result.total == 2
    assert result.succeeded == 2
    deletes = [q for q, _ in state["runs"] if "DELETE" in q and "entity_flags" in q]
    assert len(deletes) == 2


def test_batch_remove_attribute_flags_cleans_lgpd_propagation(state):
    """Remover flag LGPD de atributo dispara o DELETE e, como nenhuma outra coluna
    ainda usa a flag (still_used=False), remove também a propagação na entidade."""
    state["lgpd_flags"] = {"lg"}
    state["still_used"] = False
    payload = BatchFlagRemoveIn(target_ids=["a1"], flag_ids=["lg"])
    result = frouter.batch_remove_attribute_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 1
    deletes = [q for q, _ in state["runs"] if "DELETE" in q]
    # um DELETE no attribute_flags + um DELETE da propagação em entity_flags
    assert any("attribute_flags" in q for q in deletes)
    assert any("entity_flags" in q for q in deletes)


def test_batch_remove_attribute_flags_keeps_propagation_when_still_used(state):
    """Se outra coluna ainda carrega a flag LGPD (still_used=True), a propagação
    da entidade é preservada — só o attribute_flag some."""
    state["lgpd_flags"] = {"lg"}
    state["still_used"] = True
    payload = BatchFlagRemoveIn(target_ids=["a1"], flag_ids=["lg"])
    result = frouter.batch_remove_attribute_flags(payload, MagicMock(), MagicMock())
    assert result.succeeded == 1
    deletes = [q for q, _ in state["runs"] if "DELETE" in q]
    assert any("attribute_flags" in q for q in deletes)
    assert not any("entity_flags" in q for q in deletes)
