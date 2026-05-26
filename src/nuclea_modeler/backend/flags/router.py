"""Módulo 5 — Flagueamento de Componentes.

Endpoints for managing the catalog of available flags and applying flags to
entities (tables) and attributes (columns).

Propagation rule (spec §4.5.2): when a flag with `category = LGPD` is applied to
an attribute, an `entity_flag` row is automatically inserted on the parent
entity with `is_propagated = true` (if not already present). When the attribute
flag is removed, the propagated entity flag is removed only if no other
attributes of the same entity carry that same LGPD flag.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql, SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, ROLE_DATA_ARCHITECT, require_role
from .models import (
    AttributeFlagApplyIn,
    AttributeFlagOut,
    EntityFlagApplyIn,
    EntityFlagOut,
    FlagCategory,
    FlagIn,
    FlagOut,
    FlagPatch,
)


router = APIRouter(prefix=f"{api_prefix}/flags", tags=["flags"])
entity_router = APIRouter(prefix=f"{api_prefix}/entities", tags=["flags"])
attribute_router = APIRouter(prefix=f"{api_prefix}/attributes", tags=["flags"])


FLAG_ADMINS = (ROLE_DATA_ARCHITECT, ROLE_ADMIN)


# Column order used everywhere we build a FlagOut.
_FLAG_COLS = [
    "flag_id", "flag_key", "category", "display_name", "description",
    "color_hex", "requires_justification", "is_system", "is_active", "uc_tag_key",
]


def _flag_row_to_out(r: list) -> FlagOut:
    return FlagOut(
        flag_id=r[0],
        flag_key=r[1],
        category=r[2],
        display_name=r[3],
        description=r[4],
        color_hex=r[5],
        requires_justification=bool(r[6]),
        is_system=bool(r[7]),
        is_active=bool(r[8]),
        uc_tag_key=r[9],
    )


def _fetch_flag(sql: Sql, flag_id: str) -> FlagOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_FLAG_COLS)} FROM {s.fq_table('flags')} "
        f"WHERE flag_id = :flag_id",
        [delta.param("flag_id", flag_id)],
    )
    if not row:
        raise HTTPException(404, f"flag '{flag_id}' not found")
    return _flag_row_to_out(row)


# ─── Catalog of flags ─────────────────────────────────────────────────────────

@router.get("", response_model=list[FlagOut], operation_id="listFlags")
def list_flags(
    sql: SqlDependency,
    category: FlagCategory | None = Query(None),
    is_active: bool | None = Query(None),
) -> list[FlagOut]:
    s = get_settings()
    where: list[str] = []
    params: list = []
    if category:
        where.append("category = :category")
        params.append(delta.param("category", str(category)))
    if is_active is not None:
        where.append("is_active = :is_active")
        params.append(delta.param("is_active", is_active))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join(_FLAG_COLS)}
        FROM {s.fq_table('flags')}
        {where_clause}
        ORDER BY
          CASE category WHEN 'LGPD' THEN 0 WHEN 'USE' THEN 1
            WHEN 'QUALITY' THEN 2 WHEN 'CUSTOM' THEN 3 ELSE 4 END,
          display_name
        """,
        params,
    )
    return [_flag_row_to_out(r) for r in rows]


@router.post("", response_model=FlagOut, operation_id="createCustomFlag")
def create_custom_flag(
    payload: FlagIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> FlagOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *FLAG_ADMINS)
    s = get_settings()
    fid = delta.new_id("flag-custom-")
    now = datetime.utcnow()
    # Custom flags only — never allow injection of is_system=true via API.
    delta.insert(
        sql,
        s.fq_table("flags"),
        {
            "flag_id": fid,
            "flag_key": payload.flag_key,
            "category": "CUSTOM",
            "display_name": payload.display_name,
            "description": payload.description,
            "color_hex": payload.color_hex or "#6C757D",
            "requires_justification": payload.requires_justification,
            "is_system": False,
            "is_active": True,
            "uc_tag_key": None,
            "created_at": now,
            "created_by": actor,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return _fetch_flag(sql, fid)


@router.patch("/{flag_id}", response_model=FlagOut, operation_id="patchFlag")
def patch_flag(
    flag_id: str,
    payload: FlagPatch,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> FlagOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *FLAG_ADMINS)
    s = get_settings()
    current = _fetch_flag(sql, flag_id)
    updates: dict = {}
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if payload.display_name is not None and not current.is_system:
        updates["display_name"] = payload.display_name
    if payload.description is not None and not current.is_system:
        updates["description"] = payload.description
    if payload.color_hex is not None:
        updates["color_hex"] = payload.color_hex
    if payload.requires_justification is not None and not current.is_system:
        updates["requires_justification"] = payload.requires_justification
    if not updates:
        return current
    updates["updated_at"] = datetime.utcnow()
    updates["updated_by"] = actor
    delta.update_by_id(sql, s.fq_table("flags"), "flag_id", flag_id, updates)
    return _fetch_flag(sql, flag_id)


# ─── Entity flags ─────────────────────────────────────────────────────────────

_ENT_FLAG_SELECT = (
    "ef.entity_flag_id, ef.entity_id, ef.flag_id, ef.justification, "
    "ef.applied_at, ef.applied_by, ef.applied_in_version, ef.is_propagated, "
    + ", ".join(f"f.{c}" for c in _FLAG_COLS)
)


def _entity_flag_row_to_out(r: list) -> EntityFlagOut:
    flag_cols_start = 8
    flag = _flag_row_to_out(r[flag_cols_start:flag_cols_start + len(_FLAG_COLS)])
    return EntityFlagOut(
        entity_flag_id=r[0],
        entity_id=r[1],
        flag_id=r[2],
        justification=r[3],
        applied_at=r[4],
        applied_by=r[5],
        applied_in_version=r[6],
        is_propagated=bool(r[7]),
        flag=flag,
    )


@entity_router.get(
    "/{entity_id}/flags",
    response_model=list[EntityFlagOut],
    operation_id="listEntityFlags",
)
def list_entity_flags(entity_id: str, sql: SqlDependency) -> list[EntityFlagOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {_ENT_FLAG_SELECT}
        FROM {s.fq_table('entity_flags')} ef
        JOIN {s.fq_table('flags')} f ON f.flag_id = ef.flag_id
        WHERE ef.entity_id = :entity_id
        ORDER BY ef.applied_at DESC
        """,
        [delta.param("entity_id", entity_id)],
    )
    return [_entity_flag_row_to_out(r) for r in rows]


@entity_router.post(
    "/{entity_id}/flags",
    response_model=EntityFlagOut,
    operation_id="applyEntityFlag",
)
def apply_entity_flag(
    entity_id: str,
    payload: EntityFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityFlagOut:
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    flag = _fetch_flag(sql, payload.flag_id)
    if not flag.is_active:
        raise HTTPException(400, f"flag '{flag.flag_key}' is inactive")
    if flag.requires_justification and not (payload.justification or "").strip():
        raise HTTPException(
            400,
            f"flag '{flag.flag_key}' requires a non-empty justification",
        )
    s = get_settings()
    # idempotent: skip if same flag already applied on entity
    existing = delta.fetch_one_params(
        sql,
        f"SELECT entity_flag_id FROM {s.fq_table('entity_flags')} "
        f"WHERE entity_id = :entity_id AND flag_id = :flag_id",
        [
            delta.param("entity_id", entity_id),
            delta.param("flag_id", flag.flag_id),
        ],
    )
    if existing:
        return _entity_flag_by_id(sql, existing[0])
    efid = delta.new_id("entflag-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("entity_flags"),
        {
            "entity_flag_id": efid,
            "entity_id": entity_id,
            "flag_id": flag.flag_id,
            "justification": payload.justification,
            "applied_at": now,
            "applied_by": actor,
            "applied_in_version": None,
            "is_propagated": False,
        },
    )
    return _entity_flag_by_id(sql, efid)


def _entity_flag_by_id(sql: Sql, entity_flag_id: str) -> EntityFlagOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {_ENT_FLAG_SELECT}
        FROM {s.fq_table('entity_flags')} ef
        JOIN {s.fq_table('flags')} f ON f.flag_id = ef.flag_id
        WHERE ef.entity_flag_id = :entity_flag_id
        """,
        [delta.param("entity_flag_id", entity_flag_id)],
    )
    if not row:
        raise HTTPException(404, f"entity_flag '{entity_flag_id}' not found")
    return _entity_flag_row_to_out(row)


@entity_router.delete(
    "/{entity_id}/flags/{entity_flag_id}",
    operation_id="removeEntityFlag",
)
def remove_entity_flag(
    entity_id: str,
    entity_flag_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    s = get_settings()
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('entity_flags')} "
        f"WHERE entity_flag_id = :entity_flag_id "
        f"AND entity_id = :entity_id",
        [
            delta.param("entity_flag_id", entity_flag_id),
            delta.param("entity_id", entity_id),
        ],
    )
    return {"deleted": entity_flag_id}


# ─── Attribute flags ──────────────────────────────────────────────────────────

_ATTR_FLAG_SELECT = (
    "af.attribute_flag_id, af.attribute_id, af.flag_id, af.justification, "
    "af.applied_at, af.applied_by, af.applied_in_version, "
    + ", ".join(f"f.{c}" for c in _FLAG_COLS)
)


def _attribute_flag_row_to_out(r: list) -> AttributeFlagOut:
    flag_cols_start = 7
    flag = _flag_row_to_out(r[flag_cols_start:flag_cols_start + len(_FLAG_COLS)])
    return AttributeFlagOut(
        attribute_flag_id=r[0],
        attribute_id=r[1],
        flag_id=r[2],
        justification=r[3],
        applied_at=r[4],
        applied_by=r[5],
        applied_in_version=r[6],
        flag=flag,
    )


def _attribute_flag_by_id(sql: Sql, attribute_flag_id: str) -> AttributeFlagOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {_ATTR_FLAG_SELECT}
        FROM {s.fq_table('attribute_flags')} af
        JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
        WHERE af.attribute_flag_id = :attribute_flag_id
        """,
        [delta.param("attribute_flag_id", attribute_flag_id)],
    )
    if not row:
        raise HTTPException(404, f"attribute_flag '{attribute_flag_id}' not found")
    return _attribute_flag_row_to_out(row)


def _entity_id_for_attribute(sql: Sql, attribute_id: str) -> str | None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT entity_id FROM {s.fq_table('attributes')} "
        f"WHERE attribute_id = :attribute_id",
        [delta.param("attribute_id", attribute_id)],
    )
    return row[0] if row else None


def _propagate_lgpd_to_entity(
    sql: Sql, *, entity_id: str, flag_id: str, applied_by: str
) -> None:
    """If the parent entity does not already have this LGPD flag, insert a
    propagated row (is_propagated=true). Idempotent."""
    s = get_settings()
    existing = delta.fetch_one_params(
        sql,
        f"SELECT entity_flag_id FROM {s.fq_table('entity_flags')} "
        f"WHERE entity_id = :entity_id AND flag_id = :flag_id",
        [
            delta.param("entity_id", entity_id),
            delta.param("flag_id", flag_id),
        ],
    )
    if existing:
        return
    delta.insert(
        sql,
        s.fq_table("entity_flags"),
        {
            "entity_flag_id": delta.new_id("entflag-prop-"),
            "entity_id": entity_id,
            "flag_id": flag_id,
            "justification": "Propagado automaticamente a partir de coluna (LGPD).",
            "applied_at": datetime.utcnow(),
            "applied_by": applied_by,
            "applied_in_version": None,
            "is_propagated": True,
        },
    )


def _cleanup_propagated_entity_flag(
    sql: Sql, *, entity_id: str, flag_id: str
) -> None:
    """Remove the propagated entity flag iff no other attribute of the same
    entity still carries the same LGPD flag."""
    s = get_settings()
    still_used = delta.fetch_one_params(
        sql,
        f"""
        SELECT 1
        FROM {s.fq_table('attribute_flags')} af
        JOIN {s.fq_table('attributes')} a ON a.attribute_id = af.attribute_id
        WHERE a.entity_id = :entity_id
          AND af.flag_id = :flag_id
        LIMIT 1
        """,
        [
            delta.param("entity_id", entity_id),
            delta.param("flag_id", flag_id),
        ],
    )
    if still_used:
        return
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('entity_flags')} "
        f"WHERE entity_id = :entity_id "
        f"AND flag_id = :flag_id "
        f"AND is_propagated = true",
        [
            delta.param("entity_id", entity_id),
            delta.param("flag_id", flag_id),
        ],
    )


@attribute_router.get(
    "/{attribute_id}/flags",
    response_model=list[AttributeFlagOut],
    operation_id="listAttributeFlags",
)
def list_attribute_flags(
    attribute_id: str, sql: SqlDependency
) -> list[AttributeFlagOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {_ATTR_FLAG_SELECT}
        FROM {s.fq_table('attribute_flags')} af
        JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
        WHERE af.attribute_id = :attribute_id
        ORDER BY af.applied_at DESC
        """,
        [delta.param("attribute_id", attribute_id)],
    )
    return [_attribute_flag_row_to_out(r) for r in rows]


@attribute_router.post(
    "/{attribute_id}/flags",
    response_model=AttributeFlagOut,
    operation_id="applyAttributeFlag",
)
def apply_attribute_flag(
    attribute_id: str,
    payload: AttributeFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AttributeFlagOut:
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    flag = _fetch_flag(sql, payload.flag_id)
    if not flag.is_active:
        raise HTTPException(400, f"flag '{flag.flag_key}' is inactive")
    if flag.requires_justification and not (payload.justification or "").strip():
        raise HTTPException(
            400,
            f"flag '{flag.flag_key}' requires a non-empty justification",
        )
    s = get_settings()
    existing = delta.fetch_one_params(
        sql,
        f"SELECT attribute_flag_id FROM {s.fq_table('attribute_flags')} "
        f"WHERE attribute_id = :attribute_id AND flag_id = :flag_id",
        [
            delta.param("attribute_id", attribute_id),
            delta.param("flag_id", flag.flag_id),
        ],
    )
    if existing:
        return _attribute_flag_by_id(sql, existing[0])
    afid = delta.new_id("attrflag-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("attribute_flags"),
        {
            "attribute_flag_id": afid,
            "attribute_id": attribute_id,
            "flag_id": flag.flag_id,
            "justification": payload.justification,
            "applied_at": now,
            "applied_by": actor,
            "applied_in_version": None,
        },
    )
    # Propagation rule (spec §4.5.2): any LGPD flag on a column also marks the
    # parent entity, so DPOs see the table is touched by personal data.
    if flag.category == "LGPD":
        entity_id = _entity_id_for_attribute(sql, attribute_id)
        if entity_id:
            _propagate_lgpd_to_entity(
                sql,
                entity_id=entity_id,
                flag_id=flag.flag_id,
                applied_by=actor,
            )
    return _attribute_flag_by_id(sql, afid)


@attribute_router.delete(
    "/{attribute_id}/flags/{attribute_flag_id}",
    operation_id="removeAttributeFlag",
)
def remove_attribute_flag(
    attribute_id: str,
    attribute_flag_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    s = get_settings()
    # Capture the flag (and category) before deletion so we can clean up
    # propagated entity flags afterwards.
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT af.flag_id, f.category
        FROM {s.fq_table('attribute_flags')} af
        JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
        WHERE af.attribute_flag_id = :attribute_flag_id
          AND af.attribute_id = :attribute_id
        """,
        [
            delta.param("attribute_flag_id", attribute_flag_id),
            delta.param("attribute_id", attribute_id),
        ],
    )
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('attribute_flags')} "
        f"WHERE attribute_flag_id = :attribute_flag_id "
        f"AND attribute_id = :attribute_id",
        [
            delta.param("attribute_flag_id", attribute_flag_id),
            delta.param("attribute_id", attribute_id),
        ],
    )
    if row and row[1] == "LGPD":
        entity_id = _entity_id_for_attribute(sql, attribute_id)
        if entity_id:
            _cleanup_propagated_entity_flag(
                sql, entity_id=entity_id, flag_id=row[0]
            )
    return {"deleted": attribute_flag_id}
