"""Business service for DDL export — Módulo 10."""
from __future__ import annotations

import json
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
import re

from .generators import GENERATORS, render_foreign_keys
from .models import DDLExportRequest, DDLExportResult, DDLObjectResult


_ENT_COLS = [
    "entity_id", "system_id", "schema_name", "technical_name", "logical_name",
    "description_md", "entity_type", "native_comment",
]

_ATTR_COLS = [
    "attribute_id", "entity_id", "technical_name", "logical_name",
    "ordinal_position", "native_data_type", "is_nullable", "default_value",
    "is_primary_key", "description_md", "native_comment",
    "check_constraint",  # round 6 pt 21 — emitido como CHECK (...) no DDL
]

_IDX_COLS = [
    "index_id", "entity_id", "index_name", "index_type", "columns_json",
    "include_columns", "partial_where", "is_unique",
]

_PART_COLS = [
    "entity_id", "strategy", "columns_json", "num_partitions", "bounds_json",
]


def _entity_row_to_dict(r: list[Any]) -> dict[str, Any]:
    return dict(zip(_ENT_COLS, r))


def _attr_row_to_dict(r: list[Any]) -> dict[str, Any]:
    d = dict(zip(_ATTR_COLS, r))
    # GOTCHA: a SQL API devolve BOOLEAN como string ("true"/"false") — bool("false")
    # é True. Sem as_bool, TODA coluna virava PK/NOT NULL no DDL exportado.
    if d.get("is_nullable") is not None:
        d["is_nullable"] = delta.as_bool(d["is_nullable"])
    d["is_primary_key"] = delta.as_bool(d.get("is_primary_key"))
    return d


def _idx_row_to_dict(r: list[Any]) -> dict[str, Any]:
    d = dict(zip(_IDX_COLS, r))
    cols_raw = d.pop("columns_json", None)
    cols: list[dict[str, str]] = []
    if cols_raw:
        try:
            parsed = json.loads(cols_raw)
            if isinstance(parsed, list):
                cols = [
                    {"name": str(c.get("name", "")), "direction": c.get("direction", "ASC") or "ASC"}
                    for c in parsed
                    if isinstance(c, dict) and c.get("name")
                ]
        except (json.JSONDecodeError, TypeError):
            cols = []
    d["columns"] = cols
    d["include_columns"] = delta.as_str_list(d.get("include_columns"))
    d["is_unique"] = delta.as_bool(d.get("is_unique"))
    return d


def _part_row_to_dict(r: list[Any]) -> dict[str, Any]:
    d = dict(zip(_PART_COLS, r))
    cols_raw = d.pop("columns_json", None)
    cols: list[str] = []
    if cols_raw:
        try:
            parsed = json.loads(cols_raw)
            if isinstance(parsed, list):
                cols = [str(c) for c in parsed if c]
        except (json.JSONDecodeError, TypeError):
            cols = []
    d["columns"] = cols
    bounds_raw = d.pop("bounds_json", None)
    if bounds_raw:
        try:
            d["bounds"] = json.loads(bounds_raw)
        except (json.JSONDecodeError, TypeError):
            d["bounds"] = None
    else:
        d["bounds"] = None
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
    where = ["e.system_id = :system_id"]
    params: list = [delta.param("system_id", system_id)]
    if entity_ids:
        # Bind one parameter per id, then expand into a comma-list. The
        # Statement Execution API doesn't accept array params, so we name
        # them :eid_0, :eid_1, ... — fully safe since values are bound.
        placeholders = []
        for idx, eid in enumerate(entity_ids):
            name = f"eid_{idx}"
            placeholders.append(f":{name}")
            params.append(delta.param(name, eid))
        where.append(f"e.entity_id IN ({', '.join(placeholders)})")
    where_clause = " AND ".join(where)

    ent_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join('e.' + c for c in _ENT_COLS)}
        FROM {s.fq_table('entities')} e
        WHERE {where_clause}
        ORDER BY e.schema_name, e.technical_name
        """,
        params,
    )
    entities = [_entity_row_to_dict(r) for r in ent_rows]
    if not entities:
        return []

    # Attribute lookup: entity_ids come from the trusted DB query above. Same
    # bind-by-name expansion as above.
    placeholders = []
    attr_params: list = []
    for idx, ent in enumerate(entities):
        name = f"aeid_{idx}"
        placeholders.append(f":{name}")
        attr_params.append(delta.param(name, ent["entity_id"]))
    attr_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join(_ATTR_COLS)}
        FROM {s.fq_table('attributes')}
        WHERE entity_id IN ({', '.join(placeholders)})
        ORDER BY entity_id, COALESCE(ordinal_position, 999999), technical_name
        """,
        attr_params,
    )
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for r in attr_rows:
        d = _attr_row_to_dict(r)
        by_entity.setdefault(d["entity_id"], []).append(d)

    return [(ent, by_entity.get(ent["entity_id"], [])) for ent in entities]


def fetch_indexes_and_partitioning(
    sql: Sql, entity_ids: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Fetch índices + particionamento pra um conjunto de entities.

    Retorna ``(indexes_by_entity, partitioning_by_entity)``.
    """
    if not entity_ids:
        return {}, {}
    s = get_settings()
    placeholders, params = [], []
    for idx, eid in enumerate(entity_ids):
        name = f"ieid_{idx}"
        placeholders.append(f":{name}")
        params.append(delta.param(name, eid))
    idx_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {", ".join(_IDX_COLS)}
        FROM {s.fq_table('entity_indexes')}
        WHERE entity_id IN ({", ".join(placeholders)})
        ORDER BY entity_id, index_name
        """,
        params,
    )
    indexes_by_entity: dict[str, list[dict[str, Any]]] = {}
    for r in idx_rows:
        d = _idx_row_to_dict(r)
        indexes_by_entity.setdefault(d["entity_id"], []).append(d)

    part_placeholders, part_params = [], []
    for idx, eid in enumerate(entity_ids):
        name = f"peid_{idx}"
        part_placeholders.append(f":{name}")
        part_params.append(delta.param(name, eid))
    part_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {", ".join(_PART_COLS)}
        FROM {s.fq_table('entity_partitioning')}
        WHERE entity_id IN ({", ".join(part_placeholders)})
        """,
        part_params,
    )
    partitioning_by_entity: dict[str, dict[str, Any]] = {}
    for r in part_rows:
        d = _part_row_to_dict(r)
        partitioning_by_entity[d["entity_id"]] = d
    return indexes_by_entity, partitioning_by_entity


_REL_FK_COLS = [
    "relationship_id", "source_entity_id", "target_entity_id",
    "source_attr_ids", "target_attr_ids",
    "fk_update_rule", "fk_delete_rule", "relationship_name",
]


def _fk_constraint_name(child_ref: str, parent_ref: str) -> str:
    """Nome de constraint SEGURO (identificador SQL) para a FK.

    Deriva de `fk_<filho>_<pai>` a partir dos nomes de tabela (sem schema),
    trocando qualquer caractere não-alfanumérico por `_`. Não usamos o
    relationship_name porque ele pode ter espaços/setas ("Pedido → Cliente").
    """
    def _bare(ref: str) -> str:
        base = ref.split(".")[-1]
        return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "tbl"

    return f"fk_{_bare(child_ref)}_{_bare(parent_ref)}"


def fetch_relationships(
    sql: Sql, system_id: str, entity_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Carrega os relacionamentos (FKs) de um sistema para emissão no DDL.

    round 5, pt 11: até então o export NÃO gerava nenhuma FK. Aqui buscamos os
    relacionamentos e, no generate_export, emitimos ``ALTER TABLE <filho> ADD
    CONSTRAINT … FOREIGN KEY … REFERENCES <pai> …`` após os CREATE TABLE.

    Convenção do modelo: source = PAI (PK em source_attr_ids), target = FILHO
    (colunas FK em target_attr_ids). Arrays vêm do delta já como listas.
    """
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {", ".join(_REL_FK_COLS)}
        FROM {s.fq_table('relationships')}
        WHERE system_id = :system_id
        """,
        [delta.param("system_id", system_id)],
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(zip(_REL_FK_COLS, r))
        # GOTCHA: ARRAY<STRING> volta da SQL API como string JSON ('["attr-1"]').
        # list() cru quebraria em caracteres → nenhuma coluna-FK casaria e a FK
        # jamais seria emitida (era o motivo do DDL sair sem NENHUMA foreign key).
        d["source_attr_ids"] = delta.as_str_list(d.get("source_attr_ids"))
        d["target_attr_ids"] = delta.as_str_list(d.get("target_attr_ids"))
        out.append(d)
    # Filtra para relacionamentos cujas DUAS pontas estão no conjunto exportado.
    if entity_ids is not None:
        keep = set(entity_ids)
        out = [
            d for d in out
            if d["source_entity_id"] in keep and d["target_entity_id"] in keep
        ]
    return out


def generate_export(
    sql: Sql,
    payload: DDLExportRequest,
    actor: str | None = None,
) -> DDLExportResult:
    """Generate DDL for all entities matching the request payload."""
    pairs = fetch_entities_with_attrs(sql, payload.system_id, payload.entity_ids)
    eids = [ent["entity_id"] for ent, _ in pairs]
    indexes_by_eid, part_by_eid = fetch_indexes_and_partitioning(sql, eids)
    generator = GENERATORS.get(payload.dialect)
    files: list[DDLObjectResult] = []

    for entity, attrs in pairs:
        # Anexa índices + partição ao dict da entity pros generators usarem.
        entity = {
            **entity,
            "_indexes": indexes_by_eid.get(entity["entity_id"], []),
            "_partitioning": part_by_eid.get(entity["entity_id"]),
        }
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

    # ── Foreign keys (round 5, pt 11) ─────────────────────────────────────────
    # Emitidas como ALTER TABLE após os CREATE TABLE. Só entram FKs cujas colunas
    # (pai E filho) foram resolvidas — relacionamento sem mapeamento coluna-a-coluna
    # é ignorado (não dá pra emitir uma FK sem colunas). source=PAI, target=FILHO.
    fk_statements: list[str] = []
    rels = fetch_relationships(sql, payload.system_id, eids)
    if rels:
        ent_ref_by_id: dict[str, str] = {}
        attr_name_by_id: dict[str, str] = {}
        for ent, attrs in pairs:
            schema = ent.get("schema_name") or ""
            nm = ent.get("technical_name") or ""
            ent_ref_by_id[ent["entity_id"]] = (
                f"{schema}.{nm}" if payload.qualify_schema and schema else nm
            )
            for a in attrs:
                attr_name_by_id[a["attribute_id"]] = a["technical_name"]

        resolved_fks: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for r in rels:
            parent_id = r["source_entity_id"]
            child_id = r["target_entity_id"]
            if parent_id not in ent_ref_by_id or child_id not in ent_ref_by_id:
                continue
            parent_cols = [
                attr_name_by_id[i] for i in r["source_attr_ids"] if i in attr_name_by_id
            ]
            child_cols = [
                attr_name_by_id[i] for i in r["target_attr_ids"] if i in attr_name_by_id
            ]
            # Sem mapeamento coluna-a-coluna completo não dá pra emitir a FK.
            if not parent_cols or not child_cols or len(parent_cols) != len(child_cols):
                continue
            base = _fk_constraint_name(ent_ref_by_id[child_id], ent_ref_by_id[parent_id])
            name = base
            n = 2
            while name in used_names:  # unicidade dentro do arquivo
                name = f"{base}_{n}"
                n += 1
            used_names.add(name)
            resolved_fks.append({
                "name": name,
                "child_ref": ent_ref_by_id[child_id],
                "parent_ref": ent_ref_by_id[parent_id],
                "child_cols": child_cols,
                "parent_cols": parent_cols,
                "on_update": r.get("fk_update_rule"),
                "on_delete": r.get("fk_delete_rule"),
            })
        fk_statements = render_foreign_keys(resolved_fks, payload)

    combined_text = "\n\n-- ---\n\n".join(f.ddl_text for f in files)
    if fk_statements:
        combined_text += (
            "\n\n-- ---\n\n-- Foreign Keys (relacionamentos)\n"
            + "\n\n".join(fk_statements)
        )
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
