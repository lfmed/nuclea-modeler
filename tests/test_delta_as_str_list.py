"""Regressão do helper `delta.as_str_list` (v1.0042).

Contexto do bug (mesma família do `as_bool`): a Databricks SQL Statement Execution
API devolve TODAS as células do `data_array` como STRING — e uma coluna
`ARRAY<STRING>` volta como uma **string JSON**, ex.: `'["attr-1","attr-2"]'`
(ou `'[]'`). O código lia `list(r[n])` direto; como `list('["attr-1"]')` itera a
STRING, o resultado era uma lista de CARACTERES (`['[', '"', 'a', ...]`),
corrompendo silenciosamente o array. Sintoma real: o export de DDL não emitia
NENHUMA foreign key (as colunas-FK viravam chars e não casavam com nenhum
`attribute_id`), e a API de relationships devolvia arrays inúteis.

`as_str_list` normaliza corretamente. O assert central é
`as_str_list('["a","b"]') == ["a", "b"]`, que o `list()` cru violava.
"""
from __future__ import annotations

from nuclea_modeler.backend.core import delta


def test_as_str_list_json_array_string():
    # O CORAÇÃO do bug: string JSON de array → lista dos elementos (não de chars).
    assert delta.as_str_list('["a","b"]') == ["a", "b"]
    assert delta.as_str_list('["attr-rh-dep-3"]') == ["attr-rh-dep-3"]


def test_as_str_list_empty_forms():
    assert delta.as_str_list("[]") == []
    assert delta.as_str_list("") == []
    assert delta.as_str_list("   ") == []
    assert delta.as_str_list(None) == []


def test_as_str_list_native_list_passthrough():
    # Defensivo: se algum dia vier lista de verdade, devolve os itens como str.
    assert delta.as_str_list(["a", "b"]) == ["a", "b"]
    assert delta.as_str_list(("x", "y")) == ["x", "y"]
    assert delta.as_str_list([1, 2]) == ["1", "2"]


def test_as_str_list_non_json_string_is_single_element():
    # String que não é array JSON → único elemento (conservador, não quebra).
    assert delta.as_str_list("attr-solo") == ["attr-solo"]


def test_list_builtin_would_have_been_wrong():
    """Documenta POR QUE o helper existe: list('["a"]') vira lista de chars."""
    assert list('["a"]') == ["[", '"', "a", '"', "]"]  # comportamento errado (o bug)
    assert delta.as_str_list('["a"]') == ["a"]          # o helper corrige
