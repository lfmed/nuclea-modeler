"""Test do parse de Liquid Clustering em UC TableInfo.

Não precisa de SDK Databricks — usamos um stub com a forma esperada do
``TableInfo`` (campos ``properties`` e ``columns``).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

# extract service puxa dotenv via core._config — skip se ambiente local não
# tem (CI sempre tem)
pytest.importorskip("dotenv")
pytest.importorskip("databricks.sdk")

from nuclea_modeler.backend.extractions.service import _table_info_to_entity


def _stub_table(*, name: str, schema: str, props: dict | None = None, columns=None):
    return SimpleNamespace(
        name=name,
        schema_name=schema,
        table_type=None,
        comment=None,
        columns=columns or [],
        properties=props or {},
    )


def test_no_clustering_columns_results_in_empty_indexes():
    t = _stub_table(name="pedido", schema="public")
    ent = _table_info_to_entity(t, fallback_schema="public")
    assert ent.indexes == []


def test_parses_liquid_clustering_from_properties():
    """Liquid clustering vem como JSON string nas properties."""
    t = _stub_table(
        name="pedido",
        schema="public",
        props={"clusteringColumns": '[["id_cliente"],["data_pedido"]]'},
    )
    ent = _table_info_to_entity(t, fallback_schema="public")
    assert len(ent.indexes) == 1
    ix = ent.indexes[0]
    assert ix.index_type == "LIQUID"
    assert ix.is_unique is False
    cols = [c.name for c in ix.columns]
    assert cols == ["id_cliente", "data_pedido"]


def test_handles_malformed_clustering_property_gracefully():
    t = _stub_table(
        name="pedido", schema="public",
        props={"clusteringColumns": "not-valid-json"},
    )
    ent = _table_info_to_entity(t, fallback_schema="public")
    # Property malformada não derruba o parser — só não emite índice
    assert ent.indexes == []


def test_clustering_columns_can_be_simple_strings():
    """Alguns exports usam formato simplificado ['col_a','col_b']."""
    t = _stub_table(
        name="pedido",
        schema="public",
        props={"clusteringColumns": '["data_pedido","id_cliente"]'},
    )
    ent = _table_info_to_entity(t, fallback_schema="public")
    assert len(ent.indexes) == 1
    assert [c.name for c in ent.indexes[0].columns] == ["data_pedido", "id_cliente"]
