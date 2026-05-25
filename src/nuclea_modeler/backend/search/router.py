"""Global search across catalog, glossary, tickets and admin tables.

Implements a deliberately simple `LIKE`-based search — good enough for the
MVP and fast on Delta tables of low cardinality. Aggregates up to 20 results
total, grouped by kind on the client.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..._metadata import api_prefix
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency


SearchKind = Literal[
    "entity",
    "attribute",
    "term",
    "flag",
    "ticket",
    "connection",
    "system",
]


class SearchResult(BaseModel):
    kind: SearchKind
    id: str
    label: str
    sublabel: str | None = None
    path: str


class SearchResults(BaseModel):
    q: str
    total: int
    results: list[SearchResult]


router = APIRouter(prefix=f"{api_prefix}/search", tags=["search"])


def _escape_like(q: str) -> str:
    """Escape SQL LIKE wildcards (%, _) and single quotes."""
    return (
        q.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace("'", "''")
    )


@router.get("", response_model=SearchResults, operation_id="globalSearch")
def global_search(
    sql: SqlDependency,
    q: str = Query("", description="Texto a buscar"),
    limit: int = Query(20, ge=1, le=50),
) -> SearchResults:
    q = (q or "").strip()
    if len(q) < 2:
        return SearchResults(q=q, total=0, results=[])

    s = get_settings()
    safe = _escape_like(q.lower())
    pat = f"'%{safe}%'"
    esc = " ESCAPE '\\\\'"
    # Per-kind caps so a single table cannot dominate the result list.
    per_kind = max(2, min(limit, 8))

    results: list[SearchResult] = []

    # Entities ------------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT e.entity_id, e.technical_name, e.logical_name, e.domain, e.schema_name
            FROM {s.fq_table('entities')} e
            WHERE LOWER(COALESCE(e.technical_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(e.logical_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(e.description_md, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(e.domain, '')) LIKE {pat}{esc}
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="entity",
                    id=r[0],
                    label=r[2] or r[1] or "(sem nome)",
                    sublabel=f"{r[4] or ''}.{r[1] or ''} — {r[3] or 'sem domínio'}",
                    path=f"/entities/{r[0]}",
                )
            )
    except Exception:
        pass

    # Attributes ---------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT a.attribute_id, a.technical_name, a.logical_name, a.entity_id, e.technical_name
            FROM {s.fq_table('attributes')} a
            LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id
            WHERE LOWER(COALESCE(a.technical_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(a.logical_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(a.description_md, '')) LIKE {pat}{esc}
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="attribute",
                    id=r[0],
                    label=r[2] or r[1] or "(sem nome)",
                    sublabel=f"{r[4] or 'entidade'} · {r[1] or ''}",
                    path=f"/entities/{r[3]}",
                )
            )
    except Exception:
        pass

    # Glossary terms -----------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT term_id, canonical_name, definition, domain
            FROM {s.fq_table('glossary_terms')}
            WHERE LOWER(COALESCE(canonical_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(definition, '')) LIKE {pat}{esc}
               OR EXISTS (
                    SELECT 1 FROM (SELECT explode(COALESCE(synonyms, array())) AS syn) syns
                    WHERE LOWER(syns.syn) LIKE {pat}{esc}
               )
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="term",
                    id=r[0],
                    label=r[1] or "(termo)",
                    sublabel=(r[2] or "")[:120],
                    path=f"/glossary/{r[0]}",
                )
            )
    except Exception:
        pass

    # Flags --------------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT flag_id, flag_key, display_name, category
            FROM {s.fq_table('flags')}
            WHERE is_active = true AND (
                LOWER(COALESCE(flag_key, '')) LIKE {pat}{esc}
                OR LOWER(COALESCE(display_name, '')) LIKE {pat}{esc}
                OR LOWER(COALESCE(description, '')) LIKE {pat}{esc}
            )
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="flag",
                    id=r[0],
                    label=r[2] or r[1] or "(flag)",
                    sublabel=f"{r[3] or 'CUSTOM'} · {r[1] or ''}",
                    path="/flags",
                )
            )
    except Exception:
        pass

    # Tickets ------------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT ticket_id, title, status
            FROM {s.fq_table('reconciliation_tickets')}
            WHERE LOWER(COALESCE(title, '')) LIKE {pat}{esc}
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="ticket",
                    id=r[0],
                    label=r[1] or "(ticket)",
                    sublabel=f"status: {r[2] or '?'}",
                    path=f"/tickets/{r[0]}",
                )
            )
    except Exception:
        pass

    # Connections --------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT connection_id, alias, environment, connection_type
            FROM {s.fq_table('connections')}
            WHERE LOWER(COALESCE(alias, '')) LIKE {pat}{esc}
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="connection",
                    id=r[0],
                    label=r[1] or "(conexão)",
                    sublabel=f"{r[2] or '?'} · {r[3] or '?'}",
                    path=f"/connections/{r[0]}",
                )
            )
    except Exception:
        pass

    # Systems ------------------------------------------------------------
    try:
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT system_id, system_name, description, domain
            FROM {s.fq_table('systems')}
            WHERE LOWER(COALESCE(system_name, '')) LIKE {pat}{esc}
               OR LOWER(COALESCE(description, '')) LIKE {pat}{esc}
            LIMIT {per_kind}
            """,
        )
        for r in rows:
            results.append(
                SearchResult(
                    kind="system",
                    id=r[0],
                    label=r[1] or "(sistema)",
                    sublabel=r[3] or (r[2] or "")[:120],
                    path="/entities",
                )
            )
    except Exception:
        pass

    return SearchResults(q=q, total=len(results), results=results[:limit])
