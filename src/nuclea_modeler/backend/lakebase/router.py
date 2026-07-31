"""Lakebase Sandbox HTTP endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, ROLE_DATA_ARCHITECT, require_role
from . import service as lk
from .models import (
    ListAvailableInstancesOut,
    SandboxIn,
    SandboxListOut,
    SandboxOut,
    SandboxTestResult,
)

router = APIRouter(prefix=f"{api_prefix}/lakebase", tags=["lakebase"])

_COLS = [
    "sandbox_id", "name", "instance_name", "instance_uid",
    "database_name", "default_schema", "description",
    "read_write_dns", "pg_version",
    "last_test_status", "last_test_at", "last_test_error",
    "is_active",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _row_to_out(r: list) -> SandboxOut:
    return SandboxOut(
        sandbox_id=r[0], name=r[1], instance_name=r[2], instance_uid=r[3],
        database_name=r[4] or "databricks_postgres", default_schema=r[5] or "public",
        description=r[6], read_write_dns=r[7], pg_version=r[8],
        last_test_status=r[9], last_test_at=r[10], last_test_error=r[11],
        is_active=delta.as_bool(r[12]),
        created_at=r[13], created_by=r[14],
        updated_at=r[15], updated_by=r[16],
    )


@router.get("/instances", response_model=list[ListAvailableInstancesOut], operation_id="listLakebaseInstances")
def list_instances(user_ws: Dependencies.UserClient) -> list[ListAvailableInstancesOut]:
    """List Lakebase instances available in the workspace (live, from Databricks SDK)."""
    out: list[ListAvailableInstancesOut] = []
    try:
        for inst in user_ws.database.list_database_instances():
            out.append(
                ListAvailableInstancesOut(
                    instance_name=inst.name or "",
                    state=str(inst.state.value) if inst.state else "UNKNOWN",
                    capacity=str(inst.capacity.value) if inst.capacity else None,
                    pg_version=str(inst.pg_version.value) if inst.pg_version else None,
                    read_write_dns=inst.read_write_dns,
                    uid=inst.uid,
                )
            )
    except Exception as exc:
        raise HTTPException(500, f"failed to list Lakebase instances: {exc}") from exc
    return out


@router.get("/sandboxes", response_model=list[SandboxListOut], operation_id="listSandboxes")
def list_sandboxes(sql: SqlDependency) -> list[SandboxListOut]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT sandbox_id, name, instance_name, database_name, default_schema,
               pg_version, last_test_status, last_test_at, is_active
        FROM {s.fq_table('lakebase_sandboxes')}
        WHERE is_active = true
        ORDER BY created_at DESC
        """,
    )
    return [
        SandboxListOut(
            sandbox_id=r[0], name=r[1], instance_name=r[2],
            database_name=r[3] or "databricks_postgres",
            default_schema=r[4] or "public",
            pg_version=r[5],
            last_test_status=r[6], last_test_at=r[7],
            is_active=delta.as_bool(r[8]),
        )
        for r in rows
    ]


@router.get("/sandboxes/{sandbox_id}", response_model=SandboxOut, operation_id="getSandbox")
def get_sandbox(sandbox_id: str, sql: SqlDependency) -> SandboxOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_COLS)} FROM {s.fq_table('lakebase_sandboxes')} "
        f"WHERE sandbox_id = :sandbox_id",
        [delta.param("sandbox_id", sandbox_id)],
    )
    if not row:
        raise HTTPException(404, f"sandbox '{sandbox_id}' not found")
    return _row_to_out(row)


@router.post("/sandboxes", response_model=SandboxOut, operation_id="createSandbox")
def create_sandbox(
    payload: SandboxIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SandboxOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    # Fetch instance metadata (DNS + version + uid) from Databricks SDK
    try:
        inst = user_ws.database.get_database_instance(name=payload.instance_name)
    except Exception as exc:
        raise HTTPException(400, f"Lakebase instance '{payload.instance_name}' not accessible: {exc}") from exc
    s = get_settings()
    sid = delta.new_id("sb-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("lakebase_sandboxes"),
        {
            "sandbox_id": sid,
            "name": payload.name,
            "instance_name": payload.instance_name,
            "instance_uid": inst.uid,
            "database_name": payload.database_name,
            "default_schema": payload.default_schema,
            "description": payload.description,
            "read_write_dns": inst.read_write_dns,
            "pg_version": str(inst.pg_version.value) if inst.pg_version else None,
            "last_test_status": None,
            "is_active": True,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_sandbox(sid, sql)


@router.post(
    "/sandboxes/{sandbox_id}/test",
    response_model=SandboxTestResult,
    operation_id="testSandbox",
)
def test_sandbox(
    sandbox_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
) -> SandboxTestResult:
    sbx = get_sandbox(sandbox_id, sql)
    actor = _current_email(user_ws)
    # User OBO não tem scope `postgres`; SP do app tem via resource no app.yml.
    # Conexão usa SP; actor fica no audit.
    result = lk.test_connection(
        app_ws,
        instance_name=sbx.instance_name,
        database=sbx.database_name,
        user_email=None,
    )
    s = get_settings()
    now = datetime.utcnow()
    delta.update_by_id(
        sql,
        s.fq_table("lakebase_sandboxes"),
        "sandbox_id",
        sandbox_id,
        {
            "last_test_status": result["status"],
            "last_test_at": now,
            "last_test_error": result.get("error"),
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return SandboxTestResult(
        status=cast(any, result["status"]),
        server_version=result.get("server_version"),
        current_db=result.get("current_db"),
        schemas_visible=result.get("schemas_visible"),
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
    )


@router.get(
    "/sandboxes/{sandbox_id}/schemas",
    response_model=list[str],
    operation_id="listSandboxSchemas",
)
def list_sandbox_schemas(
    sandbox_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
) -> list[str]:
    sbx = get_sandbox(sandbox_id, sql)
    # Conexão usa SP do app (scope postgres via app.yml resource); user_ws
    # mantido só para futuro audit.
    _ = _current_email(user_ws)
    try:
        return lk.list_schemas(
            app_ws,
            instance_name=sbx.instance_name,
            database=sbx.database_name,
            user_email=None,
        )
    except Exception as exc:
        raise HTTPException(500, f"failed to list schemas: {exc}") from exc


@router.delete("/sandboxes/{sandbox_id}", operation_id="deactivateSandbox")
def deactivate_sandbox(
    sandbox_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    s = get_settings()
    delta.update_by_id(
        sql,
        s.fq_table("lakebase_sandboxes"),
        "sandbox_id",
        sandbox_id,
        {"is_active": False, "updated_at": datetime.utcnow(), "updated_by": actor},
    )
    return {"deactivated": sandbox_id}
