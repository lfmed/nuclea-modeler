"""Regressão do mapeamento linha→modelo em list_relationships (v1.0025).

Contexto: quando o campo `relationship_name` foi inserido em `_REL_COLS`
(migration 019), os índices posicionais de `list_relationships` NÃO foram
atualizados junto — `system_name`/`updated_at` passaram a ler colunas erradas
(`created_by`/`updated_by`), e o Pydantic estourava
`datetime_from_date_parsing` ao receber uma string onde esperava `datetime`.
Resultado: `GET /api/relationships` devolvia 500 e a tela de Relacionamentos
mostrava "Erro ao carregar relacionamentos".

Este teste monta uma linha no MESMO formato do SELECT de `_select_rel_query`
(as 18 colunas de `_REL_COLS` + os 5 joins: system_name, src schema/tech,
tgt schema/tech) e garante que o mapeamento posicional está correto — em
especial que `updated_at` recebe um `datetime` e `system_name`/labels as
strings certas. Sem este teste o CI não pegava o desalinhamento (era só
índice posicional, não erro de tipagem estática).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from nuclea_modeler.backend.relationships import router as rrouter
from nuclea_modeler.backend.relationships.router import _REL_COLS


def _rel_row() -> list:
    """Linha na ordem exata do SELECT: _REL_COLS (18) + 5 joins = 23 colunas."""
    created = datetime(2026, 1, 2, 3, 4, 5)
    updated = datetime(2026, 6, 7, 8, 9, 10)
    row = [
        "rel-1",                 # 0 relationship_id
        "sys-1",                 # 1 system_id
        "ent-src",               # 2 source_entity_id
        "ent-tgt",               # 3 target_entity_id
        ["a1"],                  # 4 source_attr_ids
        ["b1"],                  # 5 target_attr_ids
        "1:N",                   # 6 rel_type
        "OPTIONAL",              # 7 source_cardinality
        "MANDATORY",             # 8 target_cardinality
        "descr",                 # 9 description
        "DDL",                   # 10 origin
        None,                    # 11 fk_update_rule
        None,                    # 12 fk_delete_rule
        "Pedido → Cliente",      # 13 relationship_name
        created,                 # 14 created_at
        "creator@x.com",         # 15 created_by
        updated,                 # 16 updated_at
        "updater@x.com",         # 17 updated_by
        "Sistema X",             # 18 system_name (join)
        "public",                # 19 src_schema (join)
        "pedido",                # 20 src_tech (join)
        "public",                # 21 tgt_schema (join)
        "cliente",               # 22 tgt_tech (join)
    ]
    # Sanidade: _REL_COLS deve ter 18 entradas; se alguém adicionar/remover uma
    # coluna sem atualizar os índices, este assert falha primeiro (documenta o
    # contrato posicional).
    assert len(_REL_COLS) == 18
    return row


def test_list_relationships_maps_row_positions(monkeypatch):
    """A row do SELECT vira RelationshipListOut com os campos nos lugares certos."""
    fake_settings = MagicMock()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(rrouter, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(rrouter.delta, "fetch_all_params", lambda *a, **k: [_rel_row()])
    monkeypatch.setattr(rrouter.delta, "param", lambda k, v: {k: v})

    out = rrouter.list_relationships(system_id="sys-1", sql=MagicMock())

    assert len(out) == 1
    item = out[0]
    assert item.relationship_id == "rel-1"
    assert item.system_id == "sys-1"
    # O bug lia r[17] (updated_by) aqui → "Sistema X" só aparece com índice certo.
    assert item.system_name == "Sistema X"
    assert item.source_entity_label == "public.pedido"
    assert item.target_entity_label == "public.cliente"
    assert item.relationship_name == "Pedido → Cliente"
    # O ponto do crash: updated_at precisa ser o datetime (r[16]), não uma string.
    assert isinstance(item.updated_at, datetime)
    assert item.updated_at == datetime(2026, 6, 7, 8, 9, 10)
    assert item.rel_type == "1:N"
    assert item.description == "descr"


def test_rel_row_to_out_maps_row_positions(monkeypatch):
    """_rel_row_to_out (usado no create/get) também mapeia timestamps corretos."""
    out = rrouter._rel_row_to_out(_rel_row())
    assert out.relationship_id == "rel-1"
    assert out.relationship_name == "Pedido → Cliente"
    assert isinstance(out.created_at, datetime)
    assert isinstance(out.updated_at, datetime)
    assert out.created_at == datetime(2026, 1, 2, 3, 4, 5)
    assert out.updated_at == datetime(2026, 6, 7, 8, 9, 10)
    assert out.system_name == "Sistema X"
    assert out.source_entity_label == "public.pedido"
    assert out.target_entity_label == "public.cliente"
