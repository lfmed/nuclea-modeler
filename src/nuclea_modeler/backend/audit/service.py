"""Audit log service — read helpers for the audit_log Delta table.

Writes are performed by the AuditMiddleware. This module concentrates the SQL
required to power the admin Auditoria page.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import AuditCount, AuditDetailEntry, AuditEntry, AuditStats


_COLS_SHORT = [
    "audit_id", "occurred_at", "actor_email", "actor_role",
    "action", "object_type", "object_id", "request_id", "client_ip",
]
_COLS_FULL = _COLS_SHORT + ["before_json", "after_json", "user_agent"]


def _row_short(r: list[Any]) -> AuditEntry:
    return AuditEntry(
        audit_id=r[0], occurred_at=r[1], actor_email=r[2], actor_role=r[3],
        action=r[4], object_type=r[5], object_id=r[6],
        request_id=r[7], client_ip=r[8],
    )


def _row_full(r: list[Any]) -> AuditDetailEntry:
    return AuditDetailEntry(
        audit_id=r[0], occurred_at=r[1], actor_email=r[2], actor_role=r[3],
        action=r[4], object_type=r[5], object_id=r[6],
        request_id=r[7], client_ip=r[8],
        before_json=r[9], after_json=r[10], user_agent=r[11],
    )


def list_audit(
    sql: Sql,
    *,
    actor_email: str | None = None,
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    since: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AuditEntry]:
    s = get_settings()
    where: list[str] = []
    params: list = []
    if actor_email:
        where.append("actor_email = :actor_email")
        params.append(delta.param("actor_email", actor_email))
    if action:
        where.append("action = :action")
        params.append(delta.param("action", action))
    if object_type:
        where.append("object_type = :object_type")
        params.append(delta.param("object_type", object_type))
    if object_id:
        where.append("object_id = :object_id")
        params.append(delta.param("object_id", object_id))
    if since:
        where.append("occurred_at >= :since")
        params.append(delta.param("since", since))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(_COLS_SHORT)
    # LIMIT/OFFSET clamped — bare integers, no need to parametrise.
    safe_limit = max(1, min(int(limit), 1000))
    safe_offset = max(0, int(offset))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {cols}
        FROM {s.fq_table('audit_log')}
        {where_sql}
        ORDER BY occurred_at DESC
        LIMIT {safe_limit} OFFSET {safe_offset}
        """,
        params,
    )
    return [_row_short(r) for r in rows]


def count_audit(
    sql: Sql,
    *,
    actor_email: str | None = None,
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    since: datetime | None = None,
) -> int:
    """Count rows matching the same filters as list_audit. Used by paginator."""
    s = get_settings()
    where: list[str] = []
    params: list = []
    if actor_email:
        where.append("actor_email = :actor_email")
        params.append(delta.param("actor_email", actor_email))
    if action:
        where.append("action = :action")
        params.append(delta.param("action", action))
    if object_type:
        where.append("object_type = :object_type")
        params.append(delta.param("object_type", object_type))
    if object_id:
        where.append("object_id = :object_id")
        params.append(delta.param("object_id", object_id))
    if since:
        where.append("occurred_at >= :since")
        params.append(delta.param("since", since))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    row = delta.fetch_one_params(
        sql,
        f"SELECT COUNT(*) FROM {s.fq_table('audit_log')} {where_sql}",
        params,
    )
    return int(row[0]) if row and row[0] is not None else 0


def get_audit(sql: Sql, audit_id: str) -> AuditDetailEntry | None:
    s = get_settings()
    cols = ", ".join(_COLS_FULL)
    row = delta.fetch_one_params(
        sql,
        f"SELECT {cols} FROM {s.fq_table('audit_log')} "
        f"WHERE audit_id = :audit_id",
        [delta.param("audit_id", audit_id)],
    )
    if not row:
        return None
    return _row_full(row)


def stats_last_n_days(sql: Sql, days: int = 7) -> AuditStats:
    s = get_settings()
    until = datetime.utcnow()
    since = until - timedelta(days=days)

    rows_action = delta.fetch_all_params(
        sql,
        f"""
        SELECT action, COUNT(*) AS n
        FROM {s.fq_table('audit_log')}
        WHERE occurred_at >= :since
        GROUP BY action
        ORDER BY n DESC
        """,
        [delta.param("since", since)],
    )
    rows_obj = delta.fetch_all_params(
        sql,
        f"""
        SELECT object_type, COUNT(*) AS n
        FROM {s.fq_table('audit_log')}
        WHERE occurred_at >= :since
        GROUP BY object_type
        ORDER BY n DESC
        """,
        [delta.param("since", since)],
    )
    total = sum(int(r[1] or 0) for r in rows_action)
    return AuditStats(
        since=since,
        until=until,
        by_action=[AuditCount(key=str(r[0] or "?"), count=int(r[1] or 0)) for r in rows_action],
        by_object_type=[AuditCount(key=str(r[0] or "?"), count=int(r[1] or 0)) for r in rows_obj],
        total=total,
    )
