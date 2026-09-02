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
from .diff import RELATIONSHIP_SCHEMA
from .diff import compute_diff_against_catalog as compute_diff_against_catalog
from .models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedIndex,
    ExtractedIndexColumn,
    ExtractedRelationship,
    ExtractionResult,
    ExtractionSnapshot,
    PreviewObject,
)

log = logging.getLogger(__name__)


# Uma FK "crua" coletada na 1ª passe do parser DDL, ANTES de resolver a tabela
# referenciada. Guardamos o nome/schema-hint da tabela-alvo e resolvemos por
# nome só na 2ª passe (quando todas as entities do arquivo já foram parseadas).
# Ver `run_ddl_import` para o porquê das 2 passes (ordem de CREATE não importa).
class _PendingFK:
    __slots__ = (
        "parent_schema_hint",
        "parent_name",
        "parent_cols",
        "child_schema",
        "child_table",
        "child_cols",
    )

    def __init__(
        self,
        parent_schema_hint: str | None,
        parent_name: str,
        parent_cols: list[str],
        child_schema: str,
        child_table: str,
        child_cols: list[str],
    ) -> None:
        self.parent_schema_hint = parent_schema_hint  # schema explícito no REFERENCES, se houver
        self.parent_name = parent_name
        self.parent_cols = parent_cols
        self.child_schema = child_schema
        self.child_table = child_table
        self.child_cols = child_cols


def _ddl_reference_raw(
    ref, child_schema: str, child_table: str, child_cols: list[str]
) -> _PendingFK | None:
    """Extrai os dados CRUS de um nó sqlglot exp.Reference (FK inline ou
    table-level) SEM resolver a tabela-alvo. parent = tabela referenciada (PK);
    child = tabela sendo definida (segura a FK).

    Diferente da versão antiga (`_ddl_reference_to_rel`), NÃO descarta a FK
    quando a tabela referenciada ainda não foi vista — só coleta o nome. A
    resolução (schema + colunas PK + aviso de órfã) acontece na 2ª passe em
    `_resolve_pending_fks`. Retorna None só quando o nó não tem nome de tabela
    algum (ex.: sintaxe não reconhecida)."""
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
    parent_schema_hint = rtbl.db if getattr(rtbl, "db", "") else None
    return _PendingFK(
        parent_schema_hint=parent_schema_hint,
        parent_name=rtbl.name,
        parent_cols=parent_cols,
        child_schema=child_schema,
        child_table=child_table,
        child_cols=child_cols,
    )


def _resolve_pending_fks(
    pending: list[_PendingFK],
    entities: list[ExtractedEntity],
    search_path: list[str],
    catalog_keys: set[tuple[str, str]] | None,
) -> tuple[list[ExtractedRelationship], list[str]]:
    """2ª passe: resolve cada FK crua por NOME, agora que todas as entities do
    DDL já foram parseadas. Espelha o comportamento do fluxo DM1 (avisa quando
    a tabela-alvo não existe, em vez de descartar em silêncio).

    Resolução do schema da tabela-alvo (Postgres-like), na ordem:
      1. schema explícito no `REFERENCES schema.tabela`;
      2. mesmo schema da tabela filha (comum em modelos single-schema);
      3. schemas do `search_path`, na ordem;
      4. qualquer entity do DDL com aquele nome (match único por nome).

    parent_columns: quando o `REFERENCES` não traz colunas, assume a(s) PK(s) da
    entity-alvo do próprio DDL. Se a alvo não tem PK conhecida, registra aviso e
    segue (o relacionamento ainda é útil como "1:N por nome").

    Aviso de órfã: emitido só quando a tabela-alvo não existe NEM no DDL NEM no
    catálogo (`catalog_keys`) — padrão do DM1. Quando existe só no catálogo, o
    relacionamento é emitido normalmente (resolvido por nome no apply)."""
    # Índices por (schema, nome) e por nome-só das entities parseadas neste DDL.
    by_key: dict[tuple[str, str], ExtractedEntity] = {
        (e.schema_name, e.technical_name): e for e in entities
    }
    by_name: dict[str, list[ExtractedEntity]] = {}
    for e in entities:
        by_name.setdefault(e.technical_name, []).append(e)

    catalog_keys = catalog_keys or set()
    catalog_names = {name for (_sch, name) in catalog_keys}

    relationships: list[ExtractedRelationship] = []
    warnings: list[str] = []

    for fk in pending:
        # Candidatos de schema, na ordem de preferência.
        candidate_schemas: list[str] = []
        if fk.parent_schema_hint:
            candidate_schemas.append(fk.parent_schema_hint)
        candidate_schemas.append(fk.child_schema)
        candidate_schemas.extend(search_path)

        resolved_entity: ExtractedEntity | None = None
        resolved_schema: str | None = None
        for sch in candidate_schemas:
            ent = by_key.get((sch, fk.parent_name))
            if ent is not None:
                resolved_entity = ent
                resolved_schema = sch
                break
        # Sem hit por schema: aceita match único por nome dentro do DDL.
        if resolved_entity is None:
            same_name = by_name.get(fk.parent_name, [])
            if len(same_name) == 1:
                resolved_entity = same_name[0]
                resolved_schema = same_name[0].schema_name

        # Fallback do schema quando a alvo não está no DDL (só no catálogo, ou
        # órfã): usa hint → child_schema → 1º do search_path.
        if resolved_schema is None:
            resolved_schema = (
                fk.parent_schema_hint
                or fk.child_schema
                or (search_path[0] if search_path else "public")
            )

        # A alvo existe em algum lugar conhecido?
        target_in_ddl = resolved_entity is not None
        target_in_catalog = (
            (resolved_schema, fk.parent_name) in catalog_keys
            or fk.parent_name in catalog_names
        )
        if not target_in_ddl and not target_in_catalog:
            warnings.append(
                f"FK de {fk.child_schema}.{fk.child_table} referencia tabela "
                f"'{fk.parent_name}' inexistente no DDL e no catálogo — "
                f"relacionamento criado por nome (revisar)."
            )

        # parent_columns: usa as do REFERENCES; senão infere PK da alvo do DDL.
        parent_cols = list(fk.parent_cols)
        if not parent_cols and resolved_entity is not None:
            parent_cols = [
                a.technical_name for a in resolved_entity.attributes if a.is_primary_key
            ]
            if not parent_cols:
                warnings.append(
                    f"FK de {fk.child_schema}.{fk.child_table} para "
                    f"'{fk.parent_name}' sem colunas explícitas e alvo sem PK "
                    f"conhecida — colunas de origem indeterminadas."
                )

        relationships.append(
            ExtractedRelationship(
                parent_schema=resolved_schema,
                parent_entity=fk.parent_name,
                parent_columns=parent_cols,
                child_schema=fk.child_schema,
                child_entity=fk.child_table,
                child_columns=fk.child_cols,
                rel_type="1:N",
            )
        )

    return relationships, warnings


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


def _ddl_search_path_schemas(stmt, dialect) -> list[str]:
    """Extrai a LISTA de schemas de um `SET search_path TO a, b, c` (Postgres).

    O sqlglot ora devolve exp.Set (`SET search_path = streaming`), ora exp.Command
    (`SET search_path TO a, b` — sintaxe não suportada cai em Command), então
    detectamos via regex no SQL renderizado — robusto para os dois casos.

    Semântica Postgres (por que devolvemos a lista inteira, e não só o 1º):
    - CRIAÇÃO de objeto não-qualificado usa SEMPRE o PRIMEIRO schema do
      search_path (por isso o schema default das tabelas continua sendo o [0]).
    - RESOLUÇÃO de referência (ex.: FK `REFERENCES foo` sem schema) percorre a
      lista NA ORDEM. Guardar a lista permite casar a tabela-alvo do FK no schema
      certo quando o DDL usa múltiplos schemas.

    Retorna `[]` quando o statement não é um SET de search_path (o chamador
    então preserva o search_path corrente). Tokens `$user`/`public` implícitos e
    identificadores inválidos são filtrados.
    """
    try:
        txt = stmt.sql(dialect=dialect)
    except Exception:  # noqa: BLE001
        return []
    m = re.search(
        r"search_path\s*(?:=|to)\s+(.+)$",
        txt,
        re.IGNORECASE,
    )
    if not m:
        return []
    raw_list = m.group(1)
    schemas: list[str] = []
    for token in raw_list.split(","):
        t = token.strip().strip('"').strip("'").strip()
        # `$user` é resolvido em runtime pelo Postgres — sem valor no parse.
        if not t or t.startswith("$"):
            continue
        mt = re.match(r"^([A-Za-z_][A-Za-z0-9_$]*)", t)
        if mt:
            schemas.append(mt.group(1))
    return schemas


def _ddl_index_from_create(
    stmt, current_schema_default: str
) -> tuple[str, str, ExtractedIndex] | None:
    """Converte um `CREATE [UNIQUE] INDEX ... ON tabela (cols)` (sqlglot
    exp.Create kind=INDEX) em `(schema, tabela, ExtractedIndex)`.

    Espelha a paridade com o DM1: hoje o parser só olhava CREATE TABLE/VIEW e
    ignorava índices. Aqui reconhecemos o índice e o mapeamos para o mesmo shape
    que o DM1 persiste em `entity_indexes` (name, index_type, columns, is_unique,
    include, partial where quando o dialeto suportar).

    Robustez: a AST de índice varia por versão do sqlglot — usamos acessos
    defensivos (`args.get`) e caímos em `find_all`/regno SQL quando um caminho
    não existe. Retorna None quando não há nome de tabela ou de colunas.

    O casamento com a entity (por schema/nome) acontece no chamador, porque o
    índice pode aparecer ANTES ou DEPOIS do CREATE TABLE — a ordem não importa.
    """
    from sqlglot import expressions as exp

    # Nome do índice: `stmt.this` costuma ser um exp.Index cujo `.this` é o nome.
    index_node = stmt.this
    index_name = ""
    table_node = None
    col_nodes: list[Any] = []
    if isinstance(index_node, exp.Index):
        # Nome do índice (exp.Identifier / Table).
        name_node = index_node.this
        index_name = getattr(name_node, "name", "") or ""
        # Alvo: exp.IndexParameters em args['params'] ou o próprio 'table'.
        params = index_node.args.get("params")
        table_node = index_node.args.get("table")
        if isinstance(params, exp.IndexParameters):
            if not table_node:
                table_node = params.args.get("table")
            col_nodes = list(params.args.get("columns") or [])
        if not col_nodes:
            # Fallback: algumas versões guardam colunas direto no Index.
            col_nodes = list(index_node.args.get("columns") or [])
    else:
        # Layout alternativo: nome em `this`, tabela/colunas em args.
        index_name = getattr(index_node, "name", "") or ""
        table_node = stmt.args.get("table") or stmt.args.get("this")

    # Resolve schema + nome da tabela-alvo.
    tbl_name = getattr(table_node, "name", "") if table_node is not None else ""
    if not tbl_name and isinstance(table_node, exp.Table):
        tbl_name = table_node.name
    if not tbl_name:
        return None
    tbl_schema = (
        getattr(table_node, "db", "") if table_node is not None else ""
    ) or current_schema_default

    # Colunas do índice (ordem importa). Cada nó pode ser Column, Ordered
    # (com direção) ou Identifier. Direção: exp.Ordered com desc=True → DESC.
    columns: list[ExtractedIndexColumn] = []
    for cn in col_nodes:
        direction = "ASC"
        target = cn
        if isinstance(cn, exp.Ordered):
            if cn.args.get("desc"):
                direction = "DESC"
            target = cn.this
        col_name = getattr(target, "name", "") or ""
        if col_name:
            columns.append(ExtractedIndexColumn(name=col_name, direction=direction))
    if not columns:
        return None

    # UNIQUE: a flag `unique` pode viver no Create, no exp.Index ou no
    # IndexParameters — varia por versão do sqlglot. Checamos os três; se todos
    # forem None/ausentes, caímos no SQL renderizado (barato e determinístico).
    is_unique = bool(
        stmt.args.get("unique")
        or (isinstance(index_node, exp.Index) and index_node.args.get("unique"))
    )
    if not is_unique:
        try:
            rendered = stmt.sql()
            is_unique = bool(re.search(r"\bUNIQUE\b", rendered, re.IGNORECASE))
        except Exception:  # noqa: BLE001
            pass

    # INCLUDE (covering) e partial WHERE — só quando o dialeto expõe na AST.
    include_columns: list[str] = []
    partial_where: str | None = None
    try:
        params = index_node.args.get("params") if isinstance(index_node, exp.Index) else None
        if isinstance(params, exp.IndexParameters):
            for inc in (params.args.get("include") or []):
                nm = getattr(inc, "name", "") or ""
                if nm:
                    include_columns.append(nm)
            where_node = params.args.get("where")
            if where_node is not None:
                # exp.Where.this é a condição — renderiza sem a keyword WHERE.
                cond = getattr(where_node, "this", where_node)
                try:
                    partial_where = cond.sql()
                except Exception:  # noqa: BLE001
                    partial_where = None
    except Exception:  # noqa: BLE001 — metadados extras são best-effort
        pass

    index_type = "UNIQUE" if is_unique else "BTREE"
    return (
        tbl_schema,
        tbl_name,
        ExtractedIndex(
            index_name=index_name or f"ix_{tbl_name}_{'_'.join(c.name for c in columns)}",
            index_type=index_type,
            is_unique=is_unique,
            columns=columns,
            include_columns=include_columns,
            partial_where=partial_where,
        ),
    )


def _detect_dialect_from_content(ddl_text: str) -> str:
    """Heurística para detectar o dialeto SQL baseado no conteúdo do DDL.

    Busca por palavras-chave e construtos específicos de cada dialeto:
      - Postgres: SERIAL, BIGSERIAL, CURRENT_TIMESTAMP, SET search_path, ::type
      - T-SQL: NVARCHAR, GETDATE(), CONVERT(), IDENTITY, [column], dbo.
      - MySQL: AUTO_INCREMENT, ENGINE=, unsigned int, COLLATE
      - Oracle: NUMBER, SYSDATE, TO_DATE, CREATE OR REPLACE VIEW

    Retorna o dialeto detectado (ex.: "postgres", "tsql", "mysql", "oracle") ou
    None se nenhuma heurística bater (caller mantém o dialeto informado).

    Razão: Quando o frontend envia dialeto vazio/ANSI (por qualquer motivo), podemos
    tentar recuperar a informação do próprio DDL. Exemplo: streaming.sql é Postgres
    puro; se o frontend mandar "ANSI", detectamos "postgres" antes de falhar.
    """
    text_upper = ddl_text.upper()

    # Postgres: SERIAL é exclusivo (INT SERIAL /  BIGSERIAL, SET search_path, ::type)
    if re.search(r'\b(?:SERIAL|BIGSERIAL)\b', text_upper) or \
       re.search(r'\bSET\s+search_path\b', text_upper, re.IGNORECASE) or \
       re.search(r'::[\w\[\]]+', ddl_text):  # type cast ::json, ::bigint, etc.
        return "postgres"

    # T-SQL: NVARCHAR, GETDATE(), CONVERT(), IDENTITY, [brackets], dbo.
    if re.search(r'\b(?:NVARCHAR|GETDATE|CONVERT|IDENTITY)\b', text_upper) or \
       re.search(r'[\[\]][^\[\]]*[\[\]]', ddl_text) or \
       re.search(r'\bdbo\.', ddl_text, re.IGNORECASE):
        return "tsql"

    # MySQL: AUTO_INCREMENT, ENGINE=, COLLATE, unsigned
    if re.search(r'\bAUTO_INCREMENT\b', text_upper) or \
       re.search(r'\bENGINE\s*=', text_upper) or \
       re.search(r'\b(?:UNSIGNED|COLLATE)\b', text_upper):
        return "mysql"

    # Oracle: NUMBER, SYSDATE, TO_DATE, CREATE OR REPLACE VIEW
    if re.search(r'\b(?:NUMBER|SYSDATE|TO_DATE)\b', text_upper) or \
       re.search(r'\bCREATE\s+OR\s+REPLACE\s+VIEW\b', text_upper):
        return "oracle"

    # DB2 (IBM Db2 / Db2 for i): tipos e catálogo EXCLUSIVOS — DECFLOAT,
    # VARGRAPHIC/GRAPHIC/DBCLOB, SYSIBM/SYSCAT, NEXTVAL FOR. Nota: NÃO usamos
    # "GENERATED … AS IDENTITY" aqui porque a palavra IDENTITY também aparece no
    # T-SQL (checado acima) e venceria a classificação — ficaríamos com o dialeto
    # errado. Os marcadores abaixo não colidem com outros dialetos.
    if re.search(r'\b(?:DECFLOAT|VARGRAPHIC|DBCLOB|GRAPHIC)\b', text_upper) or \
       re.search(r'\bSYS(?:IBM|CAT)\.', text_upper) or \
       re.search(r'\bNEXTVAL\s+FOR\b', text_upper):
        return "db2"

    # Sem match — retorna None (caller mantém o dialeto informado)
    return None


# ─── Resolução de dialeto para o sqlglot ──────────────────────────────────────
# O sqlglot só reconhece nomes canônicos ("postgres", "tsql", "oracle", "mysql",
# "spark", "db2"). O app, porém, tem MAIS de uma tela mandando o dialeto e elas não
# usavam o mesmo vocabulário: o wizard de novo sistema enviava
# "POSTGRESQL"/"MSSQL"/"ORACLE"/"DATABRICKS", que NÃO batiam com o mapa canônico —
# o sqlglot recebia um nome desconhecido, o parse devolvia 0 objetos e o import
# terminava "FAILED" sem pista do motivo (round 5, pt 12). Centralizamos a tradução
# aqui, com uma tabela de aliases, para o backend ficar resiliente a QUALQUER
# chamador; um nome ainda assim desconhecido cai em None (modo auto do sqlglot) em
# vez de estourar "Unknown dialect".
_DDL_DIALECT_ALIASES: dict[str, str] = {
    # PostgreSQL
    "POSTGRESQL": "POSTGRES", "PSQL": "POSTGRES", "PG": "POSTGRES",
    # Oracle → nossa chave canônica é PLSQL
    "ORACLE": "PLSQL",
    # SQL Server → nossa chave canônica é TSQL
    "MSSQL": "TSQL", "SQLSERVER": "TSQL", "SQL SERVER": "TSQL", "SQL_SERVER": "TSQL",
    # Databricks/Spark/Delta → nossa chave canônica é SPARKSQL
    "DATABRICKS": "SPARKSQL", "SPARK": "SPARKSQL", "DELTA": "SPARKSQL",
    # IBM Db2 (variações)
    "DB2 FOR I": "DB2", "DB2LUW": "DB2", "LUW": "DB2",
}

# Chave canônica (após aliases) → nome que o sqlglot entende. None = ANSI/auto.
_SQLGLOT_DIALECT_BY_KEY: dict[str, str | None] = {
    "ANSI": None,
    "TSQL": "tsql",
    "PLSQL": "oracle",
    "POSTGRES": "postgres",
    "MYSQL": "mysql",
    "SPARKSQL": "spark",
    "DB2": "db2",
}

# Allowlist de dialetos que o sqlglot reconhece — consultada quando o nome informado
# não é canônico nem alias conhecido. Se estiver aqui, passamos direto (lowercase);
# senão, caímos em None (auto) para nunca estourar "Unknown dialect".
_SQLGLOT_KNOWN_DIALECTS: frozenset[str] = frozenset({
    "tsql", "oracle", "postgres", "mysql", "spark", "db2", "sqlite",
    "snowflake", "bigquery", "redshift", "presto", "trino", "hive",
    "databricks", "duckdb", "clickhouse", "teradata", "drill",
})


def _resolve_sqlglot_dialect(dialect: str | None) -> str | None:
    """Traduz o dialeto informado (canônico OU alias comum) para o nome do sqlglot.

    Retorna None para ANSI/genérico/desconhecido — nesses casos o sqlglot roda em
    modo automático em vez de estourar "Unknown dialect". Ver a nota acima sobre o
    bug do wizard (round 5, pt 12).

    Exemplos:
        _resolve_sqlglot_dialect("POSTGRES")    -> "postgres"
        _resolve_sqlglot_dialect("POSTGRESQL")  -> "postgres"   (alias)
        _resolve_sqlglot_dialect("MSSQL")       -> "tsql"        (alias)
        _resolve_sqlglot_dialect("ANSI")        -> None          (auto)
        _resolve_sqlglot_dialect("XYZ")         -> None          (desconhecido → auto)
    """
    if not dialect:
        return None
    key = dialect.strip().upper()
    key = _DDL_DIALECT_ALIASES.get(key, key)
    if key in _SQLGLOT_DIALECT_BY_KEY:
        return _SQLGLOT_DIALECT_BY_KEY[key]
    lowered = key.lower()
    return lowered if lowered in _SQLGLOT_KNOWN_DIALECTS else None


# round 6 (follow-up pt 15): extração de COMMENT ON por REGEX do DDL cru.
# GOTCHA (achado na validação ao vivo): algumas versões do sqlglot NÃO modelam
# `COMMENT ON TABLE … IS '…'` como `exp.Comment` no AST (só a de COLUMN), então a
# descrição da TABELA "sumia" no import — mesmo o teste de CI (sqlglot fixado)
# passando. O regex roda como SUPLEMENTO version-agnostic: casa TABLE e COLUMN
# direto no texto e é a baseline dos deferred comments (o parse do sqlglot ainda
# roda e sobrescreve com o mesmo valor quando também reconhece).
# Nome qualificado: aceita 1..3 partes (catalog.schema.table), com aspas opcionais
# e identificadores unicode (\w cobre acentos em py3). O `IS '<texto>'` pode estar
# na linha seguinte (o `\s+` cobre quebras); `''` é aspa escapada dentro do texto.
_RE_COMMENT_TABLE = re.compile(
    r"COMMENT\s+ON\s+TABLE\s+(?P<name>[\w\".]+)\s+IS\s+'(?P<text>(?:[^']|'')*)'",
    re.IGNORECASE,
)
_RE_COMMENT_COLUMN = re.compile(
    r"COMMENT\s+ON\s+COLUMN\s+(?P<name>[\w\".]+)\s+IS\s+'(?P<text>(?:[^']|'')*)'",
    re.IGNORECASE,
)


def _strip_sql_comments(ddl: str) -> str:
    """Remove comentários SQL de bloco `/* … */` e de LINHA INTEIRA `-- …` antes do
    regex de COMMENT ON — senão um `-- COMMENT ON TABLE x IS 'velho'` comentado seria
    capturado como descrição real (review). Só strip de linha-inteira (`^\\s*--`)
    para NÃO truncar um `--` legítimo DENTRO de uma string (ex.: IS 'a -- b')."""
    ddl = re.sub(r"/\*.*?\*/", " ", ddl, flags=re.DOTALL)
    ddl = re.sub(r"(?m)^\s*--.*$", "", ddl)
    return ddl


def _qual_name(raw: str) -> list[str]:
    """Quebra um nome qualificado em partes, tirando aspas. `"My"."Tbl"` → ['My','Tbl']."""
    return [p.strip('"') for p in raw.split(".") if p.strip('"')]


def _regex_comment_ons(
    ddl_text: str,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], str]]:
    """Extrai (deferred_table_comments, deferred_col_comments) do DDL cru via regex.

    Schema default 'public' (mesmo default do parser sqlglot). Desescapa `''`→`'`.
    Cobre nomes 1..3 partes; a última parte é a tabela (TABLE) ou coluna (COLUMN).
    """
    ddl = _strip_sql_comments(ddl_text)
    tbl: dict[tuple[str, str], str] = {}
    col: dict[tuple[str, str, str], str] = {}
    for m in _RE_COMMENT_TABLE.finditer(ddl):
        parts = _qual_name(m.group("name"))
        if not parts:
            continue
        table = parts[-1]
        schema = parts[-2] if len(parts) >= 2 else "public"
        tbl[(schema, table)] = m.group("text").replace("''", "'")
    for m in _RE_COMMENT_COLUMN.finditer(ddl):
        parts = _qual_name(m.group("name"))
        if len(parts) < 2:
            continue
        col_name = parts[-1]
        table = parts[-2]
        schema = parts[-3] if len(parts) >= 3 else "public"
        col[(schema, table, col_name)] = m.group("text").replace("''", "'")
    return tbl, col


def _build_preview(diff: Any) -> list[PreviewObject]:
    """Constrói o PREVIEW (dry-run) a partir do ``TicketDiff`` calculado.

    Uma linha por objeto que MUDARIA — separando relacionamentos (FK) das
    tabelas/views para o cliente ler de relance o que o import faria, SEM abrir
    ticket nem persistir. Best-effort: nunca derruba o import (um diff torto vira
    preview vazio em vez de erro)."""
    out: list[PreviewObject] = []
    try:
        entities = getattr(diff, "entities", None) or []
    except Exception:  # noqa: BLE001
        return out
    for ent in entities:
        try:
            op = getattr(ent, "op", "") or ""
            schema = getattr(ent, "schema_name", "") or ""
            name = getattr(ent, "technical_name", "") or ""
            etype = getattr(ent, "entity_type", "TABLE") or "TABLE"
            # Relacionamento sintético (FK) — rotula distinto no preview.
            if schema == RELATIONSHIP_SCHEMA:
                out.append(PreviewObject(
                    op=op if op in ("add", "change", "remove") else "add",
                    schema_name="(relacionamento)", technical_name=name,
                    entity_type="RELATIONSHIP", detail="chave estrangeira",
                ))
                continue
            if op == "add":
                n = len(getattr(ent, "attributes", None) or [])
                detail = f"+{n} coluna(s)" if n else "nova tabela/view"
                out.append(PreviewObject(op="add", schema_name=schema, technical_name=name,
                                         entity_type=etype, change_count=n, detail=detail))
            elif op == "change":
                fcs = getattr(ent, "field_changes", None) or []
                out.append(PreviewObject(op="change", schema_name=schema, technical_name=name,
                                         entity_type=etype, change_count=len(fcs),
                                         detail=f"{len(fcs)} alteração(ões)"))
            elif op == "remove":
                out.append(PreviewObject(op="remove", schema_name=schema, technical_name=name,
                                         entity_type=etype, detail="removido do catálogo"))
        except Exception:  # noqa: BLE001 — uma linha torta não invalida o preview
            continue
    return out


def run_ddl_import(
    sql: Sql,
    *,
    system_id: str,
    dialect: str,
    ddl_text: str,
    actor: str,
    open_ticket_on_diff: bool,
    dry_run: bool = False,
) -> ExtractionResult:
    """Parse DDL com sqlglot, constrói snapshot, compara com catálogo, abre ticket.

    Fluxo:
      1. Auto-detecta dialeto se vazio/ANSI (heurística por conteúdo DDL)
      2. Parse statement-a-statement (resiliente: ignora CREATE SCHEMA/SET)
      3. Suporta SERIAL/BIGSERIAL, CHECK, PK composta, FKs multi-schema
      4. Resolve schema de tabelas não-qualificadas por search_path[0]
      5. Dedup de relacionamentos por id determinístico (idempotente)
      6. Cria ticket se houver mudanças (entidades novas/alteradas/removidas)

    ``dry_run=True`` (PREVIEW): faz TODO o parse + diff, mas NÃO abre ticket e NÃO
    persiste a extração — devolve o ExtractionResult com as contagens + a lista
    ``preview`` (o que mudaria por objeto). Deixa o cliente conferir antes de
    importar de verdade. É read-only (não escreve nada no catálogo).
    """
    import sqlglot
    from sqlglot import expressions as exp

    started = datetime.utcnow()
    start_clock = time.monotonic()

    # Auto-detecta dialeto se vazio ou "ANSI" (fallback heurístico)
    effective_dialect = dialect
    if not effective_dialect or effective_dialect.upper() in ("ANSI", ""):
        detected = _detect_dialect_from_content(ddl_text)
        if detected:
            effective_dialect = detected.upper()
            log.info(
                "run_ddl_import: dialeto auto-detectado '%s' (informado: '%s')",
                detected, dialect
            )
        else:
            effective_dialect = dialect or "ANSI"

    # Traduz para o nome que o sqlglot entende (resiliente a aliases; ver
    # _resolve_sqlglot_dialect). Antes, um dialeto fora do mapa canônico (ex.:
    # "POSTGRESQL" vindo do wizard) escapava como nome desconhecido e zerava o
    # parse → import "FAILED" (round 5, pt 12).
    sg_dialect = _resolve_sqlglot_dialect(effective_dialect)

    entities: list[ExtractedEntity] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Parse RESILIENTE: tenta todo o texto; se falhar, tenta statement-a-statement.
    # Assim, um `CREATE SCHEMA` ou `SET` malformado não aborta o lote inteiro.
    # (errors/warnings já inicializados acima para o fallback poder registrar.)
    parsed: list[Any] = []
    try:
        parsed = sqlglot.parse(ddl_text, dialect=sg_dialect) or []
    except Exception as exc_full:
        # Fallback: split por ";" e tenta cada statement isolado.
        log.debug("run_ddl_import: falha no parse global, tentando statement-a-statement: %s", exc_full)
        for raw_stmt in ddl_text.split(";"):
            raw_stmt = raw_stmt.strip()
            if not raw_stmt:
                continue
            try:
                stmts = sqlglot.parse(raw_stmt + ";", dialect=sg_dialect) or []
                parsed.extend(stmts)
            except Exception as exc_stmt:
                errors.append(f"Statement ignorado: {str(exc_stmt)[:100]}")
    # FKs coletadas CRUAS na 1ª passe; resolvidas por nome na 2ª passe (ver
    # `_resolve_pending_fks`). Assim a ORDEM dos CREATE TABLE deixa de importar:
    # uma FK declarada antes da tabela-alvo passa a ser resolvida corretamente.
    pending_fks: list[_PendingFK] = []
    # Índices de `CREATE INDEX` coletados na 1ª passe — casados às entities na
    # 2ª passe (o índice pode vir antes OU depois do CREATE TABLE).
    pending_indexes: list[tuple[str, str, ExtractedIndex]] = []
    # Comentários de `COMMENT ON TABLE/COLUMN ... IS '...'` costumam vir DEPOIS
    # do CREATE — guardamos e aplicamos no fim (chave = schema/tabela[/coluna]).
    deferred_table_comments: dict[tuple[str, str], str] = {}
    deferred_col_comments: dict[tuple[str, str, str], str] = {}
    # Baseline via REGEX (version-agnostic) — garante COMMENT ON TABLE mesmo quando
    # o AST do sqlglot não o modela. O parse do sqlglot abaixo pode sobrescrever
    # (mesmo valor) e cobre variações que o regex não pegue.
    _rx_tbl, _rx_col = _regex_comment_ons(ddl_text)
    deferred_table_comments.update(_rx_tbl)
    deferred_col_comments.update(_rx_col)
    # search_path corrente (lista, na ordem). O 1º item é o schema default de
    # objetos não-qualificados (semântica Postgres: CREATE usa sempre o 1º).
    # A lista completa é usada na resolução de FKs multi-schema. Honra
    # `SET search_path TO a, b, c` (dumps Postgres): sem isso, tudo caía em
    # "public" mesmo quando o DDL declara `SET search_path TO streaming, public`.
    current_search_path: list[str] = ["public"]
    for stmt in parsed:
        if stmt is None:
            continue
        # SET search_path muda o schema default (e a ordem de resolução).
        if isinstance(stmt, (exp.Set, exp.Command)):
            sp = _ddl_search_path_schemas(stmt, sg_dialect)
            if sp:
                current_search_path = sp
            continue
        # CREATE SCHEMA — ignorado silenciosamente (não é entidade, só define context)
        if isinstance(stmt, exp.Create) and stmt.kind and stmt.kind.upper() == "SCHEMA":
            continue
        # CREATE [UNIQUE] INDEX — coletado cru e casado à entity na 2ª passe.
        if isinstance(stmt, exp.Create) and stmt.kind and stmt.kind.upper() == "INDEX":
            try:
                extracted = _ddl_index_from_create(stmt, current_search_path[0])
                if extracted:
                    pending_indexes.append(extracted)
            except Exception as exc:  # noqa: BLE001 — índice best-effort
                errors.append(f"CREATE INDEX ignorado: {exc}")
            continue
        current_schema_default = current_search_path[0]
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
                    col_check: str | None = None
                    for cons in (col_expr.args.get("constraints") or []):
                        kind = cons.args.get("kind")
                        if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                            pk_cols.add(name)
                        if isinstance(kind, exp.NotNullColumnConstraint):
                            is_nullable = False
                        # FK inline: `col INT REFERENCES outra(col)` — coletada
                        # crua e resolvida por nome na 2ª passe.
                        if isinstance(kind, exp.Reference):
                            pfk = _ddl_reference_raw(kind, schema_name, tbl_name, [name])
                            if pfk:
                                pending_fks.append(pfk)
                        # Comentário inline: `col INT COMMENT 'texto'`
                        if isinstance(kind, exp.CommentColumnConstraint):
                            col_comment = _ddl_literal_str(kind.this)
                        # CHECK inline: `col INT CHECK (col > 0)` (round 6 pt 21).
                        # O nome da classe varia entre versões do sqlglot; capturamos
                        # de forma defensiva (best-effort, nunca derruba o parse) a
                        # EXPRESSÃO interna do check como texto.
                        if type(kind).__name__ == "CheckColumnConstraint":
                            try:
                                inner = kind.this if kind.this is not None else kind
                                col_check = inner.sql()
                            except Exception:  # noqa: BLE001
                                col_check = None
                    attributes.append(
                        ExtractedAttribute(
                            technical_name=name,
                            ordinal_position=len(attributes) + 1,
                            native_data_type=native,
                            is_nullable=is_nullable,
                            is_primary_key=False,  # set below from pk_cols
                            native_comment=col_comment,
                            check_constraint=col_check,
                        )
                    )
                # PK table-level: `PRIMARY KEY (a, b)` (chave composta). Sem
                # isso, PK composta ficava sem marcação e a inferência de
                # parent_columns de FK (que usa a PK da alvo) falhava.
                for pk_node in schema_obj.find_all(exp.PrimaryKey):
                    for c in (pk_node.expressions or []):
                        cname = getattr(c, "name", "") or ""
                        if cname:
                            pk_cols.add(cname)
                # Mark PKs
                for attr in attributes:
                    if attr.technical_name in pk_cols:
                        attr.is_primary_key = True
                # FK table-level: `CONSTRAINT ... FOREIGN KEY (...) REFERENCES ...`
                for fk in schema_obj.find_all(exp.ForeignKey):
                    local_cols = [c.name for c in fk.expressions if hasattr(c, "name")]
                    ref = fk.args.get("reference")
                    if ref is not None:
                        pfk = _ddl_reference_raw(ref, schema_name, tbl_name, local_cols)
                        if pfk:
                            pending_fks.append(pfk)
                # CHECK table-level: `CONSTRAINT ck CHECK (expr)` (round 6 pt 21).
                # sqlglot modela AMBOS (inline de coluna E table-level) como
                # `CheckColumnConstraint`; `find_all` recursa e acha os dois. Assoc.
                # a expressão ao atributo referenciado quando menciona UMA única
                # coluna conhecida (ex.: `CHECK (PRINCIPAL IN (0,1))`). O de coluna
                # já foi capturado acima — o guard `not ...check_constraint` evita
                # sobrescrever. Best-effort: nunca derruba o parse (os nomes de
                # classe variam entre versões do sqlglot).
                try:
                    attr_by_name = {a.technical_name: a for a in attributes}
                    check_cls = [
                        getattr(exp, n, None)
                        for n in ("CheckColumnConstraint", "Check")
                    ]
                    check_nodes: list = []
                    for cls in check_cls:
                        if cls is not None:
                            check_nodes.extend(schema_obj.find_all(cls))
                    for chk in check_nodes:
                        expr = chk.this if getattr(chk, "this", None) is not None else chk
                        try:
                            refs = {
                                c.name for c in expr.find_all(exp.Column)
                                if getattr(c, "name", None)
                            }
                            expr_sql = expr.sql()
                        except Exception:  # noqa: BLE001
                            continue
                        known = [r for r in refs if r in attr_by_name]
                        if len(known) == 1 and not attr_by_name[known[0]].check_constraint:
                            attr_by_name[known[0]].check_constraint = expr_sql
                except Exception:  # noqa: BLE001
                    pass
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
                    # setdefault: o REGEX (baseline, rodado antes) é autoritativo —
                    # o parse do sqlglot para COMMENT ON é declaradamente não-confiável
                    # neste app, então só PREENCHE chaves que o regex não pegou; nunca
                    # sobrescreve o valor do regex com uma extração pior (review).
                    if obj_kind == "COLUMN":
                        col = target.name if hasattr(target, "name") else ""
                        tbl = getattr(target, "table", "") or ""
                        sch = getattr(target, "db", "") or "public"
                        if col and tbl:
                            deferred_col_comments.setdefault((sch, tbl, col), text)
                    else:  # TABLE (default)
                        tbl = target.name if hasattr(target, "name") else ""
                        sch = (getattr(target, "db", "") or None) or "public"
                        if tbl:
                            deferred_table_comments.setdefault((sch, tbl), text)
        except Exception as exc:
            errors.append(f"parse stmt skipped: {exc}")

    # Aplica os comentários de COMMENT ON coletados (autoritativos — sobrescrevem
    # o que veio inline no CREATE, pois são declarações explícitas).
    #
    # GOTCHA (round 6, arquivo real do cliente): o schema do COMMENT ON pode
    # DIVERGIR do schema resolvido no CREATE. Ex.: o DDL tem `SET search_path TO
    # social;` → a tabela vira `social.pessoa`, mas o `COMMENT ON TABLE pessoa`
    # (sem schema) é indexado como `public.pessoa`. Sem fallback, o comentário não
    # casa e a descrição não é importada. Fazemos fallback por NOME de tabela
    # quando (a) o match schema-qualificado falha e (b) o nome é ÚNICO no arquivo.
    from collections import Counter as _Counter
    _tbl_counts = _Counter(e.technical_name for e in entities)
    _tbl_comment_by_name: dict[str, str] = {}
    for (_s, _t), _txt in deferred_table_comments.items():
        _tbl_comment_by_name.setdefault(_t, _txt)
    _col_comment_by_name: dict[tuple[str, str], str] = {}
    for (_s, _t, _c), _txt in deferred_col_comments.items():
        _col_comment_by_name.setdefault((_t, _c), _txt)

    for e in entities:
        tc = deferred_table_comments.get((e.schema_name, e.technical_name))
        if not tc and _tbl_counts[e.technical_name] == 1:
            tc = _tbl_comment_by_name.get(e.technical_name)
        if tc:
            e.native_comment = tc
        # round 6 pt 15: o COMMENT ON de tabela vira também descrição de negócio.
        # ExtractedEntity não tem description_md; o apply de entity nova já faz o
        # fallback native_comment→description_md (tickets/service _apply_op_add),
        # então o comentário de tabela chega em description_md sem mais nada aqui.
        for a in e.attributes:
            cc = deferred_col_comments.get((e.schema_name, e.technical_name, a.technical_name))
            if not cc and _tbl_counts[e.technical_name] == 1:
                cc = _col_comment_by_name.get((e.technical_name, a.technical_name))
            if cc:
                a.native_comment = cc
            # round 6 pt 15: importa o COMMENT ON COLUMN (ou comentário inline) como
            # DESCRIÇÃO de negócio da coluna (description_md), além do comentário
            # nativo. É o "descritivo/definição/metadado" que o cliente quer trazer
            # do DDL para o modelo.
            if a.native_comment and not a.description_md:
                a.description_md = a.native_comment

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
            f"Dialeto usado: {effective_dialect} "
            f"(sqlglot: {sg_dialect or 'auto'}). "
            "Confirme se o dialeto corresponde ao arquivo "
            "(aceitos: ANSI, POSTGRES, TSQL, PLSQL, MYSQL, SPARKSQL, DB2)."
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
        # dry_run: NÃO persiste a extração — só devolve o diagnóstico (preview vazio).
        ext_id = "(dry-run)" if dry_run else persist_extraction(
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

    # 2ª passe — casa os `CREATE INDEX` às entities (por schema+nome, ou só por
    # nome quando o índice não qualificou o schema). Feito aqui, depois de TODAS
    # as tabelas parseadas, para não depender da ordem CREATE TABLE vs INDEX.
    entity_by_key: dict[tuple[str, str], ExtractedEntity] = {
        (e.schema_name, e.technical_name): e for e in entities
    }
    entity_by_name: dict[str, list[ExtractedEntity]] = {}
    for e in entities:
        entity_by_name.setdefault(e.technical_name, []).append(e)
    for ix_schema, ix_table, ix in pending_indexes:
        target = entity_by_key.get((ix_schema, ix_table))
        if target is None:
            same_name = entity_by_name.get(ix_table, [])
            if len(same_name) == 1:
                target = same_name[0]
        if target is None:
            warnings.append(
                f"Índice '{ix.index_name}' referencia tabela "
                f"'{ix_schema}.{ix_table}' não encontrada no DDL — ignorado."
            )
            continue
        # Dedup por nome (não duplica se o mesmo índice aparecer 2x).
        if any(existing.index_name == ix.index_name for existing in target.indexes):
            continue
        target.indexes.append(ix)

    # 2ª passe — resolve as FKs coletadas cruas. Precisa das chaves do catálogo
    # para decidir órfã (existe só no catálogo → não é órfã). Query enxuta,
    # espelhando o que o diff já faz, mas só das chaves.
    catalog_keys: set[tuple[str, str]] = set()
    try:
        s = get_settings()
        cat_rows = delta.fetch_all_params(
            sql,
            f"SELECT schema_name, technical_name FROM {s.fq_table('entities')} "
            f"WHERE system_id = :system_id",
            [delta.param("system_id", system_id)],
        )
        catalog_keys = {(r[0], r[1]) for r in cat_rows}
    except Exception as exc:  # noqa: BLE001 — sem catálogo, resolvemos só pelo DDL
        log.warning("run_ddl_import: falha ao ler chaves do catálogo: %s", exc)

    relationships, fk_warnings = _resolve_pending_fks(
        pending_fks, entities, current_search_path, catalog_keys
    )
    warnings.extend(fk_warnings)

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
    # Total de índices casados às entities (métrica para o log/ticket).
    idx_count = sum(len(e.indexes) for e in entities)
    ticket_id: str | None = None
    if has_changes and open_ticket_on_diff:
        warnings_block = (
            "\n\n**Avisos do parser:**\n"
            + "\n".join(f"- {w}" for w in warnings[:20])
            if warnings
            else ""
        )
        ticket_id = open_ticket(
            sql,
            title=(
                f"Reconciliação DDL ({dialect}) — {summary['new']} novos, "
                f"{summary['changed']} alterados, {summary['removed']} removidos"
            ),
            system_id=system_id,
            source_type="DDL_IMPORT",
            diff=diff,
            summary_md=(
                f"Dialeto: {dialect}\n"
                f"{len(entities)} CREATE statements parseados.\n"
                f"{summary.get('relationships', 0)} relacionamento(s), "
                f"{idx_count} índice(s).\n"
                f"Erros de parse: {len(errors)}"
                f"{warnings_block}"
            ),
            created_by=actor,
        )
    # PARTIAL quando houve erro de parse OU aviso (FK órfã / índice sem tabela):
    # o usuário precisa revisar. Espelha o DM1, que marca PARTIAL com problemas.
    status = "SUCCESS" if not (errors or warnings) else "PARTIAL"
    rel_note = (
        f" {summary.get('relationships', 0)} relacionamento(s)."
        if summary.get("relationships")
        else ""
    )
    idx_note = f" {idx_count} índice(s)." if idx_count else ""
    base_summary = (
        f"Parseado {summary['found']} objetos. "
        f"+{summary['new']} novos, ~{summary['changed']} alterados, "
        f"-{summary['removed']} removidos.{rel_note}{idx_note}"
    )
    # `errors` = problemas de parse; `warnings` = avisos informativos (órfãs etc).
    import_log = format_import_log(errors, warnings)
    summary_md = base_summary + (f"\n\n{import_log}" if import_log else "")

    # dry_run (PREVIEW): NÃO persiste extração NEM abre ticket (o ticket já ficou
    # de fora porque o router passa open_ticket_on_diff=False). Devolve só as
    # contagens + a lista `preview` do que mudaria — 100% read-only.
    if dry_run:
        return ExtractionResult(
            extraction_id="(dry-run)",
            status=status,
            objects_found=summary["found"],
            objects_new=summary["new"],
            objects_changed=summary["changed"],
            objects_removed=summary["removed"],
            duration_ms=duration_ms,
            ticket_id=None,
            summary_md=summary_md,
            errors=errors + warnings,
            preview=_build_preview(diff),
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
        status=status,
        started_at=started,
        ended_at=ended,
        objects_found=summary["found"],
        objects_new=summary["new"],
        objects_changed=summary["changed"],
        objects_removed=summary["removed"],
        snapshot=snapshot,
        diff_summary=summary,
        error_summary=("\n".join(errors + warnings)[:4000]) if (errors or warnings) else None,
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
        # errors do resultado = parse errors + avisos (ambos merecem atenção).
        errors=errors + warnings,
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
