"""Reverse Engineering (M2) HTTP endpoints."""
from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .models import (
    DDLImportIn,
    ExtractionListOut,
    ExtractionOut,
    ExtractionResult,
    ExtractionSnapshot,
    LakebaseExtractionIn,
)
from .service import run_ddl_import, run_lakebase_extraction

router = APIRouter(prefix=f"{api_prefix}/extractions", tags=["extractions"])


@router.get("", response_model=list[ExtractionListOut], operation_id="listExtractions")
def list_extractions(sql: SqlDependency, system_id: str | None = None) -> list[ExtractionListOut]:
    s = get_settings()
    where = ""
    if system_id:
        where = f"WHERE e.system_id = '{system_id.replace(chr(39), chr(39)*2)}'"
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT e.extraction_id, e.source_kind, e.system_id, sys.system_name, e.status,
               e.started_at, e.ended_at, e.duration_ms,
               e.objects_found, e.objects_new, e.objects_changed, e.objects_removed,
               e.ticket_id, e.created_by
        FROM {s.fq_table('extractions')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        {where}
        ORDER BY e.started_at DESC
        LIMIT 100
        """,
    )
    return [
        ExtractionListOut(
            extraction_id=r[0],
            source_kind=cast(any, r[1]),
            system_id=r[2],
            system_name=r[3],
            status=cast(any, r[4]),
            started_at=r[5], ended_at=r[6],
            duration_ms=int(r[7]) if r[7] is not None else None,
            objects_found=int(r[8]) if r[8] is not None else None,
            objects_new=int(r[9]) if r[9] is not None else None,
            objects_changed=int(r[10]) if r[10] is not None else None,
            objects_removed=int(r[11]) if r[11] is not None else None,
            ticket_id=r[12],
            created_by=r[13],
        )
        for r in rows
    ]


@router.get("/{extraction_id}", response_model=ExtractionOut, operation_id="getExtraction")
def get_extraction(extraction_id: str, sql: SqlDependency) -> ExtractionOut:
    s = get_settings()
    row = delta.fetch_one(
        sql,
        f"""
        SELECT e.extraction_id, e.source_kind, e.system_id, sys.system_name, e.status,
               e.started_at, e.ended_at, e.duration_ms,
               e.objects_found, e.objects_new, e.objects_changed, e.objects_removed,
               e.ticket_id, e.created_by,
               e.connection_id, e.lakebase_sandbox_id,
               e.requested_schemas, e.requested_kinds,
               e.error_summary, e.snapshot_json, e.diff_summary_json
        FROM {s.fq_table('extractions')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE e.extraction_id = '{extraction_id.replace(chr(39), chr(39)*2)}'
        """,
    )
    if not row:
        raise HTTPException(404, f"extraction '{extraction_id}' not found")
    snapshot: ExtractionSnapshot | None = None
    if row[19]:
        try:
            snapshot = ExtractionSnapshot.model_validate_json(row[19])
        except Exception:
            snapshot = None
    diff_summary: dict | None = None
    if row[20]:
        try:
            diff_summary = json.loads(row[20])
        except Exception:
            diff_summary = None
    return ExtractionOut(
        extraction_id=row[0],
        source_kind=cast(any, row[1]),
        system_id=row[2],
        system_name=row[3],
        status=cast(any, row[4]),
        started_at=row[5], ended_at=row[6],
        duration_ms=int(row[7]) if row[7] is not None else None,
        objects_found=int(row[8]) if row[8] is not None else None,
        objects_new=int(row[9]) if row[9] is not None else None,
        objects_changed=int(row[10]) if row[10] is not None else None,
        objects_removed=int(row[11]) if row[11] is not None else None,
        ticket_id=row[12],
        created_by=row[13],
        connection_id=row[14],
        lakebase_sandbox_id=row[15],
        requested_schemas=row[16],
        requested_kinds=row[17],
        error_summary=row[18],
        snapshot=snapshot,
        diff_summary=diff_summary,
    )


@router.post(
    "/lakebase/run",
    response_model=ExtractionResult,
    operation_id="runLakebaseExtraction",
)
def run_lakebase(
    payload: LakebaseExtractionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ExtractionResult:
    actor = _current_email(user_ws)
    return run_lakebase_extraction(
        sql,
        user_ws,
        sandbox_id=payload.sandbox_id,
        system_id=payload.system_id,
        schemas=payload.schemas,
        object_kinds=payload.object_kinds,
        actor=actor,
        open_ticket_on_diff=payload.open_ticket,
    )


@router.post(
    "/ddl/run",
    response_model=ExtractionResult,
    operation_id="runDDLImport",
)
def run_ddl(
    payload: DDLImportIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ExtractionResult:
    actor = _current_email(user_ws)
    return run_ddl_import(
        sql,
        system_id=payload.system_id,
        dialect=payload.dialect,
        ddl_text=payload.ddl_text,
        actor=actor,
        open_ticket_on_diff=payload.open_ticket,
    )
