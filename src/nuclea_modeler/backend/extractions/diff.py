"""Diff de extração contra catálogo Delta.

Extraído de ``extractions/service.py`` em refactor estrutural — o módulo
original concentrava 4 extractors (Lakebase/UC/DDL/DM1) + diff + persistência
em ~1200 linhas. Aqui só a função de diff; comportamento idêntico.
"""
from __future__ import annotations

from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from ..tickets.models import DiffEntity, TicketDiff
from .models import ExtractionSnapshot


def _quote_id(value: str | None) -> str:
    """Quote a trusted ID (from a prior DB query) for inlining in an IN list.

    Use ONLY com valores originados server-side, nunca user input direto.
    None/vazio viram ``"''"`` (compat com chamadas que podem receber None).
    """
    return "'" + (value or "").replace("'", "''") + "'"


def compute_diff_against_catalog(
    sql: Sql, system_id: str, snapshot: ExtractionSnapshot
) -> tuple[TicketDiff, dict[str, int]]:
    """Compara o snapshot extraído contra o estado atual do catálogo.

    Retorna ``(diff, summary)`` onde summary tem chaves: ``found``, ``new``,
    ``changed``, ``removed``. Diff contém ``DiffEntity`` por entity com:
    - ``op='add'``: full payload + attributes + indexes pra materializar
    - ``op='change'``: ``field_changes`` por campo (entity + attributes)
    - ``op='remove'``: só identificadores
    """
    s = get_settings()
    entity_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, entity_type,
               native_comment, row_count_approx, logical_name, description_md
        FROM {s.fq_table('entities')}
        WHERE system_id = :system_id
        """,
        [delta.param("system_id", system_id)],
    )
    catalog_index: dict[tuple[str, str], dict[str, Any]] = {}
    catalog_entity_ids_by_key: dict[tuple[str, str], str] = {}
    for r in entity_rows:
        eid, schema, tech, etype, comment, rowct, logical, desc = r
        key = (schema, tech)
        catalog_entity_ids_by_key[key] = eid
        catalog_index[key] = {
            "entity_type": etype,
            "native_comment": comment,
            "row_count_approx": rowct,
            "logical_name": logical,
            "description_md": desc,
        }

    # Fetch attributes só pras entities que existem no catálogo.
    attr_rows: list[list[Any]] = []
    if catalog_entity_ids_by_key:
        # entity_ids vêm da query trusted acima — safe inline.
        ids_csv = ", ".join(
            _quote_id(eid) for eid in catalog_entity_ids_by_key.values()
        )
        attr_rows = delta.fetch_all(
            sql,
            f"""
            SELECT entity_id, technical_name, native_data_type, is_nullable,
                   default_value, is_primary_key, native_comment, ordinal_position
            FROM {s.fq_table('attributes')}
            WHERE entity_id IN ({ids_csv})
            """,
        )
    attrs_by_entity: dict[str, list[dict[str, Any]]] = {}
    for r in attr_rows:
        eid = r[0]
        attrs_by_entity.setdefault(eid, []).append({
            "technical_name": r[1], "native_data_type": r[2],
            "is_nullable": r[3], "default_value": r[4],
            "is_primary_key": bool(r[5]),
            "native_comment": r[6],
            "ordinal_position": r[7],
        })

    diff_entries: list[DiffEntity] = []
    additions = 0
    removals = 0
    changes = 0

    snap_keys = {(e.schema_name, e.technical_name) for e in snapshot.entities}

    for entity in snapshot.entities:
        key = (entity.schema_name, entity.technical_name)
        if key not in catalog_index:
            additions += 1
            diff_entries.append(_build_add_entry(entity))
        else:
            field_changes = _collect_field_changes(
                entity,
                catalog_index[key],
                attrs_by_entity.get(catalog_entity_ids_by_key[key], []),
            )
            if field_changes:
                changes += 1
                diff_entries.append(
                    DiffEntity(
                        op="change",
                        schema_name=entity.schema_name,
                        technical_name=entity.technical_name,
                        entity_type=entity.entity_type,
                        field_changes=field_changes,
                    )
                )

    for key in catalog_index:
        if key not in snap_keys:
            removals += 1
            diff_entries.append(
                DiffEntity(
                    op="remove",
                    schema_name=key[0],
                    technical_name=key[1],
                    entity_type=catalog_index[key].get("entity_type") or "TABLE",
                )
            )

    summary = {
        "found": len(snapshot.entities),
        "new": additions,
        "changed": changes,
        "removed": removals,
    }
    diff = TicketDiff(
        entities=diff_entries,
        additions=additions,
        removals=removals,
        changes=changes,
    )
    return diff, summary


def _build_add_entry(entity) -> DiffEntity:
    return DiffEntity(
        op="add",
        schema_name=entity.schema_name,
        technical_name=entity.technical_name,
        entity_type=entity.entity_type,
        payload={
            "native_comment": entity.native_comment,
            "row_count_approx": entity.row_count_approx,
        },
        attributes=[a.model_dump() for a in entity.attributes],
        indexes=[ix.model_dump() for ix in getattr(entity, "indexes", []) or []],
    )


def _collect_field_changes(
    entity,
    catalog_entity: dict[str, Any],
    catalog_attrs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Coleta field_changes pra entity já existente no catálogo."""
    field_changes: list[dict[str, Any]] = []

    # Entity-level fields
    for field in ("native_comment", "row_count_approx", "entity_type"):
        ext_val = (
            getattr(entity, field)
            if field != "entity_type"
            else entity.entity_type
        )
        cat_val = catalog_entity.get(field)
        if ext_val != cat_val:
            field_changes.append({
                "field": field, "before": cat_val, "after": ext_val,
            })

    # Attributes: add / remove / change
    cat_attrs = {a["technical_name"]: a for a in catalog_attrs}
    ext_attrs = {a.technical_name: a for a in entity.attributes}

    for name, ext_a in ext_attrs.items():
        if name not in cat_attrs:
            field_changes.append({
                "field": f"attribute_add:{name}",
                "before": None,
                "after": (
                    f"{ext_a.native_data_type or ''} "
                    f"{'PK' if ext_a.is_primary_key else ''}"
                ).strip(),
            })
        else:
            cat_a = cat_attrs[name]
            if (cat_a.get("native_data_type") or "").lower() != (
                ext_a.native_data_type or ""
            ).lower():
                field_changes.append({
                    "field": f"attribute:{name}.native_data_type",
                    "before": cat_a.get("native_data_type"),
                    "after": ext_a.native_data_type,
                })
            if bool(cat_a.get("is_primary_key")) != bool(ext_a.is_primary_key):
                field_changes.append({
                    "field": f"attribute:{name}.is_primary_key",
                    "before": bool(cat_a.get("is_primary_key")),
                    "after": bool(ext_a.is_primary_key),
                })

    for name in cat_attrs:
        if name not in ext_attrs:
            field_changes.append({
                "field": f"attribute_remove:{name}",
                "before": cat_attrs[name].get("native_data_type"),
                "after": None,
            })

    return field_changes
