"""Systems (sistemas de origem) CRUD — shared by Connections, Extractions, Entities."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..core import Dependencies
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.service import (
    ROLE_ADMIN,
    ROLE_DATA_ARCHITECT,
    ROLE_DATA_STEWARD,
    require_role,
)
from .models import SystemIn, SystemListOut, SystemOut
from .service import count_entities, purge_system_model
from ..versions.service import publish_version
from ..._metadata import api_prefix

router = APIRouter(prefix=f"{api_prefix}/systems", tags=["systems"])

_COLS = ["system_id", "system_name", "description", "domain", "owner_team",
         "technology", "is_active", "created_at", "created_by",
         "updated_at", "updated_by", "environment"]


def _row_to_out(r: list) -> SystemOut:
    return SystemOut(
        system_id=r[0], system_name=r[1], description=r[2], domain=r[3],
        owner_team=r[4], technology=r[5], is_active=bool(r[6]),
        created_at=r[7], created_by=r[8], updated_at=r[9], updated_by=r[10],
        environment=r[11] if len(r) > 11 else None,
    )


def _actor(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "unknown"


def _systems_where(archived: bool) -> str:
    # archived_at NULL = ativo; NOT NULL = arquivado (soft-delete).
    return "WHERE archived_at IS NOT NULL" if archived else "WHERE archived_at IS NULL"


def _list_systems(sql, archived: bool) -> list[SystemListOut]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT system_id, system_name, domain, technology, is_active, environment
        FROM {s.fq_table('systems')}
        {_systems_where(archived)}
        ORDER BY system_name
        """,
    )
    return [
        SystemListOut(
            system_id=r[0], system_name=r[1], domain=r[2],
            technology=r[3], is_active=bool(r[4]),
            environment=r[5] if len(r) > 5 else None,
        )
        for r in rows
    ]


@router.get("", response_model=list[SystemListOut], operation_id="listSystems")
def list_systems(sql: SqlDependency) -> list[SystemListOut]:
    """Sistemas ATIVOS (arquivados são ocultados — ver listArchivedSystems)."""
    return _list_systems(sql, archived=False)


# IMPORTANTE: rota literal /archived precisa vir ANTES de /{system_id}.
@router.get("/archived", response_model=list[SystemListOut], operation_id="listArchivedSystems")
def list_archived_systems(sql: SqlDependency) -> list[SystemListOut]:
    """Sistemas arquivados (soft-deleted) — para restaurar."""
    return _list_systems(sql, archived=True)


@router.get("/{system_id}", response_model=SystemOut, operation_id="getSystem")
def get_system(system_id: str, sql: SqlDependency) -> SystemOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_COLS)} FROM {s.fq_table('systems')} "
        f"WHERE system_id = :system_id",
        [delta.param("system_id", system_id)],
    )
    if not row:
        raise HTTPException(404, f"system '{system_id}' not found")
    return _row_to_out(row)


@router.post("", response_model=SystemOut, operation_id="createSystem")
def create_system(
    payload: SystemIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SystemOut:
    s = get_settings()
    actor = _actor(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
    sid = delta.new_id("sys-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("systems"),
        {
            "system_id": sid,
            "system_name": payload.system_name,
            "description": payload.description,
            "domain": payload.domain,
            "owner_team": payload.owner_team,
            "technology": payload.technology,
            "environment": payload.environment,
            "is_active": payload.is_active,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_system(sid, sql)


@router.put("/{system_id}", response_model=SystemOut, operation_id="updateSystem")
def update_system(
    system_id: str,
    payload: SystemIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SystemOut:
    s = get_settings()
    actor = _actor(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
    delta.update_by_id(
        sql,
        s.fq_table("systems"),
        "system_id",
        system_id,
        {
            "system_name": payload.system_name,
            "description": payload.description,
            "domain": payload.domain,
            "owner_team": payload.owner_team,
            "technology": payload.technology,
            "environment": payload.environment,
            "is_active": payload.is_active,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_system(system_id, sql)


def _require_system(sql, system_id: str) -> None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT system_id FROM {s.fq_table('systems')} WHERE system_id = :sid",
        [delta.param("sid", system_id)],
    )
    if not row:
        raise HTTPException(404, f"system '{system_id}' não encontrado")


def _snapshot_before_purge(sql, system_id: str, actor: str, reason: str) -> int:
    """Publica um snapshot de versão (histórico) se houver entities; retorna o count.

    É o que garante "reter histórico": o modelo fica arquivado em `model_versions`
    e pode ser restaurado depois via Versões (M8), mesmo após o purge.
    """
    n = count_entities(sql, system_id)
    if n > 0:
        publish_version(
            sql,
            system_id=system_id,
            title=f"Arquivo automático — antes de {reason}",
            changelog=f"Snapshot automático antes de {reason} ({n} entidades).",
            make_active=False,
            actor=actor,
        )
    return n


@router.post("/{system_id}/clear", operation_id="clearSystem")
def clear_system(
    system_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Limpa o MODELO do sistema (entities/attributes/relationships/schemas/
    diagramas/code objects) mantendo o registro do sistema. Publica um snapshot
    de versão antes (histórico). Restrito a Data Architect / Admin."""
    actor = _actor(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    _require_system(sql, system_id)
    n = _snapshot_before_purge(sql, system_id, actor, "limpar o modelo")
    purge_system_model(sql, system_id)
    return {"cleared": system_id, "entities_removed": n}


@router.delete("/{system_id}", operation_id="deleteSystem")
def delete_system(
    system_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Exclui (arquiva) o sistema — SOFT-DELETE, retendo tudo.

    Em vez de apagar, marca `archived_at`: o sistema some das listas/navegador e
    seus objetos deixam de aparecer, mas nada é perdido — dá pra RESTAURAR depois
    (POST /systems/{id}/restore). Para zerar o modelo destrutivamente (mantendo o
    sistema), use /clear. Restrito a Data Architect / Admin.
    """
    s = get_settings()
    actor = _actor(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    _require_system(sql, system_id)
    delta.run_params(
        sql,
        f"UPDATE {s.fq_table('systems')} SET archived_at = current_timestamp(), "
        f"archived_by = :actor, updated_at = current_timestamp(), updated_by = :actor "
        f"WHERE system_id = :sid",
        [delta.param("actor", actor), delta.param("sid", system_id)],
    )
    return {"archived": system_id}


@router.post("/{system_id}/restore", operation_id="restoreSystem")
def restore_system(
    system_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Restaura um sistema arquivado (limpa `archived_at`). Architect / Admin."""
    s = get_settings()
    actor = _actor(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    _require_system(sql, system_id)
    delta.run_params(
        sql,
        f"UPDATE {s.fq_table('systems')} SET archived_at = NULL, archived_by = NULL, "
        f"updated_at = current_timestamp(), updated_by = :actor WHERE system_id = :sid",
        [delta.param("actor", actor), delta.param("sid", system_id)],
    )
    return {"restored": system_id}
