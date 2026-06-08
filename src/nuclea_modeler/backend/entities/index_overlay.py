"""Overlay editorial de índices + particionamento.

Helpers puros (sem dependência de Delta/SDK) que mesclam um diff de
sessão sobre a lista do catálogo. Movidos pra fora de ``indexes.py`` pra
que possam ser testados sem stub de dotenv/databricks-sdk.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    EntityIndexOut,
    EntityPartitioningOut,
    IndexColumn,
)


def _field_changes_for_entity(
    session_diff: dict[str, Any], entity_id: str,
) -> list[dict[str, Any]]:
    """Achata field_changes dos ent_changes que apontam pra esta entity."""
    out: list[dict[str, Any]] = []
    for ent in session_diff.get("entities", []) or []:
        if (ent.get("payload") or {}).get("target_entity_id") == entity_id:
            for fc in ent.get("field_changes") or []:
                out.append(fc)
    return out


def apply_session_overlay_to_indexes(
    catalog: list[EntityIndexOut],
    session_diff: dict[str, Any],
    entity_id: str,
) -> list[EntityIndexOut]:
    """Aplica field_changes do ticket OPEN sobre a lista do catálogo.

    - ``index_add:NAME`` adiciona ``EntityIndexOut`` virtual com pending_op="add"
    - ``index_remove:NAME`` marca a row do catálogo com pending_op="remove"
    - ``index_change:ID`` substitui campos da row catalog com pending_op="change"
    """
    fcs = _field_changes_for_entity(session_diff, entity_id)
    if not fcs:
        return catalog

    by_name = {ix.index_name: ix for ix in catalog}
    result: list[EntityIndexOut] = list(catalog)
    pending_ops: dict[str, str] = {}
    pending_payload: dict[str, dict[str, Any]] = {}

    for fc in fcs:
        field = fc.get("field", "")
        after = fc.get("after") or {}
        if field.startswith("index_add:"):
            ix_id = after.get("index_id") or f"virtual-{field}"
            virtual = EntityIndexOut(
                index_id=ix_id,
                entity_id=entity_id,
                index_name=after.get("index_name") or field.split(":", 1)[1],
                index_type=after.get("index_type") or "BTREE",
                columns=[
                    IndexColumn(
                        name=str(c.get("name", "")),
                        direction=c.get("direction", "ASC") or "ASC",
                    )
                    for c in (after.get("columns") or [])
                    if isinstance(c, dict) and c.get("name")
                ],
                include_columns=list(after.get("include_columns") or []),
                partial_where=after.get("partial_where"),
                is_unique=bool(after.get("is_unique", False)),
                description_md=after.get("description_md"),
                native_comment=after.get("native_comment"),
                origin="MANUAL",
                created_at=datetime.utcnow(),
                created_by="(sessão)",
                updated_at=datetime.utcnow(),
                updated_by="(sessão)",
                pending_op="add",
            )
            result.append(virtual)
        elif field.startswith("index_remove:"):
            name = field.split(":", 1)[1]
            target = by_name.get(name)
            if target:
                pending_ops[target.index_id] = "remove"
        elif field.startswith("index_change:"):
            ix_id = field.split(":", 1)[1]
            pending_ops[ix_id] = "change"
            pending_payload[ix_id] = after

    if pending_ops:
        merged: list[EntityIndexOut] = []
        for ix in result:
            op = pending_ops.get(ix.index_id)
            if op == "remove":
                merged.append(ix.model_copy(update={"pending_op": "remove"}))
            elif op == "change":
                p = pending_payload.get(ix.index_id, {})
                merged.append(ix.model_copy(update={
                    "pending_op": "change",
                    "index_name": p.get("index_name", ix.index_name),
                    "index_type": p.get("index_type", ix.index_type),
                    "columns": [
                        IndexColumn(
                            name=str(c.get("name", "")),
                            direction=c.get("direction", "ASC") or "ASC",
                        )
                        for c in (p.get("columns") or [])
                        if isinstance(c, dict) and c.get("name")
                    ] or ix.columns,
                    "include_columns": list(p.get("include_columns") or ix.include_columns),
                    "partial_where": p.get("partial_where", ix.partial_where),
                    "is_unique": bool(p.get("is_unique", ix.is_unique)),
                }))
            else:
                merged.append(ix)
        result = merged

    # Mantém ordem alfabética com pendings ao fim pra usuário ver fácil
    return sorted(result, key=lambda x: (x.pending_op is not None, x.index_name))


def apply_session_overlay_to_partitioning(
    catalog: EntityPartitioningOut | None,
    session_diff: dict[str, Any],
    entity_id: str,
) -> EntityPartitioningOut | None:
    """Aplica ``partitioning:set`` do ticket OPEN sobre a partição atual."""
    fcs = _field_changes_for_entity(session_diff, entity_id)
    latest = None
    for fc in fcs:
        if fc.get("field") == "partitioning:set":
            latest = fc.get("after") or {}
    if latest is None:
        return catalog
    return EntityPartitioningOut(
        entity_id=entity_id,
        strategy=latest.get("strategy", "NONE"),
        columns=list(latest.get("columns") or []),
        num_partitions=latest.get("num_partitions"),
        bounds=latest.get("bounds"),
        description_md=latest.get("description_md"),
        origin="MANUAL",
        created_at=catalog.created_at if catalog else None,
        created_by=catalog.created_by if catalog else None,
        updated_at=datetime.utcnow(),
        updated_by="(sessão)",
        pending_op="change",
    )
