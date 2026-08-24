"""Endpoints do round-trip de edição via CSV (v1.0035).

- GET  /entities/export/csv?system_id=  → devolve o CSV re-importável (JSON com
  filename+csv, p/ o front montar o download sem lidar com content-disposition).
- POST /entities/import/csv             → parseia o CSV, compara com o catálogo e
  abre um ticket editorial (diff pendente de aprovação).

Reusa `roundtrip.py` (que por sua vez reusa o fluxo editorial de tickets).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from . import roundtrip

router = APIRouter(prefix=f"{api_prefix}/entities", tags=["entities"])


class CsvExportOut(BaseModel):
    filename: str
    csv: str


class CsvImportIn(BaseModel):
    system_id: str
    csv_text: str


class CsvImportOut(BaseModel):
    ticket_id: str | None = None
    entities_changed: int = 0
    columns_changed: int = 0
    unknown_tables: list[str] = []
    message: str = ""


@router.get("/export/csv", response_model=CsvExportOut, operation_id="exportSystemCsv")
def export_csv(system_id: str, sql: SqlDependency) -> CsvExportOut:
    """Exporta as colunas do sistema (grão coluna, com contexto de tabela/esquema)
    num CSV editável e re-importável."""
    if not system_id:
        raise HTTPException(400, "system_id é obrigatório")
    text = roundtrip.export_system_csv(sql, system_id)
    return CsvExportOut(filename=f"roundtrip-{system_id}.csv", csv=text)


@router.post("/import/csv", response_model=CsvImportOut, operation_id="importSystemCsv")
def import_csv(
    payload: CsvImportIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> CsvImportOut:
    """Reimporta o CSV editado: compara com o catálogo, monta um ticket editorial
    (diff) e devolve o resumo. Nada é aplicado até a aprovação do ticket."""
    actor = _current_email(user_ws) or "unknown"
    try:
        res = roundtrip.parse_and_stage_csv(sql, actor, payload.system_id, payload.csv_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CsvImportOut(**res)
