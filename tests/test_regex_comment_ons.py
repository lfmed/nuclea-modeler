"""Round 6 follow-up (pt 15) — extração de COMMENT ON por REGEX do DDL cru.

Contexto: na validação AO VIVO, o `COMMENT ON TABLE` do cliente NÃO era capturado
(descrição da tabela ficava vazia), embora o teste de CID do snapshot passasse — o
sqlglot instalado no deploy não modela `COMMENT ON TABLE` como `exp.Comment` no AST
(só a de COLUMN). O regex `_regex_comment_ons` roda como baseline version-agnostic,
garantindo TABLE e COLUMN direto do texto. Validado com o arquivo REAL do cliente.
"""
from __future__ import annotations

from pathlib import Path

# NB: `_regex_comment_ons` é python puro (regex) — o sqlglot é importado só DENTRO
# de funções em extractions/service.py, então NÃO precisamos de importorskip aqui
# (o próprio ponto deste path é funcionar mesmo onde o sqlglot não é confiável).
from nuclea_modeler.backend.extractions.service import _regex_comment_ons

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


# ─── robustez (achados do /review) ────────────────────────────────────────────


def test_regex_ignores_commented_out_comment_on():
    """`-- COMMENT ON TABLE …` (linha comentada) e bloco `/* … */` NÃO viram descrição."""
    tbl, _ = _regex_comment_ons("-- COMMENT ON TABLE x IS 'velho';\nCREATE TABLE x (id INT);")
    assert tbl == {}
    tbl2, _ = _regex_comment_ons("/* COMMENT ON TABLE y IS 'z' */\n")
    assert tbl2 == {}


def test_regex_preserves_double_dash_inside_string():
    """Um `--` DENTRO da string de descrição não pode ser truncado (só strip de
    linha-inteira de comentário)."""
    tbl, _ = _regex_comment_ons("COMMENT ON TABLE x IS 'antes -- depois';")
    assert tbl[("public", "x")] == "antes -- depois"


def test_regex_three_part_and_quoted_names():
    ddl = 'COMMENT ON TABLE cat.social.pessoa IS \'t\';\nCOMMENT ON COLUMN cat.social.pessoa.nome IS \'c\';'
    tbl, col = _regex_comment_ons(ddl)
    assert tbl[("social", "pessoa")] == "t"          # 3 partes → schema=social
    assert col[("social", "pessoa", "nome")] == "c"  # 4 partes → schema=social
