"""Editing session HTTP endpoints.

Expose the OPEN session ticket of the current user as a "draft state" so the
frontend can show a "you have N pending changes" badge and list them.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..tickets.models import SessionStateOut
from ..tickets.overlay import diff_counts
from ..tickets.session import discard_session, find_open_session_ticket

router = APIRouter(prefix=f"{api_prefix}/sessions", tags=["sessions"])


def _split_entries(diff: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    """Particiona `diff.entities` em (added, changed, removed)."""
    added: list[dict] = []
    changed: list[dict] = []
    removed: list[dict] = []
    for e in diff.get("entities") or []:
        if not isinstance(e, dict):
            continue
        op = e.get("op")
        if op == "add":
            added.append(e)
        elif op == "change":
            changed.append(e)
        elif op == "remove":
            removed.append(e)
    return added, changed, removed


@router.get(
    "/current",
    response_model=SessionStateOut | None,
    operation_id="getCurrentSession",
)
def get_current_session(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    system_id: str = Query(..., description="ID do sistema para o qual buscar a sessão OPEN"),
) -> SessionStateOut | None:
    """Retorna o estado da sessão editorial OPEN do user atual para o sistema.

    null se não há sessão (nenhum ticket OPEN do par user+system dentro da
    janela). Resposta inclui contagens e o conteúdo bruto de entries por op
    para a UI poder listar as mudanças pendentes.
    """
    actor = _current_email(user_ws)
    if not actor:
        return None
    found = find_open_session_ticket(sql, actor, system_id)
    if not found:
        return None
    ticket_id, diff = found
    additions, changes, removals = diff_counts(diff)
    added, changed, removed = _split_entries(diff)
    return SessionStateOut(
        ticket_id=ticket_id,
        system_id=system_id,
        additions=additions,
        changes=changes,
        removals=removals,
        entities_added=added,
        entities_changed=changed,
        entities_removed=removed,
    )


@router.post("/discard", operation_id="discardSession")
def discard_current_session(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    system_id: str = Query(..., description="Sistema cuja sessão será descartada"),
) -> dict:
    """Marca o ticket OPEN da sessão atual como REJECTED — rollback do staging."""
    actor = _current_email(user_ws)
    if not actor:
        return {"discarded": False, "reason": "no actor"}
    found = find_open_session_ticket(sql, actor, system_id)
    if not found:
        return {"discarded": False, "reason": "no open session"}
    ticket_id, _ = found
    discard_session(sql, ticket_id, by=actor)
    return {"discarded": True, "ticket_id": ticket_id}
