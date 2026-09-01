"""Resolução de dialeto DDL → nome do sqlglot (round 5, pt 12).

`_resolve_sqlglot_dialect` centraliza a tradução do dialeto informado (por QUALQUER
tela) para o nome que o sqlglot entende. O bug corrigido: o wizard de novo sistema
mandava "POSTGRESQL"/"MSSQL"/"ORACLE"/"DATABRICKS", que não batiam com o mapa
canônico → o sqlglot recebia um dialeto desconhecido, o parse devolvia 0 objetos e
o import terminava "FAILED". Estes testes fixam:

  1. Os nomes CANÔNICOS mapeiam para o dialeto certo do sqlglot.
  2. Os ALIASES comuns (que o wizard enviava) resolvem para o mesmo destino.
  3. ANSI/vazio/desconhecido caem em None (modo auto do sqlglot) — nunca estouram.

Assim uma regressão no vocabulário de dialetos volta a quebrar o CI, não o cliente.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.extractions.service import _resolve_sqlglot_dialect


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("ANSI", None),
        ("POSTGRES", "postgres"),
        ("TSQL", "tsql"),
        ("PLSQL", "oracle"),
        ("MYSQL", "mysql"),
        ("SPARKSQL", "spark"),
        ("DB2", "db2"),
    ],
)
def test_canonical_names(canonical, expected):
    assert _resolve_sqlglot_dialect(canonical) == expected


@pytest.mark.parametrize(
    "alias,expected",
    [
        # Exatamente os valores que o wizard enviava (a causa do pt 12):
        ("POSTGRESQL", "postgres"),
        ("MSSQL", "tsql"),
        ("ORACLE", "oracle"),
        ("DATABRICKS", "spark"),
        # Outras variações que humanos costumam digitar:
        ("SQL Server", "tsql"),
        ("SQLSERVER", "tsql"),
        ("PG", "postgres"),
        ("SPARK", "spark"),
        ("DELTA", "spark"),
        ("DB2 for i", "db2"),
    ],
)
def test_common_aliases(alias, expected):
    assert _resolve_sqlglot_dialect(alias) == expected


def test_case_and_whitespace_insensitive():
    assert _resolve_sqlglot_dialect("  postgres  ") == "postgres"
    assert _resolve_sqlglot_dialect("PostGreSQL") == "postgres"


@pytest.mark.parametrize("value", [None, "", "   ", "ANSI", "XYZ", "não-existe"])
def test_empty_or_unknown_falls_back_to_auto(value):
    # None = sqlglot em modo automático; nunca deve estourar "Unknown dialect".
    assert _resolve_sqlglot_dialect(value) is None


def test_already_valid_sqlglot_dialect_passes_through():
    # Nome fora do mapa canônico mas reconhecido pelo sqlglot → passa direto.
    assert _resolve_sqlglot_dialect("snowflake") == "snowflake"
    assert _resolve_sqlglot_dialect("sqlite") == "sqlite"
