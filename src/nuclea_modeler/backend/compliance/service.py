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


# ─── Datas da planilha (endurecido na rodada 9 consolidada, item 12) ─────────
#
# O cliente reportou "a importação de planilhas contendo campos de data
# apresentou falhas" sem mandar o arquivo. Cobrimos os formatos que o Excel BR
# realmente produz, além dos que já eram aceitos:
#   - data COM HORA em texto ("10/12/2026 00:00:00", "2026-12-10 00:00") — antes o
#     split por "/" pegava "2026 00:00:00" como ano e falhava;
#   - NÚMERO SERIAL do Excel (célula numérica/geral: 46000 = 2025-12-09), que o
#     openpyxl devolve como int/float quando a célula não está formatada como data;
#   - separador "." (10.12.2026) e ano-primeiro com "/" (2026/12/10);
#   - mês por extenso/abreviado PT/EN ("10-dez-2026", "10/Dec/26");
#   - AAAAMMDD compacto (20261210).
# Ambiguidade DD/MM × MM/DD: o padrão é DIA primeiro (Brasil); só lemos como
# MM/DD quando o 1º número não pode ser mês (>12 no 2º → US óbvio).

_EXCEL_EPOCH = date(1899, 12, 30)  # época do Excel (já compensa o bug do 1900 bissexto)

_MONTH_NAMES = {
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5,
    "jun": 6, "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10,
    "nov": 11, "dez": 12, "dec": 12,
}

DATE_FORMATS_HELP = (
    "formatos aceitos: DD/MM/AAAA, DD-MM-AAAA, DD.MM.AAAA, AAAA-MM-DD, AAAA/MM/DD, "
    "DD/MM/AA, 10-dez-2026, AAAAMMDD, célula de data do Excel (com ou sem hora)"
)


def _from_excel_serial(n: float) -> str | None:
    # 1 = 1900-01-01 … 2958465 = 9999-12-31. Fora disso não é data do Excel.
    if not (1 <= n <= 2_958_465):
        return None
    return (_EXCEL_EPOCH + timedelta(days=int(n))).isoformat()


def _ymd(y: int, m: int, d: int) -> str | None:
    if y < 100:
        y += 2000
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def normalize_date(raw) -> str | None:
    """Data da planilha (texto, datetime/date do openpyxl ou serial do Excel) → ISO
    'YYYY-MM-DD'. Retorna None se não reconhecer (o router reporta a linha com
    DATE_FORMATS_HELP)."""
    if raw is None:
        return None
    if isinstance(raw, (datetime, date)):
        return (raw.date() if isinstance(raw, datetime) else raw).isoformat()
    if isinstance(raw, bool):  # bool é int em Python — nunca é data
        return None
    if isinstance(raw, (int, float)):
        return _from_excel_serial(float(raw))
    s = str(raw).strip()
    if not s:
        return None
    # Hora no fim ("… 00:00:00", "…T09:30") não interessa: fica só a parte da data.
    s = s.replace("T", " ", 1) if len(s) > 10 and s[10:11] == "T" else s
    s = s.split()[0]
    # Só dígitos: AAAAMMDD (8) ou serial do Excel exportado como texto ("46000"/"46000.0").
    digits = s.replace(".0", "", 1) if s.endswith(".0") else s
    if digits.isdigit():
        if len(digits) == 8:
            return _ymd(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
        return _from_excel_serial(float(digits))
    for sep in ("/", "-", "."):
        parts = s.split(sep)
        if len(parts) != 3:
            continue
        a, b, c = (p.strip() for p in parts)
        # mês por nome no meio: 10-dez-2026 / 10/Dec/26
        if b[:3].lower() in _MONTH_NAMES and a.isdigit() and c.isdigit():
            return _ymd(int(c), _MONTH_NAMES[b[:3].lower()], int(a))
        if not (a.isdigit() and b.isdigit() and c.isdigit()):
            continue
        x, y, z = int(a), int(b), int(c)
        if len(a) == 4:  # ano primeiro: AAAA-MM-DD / AAAA/MM/DD
            return _ymd(x, y, z)
        # dia primeiro (BR); só inverte quando o 2º número não pode ser mês (US).
        if y > 12 and x <= 12:
            return _ymd(z, x, y)
        return _ymd(z, y, x)
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

# Aliases comparados já NORMALIZADOS (sem acento, minúsculas, espaço/hífen → "_"),
# então "Próxima Data", "proxima-data" e "PROXIMA_DATA" casam igual.
_COL_SYSTEM = {"sistema", "system", "system_id", "sistema_id", "nome_do_sistema", "nome_sistema"}
_COL_RECUR = {"periodicidade", "recorrencia", "recurrence", "frequencia"}
_COL_DATE = {
    "proxima_data", "data", "next_due_date", "proxima_avaliacao", "vencimento",
    "data_vencimento", "data_de_vencimento", "proxima_execucao", "data_prevista",
    "data_da_proxima_avaliacao", "proxima",
}

# Quantas linhas do topo procurar pelo cabeçalho: planilhas "bonitas" costumam ter
# título/linhas em branco antes da tabela (antes só a 1ª linha era considerada).
_HEADER_SCAN_ROWS = 10


def _norm_header(h) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(h or "")).encode("ascii", "ignore").decode("ascii")
    t = t.strip().lower()
    for ch in (" ", "-", "."):
        t = t.replace(ch, "_")
    while "__" in t:
        t = t.replace("__", "_")
    return t.strip("_")


def _match_col(header: list[str], names: set[str]) -> int | None:
    for i, h in enumerate(header):
        if _norm_header(h) in names:
            return i
    return None


def _cell(row: list, i: int | None):
    """Célula segura por índice (None se fora do range ou coluna ausente)."""
    return row[i] if (i is not None and i < len(row)) else None


def _rows_from_csv(data: bytes) -> list[list[str]]:
    # Excel BR salva "CSV (separado por vírgulas)" em Windows-1252, não UTF-8. Antes
    # decodificávamos como UTF-8 com errors="replace" → "Próxima" virava "Pr�xima"
    # (cabeçalho não casava) e nomes de sistema acentuados não eram encontrados.
    # UTF-8 estrito primeiro; se falhar, cp1252 (que decodifica qualquer byte).
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    # aceita ',' ou ';' (Excel BR costuma exportar com ';'). Decide pelo delimitador
    # do CABEÇALHO (1ª linha) — o corpo pode ter ';'/',' em textos livres e
    # enviesar a contagem (achado do /review).
    # Rodada 9: o cabeçalho pode não ser a 1ª linha (título antes) — decide pela 1ª
    # linha (entre as do topo) que tenha ≥2 delimitadores, típico de cabeçalho.
    delim = ","
    for line in text.splitlines()[:_HEADER_SCAN_ROWS]:
        n_semi, n_comma = line.count(";"), line.count(",")
        if max(n_semi, n_comma) >= 2:
            delim = ";" if n_semi > n_comma else ","
            break
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
    if name.endswith(".xls"):
        # .xls (Excel 97-2003) é binário — lido como CSV vira lixo e o erro seria
        # um enigmático "cabeçalho não reconhecido".
        raise ValueError("formato .xls não suportado: salve a planilha como .xlsx ou .csv")
    rows = _rows_from_xlsx(data) if name.endswith(".xlsx") else _rows_from_csv(data)
    # descarta linhas totalmente vazias
    rows = [r for r in rows if any((c is not None and str(c).strip()) for c in r)]
    if not rows:
        raise ValueError("planilha vazia")
    # Procura o cabeçalho nas primeiras linhas (pode haver título antes).
    header_idx = None
    for i, r in enumerate(rows[:_HEADER_SCAN_ROWS]):
        hdr = [str(c or "").strip() for c in r]
        if all(_match_col(hdr, names) is not None for names in (_COL_SYSTEM, _COL_RECUR, _COL_DATE)):
            header_idx = i
            break
    if header_idx is None:
        found = ", ".join(str(c) for c in rows[0] if c is not None and str(c).strip()) or "—"
        raise ValueError(
            "cabeçalho não reconhecido: esperado colunas de sistema, periodicidade "
            "e próxima data (ex.: 'sistema', 'periodicidade', 'proxima_data'). "
            f"Colunas encontradas na 1ª linha: {found}"
        )
    header = [str(c or "").strip() for c in rows[header_idx]]
    ci_sys = _match_col(header, _COL_SYSTEM)
    ci_rec = _match_col(header, _COL_RECUR)
    ci_dat = _match_col(header, _COL_DATE)
    rows = rows[header_idx:]
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
