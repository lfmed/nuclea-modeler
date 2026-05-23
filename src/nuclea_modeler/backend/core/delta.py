"""Lightweight DAO helpers for Delta tables via SQL Statement Execution API.

The app keeps 100% of its state in Delta (Unity Catalog) — no operational
Postgres. This module wraps the Databricks SDK StatementExecutionAPI with
helpers tailored for our row shapes and query patterns.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Sequence
from uuid import uuid4

from databricks.sdk.service.sql import StatementState

from .sql import Sql


def new_id(prefix: str = "") -> str:
    """Generate a new UUID4 (we use v4 — v7 not in stdlib yet on 3.11)."""
    uid = uuid4().hex
    return f"{prefix}{uid}" if prefix else uid


def _quote_lit(value: Any) -> str:
    """Quote a Python value as a SQL literal. Trusted-input only — use params
    when value is user-controlled and might contain special characters."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_quote_lit(x) for x in value)
        return f"array({items})"
    if isinstance(value, dict):
        return _quote_lit(json.dumps(value, ensure_ascii=False))
    # string: escape single quotes
    return "'" + str(value).replace("'", "''") + "'"


def _format_param(p: dict) -> dict:
    """Pass-through. Reserved for future parameter helpers."""
    return p


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
