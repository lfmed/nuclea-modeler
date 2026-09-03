"""Endpoints do round-trip de edição via CSV (v1.0035).

- GET  /entities/export/csv?system_id=  → devolve o CSV re-importável (JSON com
  filename+csv, p/ o front montar o download sem lidar com content-disposition).
- POST /entities/import/csv             → parseia o CSV, compara com o catálogo e
  abre um ticket editorial (diff pendente de aprovação).

Reusa `roundtrip.py` (que por sua vez reusa o fluxo editorial de tickets).
"""
from __future__ import annotations

import base64
import binascii

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
    flags_applied: int = 0  # round 6 pt 22 — flags LGPD do CLASSIFICACAO
    unknown_tables: list[str] = []
    message: str = ""


# round 6 pt 22 — .xlsx trafega como base64 em JSON (casa com o api.ts escrito à
# mão, que fala JSON; evita multipart/streaming no cliente).
class XlsxExportOut(BaseModel):
    filename: str
    xlsx_base64: str


class XlsxImportIn(BaseModel):
    system_id: str
    xlsx_base64: str


@router.get("/export/csv", response_model=CsvExportOut, operation_id="exportSystemCsv")
def export_csv(system_id: str, sql: SqlDependency) -> CsvExportOut:
    """Exporta as colunas do sistema (grão coluna, com contexto de tabela/esquema)
    num CSV editável e re-importável."""
    if not system_id:
        raise HTTPException(400, "system_id é obrigatório")
    text = roundtrip.export_system_csv(sql, system_id)
    # filename com o NOME do sistema (feedback do cliente), não o id opaco.
    return CsvExportOut(filename=f"{roundtrip.system_slug(sql, system_id)}.csv", csv=text)


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


@router.get("/export/xlsx", response_model=XlsxExportOut, operation_id="exportSystemXlsx")
def export_xlsx(system_id: str, sql: SqlDependency) -> XlsxExportOut:
    """Exporta os metadados no formato .xlsx do Embarcadero (pt 22), em base64."""
    if not system_id:
        raise HTTPException(400, "system_id é obrigatório")
    try:
        data = roundtrip.export_system_xlsx(sql, system_id)
    except ValueError as exc:  # openpyxl ausente
        raise HTTPException(503, str(exc)) from exc
    return XlsxExportOut(
        filename=f"{roundtrip.system_slug(sql, system_id)}.xlsx",
        xlsx_base64=base64.b64encode(data).decode("ascii"),
    )


@router.post("/import/xlsx", response_model=CsvImportOut, operation_id="importSystemXlsx")
def import_xlsx(
    payload: XlsxImportIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> CsvImportOut:
    """Reimporta o .xlsx do Embarcadero: converte pro formato canônico, compara com
    o catálogo e monta o ticket editorial (+ aplica flags LGPD do CLASSIFICACAO)."""
    actor = _current_email(user_ws) or "unknown"
    try:
        raw = base64.b64decode(payload.xlsx_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, "xlsx_base64 inválido") from exc
    try:
        res = roundtrip.parse_and_stage_xlsx(sql, actor, payload.system_id, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CsvImportOut(**res)
