"""Regressão do helper `delta.as_bool` (v1.0026).

Contexto do bug: a Databricks SQL Statement Execution API devolve TODAS as
células do `data_array` como STRING — inclusive colunas BOOLEAN, que voltam
como `"true"`/`"false"`. O código lia `bool(r[n])` direto; como em Python
`bool("false")` é `True` (qualquer string não-vazia é truthy), TODA coluna
booleana virava `True`. Sintoma reportado: no DER, TODAS as colunas apareciam
como PK (`is_primary_key` = `"false"` → `True`) — só após a aprovação, quando o
dado passa a vir da query SQL (string) e não do diff (JSON com bool real).

`as_bool` normaliza corretamente. Este teste fixa o comportamento; o assert
central é `as_bool("false") is False`, que o `bool()` cru violava.
"""
from __future__ import annotations

from nuclea_modeler.backend.core import delta


def test_as_bool_string_false_is_false():
    # O CORAÇÃO do bug: "false" (string vinda do SQL) deve virar False.
    assert delta.as_bool("false") is False
    assert delta.as_bool("False") is False
    assert delta.as_bool("FALSE") is False
    assert delta.as_bool("f") is False
    assert delta.as_bool("0") is False
    assert delta.as_bool("no") is False


def test_as_bool_string_true_is_true():
    assert delta.as_bool("true") is True
    assert delta.as_bool("True") is True
    assert delta.as_bool("TRUE") is True
    assert delta.as_bool("t") is True
    assert delta.as_bool("1") is True
    assert delta.as_bool("yes") is True


def test_as_bool_native_bool_passthrough():
    assert delta.as_bool(True) is True
    assert delta.as_bool(False) is False


def test_as_bool_none_and_numbers():
    assert delta.as_bool(None) is False
    assert delta.as_bool(0) is False
    assert delta.as_bool(1) is True


def test_as_bool_empty_and_garbage_strings():
    # String vazia → False; lixo desconhecido → False (conservador).
    assert delta.as_bool("") is False
    assert delta.as_bool("  ") is False
    assert delta.as_bool("qualquer") is False


def test_bool_builtin_would_have_been_wrong():
    """Documenta POR QUE o helper existe: bool('false') é True (o bug)."""
    assert bool("false") is True  # comportamento errado que causava o bug
    assert delta.as_bool("false") is False  # o helper corrige
