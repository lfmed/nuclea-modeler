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
