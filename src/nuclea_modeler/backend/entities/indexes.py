"""Catálogo de índices e particionamento por entity.

Mantém o modelo editorial: toda mutação vai pro ticket OPEN do user via
``field_changes`` com prefixos ``index_add:``, ``index_remove:``,
``index_change:``, ``partitioning:set``. O apply em ``tickets/service.py``
chama de volta as funções ``apply_*`` daqui pra materializar.

Reads suportam overlay: ``list_indexes_for_entity`` e ``get_partitioning``
aceitam um diff de sessão e mesclam pendings com badge ``pending_op``.

Helpers públicos:
    - ``list_indexes_for_entity(sql, entity_id, *, session_diff=None)``
    - ``get_partitioning(sql, entity_id, *, session_diff=None)``
    - ``apply_session_overlay_to_indexes(catalog, diff, entity_id)``
    - ``apply_session_overlay_to_partitioning(catalog, diff, entity_id)``
    - ``stage_index_*``: empilha mutação no ticket OPEN
    - ``apply_index_*`` / ``apply_partitioning_set``: chamadas pelo apply
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..tickets.session import get_or_create_session_ticket, stage_entity_change
from .index_overlay import (
    apply_session_overlay_to_indexes as apply_session_overlay_to_indexes,
    apply_session_overlay_to_partitioning as apply_session_overlay_to_partitioning,
)
from .models import (
    EntityIndexIn,
    EntityIndexOut,
    EntityPartitioningIn,
    EntityPartitioningOut,
    IndexColumn,
)

# Campos sentinela usados no ent_change para sinalizar ao apply que a
# mutação alvo é de índice/partição, e não da entity em si.
FIELD_INDEX_ADD = "index_add"
FIELD_INDEX_REMOVE = "index_remove"
FIELD_INDEX_CHANGE = "index_change"
FIELD_PARTITIONING_SET = "partitioning:set"


# ─── Serialização ───────────────────────────────────────────────────────────


def _columns_to_json(cols: list[IndexColumn]) -> str:
    return json.dumps([c.model_dump() for c in cols])


def _columns_from_json(raw: str | None) -> list[IndexColumn]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    out: list[IndexColumn] = []
    for item in data:
        if isinstance(item, dict) and item.get("name"):
            out.append(
                IndexColumn(
                    name=str(item["name"]),
                    direction=item.get("direction", "ASC") or "ASC",
                )
            )
    return out


def _idx_row_to_out(r: list) -> EntityIndexOut:
    return EntityIndexOut(
        index_id=r[0],
        entity_id=r[1],
        index_name=r[2],
        index_type=r[3] or "BTREE",
        columns=_columns_from_json(r[4]),
        include_columns=list(r[5]) if r[5] else [],
        partial_where=r[6],
        is_unique=bool(r[7]) if r[7] is not None else False,
        native_comment=r[8],
        description_md=r[9],
        origin=r[10],
        created_at=r[11],
        created_by=r[12],
        updated_at=r[13],
        updated_by=r[14],
    )


def _part_row_to_out(r: list) -> EntityPartitioningOut:
    bounds = None
    if r[4]:
        try:
            bounds = json.loads(r[4])
        except (json.JSONDecodeError, TypeError):
            bounds = None
    columns = []
    if r[2]:
        try:
            columns = json.loads(r[2])
            if not isinstance(columns, list):
                columns = []
        except (json.JSONDecodeError, TypeError):
            columns = []
    return EntityPartitioningOut(
        entity_id=r[0],
        strategy=r[1] or "NONE",
        columns=columns,
        num_partitions=int(r[3]) if r[3] is not None else None,
        bounds=bounds,
        description_md=r[5],
        origin=r[6],
        created_at=r[7],
        created_by=r[8],
        updated_at=r[9],
        updated_by=r[10],
    )


# ─── Reads (catálogo só, sem overlay) ───────────────────────────────────────


_IDX_COLS = [
    "index_id", "entity_id", "index_name", "index_type", "columns_json",
    "include_columns", "partial_where", "is_unique", "native_comment",
    "description_md", "origin",
    "created_at", "created_by", "updated_at", "updated_by",
]

_PART_COLS = [
    "entity_id", "strategy", "columns_json", "num_partitions", "bounds_json",
    "description_md", "origin",
    "created_at", "created_by", "updated_at", "updated_by",
]


def list_indexes_for_entity(
    sql, entity_id: str, *, session_diff: dict[str, Any] | None = None,
) -> list[EntityIndexOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {", ".join(_IDX_COLS)}
        FROM {s.fq_table('entity_indexes')}
        WHERE entity_id = :entity_id
        ORDER BY index_name
        """,
        [delta.param("entity_id", entity_id)],
    )
    catalog = [_idx_row_to_out(r) for r in rows]
    if session_diff:
        return apply_session_overlay_to_indexes(catalog, session_diff, entity_id)
    return catalog


def get_partitioning(
    sql, entity_id: str, *, session_diff: dict[str, Any] | None = None,
) -> EntityPartitioningOut | None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {", ".join(_PART_COLS)}
        FROM {s.fq_table('entity_partitioning')}
        WHERE entity_id = :entity_id
        """,
        [delta.param("entity_id", entity_id)],
    )
    catalog = _part_row_to_out(row) if row else None
    if session_diff:
        return apply_session_overlay_to_partitioning(catalog, session_diff, entity_id)
    return catalog


# Overlay editorial: helpers em ``index_overlay.py`` (re-exportados acima).


# ─── Stage no ticket OPEN ───────────────────────────────────────────────────


def _resolve_entity_keys(sql, entity_id: str) -> tuple[str, str, str, str] | None:
    """Mesma lógica de entities/router.py:_resolve_entity_keys — duplicada
    aqui pra evitar import circular."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT entity_id, system_id, schema_name, technical_name, entity_type
        FROM {s.fq_table('entities')}
        WHERE entity_id = :entity_id
        """,
        [delta.param("entity_id", entity_id)],
    )
    if not row:
        return None
    return (row[1], row[2], row[3], row[4] or "TABLE")


def _stage_field_change(
    sql,
    *,
    actor: str,
    entity_id: str,
    field_name: str,
    before: Any | None,
    after: Any | None,
) -> tuple[str, str] | None:
    """Empilha um field_change na entity host (op=change). Idêntico ao
    pattern usado por attributes."""
    keys = _resolve_entity_keys(sql, entity_id)
    if not keys:
        return None
    system_id, schema_name, technical_name, entity_type = keys
    ticket_id, diff = get_or_create_session_ticket(sql, actor, system_id)
    entry = {
        "op": "change",
        "schema_name": schema_name,
        "technical_name": technical_name,
        "entity_type": entity_type,
        "payload": {"target_entity_id": entity_id},
        "field_changes": [
            {"field": field_name, "before": before, "after": after}
        ],
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return ticket_id, system_id


def stage_index_add(
    sql,
    *,
    actor: str,
    entity_id: str,
    index_id: str,
    payload: EntityIndexIn,
) -> tuple[str, str] | None:
    after = {
        "index_id": index_id,
        "index_name": payload.index_name,
        "index_type": payload.index_type,
        "columns": [c.model_dump() for c in payload.columns],
        "include_columns": payload.include_columns,
        "partial_where": payload.partial_where,
        "is_unique": payload.is_unique,
        "description_md": payload.description_md,
        "native_comment": payload.native_comment,
    }
    return _stage_field_change(
        sql,
        actor=actor,
        entity_id=entity_id,
        field_name=f"{FIELD_INDEX_ADD}:{payload.index_name}",
        before=None,
        after=after,
    )


def stage_index_remove(
    sql,
    *,
    actor: str,
    entity_id: str,
    index_id: str,
    index_name: str,
) -> tuple[str, str] | None:
    return _stage_field_change(
        sql,
        actor=actor,
        entity_id=entity_id,
        field_name=f"{FIELD_INDEX_REMOVE}:{index_name}",
        before={"index_id": index_id, "index_name": index_name},
        after=None,
    )


def stage_index_update(
    sql,
    *,
    actor: str,
    entity_id: str,
    index_id: str,
    payload: EntityIndexIn,
) -> tuple[str, str] | None:
    after = {
        "index_id": index_id,
        "index_name": payload.index_name,
        "index_type": payload.index_type,
        "columns": [c.model_dump() for c in payload.columns],
        "include_columns": payload.include_columns,
        "partial_where": payload.partial_where,
        "is_unique": payload.is_unique,
        "description_md": payload.description_md,
        "native_comment": payload.native_comment,
    }
    return _stage_field_change(
        sql,
        actor=actor,
        entity_id=entity_id,
        field_name=f"{FIELD_INDEX_CHANGE}:{index_id}",
        before={"index_id": index_id},
        after=after,
    )


def stage_partitioning_set(
    sql,
    *,
    actor: str,
    entity_id: str,
    payload: EntityPartitioningIn,
) -> tuple[str, str] | None:
    after = {
        "strategy": payload.strategy,
        "columns": payload.columns,
        "num_partitions": payload.num_partitions,
        "bounds": payload.bounds,
        "description_md": payload.description_md,
    }
    return _stage_field_change(
        sql,
        actor=actor,
        entity_id=entity_id,
        field_name=FIELD_PARTITIONING_SET,
        before=None,
        after=after,
    )


# ─── Apply (chamado por tickets/service.py) ─────────────────────────────────


def apply_index_add(
    sql,
    *,
    entity_id: str,
    payload: dict,
    now: datetime,
    actor: str,
) -> None:
    s = get_settings()
    iid = payload.get("index_id") or delta.new_id("idx-")
    columns = payload.get("columns") or []
    cols_list = [
        IndexColumn(
            name=str(c.get("name", "")),
            direction=c.get("direction", "ASC") or "ASC",
        )
        for c in columns
        if isinstance(c, dict) and c.get("name")
    ]
    delta.insert(
        sql,
        s.fq_table("entity_indexes"),
        {
            "index_id": iid,
            "entity_id": entity_id,
            "index_name": payload.get("index_name", ""),
            "index_type": payload.get("index_type", "BTREE"),
            "columns_json": _columns_to_json(cols_list),
            "include_columns": list(payload.get("include_columns") or []),
            "partial_where": payload.get("partial_where"),
            "is_unique": bool(payload.get("is_unique", False)),
            "native_comment": payload.get("native_comment"),
            "description_md": payload.get("description_md"),
            "origin": payload.get("origin", "MANUAL"),
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )


def apply_index_remove(sql, *, entity_id: str, index_name: str) -> None:
    s = get_settings()
    delta.run_params(
        sql,
        f"""
        DELETE FROM {s.fq_table('entity_indexes')}
        WHERE entity_id = :entity_id AND index_name = :index_name
        """,
        [
            delta.param("entity_id", entity_id),
            delta.param("index_name", index_name),
        ],
    )


def apply_index_change(
    sql,
    *,
    entity_id: str,
    index_id: str,
    payload: dict,
    now: datetime,
    actor: str,
) -> None:
    """Replace-style update — substitui o índice inteiro por simplicidade.
    Como o conjunto de campos é pequeno e indexes são imutáveis em SGBDs
    reais, esse approach evita field-level merging."""
    s = get_settings()
    columns = payload.get("columns") or []
    cols_list = [
        IndexColumn(
            name=str(c.get("name", "")),
            direction=c.get("direction", "ASC") or "ASC",
        )
        for c in columns
        if isinstance(c, dict) and c.get("name")
    ]
    delta.run_params(
        sql,
        f"""
        UPDATE {s.fq_table('entity_indexes')}
        SET index_name = :index_name,
            index_type = :index_type,
            columns_json = :columns_json,
            include_columns = :include_columns,
            partial_where = :partial_where,
            is_unique = :is_unique,
            description_md = :description_md,
            native_comment = :native_comment,
            updated_at = :updated_at,
            updated_by = :updated_by
        WHERE index_id = :index_id AND entity_id = :entity_id
        """,
        [
            delta.param("index_name", payload.get("index_name", "")),
            delta.param("index_type", payload.get("index_type", "BTREE")),
            delta.param("columns_json", _columns_to_json(cols_list)),
            delta.param("include_columns", list(payload.get("include_columns") or [])),
            delta.param("partial_where", payload.get("partial_where")),
            delta.param("is_unique", bool(payload.get("is_unique", False))),
            delta.param("description_md", payload.get("description_md")),
            delta.param("native_comment", payload.get("native_comment")),
            delta.param("updated_at", now),
            delta.param("updated_by", actor),
            delta.param("index_id", index_id),
            delta.param("entity_id", entity_id),
        ],
    )


def apply_partitioning_set(
    sql,
    *,
    entity_id: str,
    payload: dict,
    now: datetime,
    actor: str,
) -> None:
    """Upsert no entity_partitioning (1:1 com entity). Se strategy=NONE,
    remove a row inteira."""
    s = get_settings()
    strategy = payload.get("strategy", "NONE")
    if strategy == "NONE":
        delta.run_params(
            sql,
            f"DELETE FROM {s.fq_table('entity_partitioning')} WHERE entity_id = :entity_id",
            [delta.param("entity_id", entity_id)],
        )
        return

    columns_json = json.dumps(payload.get("columns") or [])
    bounds = payload.get("bounds")
    bounds_json = json.dumps(bounds) if bounds else None

    existing = delta.fetch_one_params(
        sql,
        f"SELECT entity_id FROM {s.fq_table('entity_partitioning')} WHERE entity_id = :entity_id",
        [delta.param("entity_id", entity_id)],
    )
    if existing:
        delta.run_params(
            sql,
            f"""
            UPDATE {s.fq_table('entity_partitioning')}
            SET strategy = :strategy,
                columns_json = :columns_json,
                num_partitions = :num_partitions,
                bounds_json = :bounds_json,
                description_md = :description_md,
                updated_at = :updated_at,
                updated_by = :updated_by
            WHERE entity_id = :entity_id
            """,
            [
                delta.param("strategy", strategy),
                delta.param("columns_json", columns_json),
                delta.param("num_partitions", payload.get("num_partitions")),
                delta.param("bounds_json", bounds_json),
                delta.param("description_md", payload.get("description_md")),
                delta.param("updated_at", now),
                delta.param("updated_by", actor),
                delta.param("entity_id", entity_id),
            ],
        )
    else:
        delta.insert(
            sql,
            s.fq_table("entity_partitioning"),
            {
                "entity_id": entity_id,
                "strategy": strategy,
                "columns_json": columns_json,
                "num_partitions": payload.get("num_partitions"),
                "bounds_json": bounds_json,
                "description_md": payload.get("description_md"),
                "origin": payload.get("origin", "MANUAL"),
                "created_at": now, "created_by": actor,
                "updated_at": now, "updated_by": actor,
            },
        )
