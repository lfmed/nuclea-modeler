"""Tests para glossary/service.py — check_type_compat heuristic.

Função pura sem deps. Heurística: dado um conceptual_type (IDENTIFIER,
MONETARY, etc.) e um native_data_type (varchar(50), decimal(18,2), etc.),
retorna se são considerados compatíveis. Default-permissivo: na dúvida,
retorna True para evitar false alarms ao mapear glossário → atributos.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.glossary.service import check_type_compat


# ─── Cases compatíveis ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "conceptual,native",
    [
        # IDENTIFIER
        ("IDENTIFIER", "VARCHAR(50)"),
        ("IDENTIFIER", "BIGINT"),
        ("IDENTIFIER", "uuid"),
        ("IDENTIFIER", "uniqueidentifier"),
        ("IDENTIFIER", "INT"),
        # MONETARY
        ("MONETARY", "DECIMAL(18,2)"),
        ("MONETARY", "NUMERIC(20,4)"),
        ("MONETARY", "MONEY"),
        ("MONETARY", "DOUBLE PRECISION"),
        ("MONETARY", "FLOAT"),
        # DATE
        ("DATE", "DATE"),
        ("DATE", "TIMESTAMP"),
        ("DATE", "DATETIME2"),
        ("DATE", "TIME"),
        # BOOLEAN
        ("BOOLEAN", "BOOLEAN"),
        ("BOOLEAN", "BIT"),
        ("BOOLEAN", "TINYINT(1)"),
        # TEXT
        ("TEXT", "VARCHAR(MAX)"),
        ("TEXT", "TEXT"),
        ("TEXT", "STRING"),
        ("TEXT", "CLOB"),
        # NUMERIC
        ("NUMERIC", "INT"),
        ("NUMERIC", "BIGINT"),
        ("NUMERIC", "DECIMAL(10,2)"),
        ("NUMERIC", "DOUBLE"),
        # CATEGORICAL
        ("CATEGORICAL", "VARCHAR(20)"),
        ("CATEGORICAL", "ENUM"),
        ("CATEGORICAL", "STRING"),
    ],
)
def test_compatible_combinations_return_true(conceptual, native):
    assert check_type_compat(conceptual, native) is True


# ─── Cases incompatíveis ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "conceptual,native",
    [
        ("MONETARY", "VARCHAR(50)"),       # money em string é red flag
        ("DATE", "INT"),                    # data como int é red flag
        ("DATE", "VARCHAR(10)"),            # data como string idem
        ("BOOLEAN", "VARCHAR(5)"),          # bool como string idem
        ("IDENTIFIER", "TIMESTAMP"),        # ID como timestamp não bate
        ("MONETARY", "BOOLEAN"),
    ],
)
def test_incompatible_combinations_return_false(conceptual, native):
    assert check_type_compat(conceptual, native) is False


# ─── Default-permissive cases ───────────────────────────────────────────────


def test_returns_true_when_conceptual_type_missing():
    """Sem conceptual_type não dá pra avaliar — não soa alarme."""
    assert check_type_compat(None, "VARCHAR(50)") is True
    assert check_type_compat("", "VARCHAR(50)") is True


def test_returns_true_when_native_type_missing():
    """Sem native_data_type idem."""
    assert check_type_compat("IDENTIFIER", None) is True
    assert check_type_compat("IDENTIFIER", "") is True


def test_other_is_always_compatible():
    """OTHER é catch-all — qualquer native type passa."""
    assert check_type_compat("OTHER", "VARCHAR(50)") is True
    assert check_type_compat("OTHER", "BLOB") is True
    assert check_type_compat("OTHER", "anything_else") is True


def test_unknown_conceptual_type_returns_true():
    """Conceptual type que não está no mapa (typo, futuro) → permissivo."""
    assert check_type_compat("UNKNOWN_FUTURE_TYPE", "VARCHAR(50)") is True


def test_case_insensitive_conceptual():
    """conceptual_type pode vir em minúsculo, misturado, etc."""
    assert check_type_compat("identifier", "BIGINT") is True
    assert check_type_compat("Monetary", "DECIMAL(10,2)") is True


def test_case_insensitive_native():
    """native_data_type também não pode ser case-sensitive."""
    assert check_type_compat("IDENTIFIER", "bigint") is True
    assert check_type_compat("IDENTIFIER", "BIGINT") is True
    assert check_type_compat("IDENTIFIER", "BigInt") is True


def test_partial_match_works():
    """Heurística é partial match — DECIMAL(18,4) deve casar com 'decimal'."""
    assert check_type_compat("MONETARY", "DECIMAL(18,4)") is True
    assert check_type_compat("DATE", "TIMESTAMPTZ") is True
