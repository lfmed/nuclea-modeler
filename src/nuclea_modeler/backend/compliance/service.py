"""Lógica pura do calendário de conformidade (rodada 8, item 3).

Sem acesso a banco — só datas e parse da planilha de 1ª carga. O router orquestra
a persistência e a resolução de `system` (id/nome) → system_id.
"""
from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime

from .models import Recurrence

# Passo (em meses) de cada periodicidade.
_MONTHS_STEP: dict[str, int] = {
    "MONTHLY": 1,
    "QUARTERLY": 3,
    "SEMIANNUAL": 6,
    "ANNUAL": 12,
}

# Aliases aceitos no import (PT do cliente + EN canônico), case-insensitive.
_RECURRENCE_ALIASES: dict[str, Recurrence] = {
    "mensal": "MONTHLY", "monthly": "MONTHLY", "mês": "MONTHLY", "mes": "MONTHLY",
    "trimestral": "QUARTERLY", "quarterly": "QUARTERLY", "trimestre": "QUARTERLY",
    "semestral": "SEMIANNUAL", "semiannual": "SEMIANNUAL", "semestre": "SEMIANNUAL",
    "anual": "ANNUAL", "annual": "ANNUAL", "ano": "ANNUAL", "yearly": "ANNUAL",
}


def parse_recurrence(raw: str | None) -> Recurrence | None:
    """Normaliza o texto de periodicidade para a chave canônica (ou None)."""
    if not raw:
        return None
    return _RECURRENCE_ALIASES.get(raw.strip().lower())


def _add_months(d: date, months: int) -> date:
    """Soma meses a uma data, com clamp do dia ao último dia do mês destino
    (ex.: 31/jan + 1 mês = 28/29 de fev)."""
    m0 = d.month - 1 + months
    year = d.year + m0 // 12
    month = m0 % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def advance_iso(iso_date: str, recurrence: Recurrence) -> str:
    """Avança uma data ISO 'YYYY-MM-DD' por 1 período da recorrência."""
    d = date.fromisoformat(iso_date)
    return _add_months(d, _MONTHS_STEP[recurrence]).isoformat()


def normalize_date(raw: str | None) -> str | None:
    """Aceita 'YYYY-MM-DD' ou 'DD/MM/YYYY' (e 'DD-MM-YYYY') → ISO 'YYYY-MM-DD'.

    Também tolera datas do Excel já convertidas para datetime pelo openpyxl.
    Retorna None se não reconhecer.
    """
    if raw is None:
        return None
    if isinstance(raw, (datetime, date)):
        return (raw.date() if isinstance(raw, datetime) else raw).isoformat()
    s = str(raw).strip()
    if not s:
        return None
    # ISO direto
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    # DD/MM/YYYY ou DD-MM-YYYY
    for sep in ("/", "-"):
        parts = s.split(sep)
        if len(parts) == 3:
            try:
                dd, mm, yy = (int(p) for p in parts)
                if yy < 100:
                    yy += 2000
                return date(yy, mm, dd).isoformat()
            except (ValueError, TypeError):
                continue
    return None


def due_fields(iso_date: str, today: date | None = None) -> tuple[bool, int | None]:
    """(is_due, days_until) a partir de next_due_date vs. hoje. Negativo = vencida."""
    today = today or date.today()
    try:
        d = date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return (False, None)
    delta = (d - today).days
    return (delta <= 0, delta)


# ─── Parse da planilha de 1ª carga ───────────────────────────────────────────
#
# Colunas aceitas (header case-insensitive, aliases): sistema/system;
# periodicidade/recorrencia/recurrence; proxima_data/data/next_due_date.

_COL_SYSTEM = {"sistema", "system", "system_id", "sistema_id"}
_COL_RECUR = {"periodicidade", "recorrencia", "recorrência", "recurrence", "frequencia", "frequência"}
_COL_DATE = {"proxima_data", "próxima_data", "data", "next_due_date", "proxima avaliacao", "próxima avaliação", "vencimento"}


def _match_col(header: list[str], names: set[str]) -> int | None:
    for i, h in enumerate(header):
        if (h or "").strip().lower() in names:
            return i
    return None


def _rows_from_csv(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    # aceita ',' ou ';' (Excel BR costuma exportar com ';')
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


def _rows_from_xlsx(data: bytes) -> list[list]:
    import openpyxl  # lazy — dep já presente (round 6 pt 22)

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows: list[list] = []
    for r in ws.iter_rows(values_only=True):
        rows.append(list(r))
    wb.close()
    return rows


def parse_import(data: bytes, filename: str) -> list[dict]:
    """Lê a planilha (CSV ou XLSX) → lista de {system, recurrence_raw, date_raw}.

    A resolução de system→system_id, a validação e o upsert ficam no router.
    Levanta ValueError se não achar as colunas obrigatórias.
    """
    name = (filename or "").lower()
    rows = _rows_from_xlsx(data) if name.endswith(".xlsx") else _rows_from_csv(data)
    # descarta linhas totalmente vazias
    rows = [r for r in rows if any((c is not None and str(c).strip()) for c in r)]
    if not rows:
        raise ValueError("planilha vazia")
    header = [str(c or "").strip() for c in rows[0]]
    ci_sys = _match_col(header, _COL_SYSTEM)
    ci_rec = _match_col(header, _COL_RECUR)
    ci_dat = _match_col(header, _COL_DATE)
    if ci_sys is None or ci_rec is None or ci_dat is None:
        raise ValueError(
            "cabeçalho não reconhecido: esperado colunas de sistema, periodicidade "
            "e próxima data (ex.: 'sistema', 'periodicidade', 'proxima_data')"
        )
    out: list[dict] = []
    for r in rows[1:]:
        def _cell(i: int):
            return r[i] if i is not None and i < len(r) else None

        out.append(
            {
                "system": (str(_cell(ci_sys)).strip() if _cell(ci_sys) is not None else ""),
                "recurrence_raw": (str(_cell(ci_rec)).strip() if _cell(ci_rec) is not None else ""),
                "date_raw": _cell(ci_dat),
            }
        )
    return out
