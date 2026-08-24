"""Auto-detecção de dialeto DB2 no import DDL (v1.0034).

`_detect_dialect_from_content` recupera o dialeto pelo conteúdo do DDL quando o
front manda vazio/ANSI. Este teste fixa que construtos exclusivos do IBM Db2
(DECFLOAT, VARGRAPHIC/GRAPHIC/DBCLOB, SYSIBM/SYSCAT, NEXTVAL FOR) são detectados
como "db2" — e que DDL de outros dialetos não é classificado como db2 por engano.

Nota: "GENERATED … AS IDENTITY" NÃO é marcador DB2 aqui — a palavra IDENTITY
colide com a heurística T-SQL (checada antes), que venceria.
"""
from __future__ import annotations

from nuclea_modeler.backend.extractions.service import _detect_dialect_from_content


def test_detects_decfloat():
    ddl = "CREATE TABLE t (saldo DECFLOAT(34), id INTEGER NOT NULL);"
    assert _detect_dialect_from_content(ddl) == "db2"


def test_detects_vargraphic_and_dbclob():
    ddl = "CREATE TABLE t (nome VARGRAPHIC(50), doc DBCLOB(1M));"
    assert _detect_dialect_from_content(ddl) == "db2"


def test_detects_nextval_for():
    ddl = "INSERT INTO t (id) VALUES (NEXTVAL FOR seq_t);"
    assert _detect_dialect_from_content(ddl) == "db2"


def test_detects_sysibm_reference():
    ddl = "SELECT * FROM SYSIBM.SYSTABLES;"
    assert _detect_dialect_from_content(ddl) == "db2"


def test_postgres_ddl_not_misdetected_as_db2():
    # SERIAL é exclusivo Postgres — deve vencer antes de qualquer heurística DB2.
    ddl = "CREATE TABLE t (id SERIAL PRIMARY KEY, nome TEXT);"
    assert _detect_dialect_from_content(ddl) == "postgres"


def test_plain_ansi_returns_none():
    ddl = "CREATE TABLE t (id INTEGER PRIMARY KEY, nome VARCHAR(50));"
    assert _detect_dialect_from_content(ddl) is None
