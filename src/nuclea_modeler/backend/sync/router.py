"""Módulo 9 — Sincronização Unity Catalog HTTP endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, ROLE_DATA_ARCHITECT, require_role
from .models import (
    SyncLogListOut,
    SyncLogOut,
    SyncRunRequest,
    SyncRunResult,
)
from .service import get_run, list_runs, run_sync

router = APIRouter(prefix=f"{api_prefix}/sync", tags=["sync"])


@router.post("/run", response_model=SyncRunResult, operation_id="runSync")
def run_sync_endpoint(
    payload: SyncRunRequest,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SyncRunResult:
    """Execute a sync run — applies COMMENT/TAGS to Unity Catalog.

    Restricted to Data Architects and Admins.
    """
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_DATA_ARCHITECT, ROLE_ADMIN)
    return run_sync(sql, payload, actor)


@router.post("/preview", response_model=SyncRunResult, operation_id="previewSync")
def preview_sync_endpoint(
    payload: SyncRunRequest,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SyncRunResult:
    """Dry-run a sync — no SQL is executed against Unity Catalog. No RBAC."""
    actor = _current_email(user_ws) or "preview"
    forced = payload.model_copy(update={"dry_run": True})
    return run_sync(sql, forced, actor)


@router.get("/runs", response_model=list[SyncLogListOut], operation_id="listSyncRuns")
def list_sync_runs(sql: SqlDependency) -> list[SyncLogListOut]:
    rows = list_runs(sql, limit=50)
    return [SyncLogListOut(**r) for r in rows]


@router.get(
    "/runs/{sync_id}",
    response_model=SyncLogOut,
    operation_id="getSyncRun",
)
def get_sync_run(sync_id: str, sql: SqlDependency) -> SyncLogOut:
    row = get_run(sql, sync_id)
    if not row:
        raise HTTPException(404, f"sync run '{sync_id}' not found")
    return SyncLogOut(**row)
