"""Tests das visões globais de atributos/índices + coluna de flags.

Documentação viva do comportamento esperado das rotas paginadas de listagem
(ponto 5 do plano feedback-cliente-jul2026). Sem tocar no Delta: monkeypatcham
`get_settings`, `delta.param` e as funções de fetch para capturar os SQLs
gerados e devolver rows sintéticas.

Cobrem:
- helpers de `listings.py` (escape_like, _named_in_params, flags_by_*);
- clamp de page/page_size;
- whitelist de ordenação (sort_by inválido cai no default; sem injeção);
- montagem dos filtros no WHERE (sistema, schema, PK/UNIQUE, flag, busca);
- coerência do COUNT com os filtros;
- mapeamento de rows → models (incluindo desserialização de columns_json).
"""
from __future__ import annotations

from datetime import datetime

from nuclea_modeler.backend.entities import global_listings_router as glr
from nuclea_modeler.backend.entities import listings as lst
from nuclea_modeler.backend.entities import router as ent_router


_NOW = datetime(2026, 7, 1, 12, 0)


class _S:
    """Settings fake — fq_table só prefixa c.s. para inspeção legível."""

    def fq_table(self, t: str) -> str:
        return f"c.s.{t}"


def _patch_common(monkeypatch, module):
    monkeypatch.setattr(module, "get_settings", lambda: _S())
    monkeypatch.setattr(module.delta, "param", lambda k, v, *a, **kw: (k, v))


# ─── listings.py helpers ─────────────────────────────────────────────────────


def test_escape_like_escapes_wildcards():
    assert lst.escape_like("100%") == "100\\%"
    assert lst.escape_like("a_b") == "a\\_b"
    # backslash é escapado ANTES dos wildcards
    assert lst.escape_like("a\\b") == "a\\\\b"
    assert lst.escape_like("cliente") == "cliente"


def test_named_in_params_empty():
    placeholders, params = lst._named_in_params("e", [])
    assert placeholders == "(NULL)"
    assert params == []


def test_named_in_params_builds_placeholders(monkeypatch):
    monkeypatch.setattr(lst.delta, "param", lambda k, v, *a, **kw: (k, v))
    placeholders, params = lst._named_in_params("e", ["a", "b"])
    assert placeholders == "(:e0, :e1)"
    assert params == [("e0", "a"), ("e1", "b")]


def test_flags_by_entity_groups_by_id(monkeypatch):
    _patch_common(monkeypatch, lst)
    rows = [
        ["ent-1", "flag-1", "lgpd", "Dados Pessoais", "#f00", "LGPD"],
        ["ent-1", "flag-2", "master", "Dado Master", "#0f0", "USE"],
        ["ent-2", "flag-1", "lgpd", "Dados Pessoais", "#f00", "LGPD"],
    ]
    monkeypatch.setattr(lst.delta, "fetch_all_params", lambda sql, q, p: rows)
    out = lst.flags_by_entity(object(), ["ent-1", "ent-2"])
    assert set(out.keys()) == {"ent-1", "ent-2"}
    assert len(out["ent-1"]) == 2
    assert out["ent-1"][0].display_name == "Dados Pessoais"
    assert out["ent-2"][0].flag_key == "lgpd"


def test_flags_by_entity_empty_short_circuits(monkeypatch):
    # Sem ids → não consulta o banco.
    called = {"n": 0}
    monkeypatch.setattr(
        lst.delta, "fetch_all_params",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [],
    )
    assert lst.flags_by_entity(object(), []) == {}
    assert called["n"] == 0


# ─── list_entities_paginated: whitelist de sort + filtros ────────────────────


# Params que no endpoint têm default via fastapi.Query(...). Ao chamar a função
# diretamente (fora do FastAPI) o default é um FieldInfo, não o valor — então
# passamos explicitamente aqui. Ver nota no topo dos helpers.
_ENT_QUERY_DEFAULTS = {"q": None, "flag_id": None, "sort_by": "updated_at", "sort_dir": "desc"}


def _run_entities(monkeypatch, **kwargs):
    _patch_common(monkeypatch, ent_router)
    captured: dict = {"all": [], "one": []}

    def fake_one(sql, q, p):
        captured["one"].append(q)
        return [0]

    def fake_all(sql, q, p):
        captured["all"].append(q)
        return []  # página vazia + agregação de flags vazia

    monkeypatch.setattr(ent_router.delta, "fetch_one_params", fake_one)
    monkeypatch.setattr(ent_router.delta, "fetch_all_params", fake_all)
    # sem sessão OPEN → sem overlay
    monkeypatch.setattr(ent_router, "_get_session_diff", lambda *a, **k: (None, None, "x"))
    monkeypatch.setattr(ent_router, "flags_by_entity", lambda sql, ids: {})
    call = {**_ENT_QUERY_DEFAULTS, **kwargs}
    res = ent_router.list_entities_paginated(object(), object(), **call)
    return res, captured


def test_entities_sort_whitelist_defaults(monkeypatch):
    # sort_by malicioso não deve aparecer no ORDER BY; cai no default.
    _res, cap = _run_entities(monkeypatch, sort_by="; DROP TABLE entities;--", sort_dir="asc")
    page_sql = cap["all"][0]
    assert "DROP TABLE" not in page_sql
    assert "ORDER BY e.updated_at ASC" in page_sql


def test_entities_sort_valid_column(monkeypatch):
    _res, cap = _run_entities(monkeypatch, sort_by="technical_name", sort_dir="desc")
    assert "ORDER BY e.technical_name DESC" in cap["all"][0]


def test_entities_page_size_clamped(monkeypatch):
    res, _cap = _run_entities(monkeypatch, page=0, page_size=9999)
    assert res.page == 1  # page >= 1
    assert res.page_size == 200  # clamp máximo


def test_entities_flag_filter_uses_exists(monkeypatch):
    _res, cap = _run_entities(monkeypatch, flag_id="flag-1")
    # EXISTS aplicado no COUNT e na página (coerência do total).
    assert any("EXISTS" in q and "entity_flags" in q for q in cap["one"])
    assert "EXISTS" in cap["all"][0]


def test_entities_search_filter(monkeypatch):
    _res, cap = _run_entities(monkeypatch, q="cli")
    assert "LIKE :q" in cap["all"][0]


# ─── list_attributes_paginated ───────────────────────────────────────────────


_ATTR_QUERY_DEFAULTS = {"q": None, "flag_id": None, "sort_by": "technical_name", "sort_dir": "asc"}


def _run_attrs(monkeypatch, page_rows=None, **kwargs):
    _patch_common(monkeypatch, glr)
    captured: dict = {"all": [], "one": []}

    def fake_one(sql, q, p):
        captured["one"].append(q)
        return [len(page_rows or [])]

    def fake_all(sql, q, p):
        captured["all"].append(q)
        return page_rows or []

    monkeypatch.setattr(glr.delta, "fetch_one_params", fake_one)
    monkeypatch.setattr(glr.delta, "fetch_all_params", fake_all)
    monkeypatch.setattr(glr, "flags_by_attribute", lambda sql, ids: {})
    call = {**_ATTR_QUERY_DEFAULTS, **kwargs}
    res = glr.list_attributes_paginated(object(), **call)
    return res, captured


def test_attributes_maps_rows(monkeypatch):
    # r[14]=description_md, r[15]=business_rule adicionados ao SELECT (v1.0030).
    row = [
        "attr-1", "ent-1", "PEDIDO", "Pedido", "dbo", "sys-1", "Vendas",
        "id_cliente", "ID do Cliente", 3, "BIGINT", False, True, _NOW,
        "FK para cliente", "Sempre preenchido em pedidos ativos",
    ]
    res, _cap = _run_attrs(monkeypatch, page_rows=[row])
    assert res.total == 1
    item = res.items[0]
    assert item.attribute_id == "attr-1"
    assert item.entity_technical_name == "PEDIDO"
    assert item.system_name == "Vendas"
    assert item.is_primary_key is True
    assert item.is_nullable is False
    assert item.ordinal_position == 3
    assert item.description_md == "FK para cliente"
    assert item.business_rule == "Sempre preenchido em pedidos ativos"


def test_attributes_pk_filter_and_archived_guard(monkeypatch):
    _res, cap = _run_attrs(monkeypatch, is_primary_key=True)
    page_sql = cap["all"][0]
    assert "a.is_primary_key = :is_pk" in page_sql
    # sempre esconde sistemas arquivados
    assert "archived_at IS NOT NULL" in page_sql


def test_attributes_flag_filter_exists(monkeypatch):
    _res, cap = _run_attrs(monkeypatch, flag_id="flag-9")
    assert "EXISTS" in cap["all"][0]
    assert "attribute_flags" in cap["all"][0]


def test_attributes_sort_whitelist(monkeypatch):
    _res, cap = _run_attrs(monkeypatch, sort_by="evil; --", sort_dir="asc")
    assert "evil" not in cap["all"][0]
    assert "ORDER BY a.technical_name ASC" in cap["all"][0]


# ─── list_indexes_paginated ──────────────────────────────────────────────────


_IDX_QUERY_DEFAULTS = {"q": None, "sort_by": "index_name", "sort_dir": "asc"}


def _run_indexes(monkeypatch, page_rows=None, **kwargs):
    _patch_common(monkeypatch, glr)
    captured: dict = {"all": [], "one": []}

    def fake_one(sql, q, p):
        captured["one"].append(q)
        return [len(page_rows or [])]

    def fake_all(sql, q, p):
        captured["all"].append(q)
        return page_rows or []

    monkeypatch.setattr(glr.delta, "fetch_one_params", fake_one)
    monkeypatch.setattr(glr.delta, "fetch_all_params", fake_all)
    call = {**_IDX_QUERY_DEFAULTS, **kwargs}
    res = glr.list_indexes_paginated(object(), **call)
    return res, captured


def test_indexes_maps_rows_and_columns(monkeypatch):
    cols_json = '[{"name":"col_a","direction":"ASC"},{"name":"col_b","direction":"DESC"}]'
    # r[12]=description_md adicionado ao SELECT (v1.0030).
    row = [
        "idx-1", "ent-1", "PEDIDO", "dbo", "sys-1", "Vendas",
        "ix_pedido_cliente", "BTREE", cols_json, True, "MANUAL", _NOW,
        "Índice de busca por cliente",
    ]
    res, _cap = _run_indexes(monkeypatch, page_rows=[row])
    assert res.total == 1
    item = res.items[0]
    assert item.index_name == "ix_pedido_cliente"
    assert item.is_unique is True
    assert [c.name for c in item.columns] == ["col_a", "col_b"]
    assert item.columns[1].direction == "DESC"
    assert item.description_md == "Índice de busca por cliente"


def test_indexes_type_and_unique_filters(monkeypatch):
    _res, cap = _run_indexes(monkeypatch, index_type="GIN", is_unique=True)
    page_sql = cap["all"][0]
    assert "ix.index_type = :index_type" in page_sql
    assert "ix.is_unique = :is_unique" in page_sql


def test_indexes_sort_whitelist(monkeypatch):
    _res, cap = _run_indexes(monkeypatch, sort_by="bad_col; DELETE", sort_dir="desc")
    assert "bad_col" not in cap["all"][0]
    assert "ORDER BY ix.index_name DESC" in cap["all"][0]


def test_indexes_has_more_pagination(monkeypatch):
    # total=1 e 1 item na página 1 → has_more False
    cols_json = "[]"
    # r[12]=description_md adicionado ao SELECT (v1.0030).
    row = ["idx-1", "ent-1", "E", "dbo", "s", "S", "ix", "BTREE", cols_json, False, "MANUAL", _NOW, None]

    _patch_common(monkeypatch, glr)
    monkeypatch.setattr(glr.delta, "fetch_one_params", lambda sql, q, p: [1])
    monkeypatch.setattr(glr.delta, "fetch_all_params", lambda sql, q, p: [row])
    res = glr.list_indexes_paginated(
        object(), page=1, page_size=50, **_IDX_QUERY_DEFAULTS,
    )
    assert res.has_more is False
    assert res.total == 1
