"""Dashboard endpoints — agregados pra a home do app."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..._metadata import api_prefix
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency

router = APIRouter(prefix=f"{api_prefix}/dashboard", tags=["dashboard"])


class EnvCount(BaseModel):
    environment: str | None = None
    count: int = 0


class TicketStats(BaseModel):
    open: int = 0
    approved: int = 0
    applied: int = 0
    rejected: int = 0


class RecentItem(BaseModel):
    kind: str  # ticket|extraction|system|entity
    id: str
    label: str
    actor: str | None = None
    at: datetime | None = None
    status: str | None = None


class DashboardSummary(BaseModel):
    systems_total: int = 0
    systems_active: int = 0
    systems_by_env: list[EnvCount] = Field(default_factory=list)
    entities_total: int = 0
    entities_shared: int = 0
    attributes_total: int = 0
    relationships_total: int = 0
    tickets: TicketStats = Field(default_factory=TicketStats)
    extractions_last_7d: int = 0
    recent: list[RecentItem] = Field(default_factory=list)


@router.get("/summary", response_model=DashboardSummary, operation_id="dashboardSummary")
def summary(sql: SqlDependency) -> DashboardSummary:
    s = get_settings()

    def _scalar(query: str, params: list | None = None) -> int:
        row = (
            delta.fetch_one_params(sql, query, params)
            if params
            else delta.fetch_one(sql, query)
        )
        return int(row[0]) if row and row[0] is not None else 0

    out = DashboardSummary()

    # ─── Sistemas ──────────────────────────────────────────────────────────────
    out.systems_total = _scalar(
        f"SELECT COUNT(*) FROM {s.fq_table('systems')}"
    )
    out.systems_active = _scalar(
        f"SELECT COUNT(*) FROM {s.fq_table('systems')} WHERE is_active = true"
    )
    try:
        env_rows = delta.fetch_all(
            sql,
            f"""
            SELECT environment, COUNT(*)
            FROM {s.fq_table('systems')}
            GROUP BY environment
            ORDER BY 2 DESC
            """,
        )
        out.systems_by_env = [
            EnvCount(environment=r[0], count=int(r[1])) for r in env_rows
        ]
    except Exception:
        # Coluna environment pode não existir em ambientes ainda não migrados.
        out.systems_by_env = []

    # ─── Entidades / atributos / relacionamentos ──────────────────────────────
    out.entities_total = _scalar(
        f"SELECT COUNT(*) FROM {s.fq_table('entities')}"
    )
    try:
        out.entities_shared = _scalar(
            f"SELECT COUNT(*) FROM {s.fq_table('entities')} WHERE is_shared = true"
        )
    except Exception:
        out.entities_shared = 0
    out.attributes_total = _scalar(
        f"SELECT COUNT(*) FROM {s.fq_table('attributes')}"
    )
    out.relationships_total = _scalar(
        f"SELECT COUNT(*) FROM {s.fq_table('relationships')}"
    )

    # ─── Tickets por status ───────────────────────────────────────────────────
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT status, COUNT(*)
            FROM {s.fq_table('reconciliation_tickets')}
            GROUP BY status
            """,
        )
        counts = {r[0]: int(r[1]) for r in rows}
        out.tickets = TicketStats(
            open=counts.get("OPEN", 0),
            approved=counts.get("APPROVED", 0),
            applied=counts.get("APPLIED", 0),
            rejected=counts.get("REJECTED", 0),
        )
    except Exception:
        pass

    # ─── Extrações últimos 7 dias ─────────────────────────────────────────────
    try:
        out.extractions_last_7d = _scalar(
            f"""
            SELECT COUNT(*) FROM {s.fq_table('extractions')}
            WHERE started_at >= current_timestamp() - INTERVAL 7 DAYS
            """
        )
    except Exception:
        out.extractions_last_7d = 0

    # ─── Atividade recente: 10 últimos tickets + 5 últimas extractions ────────
    recent: list[RecentItem] = []
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT ticket_id, title, created_by, created_at, status
            FROM {s.fq_table('reconciliation_tickets')}
            ORDER BY created_at DESC
            LIMIT 10
            """,
        )
        for r in rows:
            recent.append(
                RecentItem(
                    kind="ticket",
                    id=r[0],
                    label=r[1] or "Ticket",
                    actor=r[2],
                    at=r[3],
                    status=r[4],
                )
            )
    except Exception:
        pass
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT extraction_id, source_kind, created_by, started_at, status
            FROM {s.fq_table('extractions')}
            ORDER BY started_at DESC
            LIMIT 5
            """,
        )
        for r in rows:
            recent.append(
                RecentItem(
                    kind="extraction",
                    id=r[0],
                    label=f"Extração {r[1]}",
                    actor=r[2],
                    at=r[3],
                    status=r[4],
                )
            )
    except Exception:
        pass

    # Ordena combinado por timestamp desc
    def _key(item: RecentItem) -> Any:
        return item.at or datetime.min
    recent.sort(key=_key, reverse=True)
    out.recent = recent[:12]

    return out
