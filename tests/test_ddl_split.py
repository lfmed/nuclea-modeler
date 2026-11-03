"""Divisão de script DDL + pré-filtro + constraints de ALTER TABLE (rodada 9, item 10).

Lógica PURA (`extractions/ddl_split.py`, sem sqlglot). Contexto: o import de DDL
"falhava com script extenso". Reproduzido contra o app deployado: uma instrução que
o sqlglot não entende fazia o import cair num split por `;` CRU, que picotava
strings, corpos `$$` e gerava milhares de erros; e `ALTER TABLE … ADD CONSTRAINT`
(formato do pg_dump) era ignorado. Estes testes fixam o comportamento novo.
"""
from __future__ import annotations

from nuclea_modeler.backend.extractions import ddl_split as ds


def _texts(sql: str) -> list[str]:
    return [s.text for s in ds.split_sql_statements(sql)]


# ─── split_sql_statements ────────────────────────────────────────────────────

def test_ponto_e_virgula_dentro_de_string_nao_divide():
    out = _texts("COMMENT ON TABLE a IS 'x; y';\nCREATE TABLE b (s varchar(5) DEFAULT ';');")
    assert out == ["COMMENT ON TABLE a IS 'x; y';", "CREATE TABLE b (s varchar(5) DEFAULT ';');"]


def test_aspas_escapadas_e_identificador_delimitado():
    out = _texts("""COMMENT ON TABLE a IS 'it''s; ok';\nCREATE TABLE "a;b" (id int);""")
    assert len(out) == 2 and out[1].startswith('CREATE TABLE "a;b"')


def test_corpo_dollar_quoted_fica_inteiro():
    sql = (
        "CREATE FUNCTION f() RETURNS void AS $body$\nBEGIN\n  UPDATE a SET x = 1;\nEND;\n$body$ LANGUAGE plpgsql;\n"
        "CREATE TABLE a (x int);"
    )
    out = _texts(sql)
    assert len(out) == 2
    assert out[0].endswith("LANGUAGE plpgsql;")


def test_comentarios_nao_dividem():
    out = _texts("-- a; b\n/* c; d */\nCREATE TABLE a (x int);")
    assert len(out) == 1 and "CREATE TABLE a" in out[0]


def test_barra_do_sqlplus_e_go_do_tsql():
    sql = (
        "CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n  UPDATE t SET a = 1;\n  COMMIT;\nEND;\n/\n"
        "CREATE TABLE t2 (id NUMBER)\n/\n"
        "CREATE TABLE t3 (id int)\nGO\n"
    )
    out = _texts(sql)
    assert len(out) == 3
    assert out[0].startswith("CREATE OR REPLACE PROCEDURE p") and "COMMIT;" in out[0]
    assert out[1] == "CREATE TABLE t2 (id NUMBER)"
    assert out[2] == "CREATE TABLE t3 (id int)"


def test_meta_comando_psql_termina_no_fim_da_linha():
    out = _texts("-- dump\n\\connect c3l\nCREATE TABLE a (id int);\n")
    assert "\\connect c3l" in out
    assert "CREATE TABLE a (id int);" in out


def test_numero_da_linha_de_cada_instrucao():
    st = ds.split_sql_statements("\n\nCREATE TABLE a (x int);\n\n-- c\nCREATE TABLE b (\n x int\n);")
    assert [s.line for s in st] == [3, 5]


# ─── filter_relevant ─────────────────────────────────────────────────────────

def test_pre_filtro_mantem_so_o_que_o_import_usa():
    sql = """\\connect c3l
SET statement_timeout = 0;
SET search_path TO c3l;
CREATE TABLESPACE ts LOCATION '/x';
CREATE TABLE IF NOT EXISTS a (id int);
CREATE OR REPLACE VIEW v AS SELECT 1;
CREATE UNIQUE INDEX ix ON a (id);
COMMENT ON COLUMN a.id IS 'id';
ALTER TABLE ONLY a ADD CONSTRAINT a_pkey PRIMARY KEY (id);
CREATE SEQUENCE s;
CREATE OR REPLACE FUNCTION f() RETURNS TABLE (x int) AS $$ SELECT 1 $$ LANGUAGE sql;
CREATE TYPE t AS TABLE OF NUMBER;
INSERT INTO a VALUES (1);
INSERT INTO a VALUES (2);
GRANT SELECT ON a TO bi;
"""
    fr = ds.filter_relevant(ds.split_sql_statements(sql))
    kept = [k.text.split()[0:2] for k in fr.keep]
    assert kept == [
        ["SET", "search_path"], ["CREATE", "TABLE"], ["CREATE", "OR"], ["CREATE", "UNIQUE"],
        ["COMMENT", "ON"], ["ALTER", "TABLE"],
    ]
    assert fr.skipped["INSERT"] == 2
    assert fr.skipped["meta-comando psql"] == 1
    assert "2 INSERT" in fr.skipped_summary()


def test_cabecalho_sem_comentarios_vai_para_o_parser():
    fr = ds.filter_relevant(ds.split_sql_statements("-- nota\n/* bloco */\nCREATE TABLE a (x int);"))
    assert fr.keep[0].text.startswith("CREATE TABLE a")


# ─── parse_alter_constraints ─────────────────────────────────────────────────

def test_alter_pk_pg_dump():
    ac = ds.parse_alter_constraints("ALTER TABLE ONLY c3l.pedido\n    ADD CONSTRAINT pedido_pkey PRIMARY KEY (id, versao);")
    assert (ac.schema, ac.table, ac.pk_cols, ac.fks) == ("c3l", "pedido", ["id", "versao"], [])


def test_alter_fk_com_schema_e_colunas():
    ac = ds.parse_alter_constraints(
        "ALTER TABLE ONLY c3l.item ADD CONSTRAINT fk_item FOREIGN KEY (pedido_id) "
        "REFERENCES c3l.pedido(id) ON DELETE CASCADE;"
    )
    assert ac.fks == [(["pedido_id"], "c3l", "pedido", ["id"])]


def test_alter_tsql_e_mysql():
    ts = ds.parse_alter_constraints("ALTER TABLE [dbo].[T] ADD CONSTRAINT [PK_T] PRIMARY KEY CLUSTERED ([ID] ASC)")
    assert (ts.schema, ts.table, ts.pk_cols) == ("dbo", "T", ["ID"])
    my = ds.parse_alter_constraints(
        "ALTER TABLE `x` ADD CONSTRAINT `fk1` FOREIGN KEY (`a`) REFERENCES `y` (`id`), ADD PRIMARY KEY (`a`)"
    )
    assert my.pk_cols == ["a"] and my.fks == [(["a"], None, "y", ["id"])]


def test_alter_sem_pk_fk_e_ignorado():
    assert ds.parse_alter_constraints("ALTER TABLE a OWNER TO app;") is None
    assert ds.parse_alter_constraints("ALTER TABLE a ADD COLUMN b int;") is None
    assert ds.parse_alter_constraints("CREATE TABLE a (x int);") is None
