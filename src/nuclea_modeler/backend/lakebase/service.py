"""Lakebase Postgres connectivity using Databricks OAuth credentials.

Strategy: the app's service principal (or the OBO user) requests a short-lived
Postgres credential from the Databricks SDK and uses it as the Postgres
password. Connections are NOT pooled — each operation opens a fresh conn so
token refresh is trivial.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from databricks.sdk import WorkspaceClient

# psycopg is added in requirements.txt; importing lazily to avoid hard-fail at
# module load if the wheel isn't installed yet during local syntax checks.
try:
    import psycopg
    from psycopg import Connection
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore
    Connection = object  # type: ignore


def fetch_pg_token(ws: WorkspaceClient, instance_name: str) -> str:
    """Get a short-lived Postgres credential for the user/SP via Databricks API.

    `databricks.database.generate_database_credential(instance_names=[...])`
    returns a token usable as the Postgres password.
    """
    resp = ws.database.generate_database_credential(
        request_id=f"nuclea-{int(time.time())}",
        instance_names=[instance_name],
    )
    if resp.token:
        return resp.token
    raise RuntimeError(f"No token returned for instance {instance_name}")


def get_instance(ws: WorkspaceClient, instance_name: str):
    """Resolve a Lakebase instance by name and return its DNS + uid."""
    return ws.database.get_database_instance(name=instance_name)


@contextmanager
def open_connection(
    ws: WorkspaceClient,
    *,
    instance_name: str,
    database: str,
    user_email: str | None = None,
    autocommit: bool = True,
) -> Iterator["Connection"]:
    """Open a psycopg connection to a Lakebase Postgres instance.

    The Postgres `user` is derived from the user_email (or the SP id). The
    `password` is the short-lived token from generate_database_credential.
    """
    if psycopg is None:
        raise RuntimeError("psycopg not installed; add psycopg[binary] to requirements.txt")
    inst = get_instance(ws, instance_name)
    if not inst.read_write_dns:
        raise RuntimeError(f"instance {instance_name} has no read_write_dns")
    token = fetch_pg_token(ws, instance_name)

    # Resolve postgres role. For users it's the email; for app SPs (M2M OAuth)
    # it's the OAuth client_id (= applicationId UUID), which is what Lakebase
    # provisions automatically when the app has CAN_CONNECT_AND_CREATE.
    pg_user = user_email
    if not pg_user:
        client_id = getattr(getattr(ws, "config", None), "client_id", None)
        if client_id:
            pg_user = client_id
    if not pg_user:
        try:
            me = ws.current_user.me()
            pg_user = me.user_name or me.display_name
        except Exception:
            pg_user = None
    if not pg_user:
        pg_user = "nuclea_app"
    conn = psycopg.connect(
        host=inst.read_write_dns,
        port=5432,
        dbname=database,
        user=pg_user,
        password=token,
        sslmode="require",
        connect_timeout=10,
        autocommit=autocommit,
    )
    try:
        yield conn
    finally:
        conn.close()


def test_connection(ws: WorkspaceClient, *, instance_name: str, database: str, user_email: str | None = None) -> dict:
    """Quick health-check: connect, fetch server version + visible schema count."""
    started = time.monotonic()
    try:
        with open_connection(ws, instance_name=instance_name, database=database, user_email=user_email) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()
                cur.execute("SELECT current_database()")
                current_db = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.schemata "
                    "WHERE schema_name NOT IN "
                    "('pg_catalog','information_schema','pg_toast','pg_internal') "
                    "AND schema_name NOT LIKE 'pg_temp_%' "
                    "AND schema_name NOT LIKE 'pg_toast_temp_%'"
                )
                schema_count = cur.fetchone()
        latency_ms = int((time.monotonic() - started) * 1000) or 1
        return {
            "status": "success",
            "server_version": (version[0] if version else None),
            "current_db": (current_db[0] if current_db else None),
            "schemas_visible": int(schema_count[0]) if schema_count else None,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000) or 1
        return {
            "status": "failure",
            "server_version": None,
            "current_db": None,
            "schemas_visible": None,
            "latency_ms": latency_ms,
            "error": str(exc)[:500],
        }


def list_schemas(ws: WorkspaceClient, *, instance_name: str, database: str, user_email: str | None = None) -> list[str]:
    """Return user-visible (non-system) schemas in the given database."""
    with open_connection(ws, instance_name=instance_name, database=database, user_email=user_email) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast','pg_internal') "
                "AND schema_name NOT LIKE 'pg_%' "
                "ORDER BY schema_name"
            )
            return [row[0] for row in cur.fetchall()]


def execute_ddl(
    ws: WorkspaceClient,
    *,
    instance_name: str,
    database: str,
    statements: list[str],
    user_email: str | None = None,
) -> list[tuple[bool, str]]:
    """Run a list of DDL statements. Returns (ok, message) per statement."""
    results: list[tuple[bool, str]] = []
    with open_connection(ws, instance_name=instance_name, database=database, user_email=user_email, autocommit=False) as conn:
        for stmt in statements:
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
                results.append((True, "OK"))
            except Exception as exc:
                conn.rollback()
                results.append((False, str(exc)[:500]))
    return results
