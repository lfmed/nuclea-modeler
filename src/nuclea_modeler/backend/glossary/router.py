"""Module 6 — Corporate Data Dictionary (glossary terms + N:N attribute mappings)."""
from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import (
    ROLE_ADMIN,
    ROLE_DATA_ARCHITECT,
    ROLE_DATA_STEWARD,
    has_role,
    require_role,
)
from .models import (
    ConceptualType,
    MappingIn,
    MappingOut,
    TermIn,
    TermListOut,
    TermOut,
    TermStatus,
    TermTransition,
)
from .service import check_type_compat

router = APIRouter(prefix=f"{api_prefix}/glossary", tags=["glossary"])

# Separate router for the reverse-lookup endpoint mounted under /api/attributes
attr_glossary_router = APIRouter(prefix=f"{api_prefix}/attributes", tags=["glossary"])


_TERM_COLS = [
    "term_id", "canonical_name", "definition", "synonyms", "domain",
    "conceptual_type", "valid_examples", "owner_person", "status",
    "approved_by", "approved_at",
    "created_at", "created_by", "updated_at", "updated_by",
]

# Approval permissions
APPROVERS = (ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
ARCHITECT_OR_ADMIN = (ROLE_DATA_ARCHITECT, ROLE_ADMIN)


def _term_row_to_out(r: list, mappings_count: int = 0) -> TermOut:
    return TermOut(
        term_id=r[0],
        canonical_name=r[1],
        definition=r[2] or "",
        synonyms=list(r[3]) if r[3] else [],
        domain=r[4],
        conceptual_type=cast(ConceptualType, r[5]) if r[5] else None,
        valid_examples=list(r[6]) if r[6] else [],
        owner_person=r[7],
        status=cast(TermStatus, r[8]),
        approved_by=r[9],
        approved_at=r[10],
        created_at=r[11],
        created_by=r[12],
        updated_at=r[13],
        updated_by=r[14],
        mappings_count=mappings_count,
    )


# -------------------- Terms --------------------


@router.get("/terms", response_model=list[TermListOut], operation_id="listTerms")
def list_terms(
    sql: SqlDependency,
    status: TermStatus | None = Query(None),
    domain: str | None = Query(None),
    q: str | None = Query(None, description="Full-text search on canonical_name + definition"),
) -> list[TermListOut]:
    s = get_settings()
    where: list[str] = []
    params: list = []
    if status:
        where.append("t.status = :status")
        params.append(delta.param("status", str(status)))
    if domain:
        where.append("t.domain = :domain")
        params.append(delta.param("domain", domain))
    if q:
        # LIKE pattern with bound parameter — :q already contains the %wildcards%
        where.append(
            "(lower(t.canonical_name) LIKE :q OR lower(t.definition) LIKE :q)"
        )
        params.append(delta.param("q", f"%{q.lower()}%"))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT t.term_id, t.canonical_name, t.domain, t.conceptual_type,
               t.status, t.owner_person, t.updated_at,
               (SELECT COUNT(*) FROM {s.fq_table('glossary_mappings')} m
                WHERE m.term_id = t.term_id) AS mappings_count
        FROM {s.fq_table('glossary_terms')} t
        {where_clause}
        ORDER BY t.canonical_name ASC
        LIMIT 500
        """,
        params,
    )
    return [
        TermListOut(
            term_id=r[0],
            canonical_name=r[1],
            domain=r[2],
            conceptual_type=cast(ConceptualType, r[3]) if r[3] else None,
            status=cast(TermStatus, r[4]),
            owner_person=r[5],
            updated_at=r[6],
            mappings_count=int(r[7] or 0),
        )
        for r in rows
    ]


@router.get("/terms/{term_id}", response_model=TermOut, operation_id="getTerm")
def get_term(term_id: str, sql: SqlDependency) -> TermOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('t.'+c for c in _TERM_COLS)},
               (SELECT COUNT(*) FROM {s.fq_table('glossary_mappings')} m
                WHERE m.term_id = t.term_id) AS mappings_count
        FROM {s.fq_table('glossary_terms')} t
        WHERE t.term_id = :term_id
        """,
        [delta.param("term_id", term_id)],
    )
    if not row:
        raise HTTPException(404, f"term '{term_id}' not found")
    return _term_row_to_out(row[:-1], mappings_count=int(row[-1] or 0))


@router.post("/terms", response_model=TermOut, operation_id="createTerm")
def create_term(
    payload: TermIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TermOut:
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    tid = delta.new_id("term-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("glossary_terms"),
        {
            "term_id": tid,
            "canonical_name": payload.canonical_name,
            "definition": payload.definition,
            "synonyms": payload.synonyms,
            "domain": payload.domain,
            "conceptual_type": payload.conceptual_type,
            "valid_examples": payload.valid_examples,
            "owner_person": payload.owner_person,
            "status": "DRAFT",
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_term(tid, sql)


@router.put("/terms/{term_id}", response_model=TermOut, operation_id="updateTerm")
def update_term(
    term_id: str,
    payload: TermIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TermOut:
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    current = get_term(term_id, sql)
    # Once APPROVED, editing requires ARCHITECT or ADMIN
    if current.status == "APPROVED":
        require_role(sql, actor, *ARCHITECT_OR_ADMIN)
    delta.update_by_id(
        sql,
        s.fq_table("glossary_terms"),
        "term_id",
        term_id,
        {
            "canonical_name": payload.canonical_name,
            "definition": payload.definition,
            "synonyms": payload.synonyms,
            "domain": payload.domain,
            "conceptual_type": payload.conceptual_type,
            "valid_examples": payload.valid_examples,
            "owner_person": payload.owner_person,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_term(term_id, sql)


@router.post(
    "/terms/{term_id}/transitions",
    response_model=TermOut,
    operation_id="transitionTerm",
)
def transition_term(
    term_id: str,
    payload: TermTransition,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TermOut:
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    current = get_term(term_id, sql)
    src = current.status
    dst = payload.to

    # Define allowed transitions and the role gates
    if src == "DRAFT" and dst == "IN_REVIEW":
        pass  # any user
    elif src == "IN_REVIEW" and dst == "APPROVED":
        require_role(sql, actor, *APPROVERS)
    elif src == "APPROVED" and dst == "DEPRECATED":
        require_role(sql, actor, *ARCHITECT_OR_ADMIN)
    elif dst == "DRAFT":
        # Allowed only for the creator (or admin/architect)
        if current.created_by != actor and not has_role(sql, actor, *ARCHITECT_OR_ADMIN):
            raise HTTPException(
                403,
                "Only the creator (or ARCHITECT/ADMIN) can return a term to DRAFT",
            )
    elif src == dst:
        raise HTTPException(409, f"term already in status {src}")
    else:
        raise HTTPException(
            409,
            f"transition not allowed: {src} -> {dst}",
        )

    now = datetime.utcnow()
    updates: dict = {
        "status": dst,
        "updated_at": now,
        "updated_by": actor,
    }
    if dst == "APPROVED":
        updates["approved_at"] = now
        updates["approved_by"] = actor
    delta.update_by_id(
        sql, s.fq_table("glossary_terms"), "term_id", term_id, updates,
    )
    return get_term(term_id, sql)


@router.delete("/terms/{term_id}", operation_id="deleteTerm")
def delete_term(
    term_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    actor = _current_email(user_ws) or "unknown"
    require_role(sql, actor, *ARCHITECT_OR_ADMIN)
    s = get_settings()
    # Soft delete: mark as DEPRECATED
    delta.update_by_id(
        sql,
        s.fq_table("glossary_terms"),
        "term_id",
        term_id,
        {
            "status": "DEPRECATED",
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return {"deprecated": term_id}


# -------------------- Mappings --------------------


_MAPPING_JOIN_SELECT = """
    m.mapping_id, m.term_id, m.attribute_id,
    m.inherit_description, m.override_description, m.type_compat_warning,
    m.created_at, m.created_by,
    t.canonical_name, t.status, t.conceptual_type, t.definition,
    a.technical_name AS attr_technical_name, a.logical_name AS attr_logical_name,
    a.native_data_type,
    e.entity_id, e.technical_name AS ent_technical_name, e.schema_name,
    e.system_id, sys.system_name
"""


def _mapping_row_to_out(r: list) -> MappingOut:
    return MappingOut(
        mapping_id=r[0],
        term_id=r[1],
        attribute_id=r[2],
        inherit_description=delta.as_bool(r[3]),
        override_description=r[4],
        type_compat_warning=delta.as_bool(r[5]),
        created_at=r[6],
        created_by=r[7],
        term_canonical_name=r[8],
        term_status=cast(TermStatus, r[9]) if r[9] else None,
        term_conceptual_type=cast(ConceptualType, r[10]) if r[10] else None,
        term_definition=r[11],
        attribute_technical_name=r[12],
        attribute_logical_name=r[13],
        native_data_type=r[14],
        entity_id=r[15],
        entity_technical_name=r[16],
        schema_name=r[17],
        system_id=r[18],
        system_name=r[19],
    )


@router.get(
    "/terms/{term_id}/mappings",
    response_model=list[MappingOut],
    operation_id="listTermMappings",
)
def list_term_mappings(term_id: str, sql: SqlDependency) -> list[MappingOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {_MAPPING_JOIN_SELECT}
        FROM {s.fq_table('glossary_mappings')} m
        LEFT JOIN {s.fq_table('glossary_terms')} t ON t.term_id = m.term_id
        LEFT JOIN {s.fq_table('attributes')} a ON a.attribute_id = m.attribute_id
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE m.term_id = :term_id
        ORDER BY sys.system_name, e.schema_name, e.technical_name, a.technical_name
        """,
        [delta.param("term_id", term_id)],
    )
    return [_mapping_row_to_out(r) for r in rows]


@router.post(
    "/terms/{term_id}/mappings",
    response_model=MappingOut,
    operation_id="createMapping",
)
def create_mapping(
    term_id: str,
    payload: MappingIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> MappingOut:
    if payload.term_id != term_id:
        raise HTTPException(400, "term_id in path and payload must match")
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"

    # Validate target attribute exists and get its native data type
    attr = delta.fetch_one_params(
        sql,
        f"""
        SELECT a.attribute_id, a.native_data_type
        FROM {s.fq_table('attributes')} a
        WHERE a.attribute_id = :attribute_id
        """,
        [delta.param("attribute_id", payload.attribute_id)],
    )
    if not attr:
        raise HTTPException(404, f"attribute '{payload.attribute_id}' not found")

    # Read term conceptual_type for type-compat check
    term_row = delta.fetch_one_params(
        sql,
        f"SELECT conceptual_type FROM {s.fq_table('glossary_terms')} "
        f"WHERE term_id = :term_id",
        [delta.param("term_id", term_id)],
    )
    if not term_row:
        raise HTTPException(404, f"term '{term_id}' not found")
    conceptual_type = term_row[0]
    native_data_type = attr[1]

    compatible = check_type_compat(conceptual_type, native_data_type)
    warning = not compatible

    # Reject duplicate mapping (same term + same attribute)
    dup = delta.fetch_one_params(
        sql,
        f"""
        SELECT mapping_id FROM {s.fq_table('glossary_mappings')}
        WHERE term_id = :term_id
          AND attribute_id = :attribute_id
        """,
        [
            delta.param("term_id", term_id),
            delta.param("attribute_id", payload.attribute_id),
        ],
    )
    if dup:
        raise HTTPException(409, "mapping already exists for this term/attribute")

    mid = delta.new_id("map-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("glossary_mappings"),
        {
            "mapping_id": mid,
            "term_id": term_id,
            "attribute_id": payload.attribute_id,
            "inherit_description": payload.inherit_description,
            "override_description": payload.override_description,
            "type_compat_warning": warning,
            "created_at": now,
            "created_by": actor,
        },
    )

    # If no glossary_term_id was set on the attribute, set this term as primary
    delta.run_params(
        sql,
        f"""
        UPDATE {s.fq_table('attributes')}
        SET glossary_term_id = :term_id,
            updated_at = current_timestamp(),
            updated_by = :actor
        WHERE attribute_id = :attribute_id
          AND (glossary_term_id IS NULL OR glossary_term_id = '')
        """,
        [
            delta.param("term_id", term_id),
            delta.param("actor", actor),
            delta.param("attribute_id", payload.attribute_id),
        ],
    )

    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {_MAPPING_JOIN_SELECT}
        FROM {s.fq_table('glossary_mappings')} m
        LEFT JOIN {s.fq_table('glossary_terms')} t ON t.term_id = m.term_id
        LEFT JOIN {s.fq_table('attributes')} a ON a.attribute_id = m.attribute_id
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE m.mapping_id = :mapping_id
        """,
        [delta.param("mapping_id", mid)],
    )
    if not row:
        raise HTTPException(500, "mapping create failed")
    return _mapping_row_to_out(row)


@router.delete("/mappings/{mapping_id}", operation_id="deleteMapping")
def delete_mapping(
    mapping_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    s = get_settings()
    # Discover the attribute_id and term_id before deleting so we can
    # un-pin the primary term reference on the attribute if it matches.
    row = delta.fetch_one_params(
        sql,
        f"SELECT term_id, attribute_id FROM {s.fq_table('glossary_mappings')} "
        f"WHERE mapping_id = :mapping_id",
        [delta.param("mapping_id", mapping_id)],
    )
    if not row:
        raise HTTPException(404, f"mapping '{mapping_id}' not found")
    term_id, attribute_id = row[0], row[1]
    delta.delete_by_id(sql, s.fq_table("glossary_mappings"), "mapping_id", mapping_id)
    # If this was the primary term reference and no other mapping exists, clear
    remaining = delta.fetch_one_params(
        sql,
        f"SELECT mapping_id FROM {s.fq_table('glossary_mappings')} "
        f"WHERE attribute_id = :attribute_id "
        f"AND term_id = :term_id",
        [
            delta.param("attribute_id", attribute_id),
            delta.param("term_id", term_id),
        ],
    )
    if not remaining:
        delta.run_params(
            sql,
            f"""
            UPDATE {s.fq_table('attributes')}
            SET glossary_term_id = NULL,
                updated_at = current_timestamp()
            WHERE attribute_id = :attribute_id
              AND glossary_term_id = :term_id
            """,
            [
                delta.param("attribute_id", attribute_id),
                delta.param("term_id", term_id),
            ],
        )
    return {"deleted": mapping_id}


# -------------------- Reverse lookup: attribute -> terms --------------------


@attr_glossary_router.get(
    "/{attribute_id}/glossary",
    response_model=list[MappingOut],
    operation_id="listAttributeGlossary",
)
def list_attribute_glossary(attribute_id: str, sql: SqlDependency) -> list[MappingOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {_MAPPING_JOIN_SELECT}
        FROM {s.fq_table('glossary_mappings')} m
        LEFT JOIN {s.fq_table('glossary_terms')} t ON t.term_id = m.term_id
        LEFT JOIN {s.fq_table('attributes')} a ON a.attribute_id = m.attribute_id
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE m.attribute_id = :attribute_id
        ORDER BY t.canonical_name
        """,
        [delta.param("attribute_id", attribute_id)],
    )
    return [_mapping_row_to_out(r) for r in rows]
