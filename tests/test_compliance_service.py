"""Testes da lógica pura do calendário de conformidade (v1.0063, rodada 8 item 3).

Cobre o que o CLAUDE.md exige (o CI é o loop de validação): datas (normalize/
advance com clamp de mês), aliases de periodicidade, due_fields e o round-trip do
parse da planilha (CSV vírgula/ponto-e-vírgula + XLSX real + cabeçalho inválido).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from nuclea_modeler.backend.compliance import service


# ─── normalize_date ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-01-15", "2026-01-15"),
        ("15/01/2026", "2026-01-15"),
        ("15-01-2026", "2026-01-15"),
        ("01/02/26", "2026-02-01"),   # ano 2 dígitos
        ("2026-01-15T09:30:00", "2026-01-15"),  # ISO com hora
        ("", None),
        (None, None),
        ("xx/yy/zzzz", None),
        ("2026-13-40", None),         # data impossível
    ],
)
def test_normalize_date(raw, expected):
    assert service.normalize_date(raw) == expected


def test_normalize_date_accepts_datetime_object():
    assert service.normalize_date(datetime(2026, 3, 9, 12, 0)) == "2026-03-09"
    assert service.normalize_date(date(2026, 3, 9)) == "2026-03-09"


# ─── advance_iso (soma de meses com clamp de dia) ────────────────────────────

@pytest.mark.parametrize(
    "iso,recurrence,expected",
    [
        ("2026-01-15", "MONTHLY", "2026-02-15"),
        ("2026-01-15", "QUARTERLY", "2026-04-15"),
        ("2026-01-15", "SEMIANNUAL", "2026-07-15"),
        ("2026-01-15", "ANNUAL", "2027-01-15"),
        ("2026-01-31", "MONTHLY", "2026-02-28"),   # clamp: fev não tem 31
        ("2026-12-31", "MONTHLY", "2027-01-31"),   # vira o ano
        ("2028-01-31", "MONTHLY", "2028-02-29"),   # ano bissexto
    ],
)
def test_advance_iso(iso, recurrence, expected):
    assert service.advance_iso(iso, recurrence) == expected


# ─── parse_recurrence (aliases PT + EN) ──────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mensal", "MONTHLY"), ("Mensal", "MONTHLY"), ("MONTHLY", "MONTHLY"),
        ("trimestral", "QUARTERLY"), ("Trimestral", "QUARTERLY"),
        ("semestral", "SEMIANNUAL"),
        ("anual", "ANNUAL"), ("ANUAL", "ANNUAL"),
        ("", None), (None, None), ("bianual", None),
    ],
)
def test_parse_recurrence(raw, expected):
    assert service.parse_recurrence(raw) == expected


# ─── due_fields ──────────────────────────────────────────────────────────────

def test_due_fields():
    today = date(2026, 6, 10)
    assert service.due_fields("2026-06-01", today) == (True, -9)   # vencida
    assert service.due_fields("2026-06-10", today) == (True, 0)    # hoje
    assert service.due_fields("2026-06-20", today) == (False, 10)  # futura
    assert service.due_fields("data-ruim", today) == (False, None)


def test_today_br_is_a_date():
    assert isinstance(service.today_br(), date)


# ─── parse_import (CSV vírgula/ponto-e-vírgula + XLSX + cabeçalho) ───────────

def test_parse_import_csv_comma():
    data = b"sistema,periodicidade,proxima_data\nCRM,Trimestral,2026-01-01\n"
    rows = service.parse_import(data, "x.csv")
    assert rows == [{"system": "CRM", "recurrence_raw": "Trimestral", "date_raw": "2026-01-01"}]


def test_parse_import_csv_semicolon():
    # Excel BR: delimitador ';' — decidido pela 1ª linha (cabeçalho).
    data = "sistema;periodicidade;proxima_data\nBanco Digital;Anual;30/06/2027\n".encode("utf-8")
    rows = service.parse_import(data, "x.csv")
    assert rows[0]["system"] == "Banco Digital"
    assert rows[0]["recurrence_raw"] == "Anual"


def test_parse_import_missing_header_raises():
    data = b"foo,bar,baz\n1,2,3\n"
    with pytest.raises(ValueError):
        service.parse_import(data, "x.csv")


def test_parse_import_xlsx_roundtrip():
    openpyxl = pytest.importorskip("openpyxl")
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["sistema", "periodicidade", "proxima_data"])
    ws.append(["CRM Comercial", "Mensal", "2026-05-01"])
    buf = BytesIO()
    wb.save(buf)

    rows = service.parse_import(buf.getvalue(), "cal.xlsx")
    assert rows[0]["system"] == "CRM Comercial"
    assert service.parse_recurrence(rows[0]["recurrence_raw"]) == "MONTHLY"
    assert service.normalize_date(rows[0]["date_raw"]) == "2026-05-01"


# ─── Rodada 9 (avaliação consolidada, item 12): datas e cabeçalhos do Excel BR ─
#
# O cliente reportou falha ao importar planilhas com datas, sem mandar o arquivo.
# Estes casos documentam os formatos que o Excel BR produz de fato.

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("10/12/2026 00:00:00", "2026-12-10"),   # data com hora (texto)
        ("2026-12-10 00:00", "2026-12-10"),
        ("10.12.2026", "2026-12-10"),            # separador ponto
        ("2026/12/10", "2026-12-10"),            # ano primeiro com barra
        ("10-dez-2026", "2026-12-10"),           # mês abreviado PT
        ("10/Dec/26", "2026-12-10"),             # mês abreviado EN, ano 2 dígitos
        ("20261210", "2026-12-10"),              # AAAAMMDD
        ("12/25/2026", "2026-12-25"),            # US óbvio (25 não é mês)
        ("05/06/2026", "2026-06-05"),            # ambíguo → dia primeiro (BR)
        (46000, "2025-12-09"),                   # serial do Excel (célula numérica)
        (46000.0, "2025-12-09"),
        ("46000", "2025-12-09"),                 # serial exportado como texto
        (True, None),                            # bool não é data
        (0, None),                               # fora da faixa do Excel
    ],
)
def test_normalize_date_formatos_excel_br(raw, expected):
    assert service.normalize_date(raw) == expected


def test_parse_import_csv_windows_1252_com_acentos():
    """Excel BR salva CSV em Windows-1252: cabeçalho e nomes acentuados precisam casar."""
    data = "Sistema;Periodicidade;Próxima Data\nNúcleo Câmbio;Trimestral;10/12/2026\n".encode("cp1252")
    rows = service.parse_import(data, "cal.csv")
    assert rows[0]["system"] == "Núcleo Câmbio"
    assert service.normalize_date(rows[0]["date_raw"]) == "2026-12-10"


def test_parse_import_cabecalho_com_titulo_antes_e_variantes():
    data = (
        "Calendário de Conformidade 2026\n"
        "\n"
        "Nome do Sistema,Frequência,Data de Vencimento\n"
        "CRM,Mensal,2026-01-31\n"
    ).encode("utf-8")
    rows = service.parse_import(data, "cal.csv")
    assert rows == [{"system": "CRM", "recurrence_raw": "Mensal", "date_raw": "2026-01-31"}]


def test_parse_import_xlsx_celula_data_e_serial():
    openpyxl = pytest.importorskip("openpyxl")
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Calendário"])  # título antes do cabeçalho
    ws.append(["Sistema", "Periodicidade", "Próxima Data"])
    ws.append(["A", "Anual", datetime(2026, 12, 10, 0, 0)])  # célula de data
    ws.append(["B", "Semestral", 46000])                    # célula numérica (serial)
    buf = BytesIO()
    wb.save(buf)
    rows = service.parse_import(buf.getvalue(), "cal.xlsx")
    assert [service.normalize_date(r["date_raw"]) for r in rows] == ["2026-12-10", "2025-12-09"]


def test_parse_import_xls_tem_erro_claro():
    with pytest.raises(ValueError, match=r"\.xls"):
        service.parse_import(b"\xd0\xcf\x11\xe0binario", "antigo.xls")


def test_parse_import_cabecalho_invalido_lista_colunas_encontradas():
    with pytest.raises(ValueError, match="foo, bar, baz"):
        service.parse_import(b"foo,bar,baz\n1,2,3\n", "x.csv")
