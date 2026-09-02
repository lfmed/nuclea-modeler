"""Round 6 follow-up (pt 15) — extração de COMMENT ON por REGEX do DDL cru.

Contexto: na validação AO VIVO, o `COMMENT ON TABLE` do cliente NÃO era capturado
(descrição da tabela ficava vazia), embora o teste de CID do snapshot passasse — o
sqlglot instalado no deploy não modela `COMMENT ON TABLE` como `exp.Comment` no AST
(só a de COLUMN). O regex `_regex_comment_ons` roda como baseline version-agnostic,
garantindo TABLE e COLUMN direto do texto. Validado com o arquivo REAL do cliente.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sqlglot")  # o módulo importa sqlglot no topo

from nuclea_modeler.backend.extractions.service import _regex_comment_ons  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "round6"


def test_regex_captures_table_and_column_comments():
    ddl = """
    CREATE TABLE pessoa (id INT, cpf VARCHAR(11));
    COMMENT ON TABLE pessoa IS
    'Cadastro de pessoas';
    COMMENT ON COLUMN pessoa.cpf IS 'CPF | CLASSIFICACAO=LGPD_IDENTIFICAVEL';
    """
    tbl, col = _regex_comment_ons(ddl)
    assert tbl[("public", "pessoa")] == "Cadastro de pessoas"  # multiline IS
    assert col[("public", "pessoa", "cpf")] == "CPF | CLASSIFICACAO=LGPD_IDENTIFICAVEL"


def test_regex_schema_qualified_and_escaping():
    ddl = "COMMENT ON TABLE social.pessoa IS 'd''Ávila';\nCOMMENT ON COLUMN social.pessoa.nome IS 'x';"
    tbl, col = _regex_comment_ons(ddl)
    assert tbl[("social", "pessoa")] == "d'Ávila"  # '' desescapado
    assert col[("social", "pessoa", "nome")] == "x"


def test_regex_on_client_file_captures_all_tables():
    """Arquivo REAL do cliente: as 10 tabelas têm COMMENT ON TABLE capturado."""
    ddl = (FIXTURES / "programa_social.sql").read_text(encoding="utf-8")
    tbl, col = _regex_comment_ons(ddl)
    names = {t for (_s, t) in tbl}
    assert {"pessoa", "endereco", "escolaridade", "formacao", "profissao"} <= names
    assert len(tbl) >= 10  # todas as tabelas do arquivo
    assert col[("public", "pessoa", "nome_completo")].startswith("Nome completo da pessoa")


def test_regex_empty_when_no_comments():
    tbl, col = _regex_comment_ons("CREATE TABLE t (id INT);")
    assert tbl == {} and col == {}
