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
