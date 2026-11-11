"""Erros de import VISÍVEIS depois do import (v1.0075).

Pergunta real do cliente: o ticket de um import de DDL dizia "Erros de parse: 61",
mas ele não tinha onde ver QUAIS. Antes:
- o ticket só tinha a contagem;
- o Histórico só mostrava o status PARTIAL;
- o log gravado em `extractions.error_summary` era cortado em 4000 chars NO MEIO
  de uma linha (com ~60 erros, metade se perdia).

Estes testes fixam o contrato novo:
1. `join_error_summary` grava 1 mensagem por linha, corta em FRONTEIRA DE LINHA e
   diz quantas ficaram de fora; `split_error_summary` lê de volta (round-trip).
2. `format_ticket_errors` lista os primeiros N erros + "e mais X" + onde ver tudo.
3. Ponta a ponta no `run_ddl_import` (banco mockado): o resumo do ticket traz o
   erro com o número da linha, e o log gravado na extração traz a lista inteira.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.extractions import service as svc
from nuclea_modeler.backend.extractions.service import (
    format_ticket_errors,
    join_error_summary,
    split_error_summary,
)


# ─── join / split ────────────────────────────────────────────────────────────


def test_join_vazio_vira_none():
    # Coluna fica NULL quando não há o que gravar (comportamento anterior).
    assert join_error_summary([]) is None
    assert join_error_summary(["", "   "]) is None


def test_round_trip_preserva_as_mensagens():
    msgs = [f"Linha {i}: instrução ignorada (CREATE TABLE t{i}…): erro" for i in range(61)]
    assert split_error_summary(join_error_summary(msgs)) == msgs


def test_mensagem_com_quebra_de_linha_e_achatada():
    # O log é lido com 1 mensagem por linha — uma msg multilinha (exceção do
    # sqlglot costuma trazer o trecho do SQL) não pode virar 2 itens.
    out = split_error_summary(join_error_summary(["erro\n  no trecho\nX", "outro"]))
    assert out == ["erro no trecho X", "outro"]


def test_corte_em_fronteira_de_linha_com_marcador():
    msgs = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]
    out = split_error_summary(join_error_summary(msgs, max_chars=100))
    # cabem 2 mensagens inteiras (40 + 1 + 40 = 81); a 3ª estouraria o limite
    assert out[:2] == ["a" * 40, "b" * 40]
    # nenhuma mensagem cortada no meio, e o marcador diz quantas faltaram
    assert out[2] == "… (+2 mensagem(ns) não gravada(s))"
    assert len(out) == 3


def test_limite_padrao_cabe_dezenas_de_erros_sem_corte():
    # Regressão do bug: 61 erros de ~150 chars passavam de 4000 e eram cortados.
    msgs = [f"Linha {i}: " + "x" * 140 for i in range(61)]
    out = split_error_summary(join_error_summary(msgs))
    assert out == msgs


def test_split_tolera_formato_antigo_e_vazio():
    assert split_error_summary(None) == []
    assert split_error_summary("") == []
    # formato antigo: mesmo "\n".join, possivelmente com linha final truncada
    assert split_error_summary("erro 1\n\nerro 2 cort") == ["erro 1", "erro 2 cort"]


# ─── bloco do ticket ─────────────────────────────────────────────────────────


def test_ticket_sem_erros_nao_ganha_bloco():
    assert format_ticket_errors([]) == ""


def test_ticket_lista_ate_o_limite_e_aponta_o_historico():
    errs = [f"Linha {i}: falhou" for i in range(1, 62)]
    block = format_ticket_errors(errs, limit=30)
    assert "- Linha 1: falhou" in block
    assert "- Linha 30: falhou" in block
    assert "Linha 31: falhou" not in block
    assert "e mais 31 erro(s)" in block
    assert "Histórico" in block


def test_ticket_abaixo_do_limite_nao_diz_e_mais():
    block = format_ticket_errors(["Linha 3: falhou"], limit=30)
    assert "- Linha 3: falhou" in block
    assert "e mais" not in block


# ─── ponta a ponta no run_ddl_import ─────────────────────────────────────────


@pytest.fixture
def captured(monkeypatch):
    pytest.importorskip("sqlglot")
    cap: dict = {}

    def fake_compute_diff(sql, system_id, snapshot):
        n = len(snapshot.entities)
        return object(), {"found": n, "new": n, "changed": 0, "removed": 0,
                          "relationships": len(snapshot.relationships)}

    def fake_open_ticket(*a, **k):
        cap["ticket_summary_md"] = k.get("summary_md")
        return "tk-test"

    def fake_persist(*a, **k):
        cap["error_summary"] = k.get("error_summary")
        return "ext-test"

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "open_ticket", fake_open_ticket)
    monkeypatch.setattr(svc, "persist_extraction", fake_persist)
    return cap


def test_ticket_e_historico_mostram_quais_instrucoes_falharam(captured):
    ddl = "CREATE TABLE ok1 (id int);\n\nCREATE TABLE quebrada (id int;\nCREATE TABLE ok2 (id int);\n"
    r = svc.run_ddl_import(
        object(), system_id="sys-1", dialect="POSTGRES", ddl_text=ddl,
        actor="t@x.com", open_ticket_on_diff=True,
    )
    parse_errs = [e for e in r.errors if "Linha 3" in e]
    assert parse_errs, r.errors
    # 1) o ticket traz o erro (com a linha), não só a contagem
    md = captured["ticket_summary_md"]
    assert "Erros de parse:" in md
    assert "Linha 3" in md
    # 2) o log gravado (lido pelo "Ver erros" do Histórico) traz o mesmo erro
    assert any("Linha 3" in e for e in split_error_summary(captured["error_summary"]))
