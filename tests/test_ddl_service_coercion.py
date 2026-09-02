"""Regressão: coerção de tipos ao LER resultados de query no export de DDL (v1.0042).

Contexto: a Databricks SQL Statement Execution API devolve TODAS as células como
string — BOOLEAN como `"true"`/`"false"` e `ARRAY<STRING>` como string JSON
`'["x"]'`. A camada de serviço do DDL (`ddl/service.py`) lia esses valores com
`bool()` cru e `list()` cru, o que causava dois bugs no app DEPLOYADO:

  - `bool("false")` → True  ⇒ TODA coluna virava PRIMARY KEY / NOT NULL no DDL.
  - `list('["attr-1"]')` → ['[','"','a',...]  ⇒ colunas-FK não casavam com
    nenhum attribute_id ⇒ o export NÃO emitia NENHUMA foreign key (round 5, pt 11).

Por que o CI antigo não pegou: `test_ddl_generators.py` exercita os generators com
listas Python JÁ PRONTAS — nunca o round-trip string→parse da camada de serviço.
Estes testes fecham a lacuna: alimentam linhas no formato EXATO que a API devolve
(tudo string) e provam que (a) só o PK real vira PK e (b) a FK volta a ser emitida.
"""
from __future__ import annotations

from nuclea_modeler.backend.core import delta
from nuclea_modeler.backend.ddl import service
from nuclea_modeler.backend.ddl.models import DDLExportRequest


# Ordem de _ATTR_COLS: attribute_id, entity_id, technical_name, logical_name,
# ordinal_position, native_data_type, is_nullable, default_value,
# is_primary_key, description_md, native_comment
def _attr_row(attr_id, name, pos, dtype, is_nullable, is_pk):
    return [attr_id, "e1", name, name, pos, dtype, is_nullable, None, is_pk, None, None]


def test_attr_row_bool_from_string_only_real_pk():
    """is_primary_key/is_nullable vêm como STRING; só o PK real deve ser PK."""
    pk = service._attr_row_to_dict(_attr_row("a1", "id", 1, "bigint", "false", "true"))
    nonpk = service._attr_row_to_dict(_attr_row("a2", "nome", 2, "varchar(10)", "true", "false"))
    assert pk["is_primary_key"] is True
    assert pk["is_nullable"] is False
    # O CORAÇÃO do bug: "false" (string) NÃO pode virar PK/NOT NULL.
    assert nonpk["is_primary_key"] is False
    assert nonpk["is_nullable"] is True


# Ordem de _IDX_COLS: index_id, entity_id, index_name, index_type, columns_json,
# include_columns, partial_where, is_unique
def test_idx_row_include_columns_from_json_string():
    row = [
        "ix1", "e1", "ix_x", "BTREE",
        '[{"name":"a","direction":"ASC"}]',   # columns_json (string JSON)
        '["nome","criado_em"]',               # include_columns (ARRAY como string JSON)
        None, "false",                        # partial_where, is_unique (string)
    ]
    d = service._idx_row_to_dict(row)
    assert d["include_columns"] == ["nome", "criado_em"]  # não vira lista de chars
    assert d["is_unique"] is False
    assert d["columns"] == [{"name": "a", "direction": "ASC"}]


# Ordem de _REL_FK_COLS: relationship_id, source_entity_id, target_entity_id,
# source_attr_ids, target_attr_ids, fk_update_rule, fk_delete_rule, relationship_name
def test_fetch_relationships_parses_string_arrays(monkeypatch):
    rows = [[
        "rel-1", "ent-pedido", "ent-item",
        '["attr-pedido-id"]', '["attr-item-fk"]',  # arrays como string JSON
        None, None, "Pedido → Item",
    ]]
    monkeypatch.setattr(delta, "fetch_all_params", lambda *a, **k: rows)
    out = service.fetch_relationships(sql=None, system_id="sys-x")
    assert out[0]["source_attr_ids"] == ["attr-pedido-id"]
    assert out[0]["target_attr_ids"] == ["attr-item-fk"]


def test_generate_export_emits_fk_from_string_encoded_arrays(monkeypatch):
    """End-to-end (pt 11): com arrays string-encoded (como a API devolve), o export
    DEVE emitir a FK. Este é o teste que faltava e teria pego o bug em produção."""
    parent = {
        "entity_id": "ent-pedido", "schema_name": "vendas", "technical_name": "pedido",
        "entity_type": "TABLE", "description_md": None, "native_comment": None,
    }
    child = {
        "entity_id": "ent-item", "schema_name": "vendas", "technical_name": "item",
        "entity_type": "TABLE", "description_md": None, "native_comment": None,
    }
    parent_attrs = [{
        "attribute_id": "attr-pedido-id", "entity_id": "ent-pedido", "technical_name": "id",
        "ordinal_position": 1, "native_data_type": "bigint", "is_nullable": False,
        "default_value": None, "is_primary_key": True, "description_md": None, "native_comment": None,
    }]
    child_attrs = [
        {
            "attribute_id": "attr-item-id", "entity_id": "ent-item", "technical_name": "id",
            "ordinal_position": 1, "native_data_type": "bigint", "is_nullable": False,
            "default_value": None, "is_primary_key": True, "description_md": None, "native_comment": None,
        },
        {
            "attribute_id": "attr-item-fk", "entity_id": "ent-item", "technical_name": "pedido_id",
            "ordinal_position": 2, "native_data_type": "bigint", "is_nullable": False,
            "default_value": None, "is_primary_key": False, "description_md": None, "native_comment": None,
        },
    ]
    monkeypatch.setattr(
        service, "fetch_entities_with_attrs",
        lambda *a, **k: [(parent, parent_attrs), (child, child_attrs)],
    )
    monkeypatch.setattr(service, "fetch_indexes_and_partitioning", lambda *a, **k: ({}, {}))
    # source=PAI(pedido), target=FILHO(item); arrays STRING-ENCODED como a API devolve.
    rel_rows = [[
        "rel-1", "ent-pedido", "ent-item",
        '["attr-pedido-id"]', '["attr-item-fk"]', None, None, None,
    ]]
    monkeypatch.setattr(delta, "fetch_all_params", lambda *a, **k: rel_rows)

    result = service.generate_export(
        sql=None, payload=DDLExportRequest(system_id="sys-x", dialect="SPARKSQL"),
    )
    ct = result.combined_text
    assert "ALTER TABLE vendas.item ADD CONSTRAINT" in ct
    assert "FOREIGN KEY (pedido_id) REFERENCES vendas.pedido (id)" in ct
    # E o PK do filho deve conter APENAS `id` (regressão do bug do bool: sem o fix,
    # `pedido_id` (is_primary_key="false") entraria errado na PRIMARY KEY).
    pk_line = next(line for line in ct.splitlines() if "CONSTRAINT pk_item" in line)
    assert "(id)" in pk_line and "pedido_id" not in pk_line
