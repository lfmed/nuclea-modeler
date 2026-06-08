"""Tests do overlay editorial em índices + particionamento.

Cobrem ``apply_session_overlay_to_indexes`` e ``apply_session_overlay_to_partitioning``
em isolamento — sem tocar no Delta. Garantem que field_changes do ticket
OPEN aparecem com badge ``pending_op`` correto.
"""
from __future__ import annotations

from datetime import datetime

from nuclea_modeler.backend.entities.index_overlay import (
    apply_session_overlay_to_indexes,
    apply_session_overlay_to_partitioning,
)
from nuclea_modeler.backend.entities.models import (
    EntityIndexOut,
    EntityPartitioningOut,
    IndexColumn,
)


_NOW = datetime(2026, 6, 1, 12, 0)


def _cat_index(name: str, idx_id: str = "idx-1", cols: list[str] | None = None) -> EntityIndexOut:
    return EntityIndexOut(
        index_id=idx_id,
        entity_id="ent-1",
        index_name=name,
        index_type="BTREE",
        columns=[IndexColumn(name=c) for c in (cols or ["col_a"])],
        include_columns=[],
        partial_where=None,
        is_unique=False,
        description_md=None,
        native_comment=None,
        origin="MANUAL",
        created_at=_NOW, created_by="x@y",
        updated_at=_NOW, updated_by="x@y",
    )


def _diff_with(fcs: list[dict], entity_id: str = "ent-1") -> dict:
    return {
        "entities": [
            {
                "op": "change",
                "schema_name": "dbo",
                "technical_name": "tab",
                "payload": {"target_entity_id": entity_id},
                "field_changes": fcs,
            }
        ]
    }


def test_overlay_adds_virtual_index():
    catalog: list[EntityIndexOut] = []
    diff = _diff_with([
        {
            "field": "index_add:ix_new",
            "before": None,
            "after": {
                "index_id": "idx-new",
                "index_name": "ix_new",
                "index_type": "BTREE",
                "columns": [{"name": "email", "direction": "ASC"}],
                "include_columns": [],
                "partial_where": None,
                "is_unique": True,
            },
        }
    ])
    out = apply_session_overlay_to_indexes(catalog, diff, "ent-1")
    assert len(out) == 1
    assert out[0].pending_op == "add"
    assert out[0].index_name == "ix_new"
    assert out[0].is_unique is True


def test_overlay_marks_remove_on_catalog_index():
    cat = [_cat_index("ix_old")]
    diff = _diff_with([
        {"field": "index_remove:ix_old", "before": {"index_name": "ix_old"}, "after": None}
    ])
    out = apply_session_overlay_to_indexes(cat, diff, "ent-1")
    assert len(out) == 1
    assert out[0].pending_op == "remove"


def test_overlay_applies_change_payload():
    cat = [_cat_index("ix_a", idx_id="idx-1", cols=["a"])]
    diff = _diff_with([
        {
            "field": "index_change:idx-1",
            "before": {"index_id": "idx-1"},
            "after": {
                "index_id": "idx-1",
                "index_name": "ix_a_renomed",
                "index_type": "GIN",
                "columns": [{"name": "doc", "direction": "ASC"}],
                "include_columns": [],
                "is_unique": False,
            },
        }
    ])
    out = apply_session_overlay_to_indexes(cat, diff, "ent-1")
    assert len(out) == 1
    assert out[0].pending_op == "change"
    assert out[0].index_name == "ix_a_renomed"
    assert out[0].index_type == "GIN"
    assert out[0].columns[0].name == "doc"


def test_overlay_ignores_changes_for_other_entity():
    cat = [_cat_index("ix_a")]
    diff = {
        "entities": [
            {
                "op": "change",
                "payload": {"target_entity_id": "ent-OTHER"},
                "field_changes": [
                    {"field": "index_remove:ix_a", "before": {}, "after": None}
                ],
            }
        ]
    }
    out = apply_session_overlay_to_indexes(cat, diff, "ent-1")
    assert out[0].pending_op is None


def test_overlay_partitioning_set_creates_virtual_when_no_catalog():
    diff = _diff_with([
        {
            "field": "partitioning:set",
            "before": None,
            "after": {
                "strategy": "RANGE",
                "columns": ["data"],
                "num_partitions": None,
                "bounds": None,
            },
        }
    ])
    out = apply_session_overlay_to_partitioning(None, diff, "ent-1")
    assert out is not None
    assert out.pending_op == "change"
    assert out.strategy == "RANGE"
    assert out.columns == ["data"]


def test_overlay_partitioning_replaces_catalog():
    cat = EntityPartitioningOut(
        entity_id="ent-1", strategy="HASH", columns=["id"], num_partitions=4,
        bounds=None, description_md=None, origin="EXTRACTED",
        created_at=_NOW, created_by="x@y", updated_at=_NOW, updated_by="x@y",
    )
    diff = _diff_with([
        {
            "field": "partitioning:set",
            "before": None,
            "after": {"strategy": "LIQUID", "columns": ["data"], "num_partitions": None},
        }
    ])
    out = apply_session_overlay_to_partitioning(cat, diff, "ent-1")
    assert out is not None
    assert out.strategy == "LIQUID"
    assert out.pending_op == "change"
