"""HTTP endpoints for DDL export — Módulo 10."""
from __future__ import annotations

from fastapi import APIRouter

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from .generators import DIALECT_LABELS, GENERATORS
from .models import (
    DDLDialectInfo,
    DDLExportRequest,
    DDLExportResult,
)
from .service import generate_export

router = APIRouter(prefix=f"{api_prefix}/ddl", tags=["ddl"])


def _actor(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "unknown"


@router.get(
    "/dialects",
    response_model=list[DDLDialectInfo],
    operation_id="listDdlDialects",
)
def list_dialects() -> list[DDLDialectInfo]:
    """Return all supported dialects with display label + subtitle."""
    return [
        DDLDialectInfo(code=code, label=label, subtitle=subtitle)  # type: ignore[arg-type]
        for code, (label, subtitle) in DIALECT_LABELS.items()
        if code in GENERATORS
    ]


@router.post(
    "/export",
    response_model=DDLExportResult,
    operation_id="exportDdl",
)
def export_ddl(
    payload: DDLExportRequest,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DDLExportResult:
    """Generate DDL for all entities of a system (or subset)."""
    actor = _actor(user_ws)
    return generate_export(sql, payload, actor=actor)


@router.post(
    "/preview",
    response_model=DDLExportResult,
    operation_id="previewDdl",
)
def preview_ddl(
    payload: DDLExportRequest,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DDLExportResult:
    """Same as export but limited to the first 10 entities (preview only)."""
    actor = _actor(user_ws)
    # Cap the result: if the caller didn't pre-select, we generate everything but
    # only return the first 10 to keep payload small. If they pre-selected, we
    # still cap to 10 here so the preview is fast.
    full = generate_export(sql, payload, actor=actor)
    if len(full.files) <= 10:
        return full
    capped_files = full.files[:10]
    combined_text = "\n\n-- ---\n\n".join(f.ddl_text for f in capped_files)
    success_count = sum(1 for f in capped_files if not f.errors)
    return DDLExportResult(
        dialect=full.dialect,
        total_objects=len(capped_files),
        success_count=success_count,
        error_count=len(capped_files) - success_count,
        files=capped_files,
        combined_text=combined_text,
    )
