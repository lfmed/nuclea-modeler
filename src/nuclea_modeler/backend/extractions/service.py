"""Extraction service — reverse engineering for Lakebase + DDL files.

Workflow:
  1. Extract a snapshot of objects from the source (Lakebase / DDL text)
  2. Compare against existing entities/attributes in the catalog
  3. Build a structured diff
  4. Persist the extraction row + (optionally) open a reconciliation ticket
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from databricks.sdk import WorkspaceClient

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from ..lakebase.service import open_connection
from ..tickets.models import DiffEntity, TicketDiff
from ..tickets.service import open_ticket
from .embarcadero import parse_erx
from .models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractionResult,
    ExtractionSnapshot,
)


def _q(s: str) -> str:
    return (s or "").replace("'", "''")


def extract_from_lakebase(
    ws: WorkspaceClient,
    *,
    sandbox_instance: str,
    sandbox_database: str,
    user_email: str | None,
    schemas: list[str],
    object_kinds: list[str],
    system_id: str,
) -> ExtractionSnapshot:
    """Pull a snapshot of tables/views + columns + PKs from a Postgres instance.

    Uses information_schema and a query against pg_index for PKs.
    """
    if not schemas:
        # Default: discover all user schemas
        with open_connection(ws, instance_name=sandbox_instance, database=sandbox_database, user_email=user_email) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast','pg_internal') "
                    "AND schema_name NOT LIKE 'pg_%'"
                )
                schemas = [r[0] for r in cur.fetchall()]

    # Build sql-safe IN-list for schemas
    schemas_sql = ", ".join(f"'{_q(s)}'" for s in schemas) if schemas else "''"
    kinds_set = set(k.upper() for k in object_kinds)
    table_type_filter = []
    if "TABLE" in kinds_set:
        table_type_filter.append("'BASE TABLE'")
    if "VIEW" in kinds_set:
        table_type_filter.append("'VIEW'")
    if not table_type_filter:
        table_type_filter = ["'BASE TABLE'", "'VIEW'"]
    table_types_sql = ", ".join(table_type_filter)

    entities: list[ExtractedEntity] = []

    with open_connection(ws, instance_name=sandbox_instance, database=sandbox_database, user_email=user_email) as conn:
        with conn.cursor() as cur:
            # 1) Tables/views in scope
            cur.execute(
                f"""
                SELECT t.table_schema, t.table_name, t.table_type,
                       obj_description(c.oid, 'pg_class') AS table_comment
                FROM information_schema.tables t
                LEFT JOIN pg_class c
                  ON c.relname = t.table_name
                 AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.table_schema)
                WHERE t.table_schema IN ({schemas_sql})
                  AND t.table_type IN ({table_types_sql})
                ORDER BY t.table_schema, t.table_name
                """
            )
            tables = cur.fetchall()

            # 2) Columns for those tables
            cur.execute(
                f"""
                SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
                       c.udt_name,
                       COALESCE(c.character_maximum_length::text, c.numeric_precision::text || ',' || c.numeric_scale::text, '') AS extra,
                       c.is_nullable, c.column_default,
                       pgd.description AS col_comment,
                       c.data_type
                FROM information_schema.columns c
                LEFT JOIN pg_catalog.pg_statio_all_tables st
                  ON st.schemaname = c.table_schema AND st.relname = c.table_name
                LEFT JOIN pg_catalog.pg_description pgd
                  ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
                WHERE c.table_schema IN ({schemas_sql})
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """
            )
            columns = cur.fetchall()

            # 3) Primary keys
            cur.execute(
                f"""
                SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(con.conkey)
                WHERE con.contype = 'p'
                  AND n.nspname IN ({schemas_sql})
                """
            )
            pks = {(r[0], r[1], r[2]) for r in cur.fetchall()}

            # 4) Row counts (approximation, fast)
            cur.execute(
                f"""
                SELECT n.nspname, c.relname, c.reltuples::bigint
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ({schemas_sql})
                  AND c.relkind IN ('r','v','m')
                """
            )
            row_counts = {(r[0], r[1]): int(r[2]) if r[2] is not None else None for r in cur.fetchall()}

    # Group columns by (schema, table)
    cols_by_table: dict[tuple[str, str], list[ExtractedAttribute]] = {}
    for c in columns:
        schema, table, name, ordinal, udt, extra, nullable, default, comment, data_type = c
        # Build a friendly native_data_type string
        if extra and extra not in ("", "None", ",", "None,None"):
            native = f"{udt}({extra})" if "," in extra else f"{udt}({extra})"
            # Clean up patterns like "10,0" → "(10,0)"; "50" → "(50)"
            native = native.replace("(,)", "").replace("(None)", "").replace("(None,None)", "")
        else:
            native = udt or data_type or ""
        attr = ExtractedAttribute(
            technical_name=name,
            ordinal_position=int(ordinal) if ordinal is not None else None,
            native_data_type=native,
            is_nullable=(nullable == "YES" or nullable is True) if nullable is not None else None,
            default_value=default,
            is_primary_key=(schema, table, name) in pks,
            native_comment=comment,
        )
        cols_by_table.setdefault((schema, table), []).append(attr)

    for tbl in tables:
        schema, name, ttype, comment = tbl
        entity_type = "VIEW" if ttype == "VIEW" else "TABLE"
        entities.append(
            ExtractedEntity(
                schema_name=schema,
                technical_name=name,
                entity_type=entity_type,
                native_comment=comment,
                row_count_approx=row_counts.get((schema, name)),
                attributes=cols_by_table.get((schema, name), []),
            )
        )

    return ExtractionSnapshot(
        source_kind="LAKEBASE",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=schemas,
        entities=entities,
    )


def compute_diff_against_catalog(
    sql: Sql, system_id: str, snapshot: ExtractionSnapshot
) -> tuple[TicketDiff, dict[str, int]]:
    """Compare the extracted snapshot against current catalog state.

    Returns (diff, summary) where summary has keys: found, new, changed, removed.
    """
    s = get_settings()
    # Fetch current catalog entities for this system
    entity_rows = delta.fetch_all(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, entity_type, native_comment, row_count_approx, logical_name, description_md
        FROM {s.fq_table('entities')}
        WHERE system_id = '{_q(system_id)}'
        """,
    )
    # Index by (schema, technical_name) for fast lookup
    catalog_index: dict[tuple[str, str], dict[str, Any]] = {}
    catalog_entity_ids_by_key: dict[tuple[str, str], str] = {}
    for r in entity_rows:
        eid, schema, tech, etype, comment, rowct, logical, desc = r
        key = (schema, tech)
        catalog_entity_ids_by_key[key] = eid
        catalog_index[key] = {
            "entity_type": etype, "native_comment": comment, "row_count_approx": rowct,
            "logical_name": logical, "description_md": desc,
        }

    # Fetch attributes only for catalog entities (we'll compare per-entity that exists in both)
    attr_rows: list[list[Any]] = []
    if catalog_entity_ids_by_key:
        ids_csv = ", ".join(f"'{eid}'" for eid in catalog_entity_ids_by_key.values())
        attr_rows = delta.fetch_all(
            sql,
            f"""
            SELECT entity_id, technical_name, native_data_type, is_nullable, default_value,
                   is_primary_key, native_comment, ordinal_position
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

    # Build diff
    diff_entries: list[DiffEntity] = []
    additions = 0
    removals = 0
    changes = 0

    snap_keys = {(e.schema_name, e.technical_name) for e in snapshot.entities}

    for entity in snapshot.entities:
        key = (entity.schema_name, entity.technical_name)
        if key not in catalog_index:
            additions += 1
            diff_entries.append(
                DiffEntity(
                    op="add",
                    schema_name=entity.schema_name,
                    technical_name=entity.technical_name,
                    entity_type=entity.entity_type,
                    payload={
                        "native_comment": entity.native_comment,
                        "row_count_approx": entity.row_count_approx,
                    },
                    attributes=[a.model_dump() for a in entity.attributes],
                )
            )
        else:
            # Compare fields
            cat = catalog_index[key]
            field_changes: list[dict[str, Any]] = []
            for field in ("native_comment", "row_count_approx", "entity_type"):
                ext_val = getattr(entity, field) if field != "entity_type" else entity.entity_type
                cat_val = cat.get(field)
                if ext_val != cat_val:
                    field_changes.append({
                        "field": field,
                        "before": cat_val,
                        "after": ext_val,
                    })
            # Compare attributes (added / removed / changed type)
            eid = catalog_entity_ids_by_key[key]
            cat_attrs = {a["technical_name"]: a for a in attrs_by_entity.get(eid, [])}
            ext_attrs = {a.technical_name: a for a in entity.attributes}
            for name, ext_a in ext_attrs.items():
                if name not in cat_attrs:
                    field_changes.append({
                        "field": f"attribute_add:{name}",
                        "before": None,
                        "after": f"{ext_a.native_data_type or ''} {'PK' if ext_a.is_primary_key else ''}".strip(),
                    })
                else:
                    cat_a = cat_attrs[name]
                    if (cat_a.get("native_data_type") or "").lower() != (ext_a.native_data_type or "").lower():
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
    diff = TicketDiff(entities=diff_entries, additions=additions, removals=removals, changes=changes)
    return diff, summary


def persist_extraction(
    sql: Sql,
    *,
    source_kind: str,
    system_id: str,
    actor: str,
    requested_schemas: list[str],
    requested_kinds: list[str],
    lakebase_sandbox_id: str | None,
    connection_id: str | None,
    status: str,
    started_at: datetime,
    ended_at: datetime,
    objects_found: int,
    objects_new: int,
    objects_changed: int,
    objects_removed: int,
    snapshot: ExtractionSnapshot | None,
    diff_summary: dict | None,
    error_summary: str | None,
    ticket_id: str | None,
) -> str:
    """Insert an extraction row. Returns extraction_id."""
    s = get_settings()
    eid = delta.new_id("extr-")
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    delta.insert(
        sql,
        s.fq_table("extractions"),
        {
            "extraction_id": eid,
            "source_kind": source_kind,
            "connection_id": connection_id,
            "lakebase_sandbox_id": lakebase_sandbox_id,
            "system_id": system_id,
            "requested_schemas": ",".join(requested_schemas) if requested_schemas else None,
            "requested_kinds": ",".join(requested_kinds) if requested_kinds else None,
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "objects_found": objects_found,
            "objects_new": objects_new,
            "objects_changed": objects_changed,
            "objects_removed": objects_removed,
            "error_summary": error_summary,
            "snapshot_json": json.dumps(snapshot.model_dump(), default=str, ensure_ascii=False) if snapshot else None,
            "diff_summary_json": json.dumps(diff_summary, ensure_ascii=False) if diff_summary else None,
            "ticket_id": ticket_id,
            "created_by": actor,
        },
    )
    return eid


def run_lakebase_extraction(
    sql: Sql,
    ws: WorkspaceClient,
    *,
    sandbox_id: str,
    system_id: str,
    schemas: list[str],
    object_kinds: list[str],
    actor: str,
    open_ticket_on_diff: bool,
) -> ExtractionResult:
    """Full pipeline: extract from Lakebase + diff against catalog + (optional) open ticket."""
    s = get_settings()
    started = datetime.utcnow()
    start_clock = time.monotonic()
    # Resolve sandbox details
    sb_row = delta.fetch_one(
        sql,
        f"SELECT instance_name, database_name FROM {s.fq_table('lakebase_sandboxes')} "
        f"WHERE sandbox_id = '{_q(sandbox_id)}'",
    )
    if not sb_row:
        raise ValueError(f"sandbox '{sandbox_id}' not found")
    instance_name, database_name = sb_row

    try:
        snapshot = extract_from_lakebase(
            ws,
            sandbox_instance=instance_name,
            sandbox_database=database_name or "databricks_postgres",
            user_email=actor or None,
            schemas=schemas,
            object_kinds=object_kinds,
            system_id=system_id,
        )
        snapshot.sandbox_id = sandbox_id
        diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)

        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        has_changes = summary["new"] + summary["changed"] + summary["removed"] > 0

        ticket_id: str | None = None
        if has_changes and open_ticket_on_diff:
            ticket_id = open_ticket(
                sql,
                title=(
                    f"Reconciliação Lakebase — {summary['new']} novos, "
                    f"{summary['changed']} alterados, {summary['removed']} removidos"
                ),
                system_id=system_id,
                source_type="LAKEBASE_ROUNDTRIP",
                diff=diff,
                extraction_id=None,
                summary_md=(
                    f"Sandbox: `{instance_name}` (db `{database_name}`).\n"
                    f"Schemas: {', '.join(snapshot.schemas) or 'todos'}\n\n"
                    f"- **{summary['new']}** entidades novas\n"
                    f"- **{summary['changed']}** entidades alteradas\n"
                    f"- **{summary['removed']}** entidades removidas\n"
                ),
                created_by=actor,
            )

        ext_id = persist_extraction(
            sql,
            source_kind="LAKEBASE",
            system_id=system_id,
            actor=actor,
            requested_schemas=schemas,
            requested_kinds=object_kinds,
            lakebase_sandbox_id=sandbox_id,
            connection_id=None,
            status="SUCCESS",
            started_at=started,
            ended_at=ended,
            objects_found=summary["found"],
            objects_new=summary["new"],
            objects_changed=summary["changed"],
            objects_removed=summary["removed"],
            snapshot=snapshot,
            diff_summary=summary,
            error_summary=None,
            ticket_id=ticket_id,
        )
        return ExtractionResult(
            extraction_id=ext_id,
            status="SUCCESS",
            objects_found=summary["found"],
            objects_new=summary["new"],
            objects_changed=summary["changed"],
            objects_removed=summary["removed"],
            duration_ms=duration_ms,
            ticket_id=ticket_id,
            summary_md=(
                f"Extraídos {summary['found']} objetos. "
                f"+{summary['new']} novos, ~{summary['changed']} alterados, -{summary['removed']} removidos."
            ),
        )
    except Exception as exc:
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        persist_extraction(
            sql,
            source_kind="LAKEBASE",
            system_id=system_id,
            actor=actor,
            requested_schemas=schemas,
            requested_kinds=object_kinds,
            lakebase_sandbox_id=sandbox_id,
            connection_id=None,
            status="FAILED",
            started_at=started,
            ended_at=ended,
            objects_found=0, objects_new=0, objects_changed=0, objects_removed=0,
            snapshot=None,
            diff_summary=None,
            error_summary=str(exc)[:500],
            ticket_id=None,
        )
        return ExtractionResult(
            extraction_id="",
            status="FAILED",
            objects_found=0, objects_new=0, objects_changed=0, objects_removed=0,
            duration_ms=duration_ms,
            ticket_id=None,
            summary_md=f"Falha na extração: {exc}",
            errors=[str(exc)[:500]],
        )


def run_ddl_import(
    sql: Sql,
    *,
    system_id: str,
    dialect: str,
    ddl_text: str,
    actor: str,
    open_ticket_on_diff: bool,
) -> ExtractionResult:
    """Parse DDL with sqlglot, build a snapshot, diff against catalog, open ticket."""
    import sqlglot
    from sqlglot import expressions as exp

    started = datetime.utcnow()
    start_clock = time.monotonic()
    dialect_l = dialect.lower() if dialect else None
    # sqlglot uses lowercase dialect names: 'tsql' (T-SQL), 'oracle', 'postgres', 'mysql', 'spark'
    dialect_map = {
        "ANSI": None, "TSQL": "tsql", "PLSQL": "oracle",
        "POSTGRES": "postgres", "MYSQL": "mysql", "SPARKSQL": "spark",
    }
    sg_dialect = dialect_map.get(dialect.upper(), dialect_l)

    try:
        parsed = sqlglot.parse(ddl_text, dialect=sg_dialect)
    except Exception as exc:
        return ExtractionResult(
            extraction_id="",
            status="FAILED",
            objects_found=0, objects_new=0, objects_changed=0, objects_removed=0,
            duration_ms=int((time.monotonic() - start_clock) * 1000),
            ticket_id=None,
            summary_md=f"Parse error: {exc}",
            errors=[str(exc)[:500]],
        )

    entities: list[ExtractedEntity] = []
    errors: list[str] = []
    for stmt in parsed:
        if stmt is None:
            continue
        try:
            if isinstance(stmt, exp.Create) and stmt.kind and stmt.kind.upper() in ("TABLE", "VIEW"):
                tbl = stmt.this
                tbl_name = tbl.this.name if hasattr(tbl, "this") and hasattr(tbl.this, "name") else (tbl.name if hasattr(tbl, "name") else "")
                schema_name = (tbl.this.args.get("db").name if hasattr(tbl, "this") and tbl.this.args.get("db") else None) or "public"

                attributes: list[ExtractedAttribute] = []
                pk_cols: set[str] = set()
                # Look for inline PK constraints
                if hasattr(stmt, "expressions"):
                    for col_expr in stmt.expressions or []:
                        if isinstance(col_expr, exp.ColumnDef):
                            name = col_expr.this.name if col_expr.this else ""
                            dtype = col_expr.args.get("kind")
                            native = dtype.sql() if dtype else ""
                            is_nullable = True
                            for cons in (col_expr.args.get("constraints") or []):
                                if isinstance(cons.args.get("kind"), exp.PrimaryKeyColumnConstraint):
                                    pk_cols.add(name)
                                if isinstance(cons.args.get("kind"), exp.NotNullColumnConstraint):
                                    is_nullable = False
                            attributes.append(
                                ExtractedAttribute(
                                    technical_name=name,
                                    ordinal_position=len(attributes) + 1,
                                    native_data_type=native,
                                    is_nullable=is_nullable,
                                    is_primary_key=False,  # set below from pk_cols
                                )
                            )
                # Mark PKs
                for attr in attributes:
                    if attr.technical_name in pk_cols:
                        attr.is_primary_key = True
                entities.append(
                    ExtractedEntity(
                        schema_name=schema_name,
                        technical_name=tbl_name,
                        entity_type="VIEW" if stmt.kind.upper() == "VIEW" else "TABLE",
                        native_comment=None,
                        attributes=attributes,
                    )
                )
        except Exception as exc:
            errors.append(f"parse stmt skipped: {exc}")

    snapshot = ExtractionSnapshot(
        source_kind="DDL_FILE",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=sorted({e.schema_name for e in entities}),
        entities=entities,
    )
    diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)
    ended = datetime.utcnow()
    duration_ms = int((time.monotonic() - start_clock) * 1000)
    has_changes = summary["new"] + summary["changed"] + summary["removed"] > 0
    ticket_id: str | None = None
    if has_changes and open_ticket_on_diff:
        ticket_id = open_ticket(
            sql,
            title=(
                f"Reconciliação DDL ({dialect}) — {summary['new']} novos, "
                f"{summary['changed']} alterados, {summary['removed']} removidos"
            ),
            system_id=system_id,
            source_type="DDL_IMPORT",
            diff=diff,
            summary_md=f"Dialeto: {dialect}\n{len(entities)} CREATE statements parseados.\nErros de parse: {len(errors)}",
            created_by=actor,
        )
    ext_id = persist_extraction(
        sql,
        source_kind="DDL_FILE",
        system_id=system_id,
        actor=actor,
        requested_schemas=[],
        requested_kinds=["TABLE", "VIEW"],
        lakebase_sandbox_id=None,
        connection_id=None,
        status="SUCCESS" if not errors else "PARTIAL",
        started_at=started,
        ended_at=ended,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        snapshot=snapshot,
        diff_summary=summary,
        error_summary="; ".join(errors)[:500] if errors else None,
        ticket_id=ticket_id,
    )
    return ExtractionResult(
        extraction_id=ext_id,
        status="SUCCESS" if not errors else "PARTIAL",
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        duration_ms=duration_ms,
        ticket_id=ticket_id,
        summary_md=(
            f"Parseado {summary['found']} objetos. "
            f"+{summary['new']} novos, ~{summary['changed']} alterados, -{summary['removed']} removidos."
        ),
        errors=errors,
    )


def run_embarcadero_import(
    sql: Sql,
    *,
    system_id: str,
    xml_text: str,
    actor: str,
    open_ticket_on_diff: bool,
) -> ExtractionResult:
    """Parse an Embarcadero ER/Studio .erx XML, diff against catalog, open ticket if needed."""
    started = datetime.utcnow()
    start_clock = time.monotonic()

    try:
        snapshot, parse_warnings = parse_erx(xml_text, system_id)
    except Exception as exc:
        return ExtractionResult(
            extraction_id="",
            status="FAILED",
            objects_found=0,
            objects_new=0,
            objects_changed=0,
            objects_removed=0,
            duration_ms=int((time.monotonic() - start_clock) * 1000),
            ticket_id=None,
            summary_md=f"Falha ao processar arquivo .erx: {exc}",
            errors=[str(exc)[:500]],
        )

    if not snapshot.entities:
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        error_msg = (
            "Não foi possível identificar entidades no arquivo. "
            "Formato suportado: Embarcadero ER/Studio .erx XML."
        )
        persist_extraction(
            sql,
            source_kind="EMBARCADERO",
            system_id=system_id,
            actor=actor,
            requested_schemas=[],
            requested_kinds=["TABLE"],
            lakebase_sandbox_id=None,
            connection_id=None,
            status="FAILED",
            started_at=started,
            ended_at=ended,
            objects_found=0,
            objects_new=0,
            objects_changed=0,
            objects_removed=0,
            snapshot=None,
            diff_summary=None,
            error_summary=error_msg,
            ticket_id=None,
        )
        return ExtractionResult(
            extraction_id="",
            status="FAILED",
            objects_found=0,
            objects_new=0,
            objects_changed=0,
            objects_removed=0,
            duration_ms=duration_ms,
            ticket_id=None,
            summary_md=error_msg,
            errors=[error_msg] + parse_warnings,
        )

    diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)
    ended = datetime.utcnow()
    duration_ms = int((time.monotonic() - start_clock) * 1000)
    has_changes = summary["new"] + summary["changed"] + summary["removed"] > 0

    ticket_id: str | None = None
    if has_changes and open_ticket_on_diff:
        warnings_block = (
            "\n\n**Avisos do parser:**\n" + "\n".join(f"- {w}" for w in parse_warnings[:20])
            if parse_warnings
            else ""
        )
        ticket_id = open_ticket(
            sql,
            title=(
                f"Reconciliação Embarcadero (.erx) — {summary['new']} novos, "
                f"{summary['changed']} alterados, {summary['removed']} removidos"
            ),
            system_id=system_id,
            source_type="REVERSE_ENG",
            diff=diff,
            extraction_id=None,
            summary_md=(
                f"Fonte: arquivo Embarcadero ER/Studio .erx\n"
                f"Schemas detectados: {', '.join(snapshot.schemas) or '(nenhum)'}\n\n"
                f"- **{summary['new']}** entidades novas\n"
                f"- **{summary['changed']}** entidades alteradas\n"
                f"- **{summary['removed']}** entidades removidas\n"
                f"{warnings_block}"
            ),
            created_by=actor,
        )

    ext_id = persist_extraction(
        sql,
        source_kind="EMBARCADERO",
        system_id=system_id,
        actor=actor,
        requested_schemas=snapshot.schemas,
        requested_kinds=["TABLE"],
        lakebase_sandbox_id=None,
        connection_id=None,
        status="SUCCESS",
        started_at=started,
        ended_at=ended,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        snapshot=snapshot,
        diff_summary=summary,
        error_summary="; ".join(parse_warnings)[:500] if parse_warnings else None,
        ticket_id=ticket_id,
    )

    return ExtractionResult(
        extraction_id=ext_id,
        status="SUCCESS",
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        duration_ms=duration_ms,
        ticket_id=ticket_id,
        summary_md=(
            f"Parseado {summary['found']} objetos do .erx. "
            f"+{summary['new']} novos, ~{summary['changed']} alterados, -{summary['removed']} removidos."
        ),
        errors=parse_warnings,
    )
