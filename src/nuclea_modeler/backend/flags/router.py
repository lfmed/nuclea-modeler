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
    BatchFlagApplyIn,
    BatchFlagItemResult,
    BatchFlagRemoveIn,
    BatchFlagResult,
    EntityFlagApplyIn,
    EntityFlagOut,
    FlagCategory,
    FlagIn,
    FlagOut,
    FlagPatch,
    RelationshipFlagApplyIn,
    RelationshipFlagOut,
)


router = APIRouter(prefix=f"{api_prefix}/flags", tags=["flags"])
entity_router = APIRouter(prefix=f"{api_prefix}/entities", tags=["flags"])
attribute_router = APIRouter(prefix=f"{api_prefix}/attributes", tags=["flags"])
relationship_router = APIRouter(prefix=f"{api_prefix}/relationships", tags=["flags"])


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


def _summarize_batch(
    action: str, results: list[BatchFlagItemResult]
) -> BatchFlagResult:
    """Consolida os itens de um lote no formato total/succeeded/failed (mesmo
    contrato de BatchTicketResult, para a UI tratar tudo igual)."""
    succeeded = sum(1 for r in results if r.ok)
    return BatchFlagResult(
        action=action,  # type: ignore[arg-type]
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


# NOTA DE ROTEAMENTO: os endpoints /batch/flags são declarados ANTES das rotas
# dinâmicas /{entity_id}/flags. O FastAPI casa por ordem de declaração; se a rota
# dinâmica viesse primeiro, "POST /entities/batch/flags" cairia nela com
# entity_id="batch". Por isso batch vem primeiro.

@entity_router.post(
    "/batch/flags",
    response_model=BatchFlagResult,
    operation_id="batchApplyEntityFlags",
)
def batch_apply_entity_flags(
    payload: BatchFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Aplica VÁRIAS flags a VÁRIAS entidades numa única chamada.

    Resolve o atrito de "aplicar flag em N entidades" sem inflar tickets. Cada par
    (entidade, flag) vira um item em `results` — o lote não aborta por causa de um
    item (ex.: flag LGPD sem justificativa falha só naquele item). Idempotente:
    reaplicar flag já presente conta como sucesso.
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    # Cache de flags para não refazer o SELECT do catálogo por par (alvo, flag).
    flag_cache: dict[str, FlagOut] = {}
    results: list[BatchFlagItemResult] = []
    for spec in payload.flags:
        try:
            flag = flag_cache.get(spec.flag_id) or _fetch_flag(sql, spec.flag_id)
            flag_cache[spec.flag_id] = flag
            _validate_flag_applicable(flag, spec.justification)
        except HTTPException as exc:
            # Flag inválida/ausente ou justificativa faltando → falha para TODOS
            # os alvos desta flag (o alvo em si não foi tocado).
            for tid in payload.target_ids:
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc.detail),
                ))
            continue
        for tid in payload.target_ids:
            try:
                efid = _apply_entity_flag_core(
                    sql, entity_id=tid, flag=flag,
                    justification=spec.justification, actor=actor,
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=True,
                    applied_flag_id=efid,
                ))
            except Exception as exc:  # noqa: BLE001 — lote não aborta por 1 item
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc)[:300],
                ))
    return _summarize_batch("apply", results)


@entity_router.post(
    "/batch/flags/remove",
    response_model=BatchFlagResult,
    operation_id="batchRemoveEntityFlags",
)
def batch_remove_entity_flags(
    payload: BatchFlagRemoveIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Remove VÁRIAS flags de VÁRIAS entidades numa única chamada.

    Remove por `flag_id` (não pelo id da linha), pois o lote cobre muitos alvos.
    Idempotente: remover flag ausente conta como sucesso. Usamos POST (e não DELETE)
    porque o corpo carrega listas — DELETE com body tem suporte irregular.
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    s = get_settings()
    results: list[BatchFlagItemResult] = []
    for fid in payload.flag_ids:
        for tid in payload.target_ids:
            try:
                delta.run_params(
                    sql,
                    f"DELETE FROM {s.fq_table('entity_flags')} "
                    f"WHERE entity_id = :entity_id AND flag_id = :flag_id",
                    [
                        delta.param("entity_id", tid),
                        delta.param("flag_id", fid),
                    ],
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=True,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=False, error=str(exc)[:300],
                ))
    return _summarize_batch("remove", results)


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
    _validate_flag_applicable(flag, payload.justification)
    efid = _apply_entity_flag_core(
        sql,
        entity_id=entity_id,
        flag=flag,
        justification=payload.justification,
        actor=actor,
    )
    return _entity_flag_by_id(sql, efid)


def _validate_flag_applicable(flag: FlagOut, justification: str | None) -> None:
    """Regras compartilhadas entre apply single-id e batch: flag ativa e
    justificativa presente quando exigida. Levanta HTTPException(400)."""
    if not flag.is_active:
        raise HTTPException(400, f"flag '{flag.flag_key}' is inactive")
    if flag.requires_justification and not (justification or "").strip():
        raise HTTPException(
            400,
            f"flag '{flag.flag_key}' requires a non-empty justification",
        )


def _apply_entity_flag_core(
    sql: Sql,
    *,
    entity_id: str,
    flag: FlagOut,
    justification: str | None,
    actor: str,
) -> str:
    """Insere (ou reaproveita) a flag na entidade e devolve o entity_flag_id.

    Idempotente: se a mesma flag já está aplicada, retorna o id existente sem
    inserir de novo. Extraído do endpoint single-id para o batch reutilizar
    exatamente a mesma lógica de persistência.
    """
    s = get_settings()
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
        return existing[0]
    efid = delta.new_id("entflag-")
    delta.insert(
        sql,
        s.fq_table("entity_flags"),
        {
            "entity_flag_id": efid,
            "entity_id": entity_id,
            "flag_id": flag.flag_id,
            "justification": justification,
            "applied_at": datetime.utcnow(),
            "applied_by": actor,
            "applied_in_version": None,
            "is_propagated": False,
        },
    )
    return efid


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


# NOTA DE ROTEAMENTO: batch antes das rotas dinâmicas /{attribute_id}/flags,
# pela mesma razão dos endpoints de entidade (evitar attribute_id="batch").

@attribute_router.post(
    "/batch/flags",
    response_model=BatchFlagResult,
    operation_id="batchApplyAttributeFlags",
)
def batch_apply_attribute_flags(
    payload: BatchFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Aplica VÁRIAS flags a VÁRIOS atributos numa única chamada.

    Este é o endpoint que mata os ~250 cliques do cenário do cliente (50 atributos
    × 5 flags). Cada par (atributo, flag) vira um item em `results` — o lote não
    aborta por um item. Idempotente. Preserva a propagação LGPD atributo→entidade
    reutilizando `_apply_attribute_flag_core`.
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    flag_cache: dict[str, FlagOut] = {}
    results: list[BatchFlagItemResult] = []
    for spec in payload.flags:
        try:
            flag = flag_cache.get(spec.flag_id) or _fetch_flag(sql, spec.flag_id)
            flag_cache[spec.flag_id] = flag
            _validate_flag_applicable(flag, spec.justification)
        except HTTPException as exc:
            for tid in payload.target_ids:
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc.detail),
                ))
            continue
        for tid in payload.target_ids:
            try:
                afid = _apply_attribute_flag_core(
                    sql, attribute_id=tid, flag=flag,
                    justification=spec.justification, actor=actor,
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=True,
                    applied_flag_id=afid,
                ))
            except Exception as exc:  # noqa: BLE001 — lote não aborta por 1 item
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc)[:300],
                ))
    return _summarize_batch("apply", results)


@attribute_router.post(
    "/batch/flags/remove",
    response_model=BatchFlagResult,
    operation_id="batchRemoveAttributeFlags",
)
def batch_remove_attribute_flags(
    payload: BatchFlagRemoveIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Remove VÁRIAS flags de VÁRIOS atributos numa única chamada.

    Preserva a limpeza da propagação LGPD (remove a flag propagada da entidade só
    se nenhuma outra coluna ainda a carrega). Idempotente.
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    results: list[BatchFlagItemResult] = []
    for fid in payload.flag_ids:
        for tid in payload.target_ids:
            try:
                _remove_attribute_flag_by_flag(
                    sql, attribute_id=tid, flag_id=fid
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=True,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=False, error=str(exc)[:300],
                ))
    return _summarize_batch("remove", results)


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
    _validate_flag_applicable(flag, payload.justification)
    afid = _apply_attribute_flag_core(
        sql,
        attribute_id=attribute_id,
        flag=flag,
        justification=payload.justification,
        actor=actor,
    )
    return _attribute_flag_by_id(sql, afid)


def _apply_attribute_flag_core(
    sql: Sql,
    *,
    attribute_id: str,
    flag: FlagOut,
    justification: str | None,
    actor: str,
) -> str:
    """Insere (ou reaproveita) a flag no atributo, propaga LGPD e devolve o
    attribute_flag_id.

    Idempotente. Preserva a regra de propagação (spec §4.5.2): qualquer flag LGPD
    numa coluna também marca a entidade-pai (para o DPO ver que a tabela é tocada
    por dado pessoal). Extraído do endpoint single-id para o batch reutilizar a
    MESMA propagação — não duplicar a lógica.
    """
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
        afid = existing[0]
    else:
        afid = delta.new_id("attrflag-")
        delta.insert(
            sql,
            s.fq_table("attribute_flags"),
            {
                "attribute_flag_id": afid,
                "attribute_id": attribute_id,
                "flag_id": flag.flag_id,
                "justification": justification,
                "applied_at": datetime.utcnow(),
                "applied_by": actor,
                "applied_in_version": None,
            },
        )
    # Propagação LGPD atributo→entidade (idempotente): roda mesmo quando a flag já
    # existia, para curar casos em que a propagação tenha falhado antes.
    if flag.category == "LGPD":
        entity_id = _entity_id_for_attribute(sql, attribute_id)
        if entity_id:
            _propagate_lgpd_to_entity(
                sql,
                entity_id=entity_id,
                flag_id=flag.flag_id,
                applied_by=actor,
            )
    return afid


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


def _remove_attribute_flag_by_flag(
    sql: Sql, *, attribute_id: str, flag_id: str
) -> None:
    """Remove a flag do atributo por (attribute_id, flag_id) e limpa a propagação
    LGPD na entidade-pai se nenhuma outra coluna ainda carregar a mesma flag.

    Usado pelo batch (que opera por flag_id, não pelo id da linha). Idempotente:
    se a flag não estava aplicada, o DELETE é noop e a limpeza LGPD não remove nada
    indevido (o guard `still_used` protege).
    """
    s = get_settings()
    # Descobre a categoria antes de deletar, para decidir se precisa limpar a
    # propagação LGPD depois.
    cat_row = delta.fetch_one_params(
        sql,
        f"SELECT category FROM {s.fq_table('flags')} WHERE flag_id = :flag_id",
        [delta.param("flag_id", flag_id)],
    )
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('attribute_flags')} "
        f"WHERE attribute_id = :attribute_id AND flag_id = :flag_id",
        [
            delta.param("attribute_id", attribute_id),
            delta.param("flag_id", flag_id),
        ],
    )
    if cat_row and cat_row[0] == "LGPD":
        entity_id = _entity_id_for_attribute(sql, attribute_id)
        if entity_id:
            _cleanup_propagated_entity_flag(
                sql, entity_id=entity_id, flag_id=flag_id
            )


# ─── Relationship flags (Bloco 5, sem propagação LGPD) ────────────────────────

_REL_FLAG_SELECT = (
    "rf.relationship_flag_id, rf.relationship_id, rf.flag_id, rf.justification, "
    "rf.applied_at, rf.applied_by, rf.applied_in_version, "
    + ", ".join(f"f.{c}" for c in _FLAG_COLS)
)


def _relationship_flag_row_to_out(r: list) -> RelationshipFlagOut:
    """Converte linha do SELECT para RelationshipFlagOut."""
    flag_cols_start = 7
    flag = _flag_row_to_out(r[flag_cols_start:flag_cols_start + len(_FLAG_COLS)])
    return RelationshipFlagOut(
        relationship_flag_id=r[0],
        relationship_id=r[1],
        flag_id=r[2],
        justification=r[3],
        applied_at=r[4],
        applied_by=r[5],
        applied_in_version=r[6],
        flag=flag,
    )


def _relationship_flag_by_id(sql: Sql, relationship_flag_id: str) -> RelationshipFlagOut:
    """Busca uma flag aplicada ao relacionamento pelo seu id."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {_REL_FLAG_SELECT}
        FROM {s.fq_table('relationship_flags')} rf
        JOIN {s.fq_table('flags')} f ON f.flag_id = rf.flag_id
        WHERE rf.relationship_flag_id = :relationship_flag_id
        """,
        [delta.param("relationship_flag_id", relationship_flag_id)],
    )
    if not row:
        raise HTTPException(404, f"relationship_flag '{relationship_flag_id}' not found")
    return _relationship_flag_row_to_out(row)


def _apply_relationship_flag_core(
    sql: Sql,
    *,
    relationship_id: str,
    flag: FlagOut,
    justification: str | None,
    actor: str,
) -> str:
    """Insere (ou reaproveita) a flag no relacionamento e devolve o
    relationship_flag_id.

    Idempotente: se a mesma flag já está aplicada, retorna o id existente.
    Sem propagação LGPD (não faz sentido para relacionamentos).
    Extraído para o batch reutilizar.
    """
    s = get_settings()
    existing = delta.fetch_one_params(
        sql,
        f"SELECT relationship_flag_id FROM {s.fq_table('relationship_flags')} "
        f"WHERE relationship_id = :relationship_id AND flag_id = :flag_id",
        [
            delta.param("relationship_id", relationship_id),
            delta.param("flag_id", flag.flag_id),
        ],
    )
    if existing:
        return existing[0]
    rfid = delta.new_id("relflag-")
    delta.insert(
        sql,
        s.fq_table("relationship_flags"),
        {
            "relationship_flag_id": rfid,
            "relationship_id": relationship_id,
            "flag_id": flag.flag_id,
            "justification": justification,
            "applied_at": datetime.utcnow(),
            "applied_by": actor,
            "applied_in_version": None,
        },
    )
    return rfid


# NOTA DE ROTEAMENTO: batch antes das rotas dinâmicas /{relationship_id}/flags,
# pela mesma razão (evitar relationship_id="batch").

@relationship_router.post(
    "/batch/flags",
    response_model=BatchFlagResult,
    operation_id="batchApplyRelationshipFlags",
)
def batch_apply_relationship_flags(
    payload: BatchFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Aplica VÁRIAS flags a VÁRIOS relacionamentos numa única chamada.

    Segue o mesmo padrão dos endpoints batch de entidades e atributos.
    Sem propagação LGPD (relacionamento é uma abstração de ligação entre
    entidades, não um "alvo" de regulação).
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    flag_cache: dict[str, FlagOut] = {}
    results: list[BatchFlagItemResult] = []
    for spec in payload.flags:
        try:
            flag = flag_cache.get(spec.flag_id) or _fetch_flag(sql, spec.flag_id)
            flag_cache[spec.flag_id] = flag
            _validate_flag_applicable(flag, spec.justification)
        except HTTPException as exc:
            for tid in payload.target_ids:
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc.detail),
                ))
            continue
        for tid in payload.target_ids:
            try:
                rfid = _apply_relationship_flag_core(
                    sql, relationship_id=tid, flag=flag,
                    justification=spec.justification, actor=actor,
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=True,
                    applied_flag_id=rfid,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=spec.flag_id, ok=False,
                    error=str(exc)[:300],
                ))
    return _summarize_batch("apply", results)


@relationship_router.post(
    "/batch/flags/remove",
    response_model=BatchFlagResult,
    operation_id="batchRemoveRelationshipFlags",
)
def batch_remove_relationship_flags(
    payload: BatchFlagRemoveIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> BatchFlagResult:
    """Remove VÁRIAS flags de VÁRIOS relacionamentos numa única chamada.

    Remove por `flag_id` (não pelo id da linha), pois o lote cobre muitos alvos.
    Idempotente.
    """
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    s = get_settings()
    results: list[BatchFlagItemResult] = []
    for fid in payload.flag_ids:
        for tid in payload.target_ids:
            try:
                delta.run_params(
                    sql,
                    f"DELETE FROM {s.fq_table('relationship_flags')} "
                    f"WHERE relationship_id = :relationship_id AND flag_id = :flag_id",
                    [
                        delta.param("relationship_id", tid),
                        delta.param("flag_id", fid),
                    ],
                )
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=True,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(BatchFlagItemResult(
                    target_id=tid, flag_id=fid, ok=False, error=str(exc)[:300],
                ))
    return _summarize_batch("remove", results)


@relationship_router.get(
    "/{relationship_id}/flags",
    response_model=list[RelationshipFlagOut],
    operation_id="listRelationshipFlags",
)
def list_relationship_flags(
    relationship_id: str, sql: SqlDependency
) -> list[RelationshipFlagOut]:
    """Lista todas as flags aplicadas a um relacionamento."""
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {_REL_FLAG_SELECT}
        FROM {s.fq_table('relationship_flags')} rf
        JOIN {s.fq_table('flags')} f ON f.flag_id = rf.flag_id
        WHERE rf.relationship_id = :relationship_id
        ORDER BY rf.applied_at DESC
        """,
        [delta.param("relationship_id", relationship_id)],
    )
    return [_relationship_flag_row_to_out(r) for r in rows]


@relationship_router.post(
    "/{relationship_id}/flags",
    response_model=RelationshipFlagOut,
    operation_id="applyRelationshipFlag",
)
def apply_relationship_flag(
    relationship_id: str,
    payload: RelationshipFlagApplyIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> RelationshipFlagOut:
    """Aplica uma flag a um relacionamento."""
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    flag = _fetch_flag(sql, payload.flag_id)
    _validate_flag_applicable(flag, payload.justification)
    rfid = _apply_relationship_flag_core(
        sql,
        relationship_id=relationship_id,
        flag=flag,
        justification=payload.justification,
        actor=actor,
    )
    return _relationship_flag_by_id(sql, rfid)


@relationship_router.delete(
    "/{relationship_id}/flags/{relationship_flag_id}",
    operation_id="removeRelationshipFlag",
)
def remove_relationship_flag(
    relationship_id: str,
    relationship_flag_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Remove uma flag de um relacionamento."""
    actor = _current_email(user_ws)
    if not actor:
        raise HTTPException(401, "authentication required")
    s = get_settings()
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('relationship_flags')} "
        f"WHERE relationship_flag_id = :relationship_flag_id "
        f"AND relationship_id = :relationship_id",
        [
            delta.param("relationship_flag_id", relationship_flag_id),
            delta.param("relationship_id", relationship_id),
        ],
    )
    return {"deleted": relationship_flag_id}


