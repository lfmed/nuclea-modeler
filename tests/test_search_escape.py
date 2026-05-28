"""Tests para search/router._escape_like — escape de wildcards SQL LIKE.

Cobre:
- `%` (any) → `\\%`
- `_` (one char) → `\\_`
- `\\` (backslash) → `\\\\` (escape do escape)
- Strings normais passam intactas
- Ordem dos replaces preserva consistência (backslash primeiro!)
"""
from __future__ import annotations

from nuclea_modeler.backend.search.router import _escape_like


def test_normal_string_unchanged():
    assert _escape_like("cliente") == "cliente"
    assert _escape_like("CPF do Titular") == "CPF do Titular"
    assert _escape_like("") == ""


def test_percent_wildcard_escaped():
    """% é o wildcard "qualquer sequência" — precisa escape para LIKE literal."""
    assert _escape_like("100%") == "100\\%"
    assert _escape_like("%abc%") == "\\%abc\\%"


def test_underscore_wildcard_escaped():
    """_ é o wildcard "um caractere" — precisa escape também."""
    assert _escape_like("a_b") == "a\\_b"
    assert _escape_like("snake_case") == "snake\\_case"


def test_backslash_escaped_first():
    """\\ é o caractere de escape — deve ser duplicado ANTES dos outros
    para não interferir. Sequência correta: \\ → \\\\ , depois % e _."""
    # Input com backslash literal
    assert _escape_like("a\\b") == "a\\\\b"


def test_combined_chars():
    """% + _ + \\ na mesma string."""
    # Antes: "a\\b_c%d"
    # Depois: "a\\\\b\\_c\\%d"
    assert _escape_like("a\\b_c%d") == "a\\\\b\\_c\\%d"


def test_only_wildcards():
    assert _escape_like("%_%") == "\\%\\_\\%"


def test_single_quotes_NOT_escaped():
    """Single quotes vão por bind parameter (delta.param), não por escape.
    _escape_like NÃO toca em apóstrofos — eles continuam intactos."""
    assert _escape_like("O'Hara") == "O'Hara"
    assert _escape_like("test'") == "test'"


def test_repeated_application_idempotency_check():
    """ATENÇÃO: NÃO é idempotente! Aplicar 2x escape o escape.
    Verificamos isso explicitamente para que o caller saiba não chamar 2x."""
    once = _escape_like("a%b")
    twice = _escape_like(once)
    # \\% vira \\\\% (duplicou)
    assert once == "a\\%b"
    assert twice == "a\\\\\\%b"
    # Ou seja: chamar 2x corrompe — caller cuida disso
