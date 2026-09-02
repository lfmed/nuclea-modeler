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
    EmbarcaderoImportIn,
    ExtractionListOut,
    ExtractionOut,
    ExtractionResult,
    ExtractionSnapshot,
    LakebaseExtractionIn,
    UCExtractionIn,
)
from .service import (
    run_ddl_import,
    run_embarcadero_import,
    run_lakebase_extraction,
    run_uc_extraction,
)

router = APIRouter(prefix=f"{api_prefix}/extractions", tags=["extractions"])


@router.get("", response_model=list[ExtractionListOut], operation_id="listExtractions")
def list_extractions(sql: SqlDependency, system_id: str | None = None) -> list[ExtractionListOut]:
    s = get_settings()
    where = ""
    params: list = []
    if system_id:
        where = "WHERE e.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
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
        params,
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
    row = delta.fetch_one_params(
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
        WHERE e.extraction_id = :extraction_id
        """,
        [delta.param("extraction_id", extraction_id)],
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
    app_ws: Dependencies.Client,
) -> ExtractionResult:
    # User OBO não tem scope `postgres` no token (consent não pediu); o SP do app
    # tem via resource `nuclea-lakebase` no app.yml. Usamos o SP para `database.
    # generate_database_credential` e para a conexão Postgres em si. user_ws
    # continua sendo a fonte do `actor` no audit log e na escolha do pg role.
    actor = _current_email(user_ws)
    return run_lakebase_extraction(
        sql,
        app_ws,
        sandbox_id=payload.sandbox_id,
        system_id=payload.system_id,
        schemas=payload.schemas,
        object_kinds=payload.object_kinds,
        actor=actor,
        open_ticket_on_diff=payload.open_ticket,
    )


@router.post(
    "/uc/run",
    response_model=ExtractionResult,
    operation_id="runUCExtraction",
)
def run_uc(
    payload: UCExtractionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
) -> ExtractionResult:
    # Mesma decisão arquitetural do Lakebase: usamos o SP do app (`app_ws`)
    # para falar com a UC (permissões consistentes via app.yml), e só o
    # `user_ws` para resolver o actor que aparece no audit log.
    actor = _current_email(user_ws)
    return run_uc_extraction(
        sql,
        app_ws,
        system_id=payload.system_id,
        catalog=payload.catalog,
        schema=payload.schema,
        table_names=payload.table_names,
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


@router.post(
    "/ddl/preview",
    response_model=ExtractionResult,
    operation_id="previewDDLImport",
)
def preview_ddl(
    payload: DDLImportIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ExtractionResult:
    """Dry-run do import DDL: parseia + calcula o diff vs. catálogo e devolve o que
    MUDARIA (contagens + lista por objeto em ``preview``), SEM abrir ticket nem
    persistir a extração. Deixa o cliente conferir antes de importar de verdade.
    100% read-only (não escreve no catálogo)."""
    actor = _current_email(user_ws)
    return run_ddl_import(
        sql,
        system_id=payload.system_id,
        dialect=payload.dialect,
        ddl_text=payload.ddl_text,
        actor=actor,
        open_ticket_on_diff=False,  # preview nunca abre ticket
        dry_run=True,
    )


@router.post(
    "/embarcadero/run",
    response_model=ExtractionResult,
    operation_id="runEmbarcaderoImport",
)
def run_embarcadero(
    payload: EmbarcaderoImportIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ExtractionResult:
    actor = _current_email(user_ws)
    return run_embarcadero_import(
        sql,
        system_id=payload.system_id,
        dm1_text=payload.dm1_text,
        actor=actor,
        open_ticket_on_diff=payload.open_ticket,
    )
