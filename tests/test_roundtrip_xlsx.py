"""Round 6 — pt 22: import/export de metadados no formato .xlsx do Embarcadero
+ CLASSIFICACAO→flag LGPD. Validado com o arquivo REAL do cliente
(`tests/fixtures/round6/descricoes_embarcadero.xlsx`).

O staging editorial completo (parse_and_stage_*) depende do catálogo/DB, então
aqui cobrimos as partes puras/determinísticas em CI:
- `_split_classificacao`: separa o token `| CLASSIFICACAO=LGPD_*` → flag_key.
- `_read_xlsx_rows`: lê o layout Embarcadero (table/table_description/column/
  column_description) — inclusive o arquivo real do cliente.
- round-trip de escrita/leitura via openpyxl (formato do export).
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("openpyxl")

from nuclea_modeler.backend.entities import roundtrip as rt  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "round6"


# ─── _split_classificacao ─────────────────────────────────────────────────────


def test_split_classificacao_maps_and_strips():
    clean, flag = rt._split_classificacao("Nome completo da pessoa | CLASSIFICACAO=LGPD_IDENTIFICAVEL")
    assert clean == "Nome completo da pessoa"
    assert flag == "titular-identificado"

    clean, flag = rt._split_classificacao("Sexo | CLASSIFICACAO=LGPD_SENSIVEL")
    assert clean == "Sexo" and flag == "dados-sensiveis"

    clean, flag = rt._split_classificacao("Renda | CLASSIFICACAO=LGPD_PESSOAL")
    assert clean == "Renda" and flag == "dados-pessoais"


def test_split_classificacao_no_token_or_unknown():
    assert rt._split_classificacao("Só uma descrição") == ("Só uma descrição", None)
    # token desconhecido: NÃO mexe na descrição e não flageia
    assert rt._split_classificacao("X | CLASSIFICACAO=FOO") == ("X | CLASSIFICACAO=FOO", None)
    assert rt._split_classificacao(None) == (None, None)


# ─── leitura do .xlsx Embarcadero ─────────────────────────────────────────────


def test_read_xlsx_client_file():
    """O arquivo REAL do cliente é lido no layout esperado."""
    data = (FIXTURES / "descricoes_embarcadero.xlsx").read_bytes()
    rows = rt._read_xlsx_rows(data)
    assert len(rows) >= 10
    # cada linha tem as 4 chaves
    assert all({"table", "table_description", "column", "column_description"} <= set(r) for r in rows)
    # a coluna pessoa.nome_completo traz a classificação embutida
    pessoa_nome = next(
        r for r in rows if r["table"] == "pessoa" and r["column"] == "nome_completo"
    )
    assert "CLASSIFICACAO=LGPD_IDENTIFICAVEL" in (pessoa_nome["column_description"] or "")
    # e o _split extrai a flag certa dessa descrição
    _clean, flag = rt._split_classificacao(pessoa_nome["column_description"])
    assert flag == "titular-identificado"


def test_read_xlsx_roundtrip_write_then_read():
    """O que o export escreve, o import lê (formato consistente)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["table", "table_description", "column", "column_description"])
    ws.append(["conta", "Contas", "saldo", "Saldo atual | CLASSIFICACAO=LGPD_PESSOAL"])
    buf = io.BytesIO()
    wb.save(buf)
    rows = rt._read_xlsx_rows(buf.getvalue())
    assert rows == [{
        "table": "conta", "table_description": "Contas",
        "column": "saldo", "column_description": "Saldo atual | CLASSIFICACAO=LGPD_PESSOAL",
    }]


def test_read_xlsx_empty():
    from openpyxl import Workbook
    buf = io.BytesIO()
    Workbook().save(buf)  # só o header default vazio
    # sem header reconhecido → lista vazia ou linhas sem as chaves; não deve estourar
    rows = rt._read_xlsx_rows(buf.getvalue())
    assert isinstance(rows, list)
