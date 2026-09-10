"""Calendário de avaliação de conformidade — endpoints (rodada 8, item 3).

Um agendamento por sistema (periodicidade + próxima data). O pop-up da UI consome
`/compliance/due`; o botão "Registrar execução" chama `/execute`, que grava a
execução e AVANÇA a próxima data pela recorrência. A 1ª carga é feita via planilha
(`/compliance/import`, CSV/XLSX). A execução da avaliação em si é FORA do app.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql, SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, require_role
from . import service
from .models import (
    ComplianceImportResult,
    ComplianceImportRow,
    ComplianceScheduleIn,
    ComplianceScheduleOut,
)

router = APIRouter(prefix=f"{api_prefix}/compliance", tags=["compliance"])

# Mutações exigem papel de curadoria; leitura é livre para logados (como anexos).
_MUTATORS = (ROLE_DATA_STEWARD, ROLE_DATA_ARCHITECT, ROLE_ADMIN)

_COLS = [
    "calendar_id", "system_id", "recurrence", "next_due_date",
    "last_executed_at", "last_executed_by", "notes",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _row_to_out(r: list, system_name: str | None, today: date) -> ComplianceScheduleOut:
    is_due, days_until = service.due_fields(str(r[3]), today)
    return ComplianceScheduleOut(
        calendar_id=r[0],
        system_id=r[1],
        system_name=system_name,
        recurrence=r[2],
        next_due_date=str(r[3]),
        last_executed_at=r[4],
        last_executed_by=r[5],
        notes=r[6],
        is_due=is_due,
        days_until=days_until,
        created_at=r[7],
        created_by=r[8],
        updated_at=r[9],
        updated_by=r[10],
    )


def _find_by_system(sql: Sql, system_id: str) -> str | None:
    """calendar_id do agendamento existente do sistema (1 por sistema), ou None."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT calendar_id FROM {s.fq_table('compliance_calendar')} WHERE system_id = :sid LIMIT 1",
        [delta.param("sid", system_id)],
    )
    return row[0] if row else None


def _upsert(sql: Sql, *, system_id: str, recurrence: str, next_due_date: str,
            notes: str | None, actor: str) -> bool:
    """Insere ou atualiza o agendamento do sistema. Retorna True se CRIOU."""
    s = get_settings()
    now = datetime.utcnow()
    existing = _find_by_system(sql, system_id)
    if existing:
        delta.update_by_id(
            sql, s.fq_table("compliance_calendar"), "calendar_id", existing,
            {
                "recurrence": recurrence,
                "next_due_date": next_due_date,
                "notes": notes,
                "updated_at": now,
                "updated_by": actor,
            },
        )
        return False
    delta.insert(
        sql,
        s.fq_table("compliance_calendar"),
        {
            "calendar_id": delta.new_id("cal-"),
            "system_id": system_id,
            "recurrence": recurrence,
            "next_due_date": next_due_date,
            "notes": notes,
            "created_at": now,
            "created_by": actor,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return True


def _list_query(sql: Sql, where: str, params: list) -> list[ComplianceScheduleOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join('c.'+c for c in _COLS)}, sys.system_name
        FROM {s.fq_table('compliance_calendar')} c
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = c.system_id
        {where}
        ORDER BY c.next_due_date ASC
        """,
        params,
    )
    today = date.today()
    return [_row_to_out(r[:-1], r[-1], today) for r in rows]


@router.get("/schedules", response_model=list[ComplianceScheduleOut], operation_id="listComplianceSchedules")
def list_schedules(
    sql: SqlDependency,
    system_id: str | None = Query(None),
) -> list[ComplianceScheduleOut]:
    where = ""
    params: list = []
    if system_id:
        where = "WHERE c.system_id = :sid"
        params.append(delta.param("sid", system_id))
    return _list_query(sql, where, params)


@router.get("/due", response_model=list[ComplianceScheduleOut], operation_id="listComplianceDue")
def list_due(
    sql: SqlDependency,
    within_days: int = Query(0, description="Inclui avaliações que vencem nos próximos N dias (0 = só vencidas/hoje)"),
) -> list[ComplianceScheduleOut]:
    """Agendamentos vencidos/vencendo — consumido pelo pop-up da UI.

    Compara `next_due_date` (string ISO) com a data-limite em SQL (comparação
    lexicográfica de ISO 'YYYY-MM-DD' == comparação cronológica).
    """
    cutoff = (date.today() + timedelta(days=max(0, int(within_days)))).isoformat()
    where = "WHERE c.next_due_date <= :cutoff"
    params = [delta.param("cutoff", cutoff)]
    return _list_query(sql, where, params)


@router.post("/schedules", response_model=ComplianceScheduleOut, operation_id="upsertComplianceSchedule")
def upsert_schedule(
    payload: ComplianceScheduleIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ComplianceScheduleOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *_MUTATORS)
    iso = service.normalize_date(payload.next_due_date)
    if not iso:
        raise HTTPException(400, f"next_due_date inválida: {payload.next_due_date!r} (use YYYY-MM-DD)")
    _upsert(sql, system_id=payload.system_id, recurrence=payload.recurrence,
            next_due_date=iso, notes=payload.notes, actor=actor)
    out = list_schedules(sql, system_id=payload.system_id)
    if not out:
        raise HTTPException(500, "falha ao gravar agendamento")
    return out[0]


@router.post("/schedules/{calendar_id}/execute", response_model=ComplianceScheduleOut, operation_id="executeComplianceSchedule")
def execute_schedule(
    calendar_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ComplianceScheduleOut:
    """Registra a execução da avaliação e AVANÇA a próxima data pela recorrência."""
    actor = _current_email(user_ws)
    require_role(sql, actor, *_MUTATORS)
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT recurrence, next_due_date FROM {s.fq_table('compliance_calendar')} WHERE calendar_id = :cid",
        [delta.param("cid", calendar_id)],
    )
    if not row:
        raise HTTPException(404, f"agendamento '{calendar_id}' não encontrado")
    recurrence, cur_due = row[0], str(row[1])
    now = datetime.utcnow()
    # Avança a partir da MAIOR entre a data prevista e hoje, para não empilhar
    # ciclos vencidos numa data passada.
    base = max(cur_due, date.today().isoformat())
    next_due = service.advance_iso(base, recurrence)  # type: ignore[arg-type]
    delta.update_by_id(
        sql, s.fq_table("compliance_calendar"), "calendar_id", calendar_id,
        {
            "next_due_date": next_due,
            "last_executed_at": now,
            "last_executed_by": actor,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    sid_row = delta.fetch_one_params(
        sql, f"SELECT system_id FROM {s.fq_table('compliance_calendar')} WHERE calendar_id = :cid",
        [delta.param("cid", calendar_id)],
    )
    out = list_schedules(sql, system_id=sid_row[0] if sid_row else None)
    return out[0] if out else _list_query(sql, "WHERE c.calendar_id = :cid", [delta.param("cid", calendar_id)])[0]


@router.delete("/schedules/{calendar_id}", operation_id="deleteComplianceSchedule")
def delete_schedule(
    calendar_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    require_role(sql, _current_email(user_ws), *_MUTATORS)
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("compliance_calendar"), "calendar_id", calendar_id)
    return {"deleted": calendar_id}


@router.post("/import", response_model=ComplianceImportResult, operation_id="importComplianceCalendar")
async def import_calendar(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    file: UploadFile = File(...),
) -> ComplianceImportResult:
    """1ª carga do calendário via planilha (CSV/XLSX). Upsert por sistema.

    Colunas: sistema (id ou nome), periodicidade (mensal/trimestral/semestral/anual),
    próxima data (YYYY-MM-DD ou DD/MM/YYYY).
    """
    actor = _current_email(user_ws)
    require_role(sql, actor, *_MUTATORS)
    data = await file.read()
    try:
        parsed = service.parse_import(data, file.filename or "arquivo.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Mapa de resolução de sistema: por id e por nome (case-insensitive).
    s = get_settings()
    sys_rows = delta.fetch_all_params(
        sql, f"SELECT system_id, system_name FROM {s.fq_table('systems')}", []
    )
    by_id = {r[0] for r in sys_rows}
    by_name = {str(r[1]).strip().lower(): r[0] for r in sys_rows if r[1]}

    rows: list[ComplianceImportRow] = []
    imported = updated = failed = 0
    for row in parsed:
        raw_sys = row.get("system") or ""
        rec = service.parse_recurrence(row.get("recurrence_raw"))
        iso = service.normalize_date(row.get("date_raw"))
        # resolve sistema (id exato → nome CI)
        sid = raw_sys if raw_sys in by_id else by_name.get(raw_sys.strip().lower())
        if not raw_sys:
            failed += 1
            rows.append(ComplianceImportRow(ok=False, system=raw_sys, error="sistema vazio"))
            continue
        if not sid:
            failed += 1
            rows.append(ComplianceImportRow(ok=False, system=raw_sys, error="sistema não encontrado"))
            continue
        if not rec:
            failed += 1
            rows.append(ComplianceImportRow(ok=False, system=raw_sys, error=f"periodicidade inválida: {row.get('recurrence_raw')!r}"))
            continue
        if not iso:
            failed += 1
            rows.append(ComplianceImportRow(ok=False, system=raw_sys, error=f"data inválida: {row.get('date_raw')!r}"))
            continue
        created = _upsert(sql, system_id=sid, recurrence=rec, next_due_date=iso, notes=None, actor=actor)
        if created:
            imported += 1
        else:
            updated += 1
        rows.append(ComplianceImportRow(ok=True, system=raw_sys, recurrence=rec, next_due_date=iso))

    return ComplianceImportResult(
        total=len(parsed), imported=imported, updated=updated, failed=failed, rows=rows
    )
