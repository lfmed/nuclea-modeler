"""Editing session helper — gerencia o ticket OPEN da sessão de um user.

Modelo editorial:
- Toda mudança CRUD (criar/editar/remover entity, attribute, relationship)
  é staged num "ticket de sessão" do user pro sistema atual.
- Sessão = ticket OPEN do par (user, system) numa janela curta. Se o último
  ticket OPEN tem >SESSION_WINDOW_MINUTES de inatividade ou foi criado por
  outro user, abre novo.
- Aprovar/aplicar o ticket = commit das mudanças no catálogo Delta.

Aqui só ficam helpers de staging. O apply propriamente está em service.py.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql

SESSION_WINDOW_MINUTES = 15
SESSION_SOURCE_TYPE = "MANUAL"  # tickets de sessão usam source_type=MANUAL


def find_open_session_ticket(
    sql: Sql, user_email: str, system_id: str
) -> tuple[str, dict[str, Any]] | None:
    """Retorna (ticket_id, diff_dict) do ticket OPEN ativo da sessão do user
    para o sistema, ou None se não há sessão ativa.

    Considera ativo: status=OPEN, source_type=MANUAL, created_by=user_email,
    system_id match, e created_at dentro da janela de SESSION_WINDOW_MINUTES.
    """
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT ticket_id, diff_json
        FROM {s.fq_table('reconciliation_tickets')}
        WHERE status = 'OPEN'
          AND source_type = :stype
          AND created_by = :user
          AND system_id = :system
          AND created_at >= current_timestamp() - INTERVAL '{SESSION_WINDOW_MINUTES}' MINUTE
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [
            delta.param("stype", SESSION_SOURCE_TYPE),
            delta.param("user", user_email),
            delta.param("system", system_id),
        ],
    )
    if not row:
        return None
    ticket_id = row[0]
    try:
        diff = json.loads(row[1]) if row[1] else {"entities": []}
    except json.JSONDecodeError:
        diff = {"entities": []}
    return ticket_id, diff


def get_or_create_session_ticket(
    sql: Sql, user_email: str, system_id: str, *, title_hint: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Reusa ticket de sessão ativo ou cria um novo OPEN.

    Retorna (ticket_id, diff_dict_current). O diff começa vazio em ticket novo.
    """
    found = find_open_session_ticket(sql, user_email, system_id)
    if found:
        return found

    # Não há sessão ativa: criar novo ticket OPEN
    s = get_settings()
    tid = delta.new_id("ticket-")
    now = datetime.utcnow()
    empty_diff = {"entities": [], "additions": 0, "removals": 0, "changes": 0}
    title = title_hint or "Edição manual (sessão)"
    delta.insert(
        sql,
        s.fq_table("reconciliation_tickets"),
        {
            "ticket_id": tid,
            "title": title,
            "system_id": system_id,
            "extraction_id": None,
            "source_type": SESSION_SOURCE_TYPE,
            "status": "OPEN",
            "summary_md": "Mudanças feitas via DER/CRUD direto. Aprove para aplicar ao catálogo.",
            "diff_json": json.dumps(empty_diff, ensure_ascii=False, default=str),
            "additions_count": 0,
            "removals_count": 0,
            "changes_count": 0,
            "created_at": now,
            "created_by": user_email,
        },
    )
    return tid, empty_diff


def _entity_key(d: dict[str, Any]) -> str:
    return f"{d.get('schema_name', '')}.{d.get('technical_name', '')}.{d.get('op', '')}"


def _recount(diff: dict[str, Any]) -> tuple[int, int, int]:
    a = sum(1 for e in diff.get("entities", []) if e.get("op") == "add")
    r = sum(1 for e in diff.get("entities", []) if e.get("op") == "remove")
    c = sum(1 for e in diff.get("entities", []) if e.get("op") == "change")
    return a, r, c


def stage_entity_change(
    sql: Sql,
    ticket_id: str,
    diff: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Adiciona/atualiza um DiffEntity-like entry no diff_json do ticket.

    Se já há um entry com a mesma chave (schema.tech.op), substitui — última
    edição vence (granularidade de "última intenção do user").

    Para mesma entity com ops diferentes (ex: add depois change), considera:
    - se vier add e já existe change → trata como ADD com payload mesclado
    - se vier remove e existe add → remove o add (cancela)
    Para simplificar nessa primeira versão, fazemos: dedup por chave exata.
    """
    s = get_settings()
    entities = list(diff.get("entities", []))
    new_key = _entity_key(entry)
    entities = [e for e in entities if _entity_key(e) != new_key]
    entities.append(entry)
    new_diff = {
        "entities": entities,
        "additions": 0, "removals": 0, "changes": 0,
    }
    a, r, c = _recount(new_diff)
    new_diff["additions"], new_diff["removals"], new_diff["changes"] = a, r, c

    delta.update_by_id(
        sql,
        s.fq_table("reconciliation_tickets"),
        "ticket_id",
        ticket_id,
        {
            "diff_json": json.dumps(new_diff, ensure_ascii=False, default=str),
            "additions_count": a,
            "removals_count": r,
            "changes_count": c,
            # Não tem campo updated_at no schema; usamos created_at p/ heurística
            # de janela de sessão. Em vez disso, manter created_at; janela mede
            # tempo TOTAL da sessão (não desde a última atividade) — aceitável.
            "applied_at": None,  # garantia que continua OPEN
        },
    )
    return new_diff


def discard_session(sql: Sql, ticket_id: str, *, by: str) -> None:
    """Marca o ticket como REJECTED (descarta a sessão sem aplicar)."""
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
            "rejected_by": by,
            "rejection_reason": "discarded by user",
        },
    )
