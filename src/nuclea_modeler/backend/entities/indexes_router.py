"""Endpoints CRUD pra índices + particionamento por entity.

Extraído de ``entities/router.py`` em refactor estrutural — o router
original ficou >1200 linhas concentrando entities + attributes + indexes +
partitioning. Aqui só índices e partição; comportamento idêntico.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..tickets.session import find_open_session_ticket
from .index_validation import IndexValidationWarning, validate_indexes
from .indexes import (
    get_partitioning,
    list_indexes_for_entity,
    stage_index_add,
    stage_index_remove,
    stage_index_update,
    stage_partitioning_set,
)
from .models import (
    EntityIndexIn,
    EntityIndexOut,
    EntityPartitioningIn,
    EntityPartitioningOut,
)

router = APIRouter(prefix=f"{api_prefix}/entities", tags=["entities"])


# ─── Helpers locais ─────────────────────────────────────────────────────────


def _resolve_entity_keys(sql, entity_id: str) -> tuple[str, str, str, str] | None:
    """Retorna (system_id, schema_name, technical_name, entity_type)."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT system_id, schema_name, technical_name, entity_type
        FROM {s.fq_table('entities')}
        WHERE entity_id = :entity_id
        """,
        [delta.param("entity_id", entity_id)],
    )
    if not row:
        return None
    return (row[0], row[1], row[2], row[3] or "TABLE")


def _session_diff_for_entity(sql, user_ws, entity_id: str) -> dict | None:
    """Resolve o diff da sessão OPEN do user para a entity. None se não há."""
    actor = _current_email(user_ws) or "unknown"
    keys = _resolve_entity_keys(sql, entity_id)
    if not keys or actor == "unknown":
        return None
    system_id = keys[0]
    found = find_open_session_ticket(sql, actor, system_id)
    return found[1] if found else None


# ─── Indexes ─────────────────────────────────────────────────────────────────


@router.get(
    "/{entity_id}/indexes",
    response_model=list[EntityIndexOut],
    operation_id="listEntityIndexes",
)
def list_entity_indexes(
    entity_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> list[EntityIndexOut]:
    """Lista índices da entity com overlay do ticket OPEN do user — mudanças
    pendentes (add/change/remove) aparecem inline com badge."""
    diff = _session_diff_for_entity(sql, user_ws, entity_id)
    return list_indexes_for_entity(sql, entity_id, session_diff=diff)


@router.post(
    "/{entity_id}/indexes",
    response_model=EntityIndexOut,
    operation_id="createEntityIndex",
)
def create_entity_index(
    entity_id: str,
    payload: EntityIndexIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityIndexOut:
    """Stage criação de índice no ticket OPEN. Não grava no catálogo."""
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id in path and payload must match")
    actor = _current_email(user_ws) or "unknown"
    iid = delta.new_id("idx-")
    res = stage_index_add(
        sql, actor=actor, entity_id=entity_id, index_id=iid, payload=payload,
    )
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return EntityIndexOut(
        index_id=iid,
        entity_id=entity_id,
        index_name=payload.index_name,
        index_type=payload.index_type,
        columns=payload.columns,
        include_columns=payload.include_columns,
        partial_where=payload.partial_where,
        is_unique=payload.is_unique,
        description_md=payload.description_md,
        native_comment=payload.native_comment,
        origin="MANUAL",
        created_at=datetime.utcnow(),
        created_by=actor,
        updated_at=datetime.utcnow(),
        updated_by=actor,
        pending_op="add",
    )


@router.put(
    "/{entity_id}/indexes/{index_id}",
    response_model=EntityIndexOut,
    operation_id="updateEntityIndex",
)
def update_entity_index(
    entity_id: str,
    index_id: str,
    payload: EntityIndexIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityIndexOut:
    """Stage update de índice no ticket OPEN. Replace-style."""
    actor = _current_email(user_ws) or "unknown"
    res = stage_index_update(
        sql, actor=actor, entity_id=entity_id, index_id=index_id, payload=payload,
    )
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return EntityIndexOut(
        index_id=index_id,
        entity_id=entity_id,
        index_name=payload.index_name,
        index_type=payload.index_type,
        columns=payload.columns,
        include_columns=payload.include_columns,
        partial_where=payload.partial_where,
        is_unique=payload.is_unique,
        description_md=payload.description_md,
        native_comment=payload.native_comment,
        origin="MANUAL",
        created_at=datetime.utcnow(),
        created_by=actor,
        updated_at=datetime.utcnow(),
        updated_by=actor,
        pending_op="change",
    )


@router.delete(
    "/{entity_id}/indexes/{index_id}",
    operation_id="deleteEntityIndex",
)
def delete_entity_index(
    entity_id: str,
    index_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Stage delete de índice no ticket OPEN."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT index_name FROM {s.fq_table('entity_indexes')} WHERE index_id = :index_id",
        [delta.param("index_id", index_id)],
    )
    idx_name = row[0] if row else index_id
    actor = _current_email(user_ws) or "unknown"
    res = stage_index_remove(
        sql, actor=actor, entity_id=entity_id, index_id=index_id, index_name=idx_name,
    )
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    ticket_id, _ = res
    return {"deleted": index_id, "pending": True, "ticket_id": ticket_id}


@router.get(
    "/{entity_id}/indexes/validate",
    response_model=list[IndexValidationWarning],
    operation_id="validateEntityIndexes",
)
def validate_entity_indexes(
    entity_id: str, sql: SqlDependency,
) -> list[IndexValidationWarning]:
    """Roda validações semânticas: PK duplicada, índices redundantes,
    particionamento sobre coluna inválida. Não bloqueia mutations — só
    alimenta avisos na UI."""
    s = get_settings()
    attr_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT technical_name, is_primary_key, is_nullable
        FROM {s.fq_table('attributes')}
        WHERE entity_id = :entity_id
        ORDER BY COALESCE(ordinal_position, 999999), technical_name
        """,
        [delta.param("entity_id", entity_id)],
    )
    attributes = [
        {
            "technical_name": r[0],
            "is_primary_key": delta.as_bool(r[1]),
            "is_nullable": delta.as_bool(r[2]) if r[2] is not None else None,
        }
        for r in attr_rows
    ]
    indexes = [ix.model_dump() for ix in list_indexes_for_entity(sql, entity_id)]
    part = get_partitioning(sql, entity_id)
    partitioning = part.model_dump() if part else None
    return validate_indexes(
        attributes=attributes, indexes=indexes, partitioning=partitioning,
    )


# ─── Partitioning ────────────────────────────────────────────────────────────


@router.get(
    "/{entity_id}/partitioning",
    response_model=EntityPartitioningOut,
    operation_id="getEntityPartitioning",
)
def get_entity_partitioning(
    entity_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityPartitioningOut:
    """Retorna a estratégia de particionamento com overlay do ticket OPEN."""
    diff = _session_diff_for_entity(sql, user_ws, entity_id)
    part = get_partitioning(sql, entity_id, session_diff=diff)
    if part:
        return part
    return EntityPartitioningOut(
        entity_id=entity_id,
        strategy="NONE",
        columns=[],
    )


@router.put(
    "/{entity_id}/partitioning",
    response_model=EntityPartitioningOut,
    operation_id="setEntityPartitioning",
)
def set_entity_partitioning(
    entity_id: str,
    payload: EntityPartitioningIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityPartitioningOut:
    """Stage estratégia de particionamento no ticket OPEN. Replace-style."""
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id in path and payload must match")
    actor = _current_email(user_ws) or "unknown"
    res = stage_partitioning_set(
        sql, actor=actor, entity_id=entity_id, payload=payload,
    )
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return EntityPartitioningOut(
        entity_id=entity_id,
        strategy=payload.strategy,
        columns=payload.columns,
        num_partitions=payload.num_partitions,
        bounds=payload.bounds,
        description_md=payload.description_md,
        origin="MANUAL",
        pending_op="change",
    )
