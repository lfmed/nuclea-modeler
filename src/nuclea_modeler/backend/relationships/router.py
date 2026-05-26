"""Module — Relationships CRUD (manual, complements EXTRACTED relations)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .models import RelationshipIn, RelationshipListOut, RelationshipOut

router = APIRouter(prefix=f"{api_prefix}/relationships", tags=["relationships"])


_REL_COLS = [
    "relationship_id", "system_id", "source_entity_id", "target_entity_id",
    "source_attr_ids", "target_attr_ids", "rel_type",
    "source_cardinality", "target_cardinality", "description", "origin",
    "fk_update_rule", "fk_delete_rule",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _entity_label(schema: str | None, technical: str | None) -> str | None:
    if not technical:
        return None
    if schema:
        return f"{schema}.{technical}"
    return technical


def _rel_row_to_out(r: list) -> RelationshipOut:
    return RelationshipOut(
        relationship_id=r[0],
        system_id=r[1],
        source_entity_id=r[2],
        target_entity_id=r[3],
        source_attr_ids=list(r[4]) if r[4] else [],
        target_attr_ids=list(r[5]) if r[5] else [],
        rel_type=r[6] or None,
        source_cardinality=r[7] or None,
        target_cardinality=r[8] or None,
        description=r[9],
        origin=r[10] or None,
        fk_update_rule=r[11] or None,
        fk_delete_rule=r[12] or None,
        created_at=r[13],
        created_by=r[14],
        updated_at=r[15],
        updated_by=r[16],
        system_name=r[17] if len(r) > 17 else None,
        source_entity_label=_entity_label(
            r[18] if len(r) > 18 else None,
            r[19] if len(r) > 19 else None,
        ),
        target_entity_label=_entity_label(
            r[20] if len(r) > 20 else None,
            r[21] if len(r) > 21 else None,
        ),
    )


def _select_rel_query(where_clause: str = "") -> str:
    s = get_settings()
    cols = ", ".join("r." + c for c in _REL_COLS)
    return f"""
        SELECT {cols},
               sys.system_name,
               src.schema_name AS src_schema, src.technical_name AS src_tech,
               tgt.schema_name AS tgt_schema, tgt.technical_name AS tgt_tech
        FROM {s.fq_table('relationships')} r
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = r.system_id
        LEFT JOIN {s.fq_table('entities')} src ON src.entity_id = r.source_entity_id
        LEFT JOIN {s.fq_table('entities')} tgt ON tgt.entity_id = r.target_entity_id
        {where_clause}
    """


def _validate_entities(sql: SqlDependency, system_id: str,
                       source_entity_id: str, target_entity_id: str) -> None:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, system_id
        FROM {s.fq_table('entities')}
        WHERE entity_id IN (:source_id, :target_id)
        """,
        [
            delta.param("source_id", source_entity_id),
            delta.param("target_id", target_entity_id),
        ],
    )
    found = {r[0]: r[1] for r in rows}
    if source_entity_id not in found:
        raise HTTPException(400, f"source_entity_id '{source_entity_id}' not found")
    if target_entity_id not in found:
        raise HTTPException(400, f"target_entity_id '{target_entity_id}' not found")
    if found[source_entity_id] != system_id:
        raise HTTPException(
            400,
            f"source entity belongs to system '{found[source_entity_id]}', "
            f"not '{system_id}'",
        )
    if found[target_entity_id] != system_id:
        raise HTTPException(
            400,
            f"target entity belongs to system '{found[target_entity_id]}', "
            f"not '{system_id}'",
        )


@router.get("", response_model=list[RelationshipListOut], operation_id="listRelationships")
def list_relationships(
    sql: SqlDependency,
    system_id: str | None = None,
) -> list[RelationshipListOut]:
    where = ""
    params: list = []
    if system_id:
        where = "WHERE r.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        _select_rel_query(where) + "\nORDER BY r.updated_at DESC LIMIT 1000",
        params,
    )
    return [
        RelationshipListOut(
            relationship_id=r[0],
            system_id=r[1],
            system_name=r[17],
            source_entity_id=r[2],
            source_entity_label=_entity_label(r[18], r[19]),
            target_entity_id=r[3],
            target_entity_label=_entity_label(r[20], r[21]),
            rel_type=r[6] or None,
            source_cardinality=r[7] or None,
            target_cardinality=r[8] or None,
            origin=r[10] or None,
            description=r[9],
            updated_at=r[15],
        )
        for r in rows
    ]


@router.get("/{relationship_id}", response_model=RelationshipOut, operation_id="getRelationship")
def get_relationship(relationship_id: str, sql: SqlDependency) -> RelationshipOut:
    row = delta.fetch_one_params(
        sql,
        _select_rel_query("WHERE r.relationship_id = :relationship_id"),
        [delta.param("relationship_id", relationship_id)],
    )
    if not row:
        raise HTTPException(404, f"relationship '{relationship_id}' not found")
    return _rel_row_to_out(row)


@router.post("", response_model=RelationshipOut, operation_id="createRelationship")
def create_relationship(
    payload: RelationshipIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> RelationshipOut:
    _validate_entities(
        sql, payload.system_id, payload.source_entity_id, payload.target_entity_id,
    )
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    rid = delta.new_id("rel-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("relationships"),
        {
            "relationship_id": rid,
            "system_id": payload.system_id,
            "source_entity_id": payload.source_entity_id,
            "target_entity_id": payload.target_entity_id,
            "source_attr_ids": payload.source_attr_ids,
            "target_attr_ids": payload.target_attr_ids,
            "rel_type": payload.rel_type,
            "source_cardinality": payload.source_cardinality,
            "target_cardinality": payload.target_cardinality,
            "description": payload.description,
            "origin": "MANUAL",
            "fk_update_rule": payload.fk_update_rule,
            "fk_delete_rule": payload.fk_delete_rule,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_relationship(rid, sql)


@router.put("/{relationship_id}", response_model=RelationshipOut, operation_id="updateRelationship")
def update_relationship(
    relationship_id: str,
    payload: RelationshipIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> RelationshipOut:
    _validate_entities(
        sql, payload.system_id, payload.source_entity_id, payload.target_entity_id,
    )
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    delta.update_by_id(
        sql,
        s.fq_table("relationships"),
        "relationship_id",
        relationship_id,
        {
            "system_id": payload.system_id,
            "source_entity_id": payload.source_entity_id,
            "target_entity_id": payload.target_entity_id,
            "source_attr_ids": payload.source_attr_ids,
            "target_attr_ids": payload.target_attr_ids,
            "rel_type": payload.rel_type,
            "source_cardinality": payload.source_cardinality,
            "target_cardinality": payload.target_cardinality,
            "description": payload.description,
            "fk_update_rule": payload.fk_update_rule,
            "fk_delete_rule": payload.fk_delete_rule,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_relationship(relationship_id, sql)


@router.delete("/{relationship_id}", operation_id="deleteRelationship")
def delete_relationship(relationship_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(
        sql, s.fq_table("relationships"), "relationship_id", relationship_id,
    )
    return {"deleted": relationship_id}
