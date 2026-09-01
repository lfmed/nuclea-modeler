"""Hand-rolled DDL generators for 6 SQL dialects.

Each generator takes:
- entity: dict with keys {schema_name, technical_name, entity_type,
  description_md, native_comment}
- attrs: list of dicts with attribute fields, already sorted by ordinal_position
- opts: DDLExportRequest

Output: a single SQL string (possibly multi-statement).

Type mapping is best-effort. If native_data_type is recognised it is mapped
to the dialect-specific equivalent; otherwise the original native_data_type is
passed through. Dialect labels:
  ANSI     - SQL:2016 standard
  TSQL     - SQL Server / Azure SQL
  PLSQL    - Oracle
  POSTGRES - PostgreSQL
  MYSQL    - MySQL / MariaDB
  SPARKSQL - Spark SQL / Delta Lake (Databricks default)
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .models import DDLDialect, DDLExportRequest


# ──────────────────────────────────────────────────────────────────────────────
# Type mapping
# ──────────────────────────────────────────────────────────────────────────────


def _parse_native(native: str | None) -> tuple[str, str | None]:
    """Split native data type into (base, args).

    Returns (base_upper, args_or_None). Example:
        "varchar(255)" -> ("VARCHAR", "255")
        "decimal(10,2)" -> ("DECIMAL", "10,2")
        "int" -> ("INT", None)
    """
    if not native:
        return ("", None)
    m = re.match(r"^\s*([A-Za-z0-9_ ]+?)\s*(?:\(([^)]*)\))?\s*$", native.strip())
    if not m:
        return (native.strip().upper(), None)
    base = m.group(1).strip().upper()
    args = m.group(2).strip() if m.group(2) else None
    return (base, args)


_INT_TYPES = {"INT", "INTEGER", "INT4", "INT32"}
_BIGINT_TYPES = {"BIGINT", "INT8", "INT64", "LONG"}
_SMALLINT_TYPES = {"SMALLINT", "INT2", "INT16", "TINYINT"}
_DECIMAL_TYPES = {"DECIMAL", "NUMERIC", "NUMBER"}
_FLOAT_TYPES = {"FLOAT", "REAL", "DOUBLE", "DOUBLE PRECISION"}
_VARCHAR_TYPES = {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "VARCHAR2", "CHARACTER VARYING"}
_TEXT_TYPES = {"TEXT", "LONGTEXT", "STRING", "CLOB", "NTEXT", "MEDIUMTEXT"}
_DATE_TYPES = {"DATE"}
_TIMESTAMP_TYPES = {"TIMESTAMP", "DATETIME", "DATETIME2", "TIMESTAMPTZ"}
_BOOL_TYPES = {"BOOLEAN", "BOOL", "BIT"}


def map_type(native: str | None, dialect: DDLDialect) -> str:
    """Map a (loose) native type to a dialect-specific type string."""
    if not native:
        return "VARCHAR(255)"
    base, args = _parse_native(native)

    def with_args(default_args: str | None = None) -> str:
        return f"({args})" if args else (f"({default_args})" if default_args else "")

    if base in _INT_TYPES:
        return {
            "TSQL": "INT",
            "PLSQL": "NUMBER(10)",
            "POSTGRES": "INTEGER",
            "MYSQL": "INT",
            "SPARKSQL": "INT",
            "ANSI": "INTEGER",
            "DB2": "INTEGER",
        }[dialect]
    if base in _BIGINT_TYPES:
        return {
            "TSQL": "BIGINT",
            "PLSQL": "NUMBER(19)",
            "POSTGRES": "BIGINT",
            "MYSQL": "BIGINT",
            "SPARKSQL": "BIGINT",
            "ANSI": "BIGINT",
            "DB2": "BIGINT",
        }[dialect]
    if base in _SMALLINT_TYPES:
        return {
            "TSQL": "SMALLINT",
            "PLSQL": "NUMBER(5)",
            "POSTGRES": "SMALLINT",
            "MYSQL": "SMALLINT",
            "SPARKSQL": "SMALLINT",
            "ANSI": "SMALLINT",
            "DB2": "SMALLINT",
        }[dialect]
    if base in _DECIMAL_TYPES:
        a = args or "18,2"
        return {
            "TSQL": f"DECIMAL({a})",
            "PLSQL": f"NUMBER({a})",
            "POSTGRES": f"NUMERIC({a})",
            "MYSQL": f"DECIMAL({a})",
            "SPARKSQL": f"DECIMAL({a})",
            "ANSI": f"DECIMAL({a})",
            "DB2": f"DECIMAL({a})",
        }[dialect]
    if base in _FLOAT_TYPES:
        return {
            "TSQL": "FLOAT",
            "PLSQL": "NUMBER",
            "POSTGRES": "DOUBLE PRECISION",
            "MYSQL": "DOUBLE",
            "SPARKSQL": "DOUBLE",
            "ANSI": "DOUBLE PRECISION",
            "DB2": "DOUBLE",
        }[dialect]
    if base in _VARCHAR_TYPES:
        a = args or "255"
        return {
            "TSQL": f"NVARCHAR({a})",
            "PLSQL": f"VARCHAR2({a})",
            "POSTGRES": f"VARCHAR({a})",
            "MYSQL": f"VARCHAR({a})",
            "SPARKSQL": "STRING",
            "ANSI": f"VARCHAR({a})",
            "DB2": f"VARCHAR({a})",
        }[dialect]
    if base in _TEXT_TYPES:
        return {
            "TSQL": "NVARCHAR(MAX)",
            "PLSQL": "CLOB",
            "POSTGRES": "TEXT",
            "MYSQL": "TEXT",
            "SPARKSQL": "STRING",
            "ANSI": "TEXT",
            "DB2": "CLOB",
        }[dialect]
    if base in _DATE_TYPES:
        return "DATE"
    if base in _TIMESTAMP_TYPES:
        return {
            "TSQL": "DATETIME2",
            "PLSQL": "TIMESTAMP",
            "POSTGRES": "TIMESTAMP",
            "MYSQL": "DATETIME",
            "SPARKSQL": "TIMESTAMP",
            "ANSI": "TIMESTAMP",
            "DB2": "TIMESTAMP",
        }[dialect]
    if base in _BOOL_TYPES:
        return {
            "TSQL": "BIT",
            "PLSQL": "NUMBER(1)",
            "POSTGRES": "BOOLEAN",
            "MYSQL": "TINYINT(1)",
            "SPARKSQL": "BOOLEAN",
            "ANSI": "BOOLEAN",
            # DB2 tem BOOLEAN nativo desde 11.1; SMALLINT(0/1) é o fallback
            # clássico p/ Db2 for i. Usamos BOOLEAN por ser o mais direto.
            "DB2": "BOOLEAN",
        }[dialect]
    # unknown — pass through, preserving args
    if args:
        return f"{base}({args})"
    return base or "VARCHAR(255)"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _esc(value: str) -> str:
    """Escape a single-quoted SQL string."""
    return value.replace("'", "''")


def _table_ref(entity: dict[str, Any], opts: DDLExportRequest) -> str:
    schema = entity.get("schema_name") or ""
    name = entity.get("technical_name") or ""
    if opts.qualify_schema and schema:
        return f"{schema}.{name}"
    return name


def _entity_comment(entity: dict[str, Any]) -> str | None:
    """Pick the best free-text comment for an entity."""
    return entity.get("description_md") or entity.get("native_comment")


def _attr_comment(attr: dict[str, Any]) -> str | None:
    return attr.get("description_md") or attr.get("native_comment")


def _collect_pk(attrs: list[dict[str, Any]]) -> list[str]:
    return [a["technical_name"] for a in attrs if a.get("is_primary_key")]


def _col_nullable(attr: dict[str, Any]) -> str:
    """Render NULL/NOT NULL clause."""
    nullable = attr.get("is_nullable")
    if nullable is False or attr.get("is_primary_key"):
        return " NOT NULL"
    return ""


def _col_default(attr: dict[str, Any]) -> str:
    dv = attr.get("default_value")
    if dv is None or dv == "":
        return ""
    return f" DEFAULT {dv}"


# ──────────────────────────────────────────────────────────────────────────────
# Generators
# ──────────────────────────────────────────────────────────────────────────────


def _build_columns_block(
    attrs: list[dict[str, Any]],
    dialect: DDLDialect,
    inline_column_comments: bool = False,
) -> list[str]:
    """Render column definition lines (without trailing PK)."""
    lines: list[str] = []
    for a in attrs:
        col = a["technical_name"]
        typ = map_type(a.get("native_data_type"), dialect)
        nul = _col_nullable(a)
        dflt = _col_default(a)
        line = f"  {col} {typ}{dflt}{nul}"
        if inline_column_comments:
            comment = _attr_comment(a)
            if comment:
                line += f" COMMENT '{_esc(comment)}'"
        lines.append(line)
    return lines


def _drop_stmt(table_ref: str, opts: DDLExportRequest, kind: str = "TABLE") -> str:
    if not opts.include_drop_if_exists:
        return ""
    return f"DROP {kind} IF EXISTS {table_ref};\n"


# ──────────────────────────────────────────────────────────────────────────────
# Index + partition helpers (compartilhados entre dialetos)
# ──────────────────────────────────────────────────────────────────────────────


def _idx_cols_sql(idx: dict[str, Any]) -> str:
    """Renderiza ``col1, col2 DESC`` a partir de columns: [{name, direction}]."""
    parts: list[str] = []
    for c in idx.get("columns") or []:
        nm = c.get("name") if isinstance(c, dict) else None
        if not nm:
            continue
        direction = (c.get("direction") or "ASC").upper()
        parts.append(f"{nm} DESC" if direction == "DESC" else nm)
    return ", ".join(parts)


def _render_indexes_postgres(table: str, indexes: list[dict[str, Any]]) -> list[str]:
    """CREATE INDEX no estilo PostgreSQL (e ANSI/MySQL como fallback)."""
    out: list[str] = []
    for ix in indexes:
        name = ix.get("index_name")
        cols = _idx_cols_sql(ix)
        if not name or not cols:
            continue
        ix_type = (ix.get("index_type") or "BTREE").upper()
        unique = "UNIQUE " if ix.get("is_unique") or ix_type == "UNIQUE" else ""
        using = ""
        if ix_type in ("HASH", "GIN", "BRIN", "GIST"):
            using = f" USING {ix_type}"
        elif ix_type in ("BTREE", "UNIQUE"):
            pass
        stmt = f"CREATE {unique}INDEX {name} ON {table}{using} ({cols})"
        include = ix.get("include_columns") or []
        if include:
            stmt += f" INCLUDE ({', '.join(include)})"
        partial = ix.get("partial_where")
        if partial:
            stmt += f" WHERE {partial}"
        out.append(stmt + ";")
    return out


def _render_indexes_mysql(table: str, indexes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ix in indexes:
        name = ix.get("index_name")
        cols = _idx_cols_sql(ix)
        if not name or not cols:
            continue
        ix_type = (ix.get("index_type") or "BTREE").upper()
        unique = "UNIQUE " if ix.get("is_unique") or ix_type == "UNIQUE" else ""
        using = f" USING {ix_type}" if ix_type in ("BTREE", "HASH") else ""
        out.append(f"CREATE {unique}INDEX {name} ON {table} ({cols}){using};")
    return out


def _render_indexes_tsql(table: str, indexes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ix in indexes:
        name = ix.get("index_name")
        cols = _idx_cols_sql(ix)
        if not name or not cols:
            continue
        ix_type = (ix.get("index_type") or "NONCLUSTERED").upper()
        is_unique = ix.get("is_unique") or ix_type == "UNIQUE"
        unique = "UNIQUE " if is_unique else ""
        kind = "CLUSTERED" if ix_type == "CLUSTERED" else "NONCLUSTERED"
        stmt = f"CREATE {unique}{kind} INDEX {name} ON {table} ({cols})"
        include = ix.get("include_columns") or []
        if include:
            stmt += f" INCLUDE ({', '.join(include)})"
        partial = ix.get("partial_where")
        if partial:
            stmt += f" WHERE {partial}"
        out.append(stmt + ";")
    return out


def _render_indexes_oracle(table: str, indexes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ix in indexes:
        name = ix.get("index_name")
        cols = _idx_cols_sql(ix)
        if not name or not cols:
            continue
        ix_type = (ix.get("index_type") or "BTREE").upper()
        is_unique = ix.get("is_unique") or ix_type == "UNIQUE"
        unique = "UNIQUE " if is_unique else ""
        bitmap = "BITMAP " if ix_type == "BITMAP" else ""
        out.append(f"CREATE {unique}{bitmap}INDEX {name} ON {table} ({cols});")
    return out


def _partition_clause_pg(part: dict[str, Any] | None) -> str:
    """Cláusula ``PARTITION BY {STRATEGY} (cols)`` pra Postgres declarativo."""
    if not part or part.get("strategy") in (None, "NONE"):
        return ""
    strategy = (part.get("strategy") or "").upper()
    if strategy not in ("RANGE", "LIST", "HASH"):
        return ""
    cols = ", ".join(part.get("columns") or [])
    if not cols:
        return ""
    return f"\nPARTITION BY {strategy} ({cols})"


def _partition_clause_oracle(part: dict[str, Any] | None) -> str:
    if not part or part.get("strategy") in (None, "NONE"):
        return ""
    strategy = (part.get("strategy") or "").upper()
    cols = ", ".join(part.get("columns") or [])
    if not cols:
        return ""
    if strategy == "HASH":
        n = part.get("num_partitions") or 4
        return f"\nPARTITION BY HASH ({cols}) PARTITIONS {n}"
    if strategy in ("RANGE", "LIST"):
        return f"\nPARTITION BY {strategy} ({cols})"
    return ""


def _spark_partition_clause(part: dict[str, Any] | None) -> str:
    """Spark/Delta: PARTITIONED BY (col) ou cluster command (legacy)."""
    if not part or part.get("strategy") in (None, "NONE"):
        return ""
    strategy = (part.get("strategy") or "").upper()
    cols = part.get("columns") or []
    if not cols:
        return ""
    if strategy == "HASH":
        return f"\nPARTITIONED BY ({', '.join(cols)})"
    # LIQUID é setado via ALTER TABLE ... CLUSTER BY após criação
    return ""


def _spark_liquid_cluster(table: str, part: dict[str, Any] | None) -> str:
    """LIQUID CLUSTERING não é parte do CREATE TABLE em Delta — emitir
    ALTER TABLE ... CLUSTER BY ... como statement separado."""
    if not part or (part.get("strategy") or "").upper() != "LIQUID":
        return ""
    cols = part.get("columns") or []
    if not cols:
        return ""
    return f"ALTER TABLE {table} CLUSTER BY ({', '.join(cols)});"


def gen_ansi(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """ANSI SQL — minimal CREATE TABLE + inline PRIMARY KEY constraint.

    Comments rendered as leading SQL comment lines (no portable COMMENT ON).
    """
    table = _table_ref(entity, opts)
    out: list[str] = []

    if opts.include_comments:
        comment = _entity_comment(entity)
        if comment:
            for line in comment.splitlines():
                out.append(f"-- {line}")

    out.append(_drop_stmt(table, opts) + f"CREATE TABLE {table} (")
    cols = _build_columns_block(attrs, "ANSI", inline_column_comments=False)
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    out.append(");")

    if opts.include_comments:
        for a in attrs:
            c = _attr_comment(a)
            if c:
                out.append(f"-- {table}.{a['technical_name']}: {c.splitlines()[0]}")

    # ANSI/SQL não tem partição portável; emite só índices.
    out.extend(_render_indexes_postgres(table, entity.get("_indexes") or []))
    return "\n".join(out)


def gen_tsql(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """T-SQL (SQL Server / Azure SQL).

    Uses NVARCHAR/DATETIME2/BIT. Table comments rendered as leading -- comment
    (column comments via sp_addextendedproperty omitted on purpose).
    """
    table = _table_ref(entity, opts)
    out: list[str] = []

    if opts.include_comments:
        comment = _entity_comment(entity)
        if comment:
            for line in comment.splitlines():
                out.append(f"-- {line}")

    drop = ""
    if opts.include_drop_if_exists:
        drop = f"IF OBJECT_ID('{table}', 'U') IS NOT NULL DROP TABLE {table};\n"
    out.append(drop + f"CREATE TABLE {table} (")
    cols = _build_columns_block(attrs, "TSQL", inline_column_comments=False)
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    # SQL Server: partition function/scheme exigem objetos extras — emite
    # comentário pra steward configurar manualmente. Indexes via CREATE.
    part = entity.get("_partitioning")
    if part and (part.get("strategy") or "NONE") != "NONE":
        cols_part = ", ".join(part.get("columns") or [])
        out.append(");")
        out.append(
            f"-- Particionamento {part['strategy']} sobre ({cols_part}) — "
            f"requer PARTITION FUNCTION + SCHEME (criar manualmente)."
        )
    else:
        out.append(");")
    out.extend(_render_indexes_tsql(table, entity.get("_indexes") or []))
    return "\n".join(out)


def gen_plsql(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """Oracle PL/SQL. Uses VARCHAR2/NUMBER and COMMENT ON syntax."""
    table = _table_ref(entity, opts)
    out: list[str] = []

    if opts.include_drop_if_exists:
        # Oracle has no "DROP IF EXISTS" — wrap in PL/SQL block
        out.append(
            "BEGIN\n"
            f"  EXECUTE IMMEDIATE 'DROP TABLE {table}';\n"
            "EXCEPTION WHEN OTHERS THEN NULL;\n"
            "END;\n/"
        )

    out.append(f"CREATE TABLE {table} (")
    cols = _build_columns_block(attrs, "PLSQL", inline_column_comments=False)
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    part_clause = _partition_clause_oracle(entity.get("_partitioning"))
    out.append(f"){part_clause};")

    if opts.include_comments:
        tcomment = _entity_comment(entity)
        if tcomment:
            out.append(f"COMMENT ON TABLE {table} IS '{_esc(tcomment)}';")
        for a in attrs:
            c = _attr_comment(a)
            if c:
                out.append(
                    f"COMMENT ON COLUMN {table}.{a['technical_name']} IS '{_esc(c)}';"
                )

    out.extend(_render_indexes_oracle(table, entity.get("_indexes") or []))
    return "\n".join(out)


def gen_postgres(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """PostgreSQL. Uses VARCHAR/TEXT/TIMESTAMP/BOOLEAN and COMMENT ON."""
    table = _table_ref(entity, opts)
    out: list[str] = []
    out.append(_drop_stmt(table, opts) + f"CREATE TABLE {table} (")
    cols = _build_columns_block(attrs, "POSTGRES", inline_column_comments=False)
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    part_clause = _partition_clause_pg(entity.get("_partitioning"))
    out.append(f"){part_clause};")

    if opts.include_comments:
        tcomment = _entity_comment(entity)
        if tcomment:
            out.append(f"COMMENT ON TABLE {table} IS '{_esc(tcomment)}';")
        for a in attrs:
            c = _attr_comment(a)
            if c:
                out.append(
                    f"COMMENT ON COLUMN {table}.{a['technical_name']} IS '{_esc(c)}';"
                )

    out.extend(_render_indexes_postgres(table, entity.get("_indexes") or []))
    return "\n".join(out)


def gen_mysql(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """MySQL. Inline COMMENT '...' on columns and COMMENT='...' on table."""
    table = _table_ref(entity, opts)
    out: list[str] = []
    out.append(_drop_stmt(table, opts) + f"CREATE TABLE {table} (")
    cols = _build_columns_block(
        attrs, "MYSQL", inline_column_comments=opts.include_comments
    )
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    close_line = ")"
    if opts.include_comments:
        tcomment = _entity_comment(entity)
        if tcomment:
            close_line += f" COMMENT='{_esc(tcomment)}'"
    # MySQL: PARTITION BY inline
    part = entity.get("_partitioning")
    if part and (part.get("strategy") or "NONE") in ("RANGE", "LIST", "HASH"):
        strategy = part["strategy"]
        cols_part = ", ".join(part.get("columns") or [])
        if cols_part:
            if strategy == "HASH":
                n = part.get("num_partitions") or 4
                close_line += f"\nPARTITION BY HASH ({cols_part}) PARTITIONS {n}"
            else:
                close_line += f"\nPARTITION BY {strategy} ({cols_part})"
    out.append(f"{close_line};")
    out.extend(_render_indexes_mysql(table, entity.get("_indexes") or []))
    return "\n".join(out)


def gen_sparksql(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """Spark SQL / Delta Lake (Databricks default).

    Uses STRING-typed columns and supports inline COMMENT plus per-table
    COMMENT clause. Emits USING DELTA.
    """
    table = _table_ref(entity, opts)
    out: list[str] = []
    out.append(_drop_stmt(table, opts) + f"CREATE TABLE {table} (")
    cols = _build_columns_block(
        attrs, "SPARKSQL", inline_column_comments=opts.include_comments
    )
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  CONSTRAINT pk_{entity.get('technical_name', 'tbl')} "
                    f"PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    suffix = ") USING DELTA"
    if opts.include_comments:
        tcomment = _entity_comment(entity)
        if tcomment:
            suffix += f"\nCOMMENT '{_esc(tcomment)}'"
    suffix += _spark_partition_clause(entity.get("_partitioning"))
    out.append(f"{suffix};")
    liquid = _spark_liquid_cluster(table, entity.get("_partitioning"))
    if liquid:
        out.append(liquid)
    # Delta/Spark não suporta CREATE INDEX no DDL padrão (índices secundários
    # se dão por liquid clustering ou Z-ORDER). Se forem definidos no app,
    # emite Z-ORDER OPTIMIZE como statement separado quando index_type=Z-ORDER.
    for ix in entity.get("_indexes") or []:
        if (ix.get("index_type") or "").upper() == "Z-ORDER":
            cols_z = _idx_cols_sql(ix).replace(" DESC", "")
            if cols_z:
                out.append(f"OPTIMIZE {table} ZORDER BY ({cols_z});")
    return "\n".join(out)


def gen_db2(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    """IBM Db2 (LUW / Db2 for i).

    Tipos DB2 (INTEGER/BIGINT/SMALLINT/DECIMAL/VARCHAR/CLOB/TIMESTAMP…) via
    map_type. Usa a sintaxe padrão `COMMENT ON TABLE/COLUMN … IS …` (igual a
    Oracle/Postgres) e `CREATE [UNIQUE] INDEX`. DROP é best-effort (DB2 não tem
    DROP IF EXISTS universal — reusa o _drop_stmt padrão do app).
    """
    table = _table_ref(entity, opts)
    out: list[str] = []
    out.append(_drop_stmt(table, opts) + f"CREATE TABLE {table} (")
    cols = _build_columns_block(attrs, "DB2", inline_column_comments=False)
    pk = _collect_pk(attrs)
    body = list(cols)
    if pk:
        body.append(f"  PRIMARY KEY ({', '.join(pk)})")
    out.append(",\n".join(body))
    # DB2 particiona por RANGE (sintaxe próxima da do Oracle p/ export best-effort).
    part_clause = _partition_clause_oracle(entity.get("_partitioning"))
    out.append(f"){part_clause};")

    if opts.include_comments:
        tcomment = _entity_comment(entity)
        if tcomment:
            out.append(f"COMMENT ON TABLE {table} IS '{_esc(tcomment)}';")
        for a in attrs:
            c = _attr_comment(a)
            if c:
                out.append(
                    f"COMMENT ON COLUMN {table}.{a['technical_name']} IS '{_esc(c)}';"
                )

    # CREATE [UNIQUE] INDEX — sintaxe padrão, compatível com DB2.
    out.extend(_render_indexes_oracle(table, entity.get("_indexes") or []))
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Foreign keys (round 5, pt 11)
# ──────────────────────────────────────────────────────────────────────────────


def render_foreign_keys(
    fks: list[dict[str, Any]], opts: DDLExportRequest
) -> list[str]:
    """Emite ``ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY … REFERENCES …``.

    Antes o export não gerava NENHUMA FK (round 5, pt 11). As FKs são emitidas
    como ALTER TABLE DEPOIS de todos os CREATE TABLE — assim não dependem da ordem
    de criação das tabelas e a mesma sintaxe vale em todos os dialetos.

    Cada `fk` já vem resolvido pelo service (ids → nomes): ``name``, ``child_ref``,
    ``parent_ref``, ``child_cols`` (colunas FK no filho), ``parent_cols`` (PK no pai),
    ``on_update``, ``on_delete``.
    """
    out: list[str] = []
    for fk in fks:
        child_cols = ", ".join(fk["child_cols"])
        parent_cols = ", ".join(fk["parent_cols"])
        stmt = (
            f"ALTER TABLE {fk['child_ref']} ADD CONSTRAINT {fk['name']}\n"
            f"  FOREIGN KEY ({child_cols}) REFERENCES {fk['parent_ref']} ({parent_cols})"
        )
        # Databricks/Spark: a FK é apenas INFORMATIVA (não forçada) e não aceita
        # ações ON DELETE/UPDATE — omitimos essas cláusulas nesse dialeto.
        if opts.dialect != "SPARKSQL":
            if fk.get("on_delete"):
                stmt += f"\n  ON DELETE {fk['on_delete']}"
            if fk.get("on_update"):
                stmt += f"\n  ON UPDATE {fk['on_update']}"
        out.append(stmt + ";")
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────


GeneratorFn = Callable[[dict[str, Any], list[dict[str, Any]], DDLExportRequest], str]

GENERATORS: dict[DDLDialect, GeneratorFn] = {
    "ANSI": gen_ansi,
    "TSQL": gen_tsql,
    "PLSQL": gen_plsql,
    "POSTGRES": gen_postgres,
    "MYSQL": gen_mysql,
    "SPARKSQL": gen_sparksql,
    "DB2": gen_db2,
}


DIALECT_LABELS: dict[DDLDialect, tuple[str, str]] = {
    "ANSI": ("ANSI SQL", "SQL padrão (SQL:2016)"),
    "TSQL": ("T-SQL", "SQL Server / Azure SQL"),
    "PLSQL": ("PL/SQL", "Oracle Database"),
    "POSTGRES": ("PostgreSQL", "PostgreSQL 12+"),
    "MYSQL": ("MySQL", "MySQL / MariaDB"),
    "SPARKSQL": ("Spark SQL / Delta", "Databricks (padrão)"),
    "DB2": ("DB2", "IBM Db2 (LUW / Db2 for i)"),
}
