"""Divisão de scripts DDL em instruções + pré-filtro + constraints de ALTER TABLE.

Rodada 9 consolidada, item 10 — "Importação via DDL falha quando o script é
extenso (ex.: c3l com 12 mil linhas)". Reproduzido com DDL sintético contra o app
deployado (`scripts/repro_large_ddl.py`):

- O tamanho em si NÃO era o problema (12 mil linhas = ~430 KB, preview em ~14 s).
- O problema era o PARSE: o import tentava parsear o script INTEIRO de uma vez;
  bastava UMA instrução que o sqlglot não entende (meta-comando `\\connect` do psql,
  `CREATE TABLESPACE`, sintaxe proprietária — comum em scripts grandes) para cair
  num fallback que dividia o texto por `;` CRU. Isso picotava strings com `;`
  (`COMMENT ON … IS 'a; b'` → descrição perdida), corpos de function/procedure
  (`$$ … ; … $$`, `BEGIN … END;`) e gerava milhares de erros (2.207 no teste).
- Além disso, `ALTER TABLE … ADD CONSTRAINT … PRIMARY KEY/FOREIGN KEY` era
  IGNORADO — e é exatamente assim que `pg_dump` e a maioria dos dumps grandes
  declaram PK e FK (depois dos CREATE TABLE). As tabelas entravam sem PK e sem
  relacionamento.

Este módulo é PURO (sem sqlglot, sem banco): o service usa para (1) dividir o
script respeitando a sintaxe, (2) descartar o que o import não usa e (3) extrair
PK/FK de ALTER TABLE por regex — robusto a versão do sqlglot (o AST de ALTER muda
entre releases; ver o gotcha de versão do v1.0049 no CLAUDE.md).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# ─── 1. Divisão em instruções ────────────────────────────────────────────────


@dataclass
class Statement:
    line: int  # linha (1-based) onde a instrução começa — para mensagens de erro
    text: str


_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_sql_statements(text: str) -> list[Statement]:
    """Divide um script SQL em instruções, respeitando a sintaxe.

    Terminadores: `;` fora de string/comentário/bloco; linha contendo só `/`
    (SQL*Plus — Oracle/DB2); linha contendo só `GO` (T-SQL); fim da linha para
    meta-comandos do psql (`\\connect …`). Não divide dentro de:
    `'…'` (com `''` escapado), `"…"`, `[…]` (T-SQL), `` `…` `` (MySQL), comentários
    `--` e `/* */`, e corpos `$tag$ … $tag$` (Postgres).

    Blocos PL/SQL (`CREATE PROCEDURE … BEGIN … END;`) sem `$$`: quando o script usa
    `/` como terminador, o bloco vai até o `/` (padrão SQL*Plus). Sem `/`, o corpo
    pode sair em pedaços — inofensivo, porque o pré-filtro descarta esses pedaços
    (nenhum começa com CREATE TABLE/VIEW/INDEX/ALTER TABLE/COMMENT ON).
    """
    stmts: list[Statement] = []
    has_slash = any(ln.strip() == "/" for ln in text.splitlines())
    buf: list[str] = []
    start_line = 1
    line = 1
    i = 0
    n = len(text)
    plsql_block = False  # dentro de CREATE PROCEDURE/… (só quando há terminador "/")
    # Já há algo além de espaço no buffer? (evita `"".join(buf)` a cada linha —
    # quadrático em instruções longas.) Enquanto False, a linha inicial avança.
    started = False

    def flush(end_line: int) -> None:
        nonlocal buf, start_line, plsql_block, started
        chunk = "".join(buf).strip()
        if chunk:
            stmts.append(Statement(line=start_line, text=chunk))
        buf = []
        start_line = end_line
        plsql_block = False
        started = False

    at_line_start = True
    while i < n:
        ch = text[i]
        # Terminadores de linha inteira ("/" e "GO") — checados no início de linha.
        if at_line_start:
            j = text.find("\n", i)
            j = n if j < 0 else j
            ln = text[i:j].strip()
            if ln == "/" or ln.upper() == "GO":
                flush(line)
                i = j  # o "\n" é consumido abaixo
                at_line_start = False
                continue
            # Meta-comando do psql (`\connect`, `\set`…) termina no FIM DA LINHA, sem
            # `;`. Sem este caso ele "engolia" a instrução seguinte — e o pré-filtro
            # descartava as duas juntas (um CREATE TABLE logo depois sumiria).
            if ln.startswith("\\"):
                flush(line)
                stmts.append(Statement(line=line, text=ln))
                i = j
                at_line_start = False
                continue
        at_line_start = False
        if ch == "\n":
            buf.append(ch)
            line += 1
            i += 1
            at_line_start = True
            if not started:
                start_line = line
            continue
        if not ch.isspace():
            started = True
        # comentário de linha
        if ch == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            buf.append(text[i:j])
            i = j
            continue
        # comentário de bloco
        if ch == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            seg = text[i:j]
            buf.append(seg)
            line += seg.count("\n")
            i = j
            continue
        # strings / identificadores delimitados
        if ch in ("'", '"', "`", "["):
            close = {"'": "'", '"': '"', "`": "`", "[": "]"}[ch]
            j = i + 1
            while j < n:
                if text[j] == close:
                    # '' / "" escapado dentro da string
                    if close in ("'", '"') and j + 1 < n and text[j + 1] == close:
                        j += 2
                        continue
                    break
                j += 1
            seg = text[i : j + 1]
            buf.append(seg)
            line += seg.count("\n")
            i = j + 1
            continue
        # corpo $tag$ … $tag$ (Postgres)
        if ch == "$":
            m = _DOLLAR_TAG.match(text, i)
            if m:
                tag = m.group(0)
                j = text.find(tag, m.end())
                j = n if j < 0 else j + len(tag)
                seg = text[i:j]
                buf.append(seg)
                line += seg.count("\n")
                i = j
                continue
        if ch == ";":
            buf.append(ch)
            if plsql_block:
                i += 1
                continue
            flush(line)
            i += 1
            continue
        buf.append(ch)
        i += 1
        # Ao fechar o cabeçalho de um bloco PL/SQL, passa a esperar o "/".
        if has_slash and not plsql_block and len(buf) < 400:
            head = "".join(buf).lstrip()
            if _PLSQL_HEAD.match(head) and (head.endswith(" AS") or head.endswith(" IS") or head.upper().endswith(" BEGIN")):
                plsql_block = True
    flush(line)
    return stmts


_PLSQL_HEAD = re.compile(
    r"(?is)^CREATE\s+(OR\s+REPLACE\s+)?((NON)?EDITIONABLE\s+)?"
    r"(PROCEDURE|FUNCTION|TRIGGER|PACKAGE(\s+BODY)?|TYPE\s+BODY)\b"
)

# ─── 2. Pré-filtro ───────────────────────────────────────────────────────────
#
# O import só USA: CREATE TABLE/VIEW (+ MATERIALIZED VIEW), CREATE [UNIQUE] INDEX,
# ALTER TABLE (constraints), COMMENT ON, SET search_path / SET SCHEMA e CREATE
# SCHEMA. Qualquer outra coisa é contada e IGNORADA sem virar erro — em scripts
# grandes (dumps) o grosso é INSERT/GRANT/functions, e cada uma delas passava pelo
# parser (lento) e, quando falhava, poluía o log com "Statement ignorado".

_LEADING_NOISE = re.compile(r"(?s)\A(\s+|--[^\n]*\n?|/\*.*?\*/)+")

_KEEP = re.compile(
    r"(?is)^("
    # CREATE [até 4 modificadores] TABLE|VIEW — OR REPLACE, GLOBAL TEMPORARY,
    # UNLOGGED, EXTERNAL, MATERIALIZED, FOREIGN, TRANSIENT, STREAMING, IF NOT…
    # Tolerante de propósito: descartar uma tabela é pior que um erro de parse.
    # (CREATE TYPE … AS TABLE OF do Oracle é barrado em filter_relevant.)
    r"CREATE\s+(?:[A-Za-z_]+\s+){0,4}?(TABLE|VIEW)\b"
    r"|CREATE\s+(UNIQUE\s+)?((CLUSTERED|NONCLUSTERED|BITMAP)\s+)?INDEX\b"
    r"|CREATE\s+SCHEMA\b"
    r"|ALTER\s+TABLE\b"
    r"|COMMENT\s+ON\b"
    r"|SET\s+(search_path|SCHEMA|CURRENT\s+SCHEMA|CURRENT_SCHEMA)\b"
    r")"
)


# Casam o padrão genérico de CREATE … TABLE/VIEW mas não são tabela/view.
_NOT_A_TABLE = re.compile(r"(?is)^CREATE\s+(OR\s+REPLACE\s+)?(TYPE|TRIGGER|POLICY|RULE|SYNONYM|FUNCTION|PROCEDURE)\b")


def statement_head(text: str) -> str:
    """Texto sem comentários/espaços iniciais (para classificar a instrução)."""
    return _LEADING_NOISE.sub("", text, count=1)


def _skip_kind(head: str) -> str:
    """Rótulo curto do tipo de instrução ignorada (para o resumo do import)."""
    if head.startswith("\\"):
        return "meta-comando psql"
    words = re.findall(r"[A-Za-z_]+", head[:80].upper())
    if not words:
        return "outro"
    if words[0] in ("CREATE", "ALTER", "DROP") and len(words) > 1:
        nxt = [w for w in words[1:4] if w not in ("OR", "REPLACE", "EDITIONABLE", "NONEDITIONABLE")]
        return f"{words[0]} {nxt[0] if nxt else ''}".strip()
    return words[0]


@dataclass
class FilterResult:
    keep: list[Statement] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)

    def skipped_summary(self) -> str:
        """Ex.: '1.200 INSERT, 40 CREATE FUNCTION, 3 GRANT'."""
        return ", ".join(f"{n:,} {k}".replace(",", ".") for k, n in self.skipped.most_common())


def filter_relevant(stmts: list[Statement]) -> FilterResult:
    out = FilterResult()
    for st in stmts:
        head = statement_head(st.text)
        if not head:
            continue
        if _KEEP.match(head) and not _NOT_A_TABLE.match(head):
            out.keep.append(Statement(line=st.line, text=head))
        else:
            out.skipped[_skip_kind(head)] += 1
    return out


# ─── 3. Constraints de ALTER TABLE (regex) ───────────────────────────────────


def _unquote(ident: str) -> str:
    ident = ident.strip()
    if len(ident) >= 2 and ident[0] in '"[`' and ident[-1] in '"]`':
        return ident[1:-1]
    return ident


_IDENT = r'(?:"[^"]+"|\[[^\]]+\]|`[^`]+`|[A-Za-z_][\w$#]*)'
_QUAL = rf"{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}}"


def split_qualified(name: str) -> tuple[str | None, str]:
    """'a.b.c' / '"s"."t"' → (schema|None, tabela). Com 3 partes (db.schema.t)
    fica com as 2 últimas."""
    parts = [_unquote(p) for p in re.findall(_IDENT, name)]
    if not parts:
        return None, ""
    if len(parts) == 1:
        return None, parts[0]
    return parts[-2], parts[-1]


def _cols(raw: str) -> list[str]:
    out = []
    for c in raw.split(","):
        # remove ASC/DESC e afins (PK clusterizada do T-SQL)
        tok = c.strip().split()
        if tok:
            out.append(_unquote(tok[0]))
    return [c for c in out if c]


_ALTER_HEAD = re.compile(
    rf"(?is)^ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(?P<tbl>{_QUAL})\s+(?P<rest>.*)$"
)
_ADD_PK = re.compile(
    r"(?is)ADD\s+(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*(?:CLUSTERED|NONCLUSTERED)?\s*\((?P<cols>[^)]*)\)"
)
_ADD_FK = re.compile(
    rf"(?is)ADD\s+(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\((?P<cols>[^)]*)\)\s*"
    rf"REFERENCES\s+(?P<ref>{_QUAL})\s*(?:\((?P<refcols>[^)]*)\))?"
)


@dataclass
class AlterConstraints:
    """PK/FK declarados num `ALTER TABLE … ADD [CONSTRAINT …] …`."""

    schema: str | None
    table: str
    pk_cols: list[str] = field(default_factory=list)
    # (colunas locais, schema_ref|None, tabela_ref, colunas_ref)
    fks: list[tuple[list[str], str | None, str, list[str]]] = field(default_factory=list)


def parse_alter_constraints(text: str) -> AlterConstraints | None:
    """Extrai PK/FK de um ALTER TABLE. None se não for ALTER TABLE ou não tiver
    PK/FK (ex.: `ALTER TABLE … OWNER TO …` do pg_dump, ADD COLUMN, CHECK)."""
    m = _ALTER_HEAD.match(statement_head(text).rstrip().rstrip(";"))
    if not m:
        return None
    schema, table = split_qualified(m.group("tbl"))
    rest = m.group("rest")
    ac = AlterConstraints(schema=schema, table=table)
    for pm in _ADD_PK.finditer(rest):
        ac.pk_cols.extend(c for c in _cols(pm.group("cols")) if c not in ac.pk_cols)
    for fm in _ADD_FK.finditer(rest):
        rs, rt = split_qualified(fm.group("ref"))
        ac.fks.append((_cols(fm.group("cols")), rs, rt, _cols(fm.group("refcols") or "")))
    if not ac.pk_cols and not ac.fks:
        return None
    return ac
