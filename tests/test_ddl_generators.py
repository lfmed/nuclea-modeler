"""Golden-file tests for the multi-dialect DDL generators (Module 10).

Goal: detect regressions in the 6 dialect generators. Each test asserts the
*structural invariants* of the output (CREATE TABLE present, type mapped,
PK rendered, comments rendered/omitted as per options) rather than full
byte-for-byte equality — this keeps tests resilient to harmless formatting
tweaks while still catching real bugs (wrong type mapping, missing PK,
unescaped quotes).
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.ddl.generators import GENERATORS, map_type
from nuclea_modeler.backend.ddl.models import DDLExportRequest


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def cliente_entity() -> dict:
    return {
        "schema_name": "comum",
        "technical_name": "cliente",
        "entity_type": "TABLE",
        "description_md": "Cadastro de clientes da Núclea — fonte do CRM",
        "native_comment": None,
    }


@pytest.fixture
def cliente_attrs() -> list[dict]:
    return [
        {
            "technical_name": "id_cliente",
            "ordinal_position": 1,
            "native_data_type": "bigint",
            "is_primary_key": True,
            "is_nullable": False,
            "default_value": None,
            "description_md": "Identificador único do cliente",
            "native_comment": None,
        },
        {
            "technical_name": "nome",
            "ordinal_position": 2,
            "native_data_type": "varchar(120)",
            "is_primary_key": False,
            "is_nullable": False,
            "default_value": None,
            "description_md": "Nome completo (com apóstrofo: O'Hara)",
            "native_comment": None,
        },
        {
            "technical_name": "valor_credito",
            "ordinal_position": 3,
            "native_data_type": "decimal(18,4)",
            "is_primary_key": False,
            "is_nullable": True,
            "default_value": "0",
            "description_md": None,
            "native_comment": "Crédito pré-aprovado em BRL",
        },
        {
            "technical_name": "criado_em",
            "ordinal_position": 4,
            "native_data_type": "timestamp",
            "is_primary_key": False,
            "is_nullable": False,
            "default_value": None,
            "description_md": None,
            "native_comment": None,
        },
    ]


@pytest.fixture
def default_opts() -> DDLExportRequest:
    return DDLExportRequest(system_id="sys-test", dialect="SPARKSQL")


# ─── Type mapping ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "native,dialect,expected_substr",
    [
        ("varchar(120)", "TSQL", "NVARCHAR(120)"),
        ("varchar(120)", "PLSQL", "VARCHAR2(120)"),
        ("varchar(120)", "POSTGRES", "VARCHAR(120)"),
        ("varchar(120)", "MYSQL", "VARCHAR(120)"),
        ("varchar(120)", "SPARKSQL", "STRING"),
        ("varchar(120)", "ANSI", "VARCHAR(120)"),
        ("decimal(18,4)", "TSQL", "DECIMAL(18,4)"),
        ("decimal(18,4)", "PLSQL", "NUMBER(18,4)"),
        ("decimal(18,4)", "POSTGRES", "NUMERIC(18,4)"),
        ("bigint", "PLSQL", "NUMBER(19)"),
        ("bigint", "POSTGRES", "BIGINT"),
        ("int", "PLSQL", "NUMBER(10)"),
        ("timestamp", "TSQL", "DATETIME2"),
        ("timestamp", "MYSQL", "DATETIME"),
        ("boolean", "TSQL", "BIT"),
        ("boolean", "MYSQL", "TINYINT(1)"),
        ("text", "TSQL", "NVARCHAR(MAX)"),
        ("text", "PLSQL", "CLOB"),
        ("date", "PLSQL", "DATE"),
    ],
)
def test_map_type(native, dialect, expected_substr):
    assert map_type(native, dialect) == expected_substr


def test_map_type_unknown_passes_through():
    assert map_type("geography", "TSQL") == "GEOGRAPHY"
    assert map_type("interval(3)", "POSTGRES") == "INTERVAL(3)"


def test_map_type_none_defaults_to_varchar():
    assert "VARCHAR" in map_type(None, "POSTGRES")


# ─── Per-dialect generator: structural invariants ───────────────────────────


@pytest.mark.parametrize(
    "dialect",
    ["ANSI", "TSQL", "PLSQL", "POSTGRES", "MYSQL", "SPARKSQL"],
)
def test_generator_emits_create_table(dialect, cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = dialect
    ddl = GENERATORS[dialect](cliente_entity, cliente_attrs, default_opts)
    assert "CREATE TABLE" in ddl
    assert "comum.cliente" in ddl
    for attr in cliente_attrs:
        assert attr["technical_name"] in ddl


@pytest.mark.parametrize(
    "dialect", ["ANSI", "TSQL", "PLSQL", "POSTGRES", "MYSQL", "SPARKSQL"]
)
def test_generator_renders_primary_key(dialect, cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = dialect
    ddl = GENERATORS[dialect](cliente_entity, cliente_attrs, default_opts)
    assert "PRIMARY KEY" in ddl
    assert "id_cliente" in ddl


@pytest.mark.parametrize(
    "dialect", ["ANSI", "TSQL", "PLSQL", "POSTGRES", "MYSQL", "SPARKSQL"]
)
def test_generator_marks_not_null_for_pk(dialect, cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = dialect
    ddl = GENERATORS[dialect](cliente_entity, cliente_attrs, default_opts)
    pk_line = next(line for line in ddl.splitlines() if "id_cliente" in line and "PRIMARY KEY" not in line)
    assert "NOT NULL" in pk_line


def test_sparksql_emits_using_delta(cliente_entity, cliente_attrs, default_opts):
    ddl = GENERATORS["SPARKSQL"](cliente_entity, cliente_attrs, default_opts)
    assert "USING DELTA" in ddl


def test_sparksql_named_pk_constraint(cliente_entity, cliente_attrs, default_opts):
    ddl = GENERATORS["SPARKSQL"](cliente_entity, cliente_attrs, default_opts)
    assert "CONSTRAINT pk_cliente" in ddl


def test_plsql_emits_comment_on(cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = "PLSQL"
    ddl = GENERATORS["PLSQL"](cliente_entity, cliente_attrs, default_opts)
    assert "COMMENT ON TABLE comum.cliente" in ddl
    assert "COMMENT ON COLUMN comum.cliente.id_cliente" in ddl


def test_postgres_emits_comment_on(cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, default_opts)
    assert "COMMENT ON TABLE comum.cliente" in ddl


def test_mysql_inline_table_comment(cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = "MYSQL"
    ddl = GENERATORS["MYSQL"](cliente_entity, cliente_attrs, default_opts)
    assert "COMMENT=" in ddl
    # inline column comment for valor_credito
    assert "Crédito pré-aprovado" in ddl


def test_sparksql_inline_table_comment(cliente_entity, cliente_attrs, default_opts):
    ddl = GENERATORS["SPARKSQL"](cliente_entity, cliente_attrs, default_opts)
    assert "COMMENT 'Cadastro de clientes" in ddl


# ─── Edge cases: escaping, options, defaults ─────────────────────────────────


def test_single_quote_in_comment_is_escaped_postgres(cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, default_opts)
    # The "O'Hara" comment should appear with '' escaping, never as a raw '
    assert "O''Hara" in ddl
    # Sanity: no orphan single quotes that would break the SQL
    assert "O'Hara'" not in ddl.replace("O''Hara", "")


def test_default_value_rendered(cliente_entity, cliente_attrs, default_opts):
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, default_opts)
    assert "DEFAULT 0" in ddl


def test_include_comments_false_omits_entity_comment(cliente_entity, cliente_attrs):
    opts = DDLExportRequest(
        system_id="sys", dialect="POSTGRES", include_comments=False
    )
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, opts)
    assert "COMMENT ON TABLE" not in ddl


def test_drop_if_exists_postgres(cliente_entity, cliente_attrs):
    opts = DDLExportRequest(
        system_id="sys", dialect="POSTGRES", include_drop_if_exists=True
    )
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, opts)
    assert "DROP TABLE IF EXISTS" in ddl


def test_drop_if_exists_plsql_uses_exception_block(cliente_entity, cliente_attrs):
    opts = DDLExportRequest(
        system_id="sys", dialect="PLSQL", include_drop_if_exists=True
    )
    ddl = GENERATORS["PLSQL"](cliente_entity, cliente_attrs, opts)
    # Oracle: no DROP IF EXISTS — must be wrapped in PL/SQL EXCEPTION
    assert "EXECUTE IMMEDIATE 'DROP TABLE" in ddl
    assert "EXCEPTION WHEN OTHERS" in ddl


def test_drop_if_exists_tsql_uses_object_id(cliente_entity, cliente_attrs):
    opts = DDLExportRequest(
        system_id="sys", dialect="TSQL", include_drop_if_exists=True
    )
    ddl = GENERATORS["TSQL"](cliente_entity, cliente_attrs, opts)
    assert "OBJECT_ID" in ddl
    assert "DROP TABLE" in ddl


def test_qualify_schema_false_strips_schema(cliente_entity, cliente_attrs):
    opts = DDLExportRequest(
        system_id="sys", dialect="POSTGRES", qualify_schema=False
    )
    ddl = GENERATORS["POSTGRES"](cliente_entity, cliente_attrs, opts)
    assert "CREATE TABLE cliente" in ddl
    assert "comum.cliente" not in ddl


def test_no_pk_when_no_attr_is_pk(cliente_entity, default_opts):
    attrs = [
        {
            "technical_name": "anything",
            "ordinal_position": 1,
            "native_data_type": "varchar(10)",
            "is_primary_key": False,
            "is_nullable": True,
            "default_value": None,
        }
    ]
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](cliente_entity, attrs, default_opts)
    assert "PRIMARY KEY" not in ddl


# ─── Indexes + partitioning (F4) ─────────────────────────────────────────────


def _entity_with_index(base: dict, ix: dict | None = None, part: dict | None = None) -> dict:
    return {
        **base,
        "_indexes": [ix] if ix else [],
        "_partitioning": part,
    }


def test_postgres_emits_create_index_with_direction(cliente_entity, cliente_attrs, default_opts):
    ix = {
        "index_name": "ix_email_data",
        "index_type": "BTREE",
        "columns": [{"name": "email", "direction": "ASC"}, {"name": "criado_em", "direction": "DESC"}],
        "include_columns": [],
        "partial_where": None,
        "is_unique": False,
    }
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](_entity_with_index(cliente_entity, ix), cliente_attrs, default_opts)
    assert "CREATE INDEX ix_email_data" in ddl
    assert "(email, criado_em DESC)" in ddl


def test_postgres_emits_gin_with_partial_where(cliente_entity, cliente_attrs, default_opts):
    ix = {
        "index_name": "ix_doc",
        "index_type": "GIN",
        "columns": [{"name": "documento", "direction": "ASC"}],
        "include_columns": [],
        "partial_where": "ativo = TRUE",
        "is_unique": False,
    }
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](_entity_with_index(cliente_entity, ix), cliente_attrs, default_opts)
    assert "USING GIN (documento)" in ddl
    assert "WHERE ativo = TRUE" in ddl


def test_postgres_partition_by_range(cliente_entity, cliente_attrs, default_opts):
    part = {"strategy": "RANGE", "columns": ["criado_em"], "num_partitions": None, "bounds": None}
    default_opts.dialect = "POSTGRES"
    ddl = GENERATORS["POSTGRES"](_entity_with_index(cliente_entity, None, part), cliente_attrs, default_opts)
    assert "PARTITION BY RANGE (criado_em)" in ddl


def test_tsql_emits_clustered_with_include(cliente_entity, cliente_attrs, default_opts):
    ix = {
        "index_name": "ix_pk_cluster",
        "index_type": "CLUSTERED",
        "columns": [{"name": "email", "direction": "ASC"}],
        "include_columns": ["nome", "criado_em"],
        "partial_where": None,
        "is_unique": True,
    }
    default_opts.dialect = "TSQL"
    ddl = GENERATORS["TSQL"](_entity_with_index(cliente_entity, ix), cliente_attrs, default_opts)
    assert "UNIQUE CLUSTERED INDEX ix_pk_cluster" in ddl
    assert "INCLUDE (nome, criado_em)" in ddl


def test_sparksql_liquid_emits_alter_cluster_by(cliente_entity, cliente_attrs, default_opts):
    part = {"strategy": "LIQUID", "columns": ["email", "criado_em"], "num_partitions": None, "bounds": None}
    default_opts.dialect = "SPARKSQL"
    ddl = GENERATORS["SPARKSQL"](_entity_with_index(cliente_entity, None, part), cliente_attrs, default_opts)
    assert "USING DELTA" in ddl
    assert "ALTER TABLE" in ddl
    assert "CLUSTER BY (email, criado_em)" in ddl


def test_sparksql_zorder_index_emits_optimize(cliente_entity, cliente_attrs, default_opts):
    ix = {
        "index_name": "z_idx",
        "index_type": "Z-ORDER",
        "columns": [{"name": "email", "direction": "ASC"}, {"name": "criado_em", "direction": "ASC"}],
        "include_columns": [],
        "partial_where": None,
        "is_unique": False,
    }
    default_opts.dialect = "SPARKSQL"
    ddl = GENERATORS["SPARKSQL"](_entity_with_index(cliente_entity, ix), cliente_attrs, default_opts)
    assert "OPTIMIZE" in ddl and "ZORDER BY (email, criado_em)" in ddl


def test_oracle_emits_bitmap_index(cliente_entity, cliente_attrs, default_opts):
    ix = {
        "index_name": "bm_status",
        "index_type": "BITMAP",
        "columns": [{"name": "status", "direction": "ASC"}],
        "include_columns": [],
        "partial_where": None,
        "is_unique": False,
    }
    default_opts.dialect = "PLSQL"
    ddl = GENERATORS["PLSQL"](_entity_with_index(cliente_entity, ix), cliente_attrs, default_opts)
    assert "CREATE BITMAP INDEX bm_status" in ddl


def test_mysql_partition_by_hash(cliente_entity, cliente_attrs, default_opts):
    part = {"strategy": "HASH", "columns": ["id"], "num_partitions": 8, "bounds": None}
    default_opts.dialect = "MYSQL"
    ddl = GENERATORS["MYSQL"](_entity_with_index(cliente_entity, None, part), cliente_attrs, default_opts)
    assert "PARTITION BY HASH (id) PARTITIONS 8" in ddl
