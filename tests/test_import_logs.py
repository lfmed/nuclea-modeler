"""Logs de falha de import: classificação problemas vs avisos + formatação.

Funções puras de extractions/service usadas para montar o log de import e
decidir o status PARTIAL. Não dependem de sqlglot nem de SQL Warehouse.
"""
from __future__ import annotations

from nuclea_modeler.backend.extractions.service import (
    format_import_log,
    summarize_import_messages,
)


def test_summarize_splits_problems_and_infos():
    msgs = [
        "entity sem nome (EntityId=10) — ignorada",
        "2 relacionamento(s) extraído(s) e incluído(s) no diff",
        "attribute sem nome (EntityId=11, AttributeId=3) — ignorado",
        "DatatypeIds desconhecidos (revisar tipos no DER): 999",
    ]
    out = summarize_import_messages(msgs)
    # informativo (relacionamentos) vai para infos
    assert out["infos"] == ["2 relacionamento(s) extraído(s) e incluído(s) no diff"]
    # perdas de dados vão para problems
    assert len(out["problems"]) == 3
    assert any("entity sem nome" in p for p in out["problems"])
    assert any("attribute sem nome" in p for p in out["problems"])
    assert any("desconhecidos" in p for p in out["problems"])


def test_summarize_empty_and_none():
    assert summarize_import_messages([]) == {"problems": [], "infos": []}
    assert summarize_import_messages(None) == {"problems": [], "infos": []}


def test_format_import_log_sections():
    log = format_import_log(["erro X", "erro Y"], ["aviso Z"])
    assert "Problemas (2)" in log
    assert "Avisos (1)" in log
    assert "- erro X" in log
    assert "- aviso Z" in log


def test_format_import_log_empty():
    assert format_import_log([], []) == ""


def test_format_import_log_only_problems():
    log = format_import_log(["falha"], [])
    assert "Problemas (1)" in log
    assert "Avisos" not in log
