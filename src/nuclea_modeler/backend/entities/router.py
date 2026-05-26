"""Module 3 — Entities + Attributes CRUD."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..core import Dependencies
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..._metadata import api_prefix
from .models import (
    AttributeIn, AttributeOut,
    EntityIn, EntityListOut, EntityOut,
)

router = APIRouter(prefix=f"{api_prefix}/entities", tags=["entities"])

_ENT_COLS = [
    "entity_id", "system_id", "schema_name", "technical_name", "logical_name",
    "description_md", "domain", "business_owner", "technical_owner",
    "criticality", "tags", "notes", "entity_type", "native_comment",
    "row_count_approx", "last_extracted_at",
    "created_at", "created_by", "updated_at", "updated_by",
]

_ATTR_COLS = [
    "attribute_id", "entity_id", "technical_name", "logical_name",
    "ordinal_position", "native_data_type", "is_nullable", "default_value",
    "is_primary_key", "description_md", "business_rule", "sample_value",
    "glossary_term_id", "native_comment",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _actor(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "unknown"


def _ent_row_to_out(r: list, system_name: str | None = None, attr_count: int | None = None) -> EntityOut:
    return EntityOut(
        entity_id=r[0], system_id=r[1], system_name=system_name,
        schema_name=r[2], technical_name=r[3], logical_name=r[4],
        description_md=r[5], domain=r[6], business_owner=r[7],
        technical_owner=r[8], criticality=r[9] or None,
        tags=list(r[10]) if r[10] else [],
        notes=r[11], entity_type=r[12] or "TABLE",
        native_comment=r[13], row_count_approx=r[14], last_extracted_at=r[15],
        created_at=r[16], created_by=r[17], updated_at=r[18], updated_by=r[19],
        attributes_count=attr_count,
    )


def _attr_row_to_out(r: list) -> AttributeOut:
    return AttributeOut(
        attribute_id=r[0], entity_id=r[1], technical_name=r[2], logical_name=r[3],
        ordinal_position=r[4], native_data_type=r[5],
        is_nullable=bool(r[6]) if r[6] is not None else None,
        default_value=r[7], is_primary_key=bool(r[8]),
        description_md=r[9], business_rule=r[10], sample_value=r[11],
        glossary_term_id=r[12], native_comment=r[13],
        created_at=r[14], created_by=r[15], updated_at=r[16], updated_by=r[17],
    )


# -------------------- Entities --------------------

@router.get("", response_model=list[EntityListOut], operation_id="listEntities")
def list_entities(
    sql: SqlDependency,
    system_id: str | None = None,
    domain: str | None = None,
) -> list[EntityListOut]:
    s = get_settings()
    where: list[str] = []
    params: list = []
    if system_id:
        where.append("e.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    if domain:
        where.append("e.domain = :domain")
        params.append(delta.param("domain", domain))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT e.entity_id, e.system_id, sys.system_name, e.schema_name,
               e.technical_name, e.logical_name, e.entity_type, e.domain,
               e.criticality, e.updated_at,
               (SELECT COUNT(*) FROM {s.fq_table('attributes')} a WHERE a.entity_id = e.entity_id) AS attrs
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        {where_clause}
        ORDER BY e.updated_at DESC
        LIMIT 1000
        """,
        params,
    )
    return [
        EntityListOut(
            entity_id=r[0], system_id=r[1], system_name=r[2], schema_name=r[3],
            technical_name=r[4], logical_name=r[5], entity_type=r[6] or "TABLE",
            domain=r[7], criticality=r[8] or None,
            attributes_count=int(r[10]) if r[10] is not None else 0,
            updated_at=r[9],
        )
        for r in rows
    ]


@router.get("/{entity_id}", response_model=EntityOut, operation_id="getEntity")
def get_entity(entity_id: str, sql: SqlDependency) -> EntityOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('e.'+c for c in _ENT_COLS)},
               sys.system_name,
               (SELECT COUNT(*) FROM {s.fq_table('attributes')} a WHERE a.entity_id = e.entity_id) AS attrs
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE e.entity_id = :entity_id
        """,
        [delta.param("entity_id", entity_id)],
    )
    if not row:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return _ent_row_to_out(row[:-2], system_name=row[-2], attr_count=int(row[-1]) if row[-1] is not None else 0)


@router.post("", response_model=EntityOut, operation_id="createEntity")
def create_entity(
    payload: EntityIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityOut:
    s = get_settings()
    actor = _actor(user_ws)
    eid = delta.new_id("ent-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("entities"),
        {
            "entity_id": eid,
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "description_md": payload.description_md,
            "domain": payload.domain,
            "business_owner": payload.business_owner,
            "technical_owner": payload.technical_owner,
            "criticality": payload.criticality,
            "tags": payload.tags,
            "notes": payload.notes,
            "entity_type": payload.entity_type,
            "native_comment": payload.native_comment,
            "row_count_approx": payload.row_count_approx,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_entity(eid, sql)


@router.put("/{entity_id}", response_model=EntityOut, operation_id="updateEntity")
def update_entity(
    entity_id: str,
    payload: EntityIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityOut:
    s = get_settings()
    actor = _actor(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("entities"),
        "entity_id",
        entity_id,
        {
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "description_md": payload.description_md,
            "domain": payload.domain,
            "business_owner": payload.business_owner,
            "technical_owner": payload.technical_owner,
            "criticality": payload.criticality,
            "tags": payload.tags,
            "notes": payload.notes,
            "entity_type": payload.entity_type,
            "native_comment": payload.native_comment,
            "row_count_approx": payload.row_count_approx,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_entity(entity_id, sql)


@router.delete("/{entity_id}", operation_id="deleteEntity")
def delete_entity(entity_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    # cascade: delete attributes then entity
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('attributes')} WHERE entity_id = :entity_id",
        [delta.param("entity_id", entity_id)],
    )
    delta.delete_by_id(sql, s.fq_table("entities"), "entity_id", entity_id)
    return {"deleted": entity_id}


# -------------------- Attributes --------------------

@router.get(
    "/{entity_id}/attributes",
    response_model=list[AttributeOut],
    operation_id="listAttributes",
)
def list_attributes(entity_id: str, sql: SqlDependency) -> list[AttributeOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join(_ATTR_COLS)}
        FROM {s.fq_table('attributes')}
        WHERE entity_id = :entity_id
        ORDER BY COALESCE(ordinal_position, 999999), technical_name
        """,
        [delta.param("entity_id", entity_id)],
    )
    return [_attr_row_to_out(r) for r in rows]


@router.post(
    "/{entity_id}/attributes",
    response_model=AttributeOut,
    operation_id="createAttribute",
)
def create_attribute(
    entity_id: str,
    payload: AttributeIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AttributeOut:
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id in path and payload must match")
    s = get_settings()
    actor = _actor(user_ws)
    aid = delta.new_id("attr-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("attributes"),
        {
            "attribute_id": aid,
            "entity_id": entity_id,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "ordinal_position": payload.ordinal_position,
            "native_data_type": payload.native_data_type,
            "is_nullable": payload.is_nullable,
            "default_value": payload.default_value,
            "is_primary_key": payload.is_primary_key,
            "description_md": payload.description_md,
            "business_rule": payload.business_rule,
            "sample_value": payload.sample_value,
            "glossary_term_id": payload.glossary_term_id,
            "native_comment": payload.native_comment,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_ATTR_COLS)} FROM {s.fq_table('attributes')} "
        f"WHERE attribute_id = :attribute_id",
        [delta.param("attribute_id", aid)],
    )
    if not row:
        raise HTTPException(500, "attribute create failed")
    return _attr_row_to_out(row)


@router.put(
    "/{entity_id}/attributes/{attribute_id}",
    response_model=AttributeOut,
    operation_id="updateAttribute",
)
def update_attribute(
    entity_id: str,
    attribute_id: str,
    payload: AttributeIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AttributeOut:
    s = get_settings()
    actor = _actor(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("attributes"),
        "attribute_id",
        attribute_id,
        {
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "ordinal_position": payload.ordinal_position,
            "native_data_type": payload.native_data_type,
            "is_nullable": payload.is_nullable,
            "default_value": payload.default_value,
            "is_primary_key": payload.is_primary_key,
            "description_md": payload.description_md,
            "business_rule": payload.business_rule,
            "sample_value": payload.sample_value,
            "glossary_term_id": payload.glossary_term_id,
            "native_comment": payload.native_comment,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_ATTR_COLS)} FROM {s.fq_table('attributes')} "
        f"WHERE attribute_id = :attribute_id",
        [delta.param("attribute_id", attribute_id)],
    )
    if not row:
        raise HTTPException(404, f"attribute '{attribute_id}' not found")
    return _attr_row_to_out(row)


@router.delete(
    "/{entity_id}/attributes/{attribute_id}",
    operation_id="deleteAttribute",
)
def delete_attribute(entity_id: str, attribute_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("attributes"), "attribute_id", attribute_id)
    return {"deleted": attribute_id}
