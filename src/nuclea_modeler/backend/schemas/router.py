"""Schemas (M6) CRUD — schema como entidade de 1ª classe dentro de um sistema."""
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
from .models import SchemaIn, SchemaListOut, SchemaOut

router = APIRouter(prefix=f"{api_prefix}/schemas", tags=["schemas"])

_COLS = [
    "schema_id", "system_id", "schema_name", "logical_name", "domain",
    "owner_team", "description_md", "is_active",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _row_to_out(r: list) -> SchemaOut:
    return SchemaOut(
        schema_id=r[0], system_id=r[1], schema_name=r[2], logical_name=r[3],
        domain=r[4], owner_team=r[5], description_md=r[6], is_active=delta.as_bool(r[7]),
        created_at=r[8], created_by=r[9], updated_at=r[10], updated_by=r[11],
    )


@router.get("", response_model=list[SchemaListOut], operation_id="listSchemas")
def list_schemas(
    sql: SqlDependency,
    system_id: str | None = Query(None),
) -> list[SchemaListOut]:
    """Lista schemas (opcionalmente de um sistema) com contagem de entities e
    diagramas — usado pela sidebar em árvore."""
    s = get_settings()
    where = ""
    params: list = []
    if system_id:
        where = "WHERE sc.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT sc.schema_id, sc.system_id, sc.schema_name, sc.logical_name,
               sc.domain, sc.is_active,
               (SELECT COUNT(*) FROM {s.fq_table('entities')} e
                  WHERE e.system_id = sc.system_id AND e.schema_name = sc.schema_name) AS entity_count,
               (SELECT COUNT(*) FROM {s.fq_table('diagrams')} d
                  WHERE d.schema_id = sc.schema_id) AS diagram_count
        FROM {s.fq_table('schemas')} sc
        {where}
        ORDER BY sc.schema_name
        """,
        params,
    )
    return [
        SchemaListOut(
            schema_id=r[0], system_id=r[1], schema_name=r[2], logical_name=r[3],
            domain=r[4], is_active=delta.as_bool(r[5]),
            entity_count=int(r[6] or 0), diagram_count=int(r[7] or 0),
        )
        for r in rows
    ]


@router.get("/{schema_id}", response_model=SchemaOut, operation_id="getSchema")
def get_schema(schema_id: str, sql: SqlDependency) -> SchemaOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_COLS)} FROM {s.fq_table('schemas')} WHERE schema_id = :schema_id",
        [delta.param("schema_id", schema_id)],
    )
    if not row:
        raise HTTPException(404, f"schema '{schema_id}' not found")
    return _row_to_out(row)


@router.post("", response_model=SchemaOut, operation_id="createSchema")
def create_schema(
    payload: SchemaIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SchemaOut:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
    # Único por (system_id, schema_name).
    dup = delta.fetch_one_params(
        sql,
        f"SELECT schema_id FROM {s.fq_table('schemas')} "
        f"WHERE system_id = :sid AND schema_name = :name",
        [delta.param("sid", payload.system_id), delta.param("name", payload.schema_name)],
    )
    if dup:
        raise HTTPException(409, f"schema '{payload.schema_name}' já existe nesse sistema")
    sid = delta.new_id("sch-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("schemas"),
        {
            "schema_id": sid,
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "logical_name": payload.logical_name,
            "domain": payload.domain,
            "owner_team": payload.owner_team,
            "description_md": payload.description_md,
            "is_active": payload.is_active,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_schema(sid, sql)


@router.put("/{schema_id}", response_model=SchemaOut, operation_id="updateSchema")
def update_schema(
    schema_id: str,
    payload: SchemaIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SchemaOut:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
    delta.update_by_id(
        sql,
        s.fq_table("schemas"),
        "schema_id",
        schema_id,
        {
            "schema_name": payload.schema_name,
            "logical_name": payload.logical_name,
            "domain": payload.domain,
            "owner_team": payload.owner_team,
            "description_md": payload.description_md,
            "is_active": payload.is_active,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_schema(schema_id, sql)


@router.delete("/{schema_id}", operation_id="deleteSchema")
def delete_schema(
    schema_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    s = get_settings()
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    cur = get_schema(schema_id, sql)
    # Bloqueia exclusão de schema que ainda tem entities (evita órfãos visuais).
    n = delta.fetch_one_params(
        sql,
        f"SELECT COUNT(*) FROM {s.fq_table('entities')} "
        f"WHERE system_id = :sid AND schema_name = :name",
        [delta.param("sid", cur.system_id), delta.param("name", cur.schema_name)],
    )
    if n and int(n[0]) > 0:
        raise HTTPException(
            409,
            f"schema '{cur.schema_name}' tem {int(n[0])} entidade(s); "
            f"mova/remova as entidades antes de excluir o schema",
        )
    # Remove diagramas do schema (e suas memberships) antes do schema.
    diag_ids = delta.fetch_all_params(
        sql,
        f"SELECT diagram_id FROM {s.fq_table('diagrams')} WHERE schema_id = :sid",
        [delta.param("sid", schema_id)],
    )
    for (did,) in diag_ids:
        delta.run_params(
            sql,
            f"DELETE FROM {s.fq_table('diagram_entities')} WHERE diagram_id = :did",
            [delta.param("did", did)],
        )
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('diagrams')} WHERE schema_id = :sid",
        [delta.param("sid", schema_id)],
    )
    delta.delete_by_id(sql, s.fq_table("schemas"), "schema_id", schema_id)
    return {"deleted": schema_id}
