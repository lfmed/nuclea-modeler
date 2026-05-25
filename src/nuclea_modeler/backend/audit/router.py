"""Audit HTTP endpoints — ADMIN-only reads of audit_log."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, require_role
from .models import AuditDetailEntry, AuditEntry, AuditStats
from .service import get_audit, list_audit, stats_last_n_days

router = APIRouter(prefix=f"{api_prefix}/audit", tags=["audit"])


@router.get("/stats", response_model=AuditStats, operation_id="auditStats")
def audit_stats(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    days: int = Query(7, ge=1, le=30),
) -> AuditStats:
    require_role(sql, _current_email(user_ws), ROLE_ADMIN)
    return stats_last_n_days(sql, days=days)


@router.get("", response_model=list[AuditEntry], operation_id="listAudit")
def list_audit_endpoint(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    actor_email: str | None = Query(None),
    action: str | None = Query(None),
    object_type: str | None = Query(None),
    object_id: str | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> list[AuditEntry]:
    require_role(sql, _current_email(user_ws), ROLE_ADMIN)
    return list_audit(
        sql,
        actor_email=actor_email,
        action=action,
        object_type=object_type,
        object_id=object_id,
        since=since,
        limit=limit,
    )


@router.get("/{audit_id}", response_model=AuditDetailEntry, operation_id="getAudit")
def get_audit_endpoint(
    audit_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AuditDetailEntry:
    require_role(sql, _current_email(user_ws), ROLE_ADMIN)
    entry = get_audit(sql, audit_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"audit row '{audit_id}' not found")
    return entry
