"""Systems (sistemas de origem) CRUD — shared by Connections, Extractions, Entities."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..core import Dependencies
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from .models import SystemIn, SystemListOut, SystemOut
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


@router.get("", response_model=list[SystemListOut], operation_id="listSystems")
def list_systems(sql: SqlDependency) -> list[SystemListOut]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT system_id, system_name, domain, technology, is_active, environment
        FROM {s.fq_table('systems')}
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


@router.delete("/{system_id}", operation_id="deleteSystem")
def delete_system(system_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("systems"), "system_id", system_id)
    return {"deleted": system_id}
