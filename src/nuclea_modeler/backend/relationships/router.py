"""Module — Relationships CRUD (manual, complements EXTRACTED relations).

Modelo editorial: mutations (POST/PUT/DELETE) NÃO escrevem direto no catálogo.
Elas são staged num ticket OPEN de sessão do user. O ticket é aplicado depois
via /tickets/{id}/apply quando aprovado.

Como o DiffEntity (do helper de sessão) modela mudanças de entity, codificamos
mudanças de relationships como entries com schema_name='__relationship__' e
technical_name=<relationship_id ou par src->tgt>. O payload carrega os campos
do relationship. apply_ticket ainda não materializa relationships — issue
separado pra implementar isso (mantém compat com o contrato atual).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..tickets.session import get_or_create_session_ticket, stage_entity_change
from .models import RelationshipIn, RelationshipListOut, RelationshipOut

router = APIRouter(prefix=f"{api_prefix}/relationships", tags=["relationships"])


_REL_COLS = [
    "relationship_id", "system_id", "source_entity_id", "target_entity_id",
    "source_attr_ids", "target_attr_ids", "rel_type",
    "source_cardinality", "target_cardinality", "description", "origin",
    "fk_update_rule", "fk_delete_rule", "relationship_name",
    "created_at", "created_by", "updated_at", "updated_by",
]

# Schema "synthetic" usado no DiffEntity pra distinguir entries de relationship
# de entries de entity de verdade. Reads do diff podem filtrar por isso.
_REL_SCHEMA_MARKER = "__relationship__"


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
        relationship_name=r[13] or None,  # Novo
        created_at=r[14],
        created_by=r[15],
        updated_at=r[16],
        updated_by=r[17],
        system_name=r[18] if len(r) > 18 else None,
        source_entity_label=_entity_label(
            r[19] if len(r) > 19 else None,
            r[20] if len(r) > 20 else None,
        ),
        target_entity_label=_entity_label(
            r[21] if len(r) > 21 else None,
            r[22] if len(r) > 22 else None,
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


def _virtual_entity_in_session(
    sql: SqlDependency, user_email: str, system_id: str, entity_id: str,
) -> dict | None:
    """Procura uma entity virtual (op=add com pre_allocated_entity_id) na
    sessão OPEN do user pro sistema. Retorna {system_id, is_shared} ou None.

    Permite que o frontend referencie entities ainda staged (não committed)
    como source/target de relacionamentos — o relacionamento entra na MESMA
    sessão e tudo é materializado junto no apply.
    """
    from ..tickets.session import find_open_session_ticket  # avoid circular

    found = find_open_session_ticket(sql, user_email, system_id)
    if not found:
        return None
    _, diff = found
    for e in diff.get("entities", []) or []:
        if not isinstance(e, dict) or e.get("op") != "add":
            continue
        if e.get("schema_name") == "__relationship__":
            continue
        payload = e.get("payload") or {}
        pid = payload.get("pre_allocated_entity_id")
        if pid == entity_id:
            return {
                "system_id": system_id,
                "is_shared": bool(payload.get("is_shared", False)),
                "virtual": True,
            }
    return None


def _validate_entities(
    sql: SqlDependency,
    system_id: str,
    source_entity_id: str,
    target_entity_id: str,
    *,
    actor: str | None = None,
) -> None:
    """Confere que os entities existem (no catálogo OU virtuais na sessão do
    user atual) e que cross-system só é permitido quando o target é marcado
    como `is_shared=true`.
    """
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, system_id, COALESCE(is_shared, false) AS is_shared
        FROM {s.fq_table('entities')}
        WHERE entity_id IN (:source_id, :target_id)
        """,
        [
            delta.param("source_id", source_entity_id),
            delta.param("target_id", target_entity_id),
        ],
    )
    found: dict[str, dict] = {
        r[0]: {"system_id": r[1], "is_shared": delta.as_bool(r[2]), "virtual": False}
        for r in rows
    }
    # Fallback: source/target podem estar virtuais na sessão OPEN do user
    if actor:
        if source_entity_id not in found:
            vsrc = _virtual_entity_in_session(sql, actor, system_id, source_entity_id)
            if vsrc:
                found[source_entity_id] = vsrc
        if target_entity_id not in found:
            vtgt = _virtual_entity_in_session(sql, actor, system_id, target_entity_id)
            if vtgt:
                found[target_entity_id] = vtgt

    if source_entity_id not in found:
        raise HTTPException(400, f"source_entity_id '{source_entity_id}' not found")
    if target_entity_id not in found:
        raise HTTPException(400, f"target_entity_id '{target_entity_id}' not found")
    if found[source_entity_id]["system_id"] != system_id:
        raise HTTPException(
            400,
            f"source entity belongs to system '{found[source_entity_id]['system_id']}', "
            f"not '{system_id}'",
        )
    if found[target_entity_id]["system_id"] != system_id:
        if not found[target_entity_id]["is_shared"]:
            raise HTTPException(
                400,
                f"target entity está em outro sistema "
                f"('{found[target_entity_id]['system_id']}') e não está marcada "
                f"como compartilhada (is_shared=true). Marque-a como compartilhada "
                f"no sistema de origem ou crie a referência no sistema dela.",
            )


def _relationship_in_to_payload(
    payload: RelationshipIn, *, origin: str = "MANUAL"
) -> dict:
    return {
        "system_id": payload.system_id,
        "source_entity_id": payload.source_entity_id,
        "target_entity_id": payload.target_entity_id,
        "source_attr_ids": list(payload.source_attr_ids),
        "target_attr_ids": list(payload.target_attr_ids),
        "rel_type": payload.rel_type,
        "source_cardinality": payload.source_cardinality,
        "target_cardinality": payload.target_cardinality,
        "description": payload.description,
        "origin": origin,
        "fk_update_rule": payload.fk_update_rule,
        "fk_delete_rule": payload.fk_delete_rule,
        # Sem isto o nome digitado se perdia entre o staging e o apply (a coluna
        # existe desde a migration 019, mas nunca era gravada). round 5.
        "relationship_name": payload.relationship_name,
    }


def _virtual_relationship_out(
    relationship_id: str,
    payload: RelationshipIn,
    actor: str,
    *,
    source_label: str | None = None,
    target_label: str | None = None,
) -> RelationshipOut:
    now = datetime.utcnow()
    return RelationshipOut(
        relationship_id=relationship_id,
        system_id=payload.system_id,
        system_name=None,
        source_entity_id=payload.source_entity_id,
        source_entity_label=source_label,
        target_entity_id=payload.target_entity_id,
        target_entity_label=target_label,
        source_attr_ids=list(payload.source_attr_ids),
        target_attr_ids=list(payload.target_attr_ids),
        rel_type=payload.rel_type,
        source_cardinality=payload.source_cardinality,
        target_cardinality=payload.target_cardinality,
        description=payload.description,
        origin="MANUAL",
        fk_update_rule=payload.fk_update_rule,
        fk_delete_rule=payload.fk_delete_rule,
        relationship_name=payload.relationship_name,
        created_at=now,
        created_by=actor,
        updated_at=now,
        updated_by=actor,
    )


def _entity_labels(sql, source_id: str, target_id: str) -> tuple[str | None, str | None]:
    """Fetch (schema.technical_name) labels for src/tgt entities — best effort."""
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name
        FROM {s.fq_table('entities')}
        WHERE entity_id IN (:src, :tgt)
        """,
        [delta.param("src", source_id), delta.param("tgt", target_id)],
    )
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    src = by_id.get(source_id)
    tgt = by_id.get(target_id)
    return (
        _entity_label(src[0], src[1]) if src else None,
        _entity_label(tgt[0], tgt[1]) if tgt else None,
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
            # Índices seguem _REL_COLS + os 5 joins (system_name, src/tgt schema+tech).
            # relationship_name (r[13]) empurrou os timestamps: created_at=r[14],
            # created_by=r[15], updated_at=r[16], updated_by=r[17]; e os joins começam
            # em r[18]. (Antes lia r[15]/r[17] — pegava created_by/updated_by e
            # estourava datetime_from_date_parsing.)
            system_name=r[18],
            source_entity_id=r[2],
            source_entity_label=_entity_label(r[19], r[20]),
            target_entity_id=r[3],
            target_entity_label=_entity_label(r[21], r[22]),
            rel_type=r[6] or None,
            source_cardinality=r[7] or None,
            target_cardinality=r[8] or None,
            origin=r[10] or None,
            description=r[9],
            relationship_name=r[13] or None,
            updated_at=r[16],
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
    """Stage criação de relationship. NÃO grava no catálogo — vai pro ticket OPEN."""
    actor = _current_email(user_ws) or "unknown"
    _validate_entities(
        sql, payload.system_id, payload.source_entity_id, payload.target_entity_id,
        actor=actor,
    )
    rid = delta.new_id("rel-")
    ticket_id, diff = get_or_create_session_ticket(sql, actor, payload.system_id)
    rel_payload = _relationship_in_to_payload(payload, origin="MANUAL")
    rel_payload["relationship_id"] = rid
    entry = {
        "op": "add",
        "schema_name": _REL_SCHEMA_MARKER,
        "technical_name": rid,
        "entity_type": "RELATIONSHIP",
        "payload": rel_payload,
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    src_label, tgt_label = _entity_labels(
        sql, payload.source_entity_id, payload.target_entity_id,
    )
    return _virtual_relationship_out(
        rid, payload, actor, source_label=src_label, target_label=tgt_label,
    )


@router.put("/{relationship_id}", response_model=RelationshipOut, operation_id="updateRelationship")
def update_relationship(
    relationship_id: str,
    payload: RelationshipIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> RelationshipOut:
    """Stage update de relationship no ticket OPEN."""
    actor = _current_email(user_ws) or "unknown"
    _validate_entities(
        sql, payload.system_id, payload.source_entity_id, payload.target_entity_id,
        actor=actor,
    )
    ticket_id, diff = get_or_create_session_ticket(sql, actor, payload.system_id)
    rel_payload = _relationship_in_to_payload(payload)
    rel_payload["relationship_id"] = relationship_id
    entry = {
        "op": "change",
        "schema_name": _REL_SCHEMA_MARKER,
        "technical_name": relationship_id,
        "entity_type": "RELATIONSHIP",
        "payload": rel_payload,
        "field_changes": [
            {"field": "relationship_update", "before": None, "after": rel_payload}
        ],
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    src_label, tgt_label = _entity_labels(
        sql, payload.source_entity_id, payload.target_entity_id,
    )
    return _virtual_relationship_out(
        relationship_id, payload, actor,
        source_label=src_label, target_label=tgt_label,
    )


@router.delete("/{relationship_id}", operation_id="deleteRelationship")
def delete_relationship(
    relationship_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Stage delete de relationship no ticket OPEN.

    Precisa ler o system_id do catálogo pra abrir o ticket de sessão correto.
    """
    s = get_settings()
    actor = _current_email(user_ws) or "unknown"
    row = delta.fetch_one_params(
        sql,
        f"SELECT system_id FROM {s.fq_table('relationships')} "
        f"WHERE relationship_id = :relationship_id",
        [delta.param("relationship_id", relationship_id)],
    )
    if not row:
        raise HTTPException(404, f"relationship '{relationship_id}' not found")
    system_id = row[0]
    ticket_id, diff = get_or_create_session_ticket(sql, actor, system_id)
    entry = {
        "op": "remove",
        "schema_name": _REL_SCHEMA_MARKER,
        "technical_name": relationship_id,
        "entity_type": "RELATIONSHIP",
        "payload": {"relationship_id": relationship_id},
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return {"deleted": relationship_id, "pending": True, "ticket_id": ticket_id}
