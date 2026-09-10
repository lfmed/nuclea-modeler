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


class DriverUnavailable(RuntimeError):
    """Driver Python do engine ausente/incarregável no runtime.

    Levantada pelos probes quando o `import` do driver falha, para o dispatcher
    devolver uma mensagem amigável (sem stacktrace) em vez de crashar — mesmo
    padrão defensivo do antigo caminho ODBC.
    """


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


# ─── Native multi-engine database tester (v1.0058, rodada 8) ────────────────
#
# Substitui o ODBC (que não roda no Databricks Apps por falta de unixODBC). Cada
# engine usa um driver Python EMBUTIDO — nada a anexar pelo usuário:
#   POSTGRES  → psycopg (já usado pelo Lakebase; comprovado no runtime)
#   ORACLE    → oracledb (thin mode; Python puro, sem Oracle client)
#   MYSQL     → PyMySQL (Python puro)
#   SQLSERVER → python-tds (Python puro)
#   DB2       → ibm_db (wheel embarca o clidriver nativo)
# Imports são LAZY por engine: se um driver não carregar no runtime, só aquele
# engine falha com mensagem clara — o app não cai.


def _probe_postgres(host, port, database, user, password, sslmode, timeout_s) -> str | None:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise DriverUnavailable("driver Postgres (psycopg) indisponível no runtime") from exc
    conn = psycopg.connect(
        host=host,
        port=int(port or 5432),
        dbname=database or "postgres",
        user=user,
        password=password,
        sslmode=sslmode or "prefer",
        connect_timeout=int(timeout_s),
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            row = cur.fetchone()
        return str(row[0])[:200] if row else None
    finally:
        conn.close()


def _probe_oracle(host, port, database, user, password, timeout_s) -> str | None:
    try:
        import oracledb  # thin mode por padrão — não requer Oracle client
    except ImportError as exc:  # pragma: no cover
        raise DriverUnavailable("driver Oracle (oracledb) indisponível no runtime") from exc
    if not database:
        raise ValueError("Oracle requer o campo 'banco' = service name (ex.: ORCLPDB1)")
    # service-name form: host:port/service
    dsn = f"{host}:{int(port or 1521)}/{database}"
    conn = oracledb.connect(user=user, password=password, dsn=dsn, tcp_connect_timeout=float(timeout_s))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            row = cur.fetchone()
        return str(row[0])[:200] if row else "Oracle"
    finally:
        conn.close()


def _probe_mysql(host, port, database, user, password, timeout_s) -> str | None:
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover
        raise DriverUnavailable("driver MySQL (PyMySQL) indisponível no runtime") from exc
    conn = pymysql.connect(
        host=host,
        port=int(port or 3306),
        user=user,
        password=password or "",
        database=database or None,
        connect_timeout=int(timeout_s),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            row = cur.fetchone()
        return str(row[0])[:200] if row else "MySQL"
    finally:
        conn.close()


def _probe_sqlserver(host, port, database, user, password, timeout_s) -> str | None:
    try:
        import pytds  # pacote python-tds
    except ImportError as exc:  # pragma: no cover
        raise DriverUnavailable("driver SQL Server (python-tds) indisponível no runtime") from exc
    conn = pytds.connect(
        dsn=host,  # em python-tds o 1º parâmetro (dsn) é o host/servidor
        port=int(port or 1433),
        user=user,
        password=password,
        database=database or None,
        login_timeout=int(timeout_s),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT @@VERSION")
            row = cur.fetchone()
        return str(row[0])[:200] if row else "SQL Server"
    finally:
        conn.close()


def _probe_db2(host, port, database, user, password, timeout_s) -> str | None:
    try:
        import ibm_db
    except ImportError as exc:  # pragma: no cover
        raise DriverUnavailable("driver DB2 (ibm_db) indisponível no runtime") from exc
    if not database:
        raise ValueError("DB2 requer o campo 'banco' (DATABASE)")
    conn_str = (
        f"DATABASE={database};HOSTNAME={host};PORT={int(port or 50000)};"
        f"PROTOCOL=TCPIP;UID={user or ''};PWD={password or ''};"
        f"ConnectTimeout={int(timeout_s)};"
    )
    conn = ibm_db.connect(conn_str, "", "")
    try:
        try:
            info = ibm_db.server_info(conn)
            ver = getattr(info, "DBMS_VER", "") or ""
            prod = getattr(info, "DBMS_NAME", "DB2") or "DB2"
            return f"{prod} {ver}".strip()[:200]
        except Exception:
            return "DB2"
    finally:
        ibm_db.close(conn)


_ENGINE_PROBES = {
    "POSTGRES": lambda c, u, p, t: _probe_postgres(c.get("host"), c.get("port"), c.get("database"), u, p, c.get("sslmode"), t),
    "ORACLE": lambda c, u, p, t: _probe_oracle(c.get("host"), c.get("port"), c.get("database"), u, p, t),
    "MYSQL": lambda c, u, p, t: _probe_mysql(c.get("host"), c.get("port"), c.get("database"), u, p, t),
    "SQLSERVER": lambda c, u, p, t: _probe_sqlserver(c.get("host"), c.get("port"), c.get("database"), u, p, t),
    "DB2": lambda c, u, p, t: _probe_db2(c.get("host"), c.get("port"), c.get("database"), u, p, t),
}


def test_database(
    *,
    engine: str,
    config: dict[str, Any],
    username: str | None,
    password: str | None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> TesterOutcome:
    """Testa uma conexão de banco nativa abrindo uma conexão real + probe de versão.

    `engine` seleciona o driver embutido; `config` traz host/port/database/sslmode
    (sem senha); `username`/`password` chegam já decifrados do router.
    """
    started = time.monotonic()
    eng = (engine or "").upper()
    if not config.get("host"):
        return TesterOutcome(status="failure", latency_ms=1, error="config.host é obrigatório")
    probe = _ENGINE_PROBES.get(eng)
    if probe is None:
        return TesterOutcome(
            status="failure",
            latency_ms=1,
            error=f"engine de banco não suportado: {engine!r} (use POSTGRES|ORACLE|MYSQL|SQLSERVER|DB2)",
        )
    try:
        db_version = probe(config, username, password, timeout_s)
        return TesterOutcome(
            status="success",
            latency_ms=int((time.monotonic() - started) * 1000) or 1,
            db_version=db_version,
        )
    except DriverUnavailable as exc:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000) or 1,
            error=str(exc),
        )
    except Exception as exc:
        return TesterOutcome(
            status="failure",
            latency_ms=int((time.monotonic() - started) * 1000) or 1,
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
