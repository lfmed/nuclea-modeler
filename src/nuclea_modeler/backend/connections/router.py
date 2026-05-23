"""Module 1 — Connections CRUD + test endpoints."""
from __future__ import annotations

import time
from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException

from ..core import Dependencies
from ..core._nuclea_config import get_settings
from ..core import delta
from ..core.sql import SqlDependency
from .models import (
    ConnectionIn,
    ConnectionListOut,
    ConnectionOut,
    ConnectionTestResult,
    TestStatus,
)
from ..._metadata import api_prefix

router = APIRouter(prefix=f"{api_prefix}/connections", tags=["connections"])

_COLUMNS = [
    "connection_id", "alias", "environment", "system_id",
    "connection_type", "config_json", "secret_scope",
    "secret_key_user", "secret_key_pass", "secret_key_token",
    "last_test_status", "last_test_at", "last_test_latency_ms",
    "last_test_db_version", "last_test_error",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _row_to_out(row: list, system_name: str | None = None) -> ConnectionOut:
    import json
    raw_config = row[5]
    try:
        config = json.loads(raw_config) if raw_config else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return ConnectionOut(
        connection_id=row[0],
        alias=row[1],
        environment=cast(any, row[2]),
        system_id=row[3],
        system_name=system_name,
        connection_type=cast(any, row[4]),
        config=config,
        secret_scope=row[6],
        secret_key_user=row[7],
        secret_key_pass=row[8],
        secret_key_token=row[9],
        last_test_status=cast(any, row[10]) if row[10] else None,
        last_test_at=row[11],
        last_test_latency_ms=row[12],
        last_test_db_version=row[13],
        last_test_error=row[14],
        created_at=row[15],
        created_by=row[16],
        updated_at=row[17],
        updated_by=row[18],
    )


def _actor(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "unknown"


@router.get("", response_model=list[ConnectionListOut], operation_id="listConnections")
def list_connections(sql: SqlDependency) -> list[ConnectionListOut]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT c.connection_id, c.alias, c.environment, c.system_id,
               s.system_name, c.connection_type,
               c.last_test_status, c.last_test_at, c.last_test_latency_ms,
               c.updated_at
        FROM {s.fq_table('connections')} c
        LEFT JOIN {s.fq_table('systems')} s ON s.system_id = c.system_id
        ORDER BY c.updated_at DESC
        """,
    )
    return [
        ConnectionListOut(
            connection_id=r[0],
            alias=r[1],
            environment=r[2],
            system_id=r[3],
            system_name=r[4],
            connection_type=r[5],
            last_test_status=r[6] or None,
            last_test_at=r[7],
            last_test_latency_ms=r[8],
            updated_at=r[9],
        )
        for r in rows
    ]


@router.get("/{connection_id}", response_model=ConnectionOut, operation_id="getConnection")
def get_connection(connection_id: str, sql: SqlDependency) -> ConnectionOut:
    s = get_settings()
    row = delta.fetch_one(
        sql,
        f"""
        SELECT {', '.join('c.'+c for c in _COLUMNS)}, s.system_name
        FROM {s.fq_table('connections')} c
        LEFT JOIN {s.fq_table('systems')} s ON s.system_id = c.system_id
        WHERE c.connection_id = '{connection_id.replace("'", "''")}'
        """,
    )
    if not row:
        raise HTTPException(404, f"connection '{connection_id}' not found")
    return _row_to_out(row[:-1], system_name=row[-1])


@router.post("", response_model=ConnectionOut, operation_id="createConnection")
def create_connection(
    payload: ConnectionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ConnectionOut:
    import json
    s = get_settings()
    actor = _actor(user_ws)
    cid = delta.new_id("conn-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("connections"),
        {
            "connection_id": cid,
            "alias": payload.alias,
            "environment": payload.environment,
            "system_id": payload.system_id,
            "connection_type": payload.connection_type,
            "config_json": json.dumps(payload.config, ensure_ascii=False),
            "secret_scope": payload.secret_scope or s.secrets_scope,
            "secret_key_user": payload.secret_key_user,
            "secret_key_pass": payload.secret_key_pass,
            "secret_key_token": payload.secret_key_token,
            "last_test_status": "never",
            "created_at": now,
            "created_by": actor,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return get_connection(cid, sql)


@router.put("/{connection_id}", response_model=ConnectionOut, operation_id="updateConnection")
def update_connection(
    connection_id: str,
    payload: ConnectionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ConnectionOut:
    import json
    s = get_settings()
    actor = _actor(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("connections"),
        "connection_id",
        connection_id,
        {
            "alias": payload.alias,
            "environment": payload.environment,
            "system_id": payload.system_id,
            "connection_type": payload.connection_type,
            "config_json": json.dumps(payload.config, ensure_ascii=False),
            "secret_scope": payload.secret_scope or s.secrets_scope,
            "secret_key_user": payload.secret_key_user,
            "secret_key_pass": payload.secret_key_pass,
            "secret_key_token": payload.secret_key_token,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_connection(connection_id, sql)


@router.delete("/{connection_id}", operation_id="deleteConnection")
def delete_connection(connection_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("connections"), "connection_id", connection_id)
    return {"deleted": connection_id}


@router.post(
    "/{connection_id}/test",
    response_model=ConnectionTestResult,
    operation_id="testConnection",
)
def test_connection(
    connection_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ConnectionTestResult:
    """Test a connection.

    NOTE: real ODBC/REST connectivity from the Databricks Apps runtime requires
    proper drivers + network reachability. For now this endpoint persists the
    test attempt and returns a simulated result so the UI flow can be exercised.
    Real test logic will be added in Phase 1 wrap-up.
    """
    conn = get_connection(connection_id, sql)
    s = get_settings()
    actor = _actor(user_ws)
    started = time.monotonic()
    status: TestStatus = "success"
    db_version: str | None = "simulated"
    error: str | None = None
    # TODO: real per-type test (ODBC pyodbc.connect; REST httpx GET; DDL parse)
    elapsed_ms = int((time.monotonic() - started) * 1000) or 1
    now = datetime.utcnow()
    delta.update_by_id(
        sql,
        s.fq_table("connections"),
        "connection_id",
        connection_id,
        {
            "last_test_status": status,
            "last_test_at": now,
            "last_test_latency_ms": elapsed_ms,
            "last_test_db_version": db_version,
            "last_test_error": error,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return ConnectionTestResult(
        status=status,
        latency_ms=elapsed_ms,
        db_version=db_version,
        error=error,
        tested_at=now,
    )
