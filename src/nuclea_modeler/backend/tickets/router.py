"""Tickets HTTP endpoints — list, get, open, approve, reject, apply."""
from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import TICKET_APPLIERS, TICKET_APPROVERS, require_role
from .models import (
    TicketApplyResult,
    TicketApprove,
    TicketDiff,
    TicketIn,
    TicketListOut,
    TicketOut,
    TicketReject,
    TicketStatus,
)
from .service import apply_ticket, open_ticket

router = APIRouter(prefix=f"{api_prefix}/tickets", tags=["tickets"])

_COLS = [
    "ticket_id", "title", "system_id", "extraction_id", "source_type",
    "status", "summary_md", "diff_json",
    "additions_count", "removals_count", "changes_count",
    "created_at", "created_by",
    "approved_at", "approved_by",
    "applied_at", "applied_by",
    "rejected_at", "rejected_by", "rejection_reason",
    "target_version_id",
]


def _row_to_out(r: list, system_name: str | None = None) -> TicketOut:
    try:
        diff = TicketDiff.model_validate_json(r[7] or "{}")
    except Exception:
        diff = TicketDiff()
    return TicketOut(
        ticket_id=r[0], title=r[1], system_id=r[2], extraction_id=r[3],
        source_type=cast(any, r[4]), status=cast(any, r[5]),
        summary_md=r[6], diff=diff,
        additions_count=int(r[8] or 0),
        removals_count=int(r[9] or 0),
        changes_count=int(r[10] or 0),
        created_at=r[11], created_by=r[12],
        approved_at=r[13], approved_by=r[14],
        applied_at=r[15], applied_by=r[16],
        rejected_at=r[17], rejected_by=r[18], rejection_reason=r[19],
        target_version_id=r[20],
        system_name=system_name,
    )


@router.get("", response_model=list[TicketListOut], operation_id="listTickets")
def list_tickets(
    sql: SqlDependency,
    status: TicketStatus | None = Query(None),
    system_id: str | None = Query(None),
) -> list[TicketListOut]:
    s = get_settings()
    where = []
    if status:
        where.append(f"t.status = '{status}'")
    if system_id:
        where.append(f"t.system_id = '{system_id.replace(chr(39), chr(39)*2)}'")
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT t.ticket_id, t.title, t.system_id, sys.system_name,
               t.source_type, t.status,
               t.additions_count, t.removals_count, t.changes_count,
               t.created_at, t.created_by, t.approved_at, t.approved_by,
               t.applied_at
        FROM {s.fq_table('reconciliation_tickets')} t
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = t.system_id
        {where_clause}
        ORDER BY
          CASE t.status WHEN 'OPEN' THEN 0 WHEN 'APPROVED' THEN 1
            WHEN 'APPLIED' THEN 2 ELSE 3 END,
          t.created_at DESC
        """,
    )
    return [
        TicketListOut(
            ticket_id=r[0], title=r[1], system_id=r[2], system_name=r[3],
            source_type=r[4], status=r[5],
            additions_count=int(r[6] or 0),
            removals_count=int(r[7] or 0),
            changes_count=int(r[8] or 0),
            created_at=r[9], created_by=r[10],
            approved_at=r[11], approved_by=r[12],
            applied_at=r[13],
        )
        for r in rows
    ]


@router.get("/{ticket_id}", response_model=TicketOut, operation_id="getTicket")
def get_ticket(ticket_id: str, sql: SqlDependency) -> TicketOut:
    s = get_settings()
    row = delta.fetch_one(
        sql,
        f"""
        SELECT {', '.join('t.'+c for c in _COLS)}, sys.system_name
        FROM {s.fq_table('reconciliation_tickets')} t
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = t.system_id
        WHERE t.ticket_id = '{ticket_id.replace(chr(39), chr(39)*2)}'
        """,
    )
    if not row:
        raise HTTPException(404, f"ticket '{ticket_id}' not found")
    return _row_to_out(row[:-1], system_name=row[-1])


@router.post("", response_model=TicketOut, operation_id="openTicket")
def create_ticket(
    payload: TicketIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TicketOut:
    actor = _current_email(user_ws)
    tid = open_ticket(
        sql,
        title=payload.title,
        system_id=payload.system_id,
        source_type=payload.source_type,
        diff=payload.diff,
        extraction_id=payload.extraction_id,
        summary_md=payload.summary_md,
        created_by=actor,
    )
    return get_ticket(tid, sql)


@router.post(
    "/{ticket_id}/approve",
    response_model=TicketOut,
    operation_id="approveTicket",
)
def approve(
    ticket_id: str,
    payload: TicketApprove,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TicketOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *TICKET_APPROVERS)
    s = get_settings()
    current = get_ticket(ticket_id, sql)
    if current.status != "OPEN":
        raise HTTPException(409, f"only OPEN tickets can be approved (current: {current.status})")
    now = datetime.utcnow()
    delta.update_by_id(
        sql,
        s.fq_table("reconciliation_tickets"),
        "ticket_id",
        ticket_id,
        {
            "status": "APPROVED",
            "approved_at": now,
            "approved_by": actor,
            "summary_md": (current.summary_md or "") + (f"\n\n_Approval note: {payload.note}_" if payload.note else ""),
        },
    )
    return get_ticket(ticket_id, sql)


@router.post(
    "/{ticket_id}/reject",
    response_model=TicketOut,
    operation_id="rejectTicket",
)
def reject(
    ticket_id: str,
    payload: TicketReject,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TicketOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *TICKET_APPROVERS)
    current = get_ticket(ticket_id, sql)
    if current.status not in ("OPEN", "APPROVED"):
        raise HTTPException(409, f"cannot reject ticket in status {current.status}")
    s = get_settings()
    now = datetime.utcnow()
    delta.update_by_id(
        sql,
        s.fq_table("reconciliation_tickets"),
        "ticket_id",
        ticket_id,
        {
            "status": "REJECTED",
            "rejected_at": now,
            "rejected_by": actor,
            "rejection_reason": payload.reason,
        },
    )
    return get_ticket(ticket_id, sql)


@router.post(
    "/{ticket_id}/apply",
    response_model=TicketApplyResult,
    operation_id="applyTicket",
)
def apply(
    ticket_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TicketApplyResult:
    actor = _current_email(user_ws)
    require_role(sql, actor, *TICKET_APPLIERS)
    return apply_ticket(sql, ticket_id, actor)
