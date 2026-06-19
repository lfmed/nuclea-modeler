"""Diagrams (M6) CRUD + membership — vários diagramas por schema."""
from __future__ import annotations

from datetime import datetime

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
    require_role,
)
from .models import (
    DiagramDetailOut,
    DiagramIn,
    DiagramLayoutIn,
    DiagramListOut,
    DiagramMemberOut,
    DiagramMembersIn,
    DiagramOut,
)

router = APIRouter(prefix=f"{api_prefix}/diagrams", tags=["diagrams"])

_EDITORS = (ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
_COLS = [
    "diagram_id", "system_id", "schema_id", "diagram_name", "description",
    "is_default", "created_at", "created_by", "updated_at", "updated_by",
]


def _count_members(sql, s, diagram_id: str) -> int:
    n = delta.fetch_one_params(
        sql,
        f"SELECT COUNT(*) FROM {s.fq_table('diagram_entities')} WHERE diagram_id = :did",
        [delta.param("did", diagram_id)],
    )
    return int(n[0]) if n else 0


def _row_to_out(r: list, entity_count: int = 0) -> DiagramOut:
    return DiagramOut(
        diagram_id=r[0], system_id=r[1], schema_id=r[2], diagram_name=r[3],
        description=r[4], is_default=bool(r[5]),
        created_at=r[6], created_by=r[7], updated_at=r[8], updated_by=r[9],
        entity_count=entity_count,
    )


@router.get("", response_model=list[DiagramListOut], operation_id="listDiagrams")
def list_diagrams(
    sql: SqlDependency,
    schema_id: str | None = Query(None),
    system_id: str | None = Query(None),
) -> list[DiagramListOut]:
    s = get_settings()
    where: list[str] = []
    params: list = []
    if schema_id:
        where.append("d.schema_id = :schema_id")
        params.append(delta.param("schema_id", schema_id))
    if system_id:
        where.append("d.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT d.diagram_id, d.system_id, d.schema_id, d.diagram_name, d.is_default,
               (SELECT COUNT(*) FROM {s.fq_table('diagram_entities')} de
                  WHERE de.diagram_id = d.diagram_id) AS entity_count
        FROM {s.fq_table('diagrams')} d
        {where_clause}
        ORDER BY d.is_default DESC, d.diagram_name
        """,
        params,
    )
    return [
        DiagramListOut(
            diagram_id=r[0], system_id=r[1], schema_id=r[2], diagram_name=r[3],
            is_default=bool(r[4]), entity_count=int(r[5] or 0),
        )
        for r in rows
    ]


@router.get("/{diagram_id}", response_model=DiagramDetailOut, operation_id="getDiagramById")
def get_diagram(diagram_id: str, sql: SqlDependency) -> DiagramDetailOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_COLS)} FROM {s.fq_table('diagrams')} WHERE diagram_id = :did",
        [delta.param("did", diagram_id)],
    )
    if not row:
        raise HTTPException(404, f"diagram '{diagram_id}' not found")
    members = delta.fetch_all_params(
        sql,
        f"""
        SELECT de.entity_id, e.schema_name, e.technical_name, e.logical_name,
               de.pos_x, de.pos_y
        FROM {s.fq_table('diagram_entities')} de
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = de.entity_id
        WHERE de.diagram_id = :did
        """,
        [delta.param("did", diagram_id)],
    )
    base = _row_to_out(row, entity_count=len(members))
    return DiagramDetailOut(
        **base.model_dump(),
        members=[
            DiagramMemberOut(
                entity_id=m[0], schema_name=m[1], technical_name=m[2],
                logical_name=m[3],
                pos_x=float(m[4]) if m[4] is not None else None,
                pos_y=float(m[5]) if m[5] is not None else None,
            )
            for m in members
        ],
    )


def _clear_sibling_defaults(sql, s, schema_id: str, keep_diagram_id: str, now, actor) -> None:
    """Garante no máximo um diagrama default por schema."""
    delta.run_params(
        sql,
        f"UPDATE {s.fq_table('diagrams')} SET is_default = false, updated_at = :now, updated_by = :by "
        f"WHERE schema_id = :sid AND diagram_id <> :keep AND is_default = true",
        [
            delta.param("now", now), delta.param("by", actor),
            delta.param("sid", schema_id), delta.param("keep", keep_diagram_id),
        ],
    )


@router.post("", response_model=DiagramOut, operation_id="createDiagram")
def create_diagram(
    payload: DiagramIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DiagramOut:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, *_EDITORS)
    did = delta.new_id("dia-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("diagrams"),
        {
            "diagram_id": did,
            "system_id": payload.system_id,
            "schema_id": payload.schema_id,
            "diagram_name": payload.diagram_name,
            "description": payload.description,
            "is_default": payload.is_default,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    if payload.is_default:
        _clear_sibling_defaults(sql, s, payload.schema_id, did, now, actor)
    return _row_to_out_by_id(sql, s, did)


@router.put("/{diagram_id}", response_model=DiagramOut, operation_id="updateDiagram")
def update_diagram(
    diagram_id: str,
    payload: DiagramIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DiagramOut:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, *_EDITORS)
    now = datetime.utcnow()
    delta.update_by_id(
        sql,
        s.fq_table("diagrams"),
        "diagram_id",
        diagram_id,
        {
            "diagram_name": payload.diagram_name,
            "description": payload.description,
            "is_default": payload.is_default,
            "updated_at": now, "updated_by": actor,
        },
    )
    if payload.is_default:
        _clear_sibling_defaults(sql, s, payload.schema_id, diagram_id, now, actor)
    return _row_to_out_by_id(sql, s, diagram_id)


@router.delete("/{diagram_id}", operation_id="deleteDiagram")
def delete_diagram(
    diagram_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, *_EDITORS)
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('diagram_entities')} WHERE diagram_id = :did",
        [delta.param("did", diagram_id)],
    )
    delta.delete_by_id(sql, s.fq_table("diagrams"), "diagram_id", diagram_id)
    return {"deleted": diagram_id}


@router.put(
    "/{diagram_id}/members",
    response_model=DiagramDetailOut,
    operation_id="setDiagramMembers",
)
def set_members(
    diagram_id: str,
    payload: DiagramMembersIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DiagramDetailOut:
    """Substitui a membership do diagrama pelo conjunto informado (replace)."""
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, *_EDITORS)
    # garante que o diagrama existe
    get_diagram(diagram_id, sql)
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('diagram_entities')} WHERE diagram_id = :did",
        [delta.param("did", diagram_id)],
    )
    for m in payload.members:
        delta.insert(
            sql,
            s.fq_table("diagram_entities"),
            {
                "diagram_id": diagram_id,
                "entity_id": m.entity_id,
                "pos_x": m.pos_x,
                "pos_y": m.pos_y,
            },
        )
    return get_diagram(diagram_id, sql)


@router.put(
    "/{diagram_id}/layout",
    response_model=DiagramDetailOut,
    operation_id="saveDiagramLayout",
)
def save_layout(
    diagram_id: str,
    payload: DiagramLayoutIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DiagramDetailOut:
    """Salva posições (x,y) dos membros já existentes do diagrama."""
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, *_EDITORS)
    for p in payload.positions:
        delta.run_params(
            sql,
            f"UPDATE {s.fq_table('diagram_entities')} SET pos_x = :x, pos_y = :y "
            f"WHERE diagram_id = :did AND entity_id = :eid",
            [
                delta.param("x", p.pos_x), delta.param("y", p.pos_y),
                delta.param("did", diagram_id), delta.param("eid", p.entity_id),
            ],
        )
    return get_diagram(diagram_id, sql)


def _row_to_out_by_id(sql, s, diagram_id: str) -> DiagramOut:
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_COLS)} FROM {s.fq_table('diagrams')} WHERE diagram_id = :did",
        [delta.param("did", diagram_id)],
    )
    if not row:
        raise HTTPException(404, f"diagram '{diagram_id}' not found")
    return _row_to_out(row, entity_count=_count_members(sql, s, diagram_id))
