"""Business service for DDL export — Módulo 10."""
from __future__ import annotations

from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .generators import GENERATORS
from .models import DDLExportRequest, DDLExportResult, DDLObjectResult


_ENT_COLS = [
    "entity_id", "system_id", "schema_name", "technical_name", "logical_name",
    "description_md", "entity_type", "native_comment",
]

_ATTR_COLS = [
    "attribute_id", "entity_id", "technical_name", "logical_name",
    "ordinal_position", "native_data_type", "is_nullable", "default_value",
    "is_primary_key", "description_md", "native_comment",
]


def _entity_row_to_dict(r: list[Any]) -> dict[str, Any]:
    return dict(zip(_ENT_COLS, r))


def _attr_row_to_dict(r: list[Any]) -> dict[str, Any]:
    d = dict(zip(_ATTR_COLS, r))
    if d.get("is_nullable") is not None:
        d["is_nullable"] = bool(d["is_nullable"])
    d["is_primary_key"] = bool(d.get("is_primary_key"))
    return d


def fetch_entities_with_attrs(
    sql: Sql,
    system_id: str,
    entity_ids: list[str] | None = None,
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Load entities for a system + their attributes (sorted by ordinal_position).

    If entity_ids is provided, restrict to that subset.
    Returns a list of (entity_dict, sorted_attrs).
    """
    s = get_settings()
    sys_lit = "'" + system_id.replace("'", "''") + "'"
    where = [f"e.system_id = {sys_lit}"]
    if entity_ids:
        ids = ", ".join("'" + i.replace("'", "''") + "'" for i in entity_ids)
        where.append(f"e.entity_id IN ({ids})")
    where_clause = " AND ".join(where)

    ent_rows = delta.fetch_all(
        sql,
        f"""
        SELECT {', '.join('e.' + c for c in _ENT_COLS)}
        FROM {s.fq_table('entities')} e
        WHERE {where_clause}
        ORDER BY e.schema_name, e.technical_name
        """,
    )
    entities = [_entity_row_to_dict(r) for r in ent_rows]
    if not entities:
        return []

    eids = ", ".join("'" + e["entity_id"].replace("'", "''") + "'" for e in entities)
    attr_rows = delta.fetch_all(
        sql,
        f"""
        SELECT {', '.join(_ATTR_COLS)}
        FROM {s.fq_table('attributes')}
        WHERE entity_id IN ({eids})
        ORDER BY entity_id, COALESCE(ordinal_position, 999999), technical_name
        """,
    )
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for r in attr_rows:
        d = _attr_row_to_dict(r)
        by_entity.setdefault(d["entity_id"], []).append(d)

    return [(ent, by_entity.get(ent["entity_id"], [])) for ent in entities]


def generate_export(
    sql: Sql,
    payload: DDLExportRequest,
    actor: str | None = None,
) -> DDLExportResult:
    """Generate DDL for all entities matching the request payload."""
    pairs = fetch_entities_with_attrs(sql, payload.system_id, payload.entity_ids)
    generator = GENERATORS.get(payload.dialect)
    files: list[DDLObjectResult] = []

    for entity, attrs in pairs:
        schema = entity.get("schema_name") or ""
        name = entity.get("technical_name") or ""
        object_name = f"{schema}.{name}" if schema else name
        entity_type = entity.get("entity_type") or "TABLE"
        object_kind = "VIEW" if entity_type in {"VIEW", "MATERIALIZED_VIEW"} else "TABLE"
        errors: list[str] = []
        ddl_text = ""
        try:
            if generator is None:
                raise ValueError(f"No generator registered for dialect '{payload.dialect}'")
            ddl_text = generator(entity, attrs, payload)
        except Exception as exc:  # noqa: BLE001 — surface per-object failures
            errors.append(f"{type(exc).__name__}: {exc}")
            ddl_text = f"-- ERROR generating DDL for {object_name}: {exc}"

        files.append(
            DDLObjectResult(
                object_name=object_name,
                object_kind=object_kind,  # type: ignore[arg-type]
                ddl_text=ddl_text,
                errors=errors,
            )
        )

    combined_text = "\n\n-- ---\n\n".join(f.ddl_text for f in files)
    success_count = sum(1 for f in files if not f.errors)
    error_count = len(files) - success_count

    return DDLExportResult(
        dialect=payload.dialect,
        total_objects=len(files),
        success_count=success_count,
        error_count=error_count,
        files=files,
        combined_text=combined_text,
    )
