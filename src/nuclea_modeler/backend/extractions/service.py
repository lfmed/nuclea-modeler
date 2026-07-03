"""Extraction service — reverse engineering for Lakebase + DDL files.

Workflow:
  1. Extract a snapshot of objects from the source (Lakebase / DDL text)
  2. Compare against existing entities/attributes in the catalog
  3. Build a structured diff
  4. Persist the extraction row + (optionally) open a reconciliation ticket
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

from databricks.sdk import WorkspaceClient

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from ..lakebase.service import open_connection
from ..tickets.service import open_ticket
from .embarcadero import parse_dm1
from .diff import compute_diff_against_catalog as compute_diff_against_catalog
from .models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedIndex,
    ExtractedIndexColumn,
    ExtractedRelationship,
    ExtractionResult,
    ExtractionSnapshot,
)

log = logging.getLogger(__name__)


def _ddl_reference_to_rel(
    ref, child_schema: str, child_table: str, child_cols: list[str]
) -> ExtractedRelationship | None:
    """Converte um nó sqlglot exp.Reference (FK inline ou table-level) em
    ExtractedRelationship. parent = tabela referenciada (PK); child = tabela
    sendo definida (segura a FK). Defensivo: retorna None se não der pra
    resolver a tabela referenciada."""
    from sqlglot import expressions as exp

    sch = ref.this
    if isinstance(sch, exp.Schema):
        rtbl = sch.this
        parent_cols = [c.name for c in sch.expressions if hasattr(c, "name")]
    elif isinstance(sch, exp.Table):
        rtbl = sch
        parent_cols = []
    else:
        return None
    if rtbl is None or not getattr(rtbl, "name", ""):
        return None
    parent_schema = (rtbl.db if getattr(rtbl, "db", "") else None) or child_schema
    return ExtractedRelationship(
        parent_schema=parent_schema,
        parent_entity=rtbl.name,
        parent_columns=parent_cols,
        child_schema=child_schema,
        child_entity=child_table,
        child_columns=child_cols,
        rel_type="1:N",
    )


def _quote_id(value: str) -> str:
    """Quote a trusted ID (from a prior DB query) for inlining in an IN list.

    Use ONLY with values that originated server-side, never with raw user input.
    """
    return "'" + (value or "").replace("'", "''") + "'"


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

    # psycopg supports binding tuples for `ANY(%s)` and `IN %s` — much safer
    # than building the IN list as a string.
    kinds_set = set(k.upper() for k in object_kinds)
    table_types: list[str] = []
    if "TABLE" in kinds_set:
        table_types.append("BASE TABLE")
    if "VIEW" in kinds_set:
        table_types.append("VIEW")
    if not table_types:
        table_types = ["BASE TABLE", "VIEW"]

    entities: list[ExtractedEntity] = []

    with open_connection(ws, instance_name=sandbox_instance, database=sandbox_database, user_email=user_email) as conn:
        with conn.cursor() as cur:
            # 1) Tables/views in scope
            cur.execute(
                """
                SELECT t.table_schema, t.table_name, t.table_type,
                       obj_description(c.oid, 'pg_class') AS table_comment
                FROM information_schema.tables t
                LEFT JOIN pg_class c
                  ON c.relname = t.table_name
                 AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.table_schema)
                WHERE t.table_schema = ANY(%s)
                  AND t.table_type = ANY(%s)
                ORDER BY t.table_schema, t.table_name
                """,
                (schemas, table_types),
            )
            tables = cur.fetchall()

            # 2) Columns for those tables
            cur.execute(
                """
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
                WHERE c.table_schema = ANY(%s)
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """,
                (schemas,),
            )
            columns = cur.fetchall()

            # 3) Primary keys
            cur.execute(
                """
                SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(con.conkey)
                WHERE con.contype = 'p'
                  AND n.nspname = ANY(%s)
                """,
                (schemas,),
            )
            pks = {(r[0], r[1], r[2]) for r in cur.fetchall()}

            # 4) Row counts (approximation, fast)
            cur.execute(
                """
                SELECT n.nspname, c.relname, c.reltuples::bigint
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(%s)
                  AND c.relkind IN ('r','v','m')
                """,
                (schemas,),
            )
            row_counts = {(r[0], r[1]): int(r[2]) if r[2] is not None else None for r in cur.fetchall()}

            # 5) Indexes — skip PK indexes (já cobertos por is_primary_key).
            # pg_index expõe colunas em ordem via indkey + amname pelo acesso method.
            # Tipos relevantes: btree, hash, gin, brin, gist.
            cur.execute(
                """
                SELECT
                    n.nspname AS schema_name,
                    c.relname AS table_name,
                    ic.relname AS index_name,
                    am.amname AS index_type,
                    i.indisunique AS is_unique,
                    i.indpred IS NOT NULL AS has_partial,
                    pg_get_expr(i.indpred, i.indrelid) AS partial_where,
                    array_agg(a.attname ORDER BY array_position(i.indkey, a.attnum)) AS columns
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indrelid
                JOIN pg_class ic ON ic.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_am am ON am.oid = ic.relam
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
                WHERE n.nspname = ANY(%s)
                  AND NOT i.indisprimary
                GROUP BY n.nspname, c.relname, ic.relname, am.amname, i.indisunique,
                         i.indpred, i.indrelid
                ORDER BY n.nspname, c.relname, ic.relname
                """,
                (schemas,),
            )
            indexes_raw = cur.fetchall()

    # Group indexes by (schema, table)
    indexes_by_table: dict[tuple[str, str], list[ExtractedIndex]] = {}
    # PG amname → IndexType canônico
    _pg_amname_to_type = {
        "btree": "BTREE", "hash": "HASH", "gin": "GIN",
        "brin": "BRIN", "gist": "GIST",
    }
    for row in indexes_raw:
        schema, table, idx_name, am_name, is_unique, has_partial, partial_where, columns = row
        col_list = list(columns) if columns else []
        if not col_list:
            continue
        ix_type = _pg_amname_to_type.get((am_name or "btree").lower(), "BTREE")
        if is_unique:
            ix_type = "UNIQUE"
        indexes_by_table.setdefault((schema, table), []).append(
            ExtractedIndex(
                index_name=idx_name,
                index_type=ix_type,
                is_unique=bool(is_unique),
                columns=[ExtractedIndexColumn(name=c, direction="ASC") for c in col_list],
                native_comment=(f"WHERE {partial_where}" if has_partial and partial_where else None),
            )
        )

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
                indexes=indexes_by_table.get((schema, name), []),
            )
        )

    return ExtractionSnapshot(
        source_kind="LAKEBASE",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=schemas,
        entities=entities,
    )



# Marcadores de mensagens puramente informativas do parser (não são falha).
# As strings vêm do nosso próprio código (embarcadero.py), então o match por
# substring é estável e testável.
_IMPORT_INFO_MARKERS = (
    "relacionamento(s) extraíd",
    "incluído(s) no diff",
)


def summarize_import_messages(messages: list[str] | None) -> dict[str, list[str]]:
    """Separa mensagens do parser em 'problems' (perda de dados / erro) e
    'infos' (avisos informativos). Função pura — usada para montar o log de
    falha de import e decidir o status PARTIAL."""
    problems: list[str] = []
    infos: list[str] = []
    for m in messages or []:
        if any(mark in m for mark in _IMPORT_INFO_MARKERS):
            infos.append(m)
        else:
            problems.append(m)
    return {"problems": problems, "infos": infos}


def format_import_log(problems: list[str], infos: list[str]) -> str:
    """Monta um bloco markdown legível do log de import (problemas + avisos)."""
    parts: list[str] = []
    if problems:
        parts.append(
            f"❌ **Problemas ({len(problems)})**:\n"
            + "\n".join(f"- {p}" for p in problems)
        )
    if infos:
        parts.append(
            f"ℹ️ **Avisos ({len(infos)})**:\n"
            + "\n".join(f"- {i}" for i in infos)
        )
    return "\n\n".join(parts)


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
    sb_row = delta.fetch_one_params(
        sql,
        f"SELECT instance_name, database_name FROM {s.fq_table('lakebase_sandboxes')} "
        f"WHERE sandbox_id = :sandbox_id",
        [delta.param("sandbox_id", sandbox_id)],
    )
    if not sb_row:
        raise ValueError(f"sandbox '{sandbox_id}' not found")
    instance_name, database_name = sb_row

    try:
        snapshot = extract_from_lakebase(
            ws,
            sandbox_instance=instance_name,
            sandbox_database=database_name or "databricks_postgres",
            # `actor` é só pra audit no Delta. A conexão Postgres usa o
            # client_id do SP do app (provisionado via CAN_CONNECT_AND_CREATE
            # no resource Lakebase). Passar user_email=None força esse caminho
            # em open_connection.
            user_email=None,
            schemas=schemas,
            object_kinds=object_kinds,
            system_id=system_id,
        )
        snapshot.sandbox_id = sandbox_id
        diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)

        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        has_changes = summary["new"] + summary["changed"] + summary["removed"] + summary.get("relationships", 0) > 0

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


def _ddl_literal_str(node: Any) -> str | None:
    """Extrai o texto de um literal/comentário de um nó sqlglot.

    Defensivo: cobre exp.Literal (`.this` é a string), strings cruas e nós
    cujo `.name` guarda o valor já sem aspas. Retorna None quando não resolve —
    captura de comentário NUNCA pode derrubar um import.
    """
    if node is None:
        return None
    try:
        from sqlglot import expressions as exp

        if isinstance(node, str):
            return node.strip() or None
        if isinstance(node, exp.Literal):
            return (node.this or "").strip() or None
        name = getattr(node, "name", None)
        if name:
            return str(name).strip() or None
        inner = getattr(node, "this", None)
        if inner is not None and inner is not node:
            return _ddl_literal_str(inner)
    except Exception:  # noqa: BLE001 — comentário é best-effort
        return None
    return None


def _ddl_search_path_schema(stmt, dialect) -> str | None:
    """Extrai o schema de um `SET search_path TO <schema>` (Postgres).

    O sqlglot ora devolve exp.Set (`SET search_path = streaming`), ora exp.Command
    (`SET search_path TO a, b` — sintaxe não suportada cai em Command), então
    detectamos via regex no SQL renderizado — robusto para os dois casos. Pega o
    PRIMEIRO schema da lista. Retorna None se não for um SET de search_path.
    """
    try:
        txt = stmt.sql(dialect=dialect)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(
        r"search_path\s*(?:=|to)\s*[\"']?([A-Za-z_][A-Za-z0-9_$]*)",
        txt,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


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
    relationships: list[ExtractedRelationship] = []
    errors: list[str] = []
    # Comentários de `COMMENT ON TABLE/COLUMN ... IS '...'` costumam vir DEPOIS
    # do CREATE — guardamos e aplicamos no fim (chave = schema/tabela[/coluna]).
    deferred_table_comments: dict[tuple[str, str], str] = {}
    deferred_col_comments: dict[tuple[str, str, str], str] = {}
    # Schema default para tabelas NÃO-qualificadas. Honra `SET search_path TO x`
    # (dumps Postgres): sem isso, tudo caía em "public" mesmo quando o DDL declara
    # `CREATE SCHEMA streaming; SET search_path TO streaming;`. Rastreado em ordem.
    current_schema_default = "public"
    for stmt in parsed:
        if stmt is None:
            continue
        # SET search_path muda o schema default das próximas tabelas.
        if isinstance(stmt, (exp.Set, exp.Command)):
            sp = _ddl_search_path_schema(stmt, sg_dialect)
            if sp:
                current_schema_default = sp
            continue
        try:
            if isinstance(stmt, exp.Create) and stmt.kind and stmt.kind.upper() in ("TABLE", "VIEW"):
                # stmt.this é um exp.Schema (Table + ColumnDefs + Constraints).
                # ATENÇÃO: as colunas vivem em stmt.this.expressions — NÃO em
                # stmt.expressions (que é sempre vazio). O código antigo lia o
                # atributo errado e por isso não extraía coluna nenhuma do DDL.
                schema_obj = stmt.this
                table_obj = schema_obj.this if hasattr(schema_obj, "this") else schema_obj
                tbl_name = table_obj.name if hasattr(table_obj, "name") else ""
                schema_name = (
                    table_obj.db if getattr(table_obj, "db", "") else None
                ) or current_schema_default

                attributes: list[ExtractedAttribute] = []
                pk_cols: set[str] = set()
                col_defs = schema_obj.expressions if hasattr(schema_obj, "expressions") else []
                for col_expr in (col_defs or []):
                    if not isinstance(col_expr, exp.ColumnDef):
                        continue
                    name = col_expr.this.name if col_expr.this else ""
                    dtype = col_expr.args.get("kind")
                    native = dtype.sql() if dtype else ""
                    is_nullable = True
                    col_comment: str | None = None
                    for cons in (col_expr.args.get("constraints") or []):
                        kind = cons.args.get("kind")
                        if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                            pk_cols.add(name)
                        if isinstance(kind, exp.NotNullColumnConstraint):
                            is_nullable = False
                        # FK inline: `col INT REFERENCES outra(col)`
                        if isinstance(kind, exp.Reference):
                            rel = _ddl_reference_to_rel(kind, schema_name, tbl_name, [name])
                            if rel:
                                relationships.append(rel)
                        # Comentário inline: `col INT COMMENT 'texto'`
                        if isinstance(kind, exp.CommentColumnConstraint):
                            col_comment = _ddl_literal_str(kind.this)
                    attributes.append(
                        ExtractedAttribute(
                            technical_name=name,
                            ordinal_position=len(attributes) + 1,
                            native_data_type=native,
                            is_nullable=is_nullable,
                            is_primary_key=False,  # set below from pk_cols
                            native_comment=col_comment,
                        )
                    )
                # Mark PKs
                for attr in attributes:
                    if attr.technical_name in pk_cols:
                        attr.is_primary_key = True
                # FK table-level: `CONSTRAINT ... FOREIGN KEY (...) REFERENCES ...`
                for fk in schema_obj.find_all(exp.ForeignKey):
                    local_cols = [c.name for c in fk.expressions if hasattr(c, "name")]
                    ref = fk.args.get("reference")
                    if ref is not None:
                        rel = _ddl_reference_to_rel(ref, schema_name, tbl_name, local_cols)
                        if rel:
                            relationships.append(rel)
                # Comentário de tabela: `... COMMENT 'texto'` / `COMMENT = '...'`
                # aparece como exp.SchemaCommentProperty dentro de properties.
                # Best-effort: um erro aqui não pode derrubar a extração da tabela.
                tbl_comment: str | None = None
                try:
                    props = stmt.args.get("properties")
                    for prop in (getattr(props, "expressions", None) or []):
                        if isinstance(prop, exp.SchemaCommentProperty):
                            tbl_comment = _ddl_literal_str(prop.this)
                except Exception:  # noqa: BLE001
                    tbl_comment = None
                entities.append(
                    ExtractedEntity(
                        schema_name=schema_name,
                        technical_name=tbl_name,
                        entity_type="VIEW" if stmt.kind.upper() == "VIEW" else "TABLE",
                        native_comment=tbl_comment,
                        attributes=attributes,
                    )
                )
            elif isinstance(stmt, exp.Comment):
                # `COMMENT ON TABLE t IS '...'` / `COMMENT ON COLUMN t.c IS '...'`
                obj_kind = str(stmt.args.get("kind") or "").upper()
                target = stmt.this
                text = _ddl_literal_str(stmt.args.get("expression"))
                if text and target is not None:
                    if obj_kind == "COLUMN":
                        col = target.name if hasattr(target, "name") else ""
                        tbl = getattr(target, "table", "") or ""
                        sch = getattr(target, "db", "") or "public"
                        if col and tbl:
                            deferred_col_comments[(sch, tbl, col)] = text
                    else:  # TABLE (default)
                        tbl = target.name if hasattr(target, "name") else ""
                        sch = (getattr(target, "db", "") or None) or "public"
                        if tbl:
                            deferred_table_comments[(sch, tbl)] = text
        except Exception as exc:
            errors.append(f"parse stmt skipped: {exc}")

    # Aplica os comentários de COMMENT ON coletados (autoritativos — sobrescrevem
    # o que veio inline no CREATE, pois são declarações explícitas).
    for e in entities:
        tc = deferred_table_comments.get((e.schema_name, e.technical_name))
        if tc:
            e.native_comment = tc
        for a in e.attributes:
            cc = deferred_col_comments.get((e.schema_name, e.technical_name, a.technical_name))
            if cc:
                a.native_comment = cc

    # Falha "silenciosa": o parse não reconheceu nenhum CREATE TABLE/VIEW.
    # Marcamos FAILED com mensagem acionável em vez de devolver SUCCESS com 0
    # objetos. CRÍTICO: precisa vir ANTES do diff — um snapshot vazio faria o
    # compute_diff marcar TODAS as entidades do catálogo como removidas,
    # gerando um ticket destrutivo.
    if not entities:
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        msg = (
            "Nenhum objeto (CREATE TABLE/VIEW) reconhecido no DDL. "
            f"Confirme se o dialeto selecionado ({dialect}) corresponde ao arquivo."
        )
        if errors:
            msg += f" {len(errors)} statement(s) ignorado(s) no parse."
        empty_snapshot = ExtractionSnapshot(
            source_kind="DDL_FILE",
            system_id=system_id,
            captured_at=datetime.utcnow(),
            schemas=[],
            entities=[],
            relationships=[],
        )
        ended_at = ended
        ext_id = persist_extraction(
            sql,
            source_kind="DDL_FILE",
            system_id=system_id,
            actor=actor,
            requested_schemas=[],
            requested_kinds=["TABLE", "VIEW"],
            lakebase_sandbox_id=None,
            connection_id=None,
            status="FAILED",
            started_at=started,
            ended_at=ended_at,
            objects_found=0, objects_new=0, objects_changed=0, objects_removed=0,
            snapshot=empty_snapshot,
            diff_summary=None,
            error_summary=msg[:4000],
            ticket_id=None,
        )
        return ExtractionResult(
            extraction_id=ext_id,
            status="FAILED",
            objects_found=0, objects_new=0, objects_changed=0, objects_removed=0,
            duration_ms=duration_ms,
            ticket_id=None,
            summary_md=msg,
            errors=errors or [msg],
        )

    snapshot = ExtractionSnapshot(
        source_kind="DDL_FILE",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=sorted({e.schema_name for e in entities}),
        entities=entities,
        relationships=relationships,
    )
    diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)
    ended = datetime.utcnow()
    duration_ms = int((time.monotonic() - start_clock) * 1000)
    has_changes = summary["new"] + summary["changed"] + summary["removed"] + summary.get("relationships", 0) > 0
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
    status = "SUCCESS" if not errors else "PARTIAL"
    rel_note = (
        f" {summary.get('relationships', 0)} relacionamento(s)."
        if summary.get("relationships")
        else ""
    )
    base_summary = (
        f"Parseado {summary['found']} objetos. "
        f"+{summary['new']} novos, ~{summary['changed']} alterados, "
        f"-{summary['removed']} removidos.{rel_note}"
    )
    import_log = format_import_log(errors, [])
    summary_md = base_summary + (f"\n\n{import_log}" if import_log else "")

    ext_id = persist_extraction(
        sql,
        source_kind="DDL_FILE",
        system_id=system_id,
        actor=actor,
        requested_schemas=[],
        requested_kinds=["TABLE", "VIEW"],
        lakebase_sandbox_id=None,
        connection_id=None,
        status=status,
        started_at=started,
        ended_at=ended,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        snapshot=snapshot,
        diff_summary=summary,
        error_summary=("\n".join(errors)[:4000]) if errors else None,
        ticket_id=ticket_id,
    )
    return ExtractionResult(
        extraction_id=ext_id,
        status=status,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        duration_ms=duration_ms,
        ticket_id=ticket_id,
        summary_md=summary_md,
        errors=errors,
    )


def run_embarcadero_import(
    sql: Sql,
    *,
    system_id: str,
    dm1_text: str,
    actor: str,
    open_ticket_on_diff: bool,
) -> ExtractionResult:
    """Parse um arquivo Embarcadero ER/Studio .DM1, diff contra catálogo e abre ticket se necessário."""
    started = datetime.utcnow()
    start_clock = time.monotonic()

    try:
        snapshot, parse_warnings = parse_dm1(dm1_text, system_id)
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
            summary_md=f"Falha ao processar arquivo .DM1: {exc}",
            errors=[str(exc)[:500]],
        )

    if not snapshot.entities:
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        error_msg = (
            "Não foi possível identificar entidades no arquivo. "
            "Formato suportado: Embarcadero ER/Studio .DM1."
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
    has_changes = summary["new"] + summary["changed"] + summary["removed"] + summary.get("relationships", 0) > 0

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
                f"Reconciliação Embarcadero (.DM1) — {summary['new']} novos, "
                f"{summary['changed']} alterados, {summary['removed']} removidos"
            ),
            system_id=system_id,
            source_type="REVERSE_ENG",
            diff=diff,
            extraction_id=None,
            summary_md=(
                f"Fonte: arquivo Embarcadero ER/Studio .DM1\n"
                f"Schemas detectados: {', '.join(snapshot.schemas) or '(nenhum)'}\n\n"
                f"- **{summary['new']}** entidades novas\n"
                f"- **{summary['changed']}** entidades alteradas\n"
                f"- **{summary['removed']}** entidades removidas\n"
                f"{warnings_block}"
            ),
            created_by=actor,
        )

    # Classifica avisos do parser: 'problems' = perda de dados (entity/atributo
    # sem nome ignorado, FK órfã, tipo desconhecido); 'infos' = informativos.
    classified = summarize_import_messages(parse_warnings)
    problems = classified["problems"]
    infos = classified["infos"]
    # PARTIAL quando houve perda de dados — o usuário precisa revisar o log.
    status = "PARTIAL" if problems else "SUCCESS"
    rel_note = (
        f" {summary.get('relationships', 0)} relacionamento(s)."
        if summary.get("relationships")
        else ""
    )
    base_summary = (
        f"Parseado {summary['found']} objetos do .DM1. "
        f"+{summary['new']} novos, ~{summary['changed']} alterados, "
        f"-{summary['removed']} removidos.{rel_note}"
    )
    import_log = format_import_log(problems, infos)
    summary_md = base_summary + (f"\n\n{import_log}" if import_log else "")

    ext_id = persist_extraction(
        sql,
        source_kind="EMBARCADERO",
        system_id=system_id,
        actor=actor,
        requested_schemas=snapshot.schemas,
        requested_kinds=["TABLE"],
        lakebase_sandbox_id=None,
        connection_id=None,
        status=status,
        started_at=started,
        ended_at=ended,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        snapshot=snapshot,
        diff_summary=summary,
        # Log completo persistido (não mais truncado em 500): problemas primeiro.
        error_summary=("\n".join(problems + infos)[:4000]) if parse_warnings else None,
        ticket_id=ticket_id,
    )

    return ExtractionResult(
        extraction_id=ext_id,
        status=status,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        duration_ms=duration_ms,
        ticket_id=ticket_id,
        summary_md=summary_md,
        # 'errors' do resultado = só problemas reais (infos vão no summary_md).
        errors=problems,
    )


# ---------------------------------------------------------------------------
# Unity Catalog extraction
# ---------------------------------------------------------------------------


def _uc_table_type_to_entity_type(table_type: str | None) -> str:
    """Mapeia `TableType` UC -> nosso `entity_type` interno.

    Espelha `uc.router._map_table_type` (duplicado de propósito para evitar
    ciclo de import entre módulos de domínio).
    """
    if not table_type:
        return "TABLE"
    t = table_type.upper()
    if t == "VIEW":
        return "VIEW"
    if t == "MATERIALIZED_VIEW":
        return "MATERIALIZED_VIEW"
    if t in ("EXTERNAL", "EXTERNAL_SHALLOW_CLONE", "FOREIGN"):
        return "EXTERNAL"
    return "TABLE"


def extract_from_uc(
    ws: WorkspaceClient,
    *,
    catalog: str,
    schema: str,
    table_names: list[str] | None,
    system_id: str,
) -> tuple[ExtractionSnapshot, list[str]]:
    """Puxa snapshot de tabelas + colunas via Unity Catalog SDK.

    Estratégia:
      - Se `table_names` está vazio/None, lista todas as tabelas do schema
        com `tables.list(omit_columns=False)` (já vem com colunas em uma
        única chamada).
      - Se `table_names` veio explícito, faz `tables.get(full_name=…)` por
        tabela (paga 1 round-trip por tabela mas evita iterar tudo).

    Retorna (snapshot, warnings) — warnings contém erros não-fatais
    (tabela não encontrada, etc).
    """
    entities: list[ExtractedEntity] = []
    warnings: list[str] = []

    # 1) Coleta os TableInfos relevantes.
    if table_names:
        # Subset explícito.
        for tname in table_names:
            full_name = f"{catalog}.{schema}.{tname}"
            try:
                t = ws.tables.get(full_name=full_name)
            except Exception as exc:
                warnings.append(f"tabela {full_name} não acessível: {exc}")
                log.warning("uc.extract get failed %s: %s", full_name, exc)
                continue
            entities.append(_table_info_to_entity(t, fallback_schema=schema))
    else:
        # Todas as tabelas do schema.
        try:
            for t in ws.tables.list(
                catalog_name=catalog,
                schema_name=schema,
                omit_columns=False,
            ):
                entities.append(_table_info_to_entity(t, fallback_schema=schema))
        except Exception as exc:
            # Falha de listagem é fatal — propaga.
            raise RuntimeError(
                f"Falha ao listar tabelas de {catalog}.{schema}: {exc}"
            ) from exc

    snapshot = ExtractionSnapshot(
        source_kind="UC",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        # `schemas` em UC é só o schema único pedido (não há multi-schema
        # em uma única extração UC — quem quer multi precisa rodar N vezes).
        schemas=[schema],
        entities=entities,
    )
    return snapshot, warnings


def _table_info_to_entity(t: Any, *, fallback_schema: str) -> ExtractedEntity:
    """Converte um `TableInfo` do SDK em `ExtractedEntity` interno."""
    table_type_str = str(t.table_type.value) if t.table_type else None
    entity_type = _uc_table_type_to_entity_type(table_type_str)

    attributes: list[ExtractedAttribute] = []
    for c in t.columns or []:
        # `type_text` (ex: "decimal(10,2)", "string") é o mais próximo do
        # `native_data_type` que usamos para Lakebase. `type_name` é o enum
        # (DECIMAL, STRING…) — guardamos `type_text` como fonte primária.
        native = c.type_text
        if not native and c.type_name:
            native = str(c.type_name.value)
        attributes.append(
            ExtractedAttribute(
                technical_name=c.name or "",
                ordinal_position=(int(c.position) + 1) if c.position is not None else None,
                native_data_type=native,
                is_nullable=c.nullable,
                default_value=None,  # UC não expõe default em ColumnInfo
                # PKs em UC vêm via `table_constraints` (não retornado pela
                # API). Manter False — a sessão de reconciliação pode marcar
                # PK manualmente no modeler.
                is_primary_key=False,
                native_comment=c.comment,
            )
        )
    # Ordena por position (UC usa 0-based, já convertemos para 1-based).
    attributes.sort(key=lambda a: (a.ordinal_position is None, a.ordinal_position or 0))

    # Liquid Clustering: Delta expõe via TBLPROPERTIES `clusteringColumns`.
    # UC TableInfo.properties traz essas propriedades como dict[str, str].
    # Formato: 'clusteringColumns' = '[["col_a"],["col_b"]]' (lista de listas
    # — cada inner list é uma chave de cluster, normalmente 1 coluna por).
    indexes_extracted: list[ExtractedIndex] = []
    props: dict[str, Any] = getattr(t, "properties", None) or {}
    cluster_raw = props.get("clusteringColumns") if isinstance(props, dict) else None
    if cluster_raw:
        try:
            import json as _json
            parsed = _json.loads(cluster_raw)
            cluster_cols: list[str] = []
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, list) and item and isinstance(item[0], str):
                        cluster_cols.append(item[0])
                    elif isinstance(item, str):
                        cluster_cols.append(item)
            if cluster_cols:
                indexes_extracted.append(ExtractedIndex(
                    index_name=f"{t.name}_liquid",
                    index_type="LIQUID",
                    is_unique=False,
                    columns=[ExtractedIndexColumn(name=c, direction="ASC") for c in cluster_cols],
                    native_comment="Liquid clustering (Delta)",
                ))
        except (ValueError, TypeError):
            pass

    return ExtractedEntity(
        schema_name=t.schema_name or fallback_schema,
        technical_name=t.name or "",
        entity_type=entity_type,  # type: ignore[arg-type]
        native_comment=t.comment,
        row_count_approx=None,  # UC não expõe row count cheap
        attributes=attributes,
        indexes=indexes_extracted,
    )


def run_uc_extraction(
    sql: Sql,
    ws: WorkspaceClient,
    *,
    system_id: str,
    catalog: str,
    schema: str,
    table_names: list[str] | None,
    actor: str,
    open_ticket_on_diff: bool,
) -> ExtractionResult:
    """Pipeline completo: snapshot UC + diff vs catálogo + (opcional) ticket."""
    started = datetime.utcnow()
    start_clock = time.monotonic()

    try:
        snapshot, parse_warnings = extract_from_uc(
            ws,
            catalog=catalog,
            schema=schema,
            table_names=table_names,
            system_id=system_id,
        )
        diff, summary = compute_diff_against_catalog(sql, system_id, snapshot)
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        has_changes = summary["new"] + summary["changed"] + summary["removed"] + summary.get("relationships", 0) > 0

        ticket_id: str | None = None
        if has_changes and open_ticket_on_diff:
            tnames_block = (
                f"Tabelas pedidas: {', '.join(table_names)}\n"
                if table_names
                else "Tabelas: (todas do schema)\n"
            )
            warnings_block = (
                "\n\n**Avisos:**\n" + "\n".join(f"- {w}" for w in parse_warnings[:20])
                if parse_warnings
                else ""
            )
            ticket_id = open_ticket(
                sql,
                title=(
                    f"Reconciliação UC ({catalog}.{schema}) — "
                    f"{summary['new']} novos, {summary['changed']} alterados, "
                    f"{summary['removed']} removidos"
                ),
                system_id=system_id,
                source_type="REVERSE_ENG",
                diff=diff,
                extraction_id=None,
                summary_md=(
                    f"Fonte: Unity Catalog `{catalog}.{schema}`\n"
                    f"{tnames_block}\n"
                    f"- **{summary['new']}** entidades novas\n"
                    f"- **{summary['changed']}** entidades alteradas\n"
                    f"- **{summary['removed']}** entidades removidas\n"
                    f"{warnings_block}"
                ),
                created_by=actor,
            )

        # `requested_schemas` reaproveita o campo do Lakebase (CSV) — aqui
        # sempre 1 schema. `requested_kinds` segue ["TABLE","VIEW"] já que
        # UC retorna ambos na mesma listagem.
        ext_id = persist_extraction(
            sql,
            source_kind="UC",
            system_id=system_id,
            actor=actor,
            requested_schemas=[f"{catalog}.{schema}"],
            requested_kinds=["TABLE", "VIEW"],
            lakebase_sandbox_id=None,
            connection_id=None,
            status="SUCCESS" if not parse_warnings else "PARTIAL",
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
            status="SUCCESS" if not parse_warnings else "PARTIAL",
            objects_found=summary["found"],
            objects_new=summary["new"],
            objects_changed=summary["changed"],
            objects_removed=summary["removed"],
            duration_ms=duration_ms,
            ticket_id=ticket_id,
            summary_md=(
                f"Extraídos {summary['found']} objetos de "
                f"`{catalog}.{schema}`. +{summary['new']} novos, "
                f"~{summary['changed']} alterados, -{summary['removed']} removidos."
            ),
            errors=parse_warnings,
        )
    except Exception as exc:
        ended = datetime.utcnow()
        duration_ms = int((time.monotonic() - start_clock) * 1000)
        log.exception("run_uc_extraction failed catalog=%s schema=%s", catalog, schema)
        persist_extraction(
            sql,
            source_kind="UC",
            system_id=system_id,
            actor=actor,
            requested_schemas=[f"{catalog}.{schema}"],
            requested_kinds=["TABLE", "VIEW"],
            lakebase_sandbox_id=None,
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
            summary_md=f"Falha na extração UC: {exc}",
            errors=[str(exc)[:500]],
        )
