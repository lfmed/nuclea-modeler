"""Diagram (M4 DER) HTTP endpoints — view + layout persistence."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .overlay import apply_session_overlay
from ..tickets.session import (
    find_open_session_ticket,
    get_or_create_session_ticket,
    stage_entity_change,
)
from .models import (
    DiagramAttribute,
    DiagramEntity,
    DiagramIndexSummary,
    DiagramRelationship,
    DiagramView,
    LayoutOut,
    LayoutSaveIn,
    NodePosition,
    QuickEntityIn,
    SourceCheckResult,
    SourceValidationOut,
)

router = APIRouter(prefix=f"{api_prefix}/diagram", tags=["diagram"])

# Identifier validator for SQL object names (catalog/schema/table). Used where
# user input must be interpolated as an identifier — parameters cannot bind to
# identifiers in Databricks SQL, so we lock the shape down hard instead.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _require_ident(value: str, field: str) -> str:
    if not _IDENT_RE.match(value or ""):
        raise HTTPException(400, f"invalid {field}: must match {_IDENT_RE.pattern}")
    return value


def _build_diagram(
    sql,
    system_id: str,
    layout_name: str = "default",
    *,
    session_ticket_id: str | None = None,
    session_diff: dict[str, Any] | None = None,
) -> DiagramView:
    """Monta a view do DER.

    Quando `session_ticket_id`/`session_diff` são fornecidos, aplica overlay:
    - entries op=add → adiciona DiagramEntity virtual com pending_op="add"
    - entries op=change → mescla field_changes e flagga pending_op="change"
      (também aplica em attributes via field "attribute:NAME.subfield" e
      adições/remoções virtuais de attributes)
    - entries op=remove → mantém na lista com pending_op="remove" (frontend
      renderiza com opacidade)
    """
    s = get_settings()
    sys_row = delta.fetch_one_params(
        sql,
        f"SELECT system_name FROM {s.fq_table('systems')} "
        f"WHERE system_id = :system_id",
        [delta.param("system_id", system_id)],
    )
    system_name = sys_row[0] if sys_row else None

    ent_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, logical_name,
               entity_type, domain, criticality, description_md, native_comment
        FROM {s.fq_table('entities')}
        WHERE system_id = :system_id
        ORDER BY schema_name, technical_name
        """,
        [delta.param("system_id", system_id)],
    )
    entities_by_id: dict[str, DiagramEntity] = {}
    for r in ent_rows:
        eid = r[0]
        entities_by_id[eid] = DiagramEntity(
            entity_id=eid, system_id=system_id,
            schema_name=r[1], technical_name=r[2], logical_name=r[3],
            entity_type=r[4] or "TABLE", domain=r[5], criticality=r[6],
            description_md=r[7], native_comment=r[8],
        )

    if entities_by_id:
        # entity_ids come from a prior trusted query — safe to inline as IN
        # values. Parametrising an IN list of variable length isn't supported
        # by the Statement Execution API, so we list-quote.
        ids_csv = ", ".join(_quote_id(eid) for eid in entities_by_id)
        attr_rows = delta.fetch_all(
            sql,
            f"""
            SELECT attribute_id, entity_id, technical_name, logical_name,
                   native_data_type, is_primary_key, is_nullable, ordinal_position,
                   description_md, native_comment, business_rule
            FROM {s.fq_table('attributes')}
            WHERE entity_id IN ({ids_csv})
            ORDER BY entity_id, COALESCE(ordinal_position, 999999), technical_name
            """,
        )
        # Mark LGPD flagged attributes
        lgpd_attr_ids: set[str] = set()
        if attr_rows:
            attr_ids_csv = ", ".join(_quote_id(r[0]) for r in attr_rows)
            flagged_rows = delta.fetch_all(
                sql,
                f"""
                SELECT DISTINCT af.attribute_id
                FROM {s.fq_table('attribute_flags')} af
                JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
                WHERE af.attribute_id IN ({attr_ids_csv})
                  AND f.category = 'LGPD'
                """,
            )
            lgpd_attr_ids = {r[0] for r in flagged_rows}

        for r in attr_rows:
            attr_id, entity_id = r[0], r[1]
            ent = entities_by_id.get(entity_id)
            if not ent:
                continue
            attr = DiagramAttribute(
                attribute_id=attr_id,
                technical_name=r[2],
                logical_name=r[3],
                native_data_type=r[4],
                is_primary_key=delta.as_bool(r[5]),
                is_nullable=delta.as_bool(r[6]) if r[6] is not None else None,
                ordinal_position=int(r[7]) if r[7] is not None else None,
                description_md=r[8],
                native_comment=r[9],
                business_rule=r[10],
                has_lgpd_flag=attr_id in lgpd_attr_ids,
            )
            ent.attributes.append(attr)
            if attr.has_lgpd_flag:
                ent.has_lgpd_flag = True

        # Also flag entities with direct entity_flags LGPD
        lgpd_entity_rows = delta.fetch_all(
            sql,
            f"""
            SELECT DISTINCT ef.entity_id
            FROM {s.fq_table('entity_flags')} ef
            JOIN {s.fq_table('flags')} f ON f.flag_id = ef.flag_id
            WHERE ef.entity_id IN ({ids_csv}) AND f.category = 'LGPD'
            """,
        )
        for r in lgpd_entity_rows:
            ent = entities_by_id.get(r[0])
            if ent:
                ent.has_lgpd_flag = True

        # Storage: detalhes pros nodes do DER (contagem + lista resumida).
        # Carregamos todos os índices num único fetch, agrupamos por entity
        # e marcamos quais colunas estão em algum índice (pra ícone no attr).
        import json as _json
        idx_detail_rows = delta.fetch_all(
            sql,
            f"""
            SELECT entity_id, index_name, index_type, is_unique, columns_json
            FROM {s.fq_table('entity_indexes')}
            WHERE entity_id IN ({ids_csv})
            ORDER BY entity_id, index_name
            """,
        )
        indexed_attr_names_by_entity: dict[str, set[str]] = {}
        for r in idx_detail_rows:
            eid_v, ix_name, ix_type, ix_unique, cols_json = r
            ent = entities_by_id.get(eid_v)
            if not ent:
                continue
            cols: list[str] = []
            try:
                parsed = _json.loads(cols_json) if cols_json else []
                cols = [
                    str(c.get("name", ""))
                    for c in parsed
                    if isinstance(c, dict) and c.get("name")
                ]
            except (ValueError, TypeError):
                pass
            ent.indexes_count += 1
            ent.indexes.append(DiagramIndexSummary(
                index_name=ix_name,
                index_type=ix_type or "BTREE",
                is_unique=bool(ix_unique),
                columns=cols,
            ))
            indexed_attr_names_by_entity.setdefault(eid_v, set()).update(cols)

        # Aplica is_indexed nos atributos (após o loop acima ter populado).
        for eid_v, indexed_cols in indexed_attr_names_by_entity.items():
            ent = entities_by_id.get(eid_v)
            if not ent:
                continue
            for a in ent.attributes:
                if a.technical_name in indexed_cols:
                    a.is_indexed = True

        # Particionamento: estratégia + colunas
        part_rows = delta.fetch_all(
            sql,
            f"""
            SELECT entity_id, strategy, columns_json
            FROM {s.fq_table('entity_partitioning')}
            WHERE entity_id IN ({ids_csv})
            """,
        )
        for r in part_rows:
            ent = entities_by_id.get(r[0])
            if not ent or not r[1]:
                continue
            ent.partition_strategy = r[1]
            try:
                parsed = _json.loads(r[2]) if r[2] else []
                if isinstance(parsed, list):
                    ent.partition_columns = [str(c) for c in parsed if c]
            except (ValueError, TypeError):
                pass

    rel_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT relationship_id, source_entity_id, target_entity_id,
               rel_type, source_cardinality, target_cardinality,
               source_attr_ids, target_attr_ids, description, origin
        FROM {s.fq_table('relationships')}
        WHERE system_id = :system_id
        """,
        [delta.param("system_id", system_id)],
    )
    relationships: list[DiagramRelationship] = []
    for r in rel_rows:
        relationships.append(DiagramRelationship(
            relationship_id=r[0],
            source_entity_id=r[1], target_entity_id=r[2],
            rel_type=r[3], source_cardinality=r[4], target_cardinality=r[5],
            source_attrs=delta.as_str_list(r[6]),  # ARRAY<STRING> via string JSON
            target_attrs=delta.as_str_list(r[7]),
            description=r[8], origin=r[9],
        ))

    layout = _load_layout_dict(sql, system_id, layout_name)

    entities_list = list(entities_by_id.values())

    # ─── Editorial overlay (read-only) ─────────────────────────────────────
    # Aplica pending ops do ticket OPEN da sessão atual sem mexer no Delta.
    if session_diff:
        entities_list = apply_session_overlay(
            entities_list,
            system_id=system_id,
            session_ticket_id=session_ticket_id,
            session_diff=session_diff,
        )
        # Adiciona relationships pendentes (entries com schema_name=__relationship__)
        # como edges virtuais no DER pra mostrar as FKs antes do apply.
        rel_ids_existing = {r.relationship_id for r in relationships}
        for entry in session_diff.get("entities", []) or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("schema_name") != "__relationship__":
                continue
            if entry.get("op") != "add":
                continue  # change/remove não materializados aqui
            rid = entry.get("technical_name") or ""
            if rid in rel_ids_existing:
                continue
            p = entry.get("payload") or {}
            relationships.append(DiagramRelationship(
                relationship_id=rid,
                source_entity_id=p.get("source_entity_id") or "",
                target_entity_id=p.get("target_entity_id") or "",
                rel_type=p.get("rel_type"),
                source_cardinality=p.get("source_cardinality"),
                target_cardinality=p.get("target_cardinality"),
                source_attrs=list(p.get("source_attr_ids") or []),
                target_attrs=list(p.get("target_attr_ids") or []),
                description=p.get("description"),
                origin="PENDING",
            ))

    return DiagramView(
        system_id=system_id,
        system_name=system_name,
        entities=entities_list,
        relationships=relationships,
        layout={k: NodePosition(**v) for k, v in layout.items()} if layout else {},
        layout_name=layout_name,
    )



def _quote_id(value: str) -> str:
    """Quote a trusted ID (from a prior DB query) for inlining in an IN list.

    Use ONLY with values that originated server-side, never with raw user input.
    """
    return "'" + (value or "").replace("'", "''") + "'"


def _load_layout_dict(sql, system_id: str, layout_name: str) -> dict[str, dict[str, Any]] | None:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT layout_json FROM {s.fq_table('der_layouts')}
        WHERE system_id = :system_id AND layout_name = :layout_name
        ORDER BY updated_at DESC LIMIT 1
        """,
        [
            delta.param("system_id", system_id),
            delta.param("layout_name", layout_name),
        ],
    )
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


@router.get("/{system_id}", response_model=DiagramView, operation_id="getDiagram")
def get_diagram(
    system_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    layout_name: str = "default",
) -> DiagramView:
    """Retorna o DER do sistema com overlay editorial.

    Se o user atual tiver um ticket OPEN de sessão para `system_id`, suas
    mudanças pendentes (add/change/remove de entities + attributes) são
    aplicadas em cima do catálogo committed e cada item recebe
    `pending_op`/`pending_ticket_id`. O Delta NÃO é tocado.
    """
    actor = _current_email(user_ws)
    session_ticket_id: str | None = None
    session_diff: dict[str, Any] | None = None
    if actor:
        found = find_open_session_ticket(sql, actor, system_id)
        if found:
            session_ticket_id, session_diff = found
    return _build_diagram(
        sql,
        system_id,
        layout_name,
        session_ticket_id=session_ticket_id,
        session_diff=session_diff,
    )


@router.post(
    "/{system_id}/layout",
    response_model=LayoutOut,
    operation_id="saveLayout",
)
def save_layout(
    system_id: str,
    payload: LayoutSaveIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> LayoutOut:
    s = get_settings()
    actor = _current_email(user_ws)
    layout_json = json.dumps(
        {k: {"x": v.x, "y": v.y} for k, v in payload.positions.items()},
        ensure_ascii=False,
    )
    # Upsert by (system_id, layout_name): delete then insert (simple).
    delta.run_params(
        sql,
        f"""
        DELETE FROM {s.fq_table('der_layouts')}
        WHERE system_id = :system_id AND layout_name = :layout_name
        """,
        [
            delta.param("system_id", system_id),
            delta.param("layout_name", payload.layout_name),
        ],
    )
    lid = delta.new_id("layout-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("der_layouts"),
        {
            "layout_id": lid,
            "system_id": system_id,
            "layout_name": payload.layout_name,
            "layout_json": layout_json,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return LayoutOut(
        layout_id=lid,
        system_id=system_id,
        layout_name=payload.layout_name,
        positions=payload.positions,
        created_at=now, created_by=actor,
        updated_at=now, updated_by=actor,
    )


@router.get(
    "/{system_id}/layouts",
    response_model=list[str],
    operation_id="listLayoutNames",
)
def list_layouts(system_id: str, sql: SqlDependency) -> list[str]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"SELECT DISTINCT layout_name FROM {s.fq_table('der_layouts')} "
        f"WHERE system_id = :system_id ORDER BY layout_name",
        [delta.param("system_id", system_id)],
    )
    return [r[0] for r in rows]


@router.delete(
    "/{system_id}/layouts/{layout_name}",
    operation_id="deleteLayout",
)
def delete_layout(system_id: str, layout_name: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.run_params(
        sql,
        f"""
        DELETE FROM {s.fq_table('der_layouts')}
        WHERE system_id = :system_id AND layout_name = :layout_name
        """,
        [
            delta.param("system_id", system_id),
            delta.param("layout_name", layout_name),
        ],
    )
    return {"deleted": layout_name}


# ─── Quick add entity (atalho do canvas) ────────────────────────────────────

@router.post(
    "/{system_id}/entities",
    response_model=DiagramEntity,
    operation_id="quickAddEntity",
)
def quick_add_entity(
    system_id: str,
    payload: QuickEntityIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DiagramEntity:
    """Stage criação de entity + atributos iniciais no ticket OPEN.

    NÃO grava no catálogo — toda a entity + attributes vão como um único
    DiffEntity op=add no ticket de sessão. O frontend renderiza com overlay
    usando `_build_diagram(..., session_ticket_id=...)` quando o ticket está
    aberto.
    """
    if payload.system_id != system_id:
        raise HTTPException(400, "system_id mismatch")
    actor = _current_email(user_ws) or "unknown"
    eid = delta.new_id("ent-")
    # Pré-alocar attribute_ids; usados no payload do diff e no response virtual.
    attrs_for_diff: list[dict] = []
    attrs_out: list[DiagramAttribute] = []
    for idx, raw in enumerate(payload.initial_attributes):
        aid = delta.new_id("attr-")
        attrs_for_diff.append({
            "attribute_id": aid,
            "technical_name": raw.get("technical_name", ""),
            "logical_name": raw.get("logical_name"),
            "ordinal_position": idx + 1,
            "native_data_type": raw.get("native_data_type"),
            "is_nullable": raw.get("is_nullable", True),
            "is_primary_key": bool(raw.get("is_primary_key", False)),
            "default_value": raw.get("default_value"),
            # round 6 pt 16/21: descrição, flags e CHECK já na criação manual.
            "description_md": raw.get("description_md"),
            "check_constraint": raw.get("check_constraint"),
            "flag_keys": raw.get("flag_keys") or [],
        })
        attrs_out.append(
            DiagramAttribute(
                attribute_id=aid,
                technical_name=raw.get("technical_name", ""),
                logical_name=raw.get("logical_name"),
                native_data_type=raw.get("native_data_type"),
                is_primary_key=bool(raw.get("is_primary_key", False)),
                is_nullable=bool(raw.get("is_nullable", True)),
                ordinal_position=idx + 1,
                has_lgpd_flag=False,
                pending_op="add",
            )
        )

    ticket_id, diff = get_or_create_session_ticket(sql, actor, system_id)
    entry = {
        "op": "add",
        "schema_name": payload.schema_name,
        "technical_name": payload.technical_name,
        "entity_type": payload.entity_type,
        "payload": {
            "logical_name": payload.logical_name,
            "domain": payload.domain,
            "entity_type": payload.entity_type,
            "tags": [],
            "pre_allocated_entity_id": eid,
            # round 6 pt 16: descrição + flags da tabela já na criação.
            "description_md": payload.description_md,
            "flag_keys": payload.flag_keys,
        },
        "attributes": attrs_for_diff,
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return DiagramEntity(
        entity_id=eid,
        system_id=system_id,
        schema_name=payload.schema_name,
        technical_name=payload.technical_name,
        logical_name=payload.logical_name,
        entity_type=payload.entity_type,  # type: ignore[arg-type]
        domain=payload.domain,
        attributes=attrs_out,
        has_lgpd_flag=False,
        pending_op="add",
        pending_ticket_id=ticket_id,
    )


# ─── Source validation (check entity existence in source DB) ────────────────

def _detect_source_kind(system_technology: str | None) -> str:
    if not system_technology:
        return "UNKNOWN"
    t = system_technology.lower()
    if "delta" in t or "unity" in t or "uc" in t:
        return "UC_DELTA"
    if "postgres" in t or "lakebase" in t:
        return "LAKEBASE"
    return "UNKNOWN"


def _validate_against_uc(
    sql, entities: list[dict], target_catalog: str
) -> list[SourceCheckResult]:
    """For each entity, check existence in {target_catalog}.<schema>.<technical_name>."""
    # target_catalog is a SQL identifier — cannot bind via parameter. Validate
    # against a strict identifier regex so it cannot smuggle SQL.
    _require_ident(target_catalog, "target_catalog")
    results: list[SourceCheckResult] = []
    schemas = sorted({e["schema_name"] for e in entities if e["schema_name"]})

    # Fetch all tables in those schemas in one query
    tables_in_source: dict[tuple[str, str], int] = {}  # (schema, table) -> column count
    columns_in_source: dict[tuple[str, str], list[str]] = {}
    if schemas:
        # schemas come from a prior DB query — safe to inline. We still
        # _quote_id them to handle any stray apostrophes defensively.
        schemas_csv = ", ".join(_quote_id(s) for s in schemas)
        rows = delta.fetch_all(
            sql,
            f"""
            SELECT table_schema, table_name,
                   (SELECT COUNT(*) FROM {target_catalog}.information_schema.columns c
                    WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS col_count
            FROM {target_catalog}.information_schema.tables t
            WHERE t.table_schema IN ({schemas_csv})
            """,
        )
        for r in rows:
            tables_in_source[(r[0], r[1])] = int(r[2]) if r[2] is not None else 0

        # Fetch column names for matched tables
        col_rows = delta.fetch_all(
            sql,
            f"""
            SELECT table_schema, table_name, column_name
            FROM {target_catalog}.information_schema.columns
            WHERE table_schema IN ({schemas_csv})
            """,
        )
        for r in col_rows:
            columns_in_source.setdefault((r[0], r[1]), []).append(r[2])

    for ent in entities:
        key = (ent["schema_name"], ent["technical_name"])
        in_source = key in tables_in_source
        src_cols = set(columns_in_source.get(key, []))
        cat_cols = set(ent.get("columns", []))
        results.append(SourceCheckResult(
            entity_id=ent["entity_id"],
            schema_name=ent["schema_name"],
            technical_name=ent["technical_name"],
            exists_in_source=in_source,
            source_kind="UC_DELTA",
            source_catalog=target_catalog,
            columns_in_source=tables_in_source.get(key),
            columns_in_catalog=len(cat_cols),
            missing_in_source=sorted(cat_cols - src_cols)[:20] if in_source else sorted(cat_cols)[:20],
            extra_in_source=sorted(src_cols - cat_cols)[:20] if in_source else [],
        ))
    return results


def _validate_against_lakebase(
    ws, sandbox_instance: str, sandbox_database: str, user_email: str | None, entities: list[dict]
) -> list[SourceCheckResult]:
    """Connect to Lakebase via psycopg and check each entity."""
    from ..lakebase.service import open_connection
    results: list[SourceCheckResult] = []
    schemas = sorted({e["schema_name"] for e in entities if e["schema_name"]})
    if not schemas:
        return []
    try:
        with open_connection(
            ws, instance_name=sandbox_instance, database=sandbox_database, user_email=user_email
        ) as conn:
            with conn.cursor() as cur:
                # psycopg supports binding tuples for IN — much cleaner.
                cur.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_schema = ANY(%s)",
                    (schemas,),
                )
                tables_in = {(r[0], r[1]) for r in cur.fetchall()}
                cur.execute(
                    "SELECT table_schema, table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = ANY(%s)",
                    (schemas,),
                )
                cols_in: dict[tuple[str, str], list[str]] = {}
                for r in cur.fetchall():
                    cols_in.setdefault((r[0], r[1]), []).append(r[2])
        for ent in entities:
            key = (ent["schema_name"], ent["technical_name"])
            in_source = key in tables_in
            src_cols = set(cols_in.get(key, []))
            cat_cols = set(ent.get("columns", []))
            results.append(SourceCheckResult(
                entity_id=ent["entity_id"],
                schema_name=ent["schema_name"],
                technical_name=ent["technical_name"],
                exists_in_source=in_source,
                source_kind="LAKEBASE",
                source_catalog=sandbox_instance,
                columns_in_source=len(src_cols) if in_source else None,
                columns_in_catalog=len(cat_cols),
                missing_in_source=sorted(cat_cols - src_cols)[:20] if in_source else sorted(cat_cols)[:20],
                extra_in_source=sorted(src_cols - cat_cols)[:20] if in_source else [],
            ))
    except Exception as exc:
        # Single error result covering all entities
        for ent in entities:
            results.append(SourceCheckResult(
                entity_id=ent["entity_id"],
                schema_name=ent["schema_name"],
                technical_name=ent["technical_name"],
                exists_in_source=False,
                source_kind="LAKEBASE",
                source_catalog=sandbox_instance,
                error=str(exc)[:300],
            ))
    return results


@router.post(
    "/{system_id}/validate-source",
    response_model=SourceValidationOut,
    operation_id="validateSource",
)
def validate_source(
    system_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
    target_catalog: str | None = None,
    sandbox_id: str | None = None,
) -> SourceValidationOut:
    """Verifica para cada entidade do sistema se ela existe na base fonte.

    - Para `Delta UC`: passe `target_catalog` (default = catálogo configurado no app).
    - Para `Lakebase`: passe `sandbox_id` (a app conecta no sandbox e checa).
    """
    s = get_settings()
    # Load system + entities + their columns
    sys_row = delta.fetch_one_params(
        sql,
        f"SELECT system_name, technology FROM {s.fq_table('systems')} "
        f"WHERE system_id = :system_id",
        [delta.param("system_id", system_id)],
    )
    if not sys_row:
        raise HTTPException(404, f"system '{system_id}' not found")
    system_name, technology = sys_row[0], sys_row[1]
    source_kind = _detect_source_kind(technology)

    ent_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name
        FROM {s.fq_table('entities')}
        WHERE system_id = :system_id
        ORDER BY schema_name, technical_name
        """,
        [delta.param("system_id", system_id)],
    )
    if not ent_rows:
        return SourceValidationOut(
            system_id=system_id, system_name=system_name,
            source_kind=source_kind, target_catalog=target_catalog,
            results=[], total_entities=0, found_count=0, missing_count=0,
        )
    # ent_rows[i][0] are entity_ids from the trusted DB — safe to inline.
    ids_csv = ", ".join(_quote_id(r[0]) for r in ent_rows)
    attr_rows = delta.fetch_all(
        sql,
        f"""
        SELECT entity_id, technical_name
        FROM {s.fq_table('attributes')}
        WHERE entity_id IN ({ids_csv})
        """,
    )
    cols_by_ent: dict[str, list[str]] = {}
    for r in attr_rows:
        cols_by_ent.setdefault(r[0], []).append(r[1])

    entities = [
        {"entity_id": r[0], "schema_name": r[1], "technical_name": r[2],
         "columns": cols_by_ent.get(r[0], [])}
        for r in ent_rows
    ]

    # Dispatch to source-specific validator
    if source_kind == "UC_DELTA":
        catalog = target_catalog or s.catalog
        results = _validate_against_uc(sql, entities, catalog)
    elif source_kind == "LAKEBASE":
        if not sandbox_id:
            raise HTTPException(400, "sandbox_id é obrigatório para validar contra Lakebase")
        sb_row = delta.fetch_one_params(
            sql,
            f"SELECT instance_name, database_name FROM {s.fq_table('lakebase_sandboxes')} "
            f"WHERE sandbox_id = :sandbox_id",
            [delta.param("sandbox_id", sandbox_id)],
        )
        if not sb_row:
            raise HTTPException(404, f"sandbox '{sandbox_id}' not found")
        # Lakebase precisa do scope `postgres` no token OAuth, que só é concedido
        # ao SP do app via resource declarado no app.yml. OBO do usuário não
        # herda esse scope. Usamos o SP do app (`app_ws`) — o lakebase.service
        # detecta automaticamente o pg_user a partir do client_id do SP.
        results = _validate_against_lakebase(
            app_ws, sb_row[0], sb_row[1] or "databricks_postgres", None, entities,
        )
    else:
        # No automated check for Oracle/SQL Server etc.
        results = [
            SourceCheckResult(
                entity_id=e["entity_id"], schema_name=e["schema_name"],
                technical_name=e["technical_name"], exists_in_source=False,
                source_kind="UNKNOWN",
                error=f"Validação automática não disponível para tecnologia '{technology}'. "
                      "Suportado: Delta UC, Lakebase Postgres.",
            )
            for e in entities
        ]

    found = sum(1 for r in results if r.exists_in_source)
    return SourceValidationOut(
        system_id=system_id, system_name=system_name,
        source_kind=source_kind, target_catalog=target_catalog,
        results=results, total_entities=len(results),
        found_count=found, missing_count=len(results) - found,
    )
