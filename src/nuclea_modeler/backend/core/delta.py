"""Lightweight DAO helpers for Delta tables via SQL Statement Execution API.

The app keeps 100% of its state in Delta (Unity Catalog) — no operational
Postgres. This module wraps the Databricks SDK StatementExecutionAPI with
helpers tailored for our row shapes and query patterns.

Two flavours of helpers:

- Literal-inlining: `run`, `insert`, `update_by_id`, `delete_by_id`, `fetch_all`,
  `fetch_one`. Values are serialized through `_quote_lit`. Use ONLY with trusted
  values (constants, generated UUIDs, internal enums).
- Parameterized: `run_params`, `fetch_all_params`, `fetch_one_params`, plus the
  `param()` factory. Statements reference parameters as `:name`. Use ALWAYS
  when a value is user-controlled (path/query params, request body fields).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import uuid4

from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from .sql import Sql


def new_id(prefix: str = "") -> str:
    """Generate a new UUID4 (we use v4 — v7 not in stdlib yet on 3.11)."""
    uid = uuid4().hex
    return f"{prefix}{uid}" if prefix else uid


def as_bool(value: Any) -> bool:
    """Coage um valor booleano vindo do `data_array` do SQL para `bool`.

    GOTCHA CRÍTICO: a Databricks SQL Statement Execution API devolve TODAS as
    células do `data_array` como **string** — inclusive colunas BOOLEAN, que
    voltam como `"true"`/`"false"`. Fazer `bool(r[n])` direto está ERRADO porque
    em Python `bool("false")` é `True` (qualquer string não-vazia é truthy).
    Isso fazia, por exemplo, TODAS as colunas aparecerem como PK no DER
    (`is_primary_key` = `"false"` → `True`). Use SEMPRE este helper para colunas
    booleanas lidas de resultado de query.

    Aceita: bool nativo, string ("true"/"false"/"1"/"0"/"t"/"f"/"yes"/"no",
    case-insensitive), int (0/1) e None (→ False).
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "t", "1", "yes", "y")
    return bool(value)


def as_str_list(value: Any) -> list[str]:
    """Coage uma coluna ``ARRAY<STRING>`` vinda do `data_array` para `list[str]`.

    GOTCHA CRÍTICO (mesma família do :func:`as_bool`): a Databricks SQL Statement
    Execution API devolve TODAS as células como **string** — e uma coluna ARRAY
    volta como uma **string JSON**, ex.: ``'["attr-1","attr-2"]'`` (ou ``'[]'``).
    Fazer ``list(value)`` direto sobre essa string a quebra em CARACTERES
    (``['[', '"', 'a', ...]``), corrompendo silenciosamente o array. Isso fazia,
    por exemplo, o export de DDL não emitir NENHUMA foreign key (as colunas-FK em
    ``source_attr_ids``/``target_attr_ids`` viravam lista de chars e não casavam
    com nenhum ``attribute_id``) e a API de relationships devolver arrays inúteis.
    Use SEMPRE este helper para colunas ARRAY lidas de resultado de query.

    Aceita: lista nativa (defensivo — devolve os itens como str), string JSON de
    array, string vazia/``"[]"`` (→ ``[]``) e ``None`` (→ ``[]``). Uma string que
    não seja um array JSON válido é tratada como um único elemento (defensivo).
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return [s]
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
        # JSON escalar (número/bool/etc.) — trata como único elemento.
        return [str(parsed)]
    return [str(value)]


def _format_ts(value: datetime) -> str:
    """Format a datetime as a Spark-friendly ISO-8601 timestamp literal body.

    Naive datetimes are assumed to be UTC (most of the codebase uses
    `datetime.utcnow()` / `datetime.now(UTC)`). Aware datetimes are normalised
    to UTC so Spark never reinterprets them through the session timezone.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def _quote_lit(value: Any) -> str:
    """Quote a Python value as a SQL literal. Trusted-input only — use params
    (see `run_params`) when value is user-controlled and might contain
    special characters."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return "TIMESTAMP '" + _format_ts(value) + "'"
    if isinstance(value, date):
        return "DATE '" + value.isoformat() + "'"
    if isinstance(value, list):
        items = ", ".join(_quote_lit(x) for x in value)
        return f"array({items})"
    if isinstance(value, dict):
        return _quote_lit(json.dumps(value, ensure_ascii=False))
    # string: escape backslash PRIMEIRO (senão `\"` em payloads JSON é
    # interpretado pelo Databricks SQL parser e some), depois aspas simples.
    # Caso real: diff_json com strings contendo `\"` (escape JSON de aspa
    # dupla) vira `"` no Delta → JSON corrompido. Fix mantém o backslash.
    s = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + s + "'"


# ─── Parameterised query helpers ────────────────────────────────────────────

# Map Python types to the Databricks SQL `type` string accepted by the
# Statement Execution API. STRING is the default when no type is given.
_PARAM_TYPE_FOR = {
    bool: "BOOLEAN",
    int: "BIGINT",
    float: "DOUBLE",
    date: "DATE",
    datetime: "TIMESTAMP",
}


def param(name: str, value: Any, type_hint: str | None = None) -> StatementParameterListItem:
    """Build a `StatementParameterListItem` for use with `:name` placeholders.

    - `None` becomes a NULL parameter (value=None).
    - `datetime` is normalised to UTC and serialised without tz suffix; the
      `TIMESTAMP` type tells the engine how to parse it.
    - `date` is serialised as ISO 8601.
    - `bool`/`int`/`float` are serialised via `str(...)`.
    - Anything else is serialised via `str(...)` and typed as STRING.
    """
    if value is None:
        return StatementParameterListItem(name=name, value=None, type=type_hint or "STRING")

    if isinstance(value, datetime):
        return StatementParameterListItem(
            name=name, value=_format_ts(value), type=type_hint or "TIMESTAMP"
        )
    if isinstance(value, date):
        return StatementParameterListItem(
            name=name, value=value.isoformat(), type=type_hint or "DATE"
        )
    if isinstance(value, bool):
        return StatementParameterListItem(
            name=name, value="true" if value else "false", type=type_hint or "BOOLEAN"
        )
    if isinstance(value, int):
        return StatementParameterListItem(
            name=name, value=str(value), type=type_hint or "BIGINT"
        )
    if isinstance(value, float):
        return StatementParameterListItem(
            name=name, value=repr(value), type=type_hint or "DOUBLE"
        )
    # Default: STRING (also covers str, UUIDs stringified upstream, etc.)
    return StatementParameterListItem(name=name, value=str(value), type=type_hint or "STRING")


def run_params(
    sql_dep: Sql,
    statement: str,
    params: Sequence[StatementParameterListItem] | None = None,
    *,
    wait: str = "30s",
) -> list[list[Any]]:
    """Like `run`, but with positional parameter substitution (`:name`).

    Always prefer this when any embedded value comes from a request.
    """
    resp = sql_dep.execute_statement(
        statement=statement,
        parameters=list(params) if params else None,
        wait_timeout=wait,
    )
    state = resp.status.state if resp.status else None
    if state != StatementState.SUCCEEDED:
        err = (resp.status.error.message if resp.status and resp.status.error else "unknown error")
        raise ValueError(f"SQL failed (state={state}): {err}")
    if not resp.result or not resp.result.data_array:
        return []
    return list(resp.result.data_array)


def fetch_all_params(
    sql_dep: Sql,
    query: str,
    params: Sequence[StatementParameterListItem] | None = None,
) -> list[list[Any]]:
    return run_params(sql_dep, query, params)


def fetch_one_params(
    sql_dep: Sql,
    query: str,
    params: Sequence[StatementParameterListItem] | None = None,
) -> list[Any] | None:
    rows = run_params(sql_dep, query, params)
    return rows[0] if rows else None


# ─── Literal-inlining helpers (trusted input only) ──────────────────────────


def run(sql_dep: Sql, statement: str, *, wait: str = "30s") -> list[list[Any]]:
    """Execute a SQL statement and return the data array.

    Raises ValueError if the statement does not succeed.
    """
    resp = sql_dep.execute_statement(statement=statement, wait_timeout=wait)
    state = resp.status.state if resp.status else None
    if state != StatementState.SUCCEEDED:
        err = (resp.status.error.message if resp.status and resp.status.error else "unknown error")
        raise ValueError(f"SQL failed (state={state}): {err}")
    if not resp.result or not resp.result.data_array:
        return []
    return list(resp.result.data_array)


def run_scalar(sql_dep: Sql, statement: str) -> Any:
    rows = run(sql_dep, statement)
    if not rows or not rows[0]:
        return None
    return rows[0][0]


def insert(sql_dep: Sql, table: str, row: dict[str, Any]) -> None:
    """Insert a single row into a Delta table.

    `table` must be fully qualified `catalog.schema.table`.
    Values are inlined as SQL literals (caller is responsible for trust).
    """
    cols = ", ".join(row.keys())
    vals = ", ".join(_quote_lit(v) for v in row.values())
    run(sql_dep, f"INSERT INTO {table} ({cols}) VALUES ({vals})")


def update_by_id(
    sql_dep: Sql,
    table: str,
    pk_col: str,
    pk_value: str,
    updates: dict[str, Any],
) -> None:
    if not updates:
        return
    set_clauses = ", ".join(f"{k} = {_quote_lit(v)}" for k, v in updates.items())
    run(sql_dep, f"UPDATE {table} SET {set_clauses} WHERE {pk_col} = {_quote_lit(pk_value)}")


def delete_by_id(sql_dep: Sql, table: str, pk_col: str, pk_value: str) -> None:
    run(sql_dep, f"DELETE FROM {table} WHERE {pk_col} = {_quote_lit(pk_value)}")


def fetch_all(sql_dep: Sql, query: str) -> list[list[Any]]:
    return run(sql_dep, query)


def fetch_one(sql_dep: Sql, query: str) -> list[Any] | None:
    rows = run(sql_dep, query)
    return rows[0] if rows else None


def rows_to_dicts(rows: Sequence[Sequence[Any]], columns: Iterable[str]) -> list[dict[str, Any]]:
    cols = list(columns)
    return [dict(zip(cols, r)) for r in rows]
