"""Real connectivity testers for ODBC and REST connections (Módulo 1).

Each tester takes the connection record + secrets and returns a structured
result with status, latency, optional db_version and error message.

Design choices:
- All testers honour a hard timeout (default 10s) so a slow target never
  blocks the API request.
- ODBC and httpx imports are lazy. Their absence is reported as a clear error
  in the test result, rather than crashing app boot.
- Credentials are fetched from Databricks Secrets via the workspace client.
  Missing secrets are reported per-field so the operator knows what to set.
- DDL_IMPORT has no external connectivity to test — it's a paste-DDL flow.
  We return success with a friendly note.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from databricks.sdk import WorkspaceClient

from ..core._config import logger


_DEFAULT_TIMEOUT_S = 10.0


@dataclass
class TesterOutcome:
    status: str  # "success" | "failure"
    latency_ms: int
    db_version: str | None = None
    error: str | None = None


# ─── Secret resolution ──────────────────────────────────────────────────────


def _read_secret(ws: WorkspaceClient, scope: str | None, key: str | None) -> str | None:
    """Read a secret value from Databricks Secrets. Returns None if missing."""
    if not scope or not key:
        return None
    try:
        resp = ws.secrets.get_secret(scope=scope, key=key)
        if resp.value is None:
            return None
        # Databricks Secrets API returns base64-encoded value.
        import base64
        try:
            return base64.b64decode(resp.value).decode("utf-8")
        except Exception:
            return resp.value
    except Exception as exc:
        logger.warning(f"[connections] failed to read secret {scope}/{key}: {exc}")
        return None


# ─── ODBC tester ────────────────────────────────────────────────────────────


def test_odbc(
    *,
    ws: WorkspaceClient,
    config: dict[str, Any],
    secret_scope: str | None,
    secret_key_user: str | None,
    secret_key_pass: str | None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> TesterOutcome:
    """Probe an ODBC target via pyodbc.connect(... timeout=...).

    Builds a connection string from `config` (driver/host/port/database/dsn +
    additional_params) and credentials from Databricks Secrets.
    """
    started = time.monotonic()
    try:
        import pyodbc  # type: ignore
    except ImportError:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error=(
                "pyodbc not installed. Add 'pyodbc>=5.1' to requirements.txt "
                "and ensure the ODBC driver is available on the Databricks Apps "
                "runtime image."
            ),
        )

    driver = config.get("driver")
    host = config.get("host")
    port = config.get("port")
    database = config.get("database")
    dsn = config.get("dsn")
    additional = config.get("additional_params") or {}

    user = _read_secret(ws, secret_scope, secret_key_user) if secret_key_user else None
    password = _read_secret(ws, secret_scope, secret_key_pass) if secret_key_pass else None

    parts: list[str] = []
    if dsn:
        parts.append(f"DSN={dsn}")
    if driver:
        parts.append(f"DRIVER={{{driver}}}")
    if host:
        parts.append(f"SERVER={host}{(',' + str(port)) if port else ''}")
    if database:
        parts.append(f"DATABASE={database}")
    if user:
        parts.append(f"UID={user}")
    if password:
        parts.append(f"PWD={password}")
    for k, v in additional.items():
        parts.append(f"{k}={v}")

    conn_str = ";".join(parts)
    if not conn_str:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error="empty ODBC config: provide at least DSN or DRIVER+SERVER",
        )

    try:
        # `timeout` here is the LOGIN timeout. Some drivers also honour
        # `Connection Timeout` in the conn string.
        conn = pyodbc.connect(conn_str, timeout=int(timeout_s))
        try:
            cursor = conn.cursor()
            # Best-effort version probe — try a couple of common variants.
            db_version: str | None = None
            for probe in ("SELECT @@VERSION", "SELECT VERSION()", "SELECT 1"):
                try:
                    cursor.execute(probe)
                    row = cursor.fetchone()
                    if row:
                        db_version = str(row[0])[:200]
                        break
                except Exception:
                    continue
            return TesterOutcome(
                status="success",
                latency_ms=int((time.monotonic() - started) * 1000),
                db_version=db_version,
            )
        finally:
            conn.close()
    except Exception as exc:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )


# ─── REST tester ────────────────────────────────────────────────────────────


def test_rest(
    *,
    ws: WorkspaceClient,
    config: dict[str, Any],
    secret_scope: str | None,
    secret_key_token: str | None,
    secret_key_user: str | None,
    secret_key_pass: str | None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> TesterOutcome:
    """Probe a REST endpoint with a single GET to base_url.

    Auth modes:
    - NONE: no header.
    - BEARER: Authorization: Bearer <token from secret>.
    - BASIC: Basic auth from (user, pass) secrets.
    - OAUTH2: NOT implemented — requires a token-exchange flow that depends
      on the provider. Returns a clear failure asking the operator to use
      a bearer token instead.
    """
    started = time.monotonic()
    try:
        import httpx
    except ImportError:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error="httpx not installed (required for REST tests)",
        )

    base_url = config.get("base_url")
    if not base_url:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error="config.base_url is required for REST connections",
        )
    auth_type = (config.get("auth_type") or "NONE").upper()
    headers: dict[str, str] = dict(config.get("headers") or {})

    auth = None
    if auth_type == "BEARER":
        token = _read_secret(ws, secret_scope, secret_key_token)
        if not token:
            return TesterOutcome(
                status="failure",
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"BEARER auth requires secret '{secret_scope}/{secret_key_token}' to be set",
            )
        headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "BASIC":
        user = _read_secret(ws, secret_scope, secret_key_user) if secret_key_user else None
        password = _read_secret(ws, secret_scope, secret_key_pass) if secret_key_pass else None
        if not user or not password:
            return TesterOutcome(
                status="failure",
                latency_ms=int((time.monotonic() - started) * 1000),
                error="BASIC auth requires both user and password secrets to be set",
            )
        auth = (user, password)
    elif auth_type == "OAUTH2":
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error="OAUTH2 not implemented in test endpoint. Use BEARER with a pre-issued token.",
        )

    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            resp = client.get(base_url, headers=headers, auth=auth)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        # 2xx and 3xx considered reachable. 401/403 mean reachable but auth issue.
        if 200 <= resp.status_code < 400:
            return TesterOutcome(
                status="success",
                latency_ms=elapsed_ms,
                db_version=f"HTTP {resp.status_code}",
            )
        return TesterOutcome(
            status="failure",
            latency_ms=elapsed_ms,
            error=f"HTTP {resp.status_code} {resp.reason_phrase}",
        )
    except Exception as exc:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )


# ─── DDL_IMPORT tester ──────────────────────────────────────────────────────


def test_ddl_import() -> TesterOutcome:
    """DDL_IMPORT has no remote target — the test is trivially successful.

    The actual import happens via the /extractions/ddl/run endpoint with the
    SQL text in the payload.
    """
    return TesterOutcome(
        status="success",
        latency_ms=1,
        db_version="DDL_IMPORT (sem teste remoto)",
    )
