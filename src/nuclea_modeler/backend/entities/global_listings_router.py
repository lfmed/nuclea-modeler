"""Visões GLOBAIS de atributos e índices (ponto 5.2 do plano).

Até a v1.0014 atributos e índices só eram visíveis navegando entidade por
entidade. Estas rotas dão uma visão de nível de sistema/catálogo, paginada e
filtrável, seguindo o mesmo padrão de `list_entities_paginated`:

    GET /attributes/page  → PaginatedAttributes  (operation_id listAttributesPaginated)
    GET /indexes/page     → PaginatedIndexes      (operation_id listIndexesPaginated)

Decisões:
- Rotas montadas em prefixos próprios (`/attributes`, `/indexes`) porque não
  são sub-recursos de uma entity específica — são varreduras horizontais.
- Filtros expostos batem com o que a UI oferece: sistema, schema, busca,
  tipo/UNIQUE (índices), PK/flag (atributos).
- Sempre escondemos objetos de sistemas arquivados (mesma regra das entidades),
  via subquery em `systems.archived_at`.
- Ordenação por whitelist (identificadores não parametrizáveis) — igual ao
  endpoint de entidades — para fechar SQL injection via `sort_by`.
- Índices vêm com `columns_json` desserializado para a UI mostrar as colunas.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..._metadata import api_prefix
from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from .indexes import _columns_from_json
from .listings import escape_like, flags_by_attribute
from .models import (
    AttributeListOut,
    IndexListOut,
    PaginatedAttributes,
    PaginatedIndexes,
)

attributes_router = APIRouter(prefix=f"{api_prefix}/attributes", tags=["attributes"])
indexes_router = APIRouter(prefix=f"{api_prefix}/indexes", tags=["indexes"])


# Whitelist de ordenação — ver comentário em entities/router.py.
_ATTR_SORT_COLS = {
    "technical_name": "a.technical_name",
    "logical_name": "a.logical_name",
    "entity_technical_name": "e.technical_name",
    "schema_name": "e.schema_name",
    "system_name": "sys.system_name",
    "native_data_type": "a.native_data_type",
    "ordinal_position": "a.ordinal_position",
    "updated_at": "a.updated_at",
}

_IDX_SORT_COLS = {
    "index_name": "ix.index_name",
    "index_type": "ix.index_type",
    "entity_technical_name": "e.technical_name",
    "schema_name": "e.schema_name",
    "system_name": "sys.system_name",
    "is_unique": "ix.is_unique",
    "updated_at": "ix.updated_at",
}


def _archived_guard(alias: str, s) -> str:
    """Predicado que exclui objetos de sistemas arquivados."""
    return (
        f"{alias}.system_id NOT IN "
        f"(SELECT system_id FROM {s.fq_table('systems')} WHERE archived_at IS NOT NULL)"
    )


# ─── Atributos (visão global) ───────────────────────────────────────────────


@attributes_router.get(
    "/page",
    response_model=PaginatedAttributes,
    operation_id="listAttributesPaginated",
)
def list_attributes_paginated(
    sql: SqlDependency,
    system_id: str | None = None,
    schema_name: str | None = None,
    entity_id: str | None = None,
    is_primary_key: bool | None = None,
    q: str | None = Query(None, description="Busca textual (nome técnico/lógico)"),
    flag_id: str | None = Query(None, description="Filtra atributos com esta flag"),
    sort_by: str = Query("technical_name"),
    sort_dir: str = Query("asc"),
    page: int = 1,
    page_size: int = 50,
) -> PaginatedAttributes:
    """Lista atributos de todo o catálogo com contexto da entity-host.

    Filtros: sistema, schema, entidade, PK, busca textual e "por flag".
    Coluna de flags preenchida via 1 query agregada por página (evita N+1).
    """
    s = get_settings()
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size

    where: list[str] = []
    params: list = []
    # Sempre juntamos entities/systems: precisamos do contexto e do guard de
    # arquivados (attributes não tem system_id direto).
    if system_id:
        where.append("e.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    if schema_name:
        where.append("e.schema_name = :schema_name")
        params.append(delta.param("schema_name", schema_name))
    if entity_id:
        where.append("a.entity_id = :entity_id")
        params.append(delta.param("entity_id", entity_id))
    if is_primary_key is not None:
        where.append("a.is_primary_key = :is_pk")
        params.append(delta.param("is_pk", is_primary_key))
    if q and q.strip():
        pat = f"%{escape_like(q.strip().lower())}%"
        where.append(
            "(LOWER(COALESCE(a.technical_name, '')) LIKE :q ESCAPE '\\\\' "
            "OR LOWER(COALESCE(a.logical_name, '')) LIKE :q ESCAPE '\\\\')"
        )
        params.append(delta.param("q", pat))
    if flag_id:
        where.append(
            f"EXISTS (SELECT 1 FROM {s.fq_table('attribute_flags')} af "
            f"WHERE af.attribute_id = a.attribute_id AND af.flag_id = :flag_id)"
        )
        params.append(delta.param("flag_id", flag_id))
    where.append(_archived_guard("e", s))
    where_clause = "WHERE " + " AND ".join(where)

    sort_col = _ATTR_SORT_COLS.get(sort_by, "a.technical_name")
    direction = "ASC" if str(sort_dir).lower() == "asc" else "DESC"

    base_from = (
        f"FROM {s.fq_table('attributes')} a "
        f"JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id "
        f"LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id "
        f"{where_clause}"
    )

    total_row = delta.fetch_one_params(
        sql, f"SELECT COUNT(*) {base_from}", params,
    )
    total = int(total_row[0]) if total_row and total_row[0] is not None else 0

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT a.attribute_id, a.entity_id, e.technical_name, e.logical_name,
               e.schema_name, e.system_id, sys.system_name,
               a.technical_name, a.logical_name, a.ordinal_position,
               a.native_data_type, a.is_nullable, a.is_primary_key, a.updated_at
        {base_from}
        ORDER BY {sort_col} {direction}
        LIMIT {page_size} OFFSET {offset}
        """,
        params,
    )
    items = [
        AttributeListOut(
            attribute_id=r[0], entity_id=r[1],
            entity_technical_name=r[2], entity_logical_name=r[3],
            schema_name=r[4], system_id=r[5], system_name=r[6],
            technical_name=r[7], logical_name=r[8],
            ordinal_position=int(r[9]) if r[9] is not None else None,
            native_data_type=r[10],
            is_nullable=bool(r[11]) if r[11] is not None else None,
            is_primary_key=bool(r[12]),
            updated_at=r[13],
        )
        for r in rows
    ]
    flags_map = flags_by_attribute(sql, [it.attribute_id for it in items])
    for it in items:
        it.flags = flags_map.get(it.attribute_id, [])
    return PaginatedAttributes(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )


# ─── Índices (visão global) ─────────────────────────────────────────────────


@indexes_router.get(
    "/page",
    response_model=PaginatedIndexes,
    operation_id="listIndexesPaginated",
)
def list_indexes_paginated(
    sql: SqlDependency,
    system_id: str | None = None,
    schema_name: str | None = None,
    entity_id: str | None = None,
    index_type: str | None = None,
    is_unique: bool | None = None,
    q: str | None = Query(None, description="Busca textual (nome do índice)"),
    sort_by: str = Query("index_name"),
    sort_dir: str = Query("asc"),
    page: int = 1,
    page_size: int = 50,
) -> PaginatedIndexes:
    """Lista índices de todo o catálogo com contexto da entity-host.

    Filtros: sistema, schema, entidade, tipo de índice, UNIQUE e busca textual.
    """
    s = get_settings()
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size

    where: list[str] = []
    params: list = []
    if system_id:
        where.append("e.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    if schema_name:
        where.append("e.schema_name = :schema_name")
        params.append(delta.param("schema_name", schema_name))
    if entity_id:
        where.append("ix.entity_id = :entity_id")
        params.append(delta.param("entity_id", entity_id))
    if index_type:
        where.append("ix.index_type = :index_type")
        params.append(delta.param("index_type", index_type))
    if is_unique is not None:
        where.append("ix.is_unique = :is_unique")
        params.append(delta.param("is_unique", is_unique))
    if q and q.strip():
        pat = f"%{escape_like(q.strip().lower())}%"
        where.append("LOWER(COALESCE(ix.index_name, '')) LIKE :q ESCAPE '\\\\'")
        params.append(delta.param("q", pat))
    where.append(_archived_guard("e", s))
    where_clause = "WHERE " + " AND ".join(where)

    sort_col = _IDX_SORT_COLS.get(sort_by, "ix.index_name")
    direction = "ASC" if str(sort_dir).lower() == "asc" else "DESC"

    base_from = (
        f"FROM {s.fq_table('entity_indexes')} ix "
        f"JOIN {s.fq_table('entities')} e ON e.entity_id = ix.entity_id "
        f"LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id "
        f"{where_clause}"
    )

    total_row = delta.fetch_one_params(
        sql, f"SELECT COUNT(*) {base_from}", params,
    )
    total = int(total_row[0]) if total_row and total_row[0] is not None else 0

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT ix.index_id, ix.entity_id, e.technical_name, e.schema_name,
               e.system_id, sys.system_name, ix.index_name, ix.index_type,
               ix.columns_json, ix.is_unique, ix.origin, ix.updated_at
        {base_from}
        ORDER BY {sort_col} {direction}
        LIMIT {page_size} OFFSET {offset}
        """,
        params,
    )
    items = [
        IndexListOut(
            index_id=r[0], entity_id=r[1], entity_technical_name=r[2],
            schema_name=r[3], system_id=r[4], system_name=r[5],
            index_name=r[6], index_type=r[7] or "BTREE",
            columns=_columns_from_json(r[8]),
            is_unique=bool(r[9]) if r[9] is not None else False,
            origin=r[10], updated_at=r[11],
        )
        for r in rows
    ]
    return PaginatedIndexes(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )
