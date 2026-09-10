"""Lógica pura do calendário de conformidade (rodada 8, item 3).

Sem acesso a banco — só datas e parse da planilha de 1ª carga. O router orquestra
a persistência e a resolução de `system` (id/nome) → system_id.
"""
from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime, timedelta, timezone

from .models import Recurrence

# Fuso do cliente (Núclea, Brasil). Datas de conformidade são "date-only", então
# "hoje" precisa ser o dia no fuso BR, não no UTC do runtime — senão o pop-up
# dispara até um dia adiantado à noite (achado do /review). BRT = UTC-3 fixo
# (sem horário de verão desde 2019); offset fixo evita dependência de tzdata.
_BR_TZ = timezone(timedelta(hours=-3))


def today_br() -> date:
    """Data de hoje no fuso do cliente (BRT), para as comparações do calendário."""
    return datetime.now(_BR_TZ).date()

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
    """(is_due, days_until) a partir de next_due_date vs. hoje (BRT). Negativo = vencida."""
    today = today or today_br()
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


def _cell(row: list, i: int | None):
    """Célula segura por índice (None se fora do range ou coluna ausente)."""
    return row[i] if (i is not None and i < len(row)) else None


def _rows_from_csv(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    # aceita ',' ou ';' (Excel BR costuma exportar com ';'). Decide pelo delimitador
    # do CABEÇALHO (1ª linha) — o corpo pode ter ';'/',' em textos livres e
    # enviesar a contagem (achado do /review).
    first_line = text.split("\n", 1)[0]
    delim = ";" if first_line.count(";") > first_line.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


def _rows_from_xlsx(data: bytes) -> list[list]:
    import openpyxl  # lazy — dep já presente (round 6 pt 22)

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:  # workbook sem aba ativa → trata como vazio (400, não 500)
        wb.close()
        raise ValueError("planilha sem aba ativa")
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
        c_sys = _cell(r, ci_sys)
        c_rec = _cell(r, ci_rec)
        out.append(
            {
                "system": (str(c_sys).strip() if c_sys is not None else ""),
                "recurrence_raw": (str(c_rec).strip() if c_rec is not None else ""),
                "date_raw": _cell(r, ci_dat),
            }
        )
    return out
