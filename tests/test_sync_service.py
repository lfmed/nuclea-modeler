"""Tests para funções puras de sync/service.py.

Foca nas funções que não tocam SQL Warehouse:
- _classify_status: decide SUCCESS / PARTIAL / FAILED baseado em counts
- _trim: trunca strings com elipses
- _build_table_comment / _build_column_comment: compõe comment string
- _require_ident: valida identifier SQL

Sem mock de Sql — só lógica pura.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from nuclea_modeler.backend.sync.service import (
    _build_column_comment,
    _build_table_comment,
    _classify_status,
    _esc,
    _require_ident,
    _trim,
)


# ─── _classify_status ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "total,failed,synced,expected",
    [
        # No work to do → SUCCESS
        (0, 0, 0, "SUCCESS"),
        # All succeeded
        (5, 0, 5, "SUCCESS"),
        (1, 0, 1, "SUCCESS"),
        # Failed but some succeeded → PARTIAL
        (5, 2, 3, "PARTIAL"),
        (10, 1, 9, "PARTIAL"),
        # All failed → FAILED
        (3, 3, 0, "FAILED"),
        (5, 5, 0, "FAILED"),
        # Some failed, some synced (mas pode haver SKIPPED também)
        (10, 3, 5, "PARTIAL"),  # 2 skipped (não failed nem synced)
    ],
)
def test_classify_status(total, failed, synced, expected):
    assert _classify_status(total, failed, synced) == expected


# ─── _trim ──────────────────────────────────────────────────────────────────


def test_trim_returns_none_for_none():
    assert _trim(None) is None


def test_trim_keeps_short_strings_intact():
    assert _trim("short", limit=100) == "short"
    assert _trim("exactly10!", limit=10) == "exactly10!"


def test_trim_truncates_long_strings_with_ellipsis():
    long = "a" * 1500
    out = _trim(long, limit=1000)
    assert out is not None
    assert len(out) == 1000
    assert out.endswith("...")


def test_trim_converts_non_string_to_string():
    """Aceita qualquer tipo via str()."""
    assert _trim(12345) == "12345"
    assert _trim([1, 2, 3]) == "[1, 2, 3]"


# ─── _build_table_comment ───────────────────────────────────────────────────


def test_table_comment_combines_logical_and_description():
    """Logical name + body separados por ': '"""
    out = _build_table_comment(
        logical_name="Cliente",
        description_md="Cadastro principal de clientes.",
        native_comment=None,
    )
    assert out == "Cliente: Cadastro principal de clientes."


def test_table_comment_falls_back_to_native():
    """Sem description_md, usa native_comment."""
    out = _build_table_comment(
        logical_name="Cliente",
        description_md=None,
        native_comment="legacy comment from source DB",
    )
    assert out == "Cliente: legacy comment from source DB"


def test_table_comment_just_logical_when_no_body():
    """Logical name sozinho quando não há body."""
    out = _build_table_comment(
        logical_name="Cliente", description_md=None, native_comment=None
    )
    assert out == "Cliente"


def test_table_comment_just_body_when_no_logical():
    """Body sozinho quando não há logical."""
    out = _build_table_comment(
        logical_name=None,
        description_md="A description.",
        native_comment=None,
    )
    assert out == "A description."


def test_table_comment_empty_when_nothing():
    """Vazio se tudo None."""
    assert _build_table_comment(None, None, None) == ""


def test_table_comment_description_wins_over_native():
    """description_md tem precedência sobre native_comment."""
    out = _build_table_comment(
        logical_name="x",
        description_md="DESCRIPTION",
        native_comment="NATIVE",
    )
    assert "DESCRIPTION" in out
    assert "NATIVE" not in out


# ─── _build_column_comment ──────────────────────────────────────────────────


def test_column_comment_same_logic_as_table():
    """Mesma regra que table comment."""
    assert (
        _build_column_comment("CPF", "Documento", None)
        == "CPF: Documento"
    )
    assert _build_column_comment(None, None, None) == ""


# ─── _require_ident ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "table",
        "my_table",
        "Table123",
        "_underscore_start",
        "a",
        "a" * 128,  # max length
    ],
)
def test_require_ident_accepts_valid(value):
    """Identifiers válidos passam direto."""
    assert _require_ident(value, "field") == value


@pytest.mark.parametrize(
    "value",
    [
        "",                  # empty
        "1starts_with_digit",  # SQL não permite
        "has space",
        "has-dash",
        "has;semicolon",
        "has'quote",
        "DROP TABLE x",      # injection attempt
        "a" * 129,           # excede max
    ],
)
def test_require_ident_rejects_invalid(value):
    """Identifiers inválidos raise HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        _require_ident(value, "field")
    assert exc_info.value.status_code == 400
    assert "invalid field" in exc_info.value.detail


# ─── _esc ───────────────────────────────────────────────────────────────────


def test_esc_doubles_single_quotes():
    """Escape clássico: ' → ''."""
    assert _esc("O'Hara") == "O''Hara"


def test_esc_passes_through_safe_strings():
    assert _esc("no quotes") == "no quotes"
    assert _esc("") == ""


def test_esc_handles_none():
    assert _esc(None) == ""
