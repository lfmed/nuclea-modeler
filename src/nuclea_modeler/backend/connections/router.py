"""Module 1 — Connections CRUD + test endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException

from ..core import Dependencies
from ..core._nuclea_config import get_settings
from ..core import delta
from ..core.sql import SqlDependency
from . import crypto, testers
from .models import (
    ConnectionIn,
    ConnectionListOut,
    ConnectionOut,
    ConnectionTestResult,
    TestStatus,
)
from ..._metadata import api_prefix

router = APIRouter(prefix=f"{api_prefix}/connections", tags=["connections"])

_COLUMNS = [
    "connection_id", "alias", "environment", "system_id",
    "connection_type", "config_json", "secret_scope",
    "secret_key_user", "secret_key_pass", "secret_key_token",
    "last_test_status", "last_test_at", "last_test_latency_ms",
    "last_test_db_version", "last_test_error",
    "created_at", "created_by", "updated_at", "updated_by",
    # enc_password (v1.0058): APÊNDICE no fim para não deslocar os índices que o
    # _row_to_out mapeia por posição. É o cifrado da senha (Fernet) — NUNCA é
    # devolvido; só vira o booleano has_password.
    "enc_password",
]


def _row_to_out(row: list, system_name: str | None = None) -> ConnectionOut:
    import json
    raw_config = row[5]
    try:
        config = json.loads(raw_config) if raw_config else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return ConnectionOut(
        connection_id=row[0],
        alias=row[1],
        environment=cast(any, row[2]),
        system_id=row[3],
        system_name=system_name,
        connection_type=cast(any, row[4]),
        config=config,
        secret_scope=row[6],
        secret_key_user=row[7],
        secret_key_pass=row[8],
        secret_key_token=row[9],
        last_test_status=cast(any, row[10]) if row[10] else None,
        last_test_at=row[11],
        last_test_latency_ms=row[12],
        last_test_db_version=row[13],
        last_test_error=row[14],
        created_at=row[15],
        created_by=row[16],
        updated_at=row[17],
        updated_by=row[18],
        # row[19] = enc_password (cifrado) → expõe só se HÁ senha, nunca o valor.
        has_password=bool(len(row) > 19 and row[19]),
    )


def _actor(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "unknown"


def _encrypt_password_or_400(password: str | None) -> str | None:
    """Cifra a senha para gravar em `enc_password`. Falha FECHADO.

    Se a senha veio mas a chave-mestra (NUCLEA_CONN_ENC_KEY) não está
    configurada, devolve 500 claro em vez de gravar em texto plano.
    """
    if not password:
        return None
    if not crypto.is_configured():
        raise HTTPException(
            500,
            "NUCLEA_CONN_ENC_KEY não configurada no app — não é possível salvar a "
            "senha com segurança. Configure o secret 'nuclea-modeler/conn_enc_key'.",
        )
    return crypto.encrypt(password)


def _fetch_enc_password(sql: SqlDependency, connection_id: str) -> str | None:
    """Lê o cifrado da senha direto da tabela (get_connection não o expõe)."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT enc_password FROM {s.fq_table('connections')} WHERE connection_id = :cid",
        [delta.param("cid", connection_id)],
    )
    return row[0] if row and row[0] else None


@router.get("", response_model=list[ConnectionListOut], operation_id="listConnections")
def list_connections(sql: SqlDependency) -> list[ConnectionListOut]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT c.connection_id, c.alias, c.environment, c.system_id,
               s.system_name, c.connection_type,
               c.last_test_status, c.last_test_at, c.last_test_latency_ms,
               c.updated_at
        FROM {s.fq_table('connections')} c
        LEFT JOIN {s.fq_table('systems')} s ON s.system_id = c.system_id
        ORDER BY c.updated_at DESC
        """,
    )
    return [
        ConnectionListOut(
            connection_id=r[0],
            alias=r[1],
            environment=r[2],
            system_id=r[3],
            system_name=r[4],
            connection_type=r[5],
            last_test_status=r[6] or None,
            last_test_at=r[7],
            last_test_latency_ms=r[8],
            updated_at=r[9],
        )
        for r in rows
    ]


@router.get("/{connection_id}", response_model=ConnectionOut, operation_id="getConnection")
def get_connection(connection_id: str, sql: SqlDependency) -> ConnectionOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('c.'+c for c in _COLUMNS)}, s.system_name
        FROM {s.fq_table('connections')} c
        LEFT JOIN {s.fq_table('systems')} s ON s.system_id = c.system_id
        WHERE c.connection_id = :connection_id
        """,
        [delta.param("connection_id", connection_id)],
    )
    if not row:
        raise HTTPException(404, f"connection '{connection_id}' not found")
    return _row_to_out(row[:-1], system_name=row[-1])


@router.post("", response_model=ConnectionOut, operation_id="createConnection")
def create_connection(
    payload: ConnectionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ConnectionOut:
    import json
    s = get_settings()
    actor = _actor(user_ws)
    cid = delta.new_id("conn-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("connections"),
        {
            "connection_id": cid,
            "alias": payload.alias,
            "environment": payload.environment,
            "system_id": payload.system_id,
            "connection_type": payload.connection_type,
            "config_json": json.dumps(payload.config, ensure_ascii=False),
            "secret_scope": payload.secret_scope or s.secrets_scope,
            "secret_key_user": payload.secret_key_user,
            "secret_key_pass": payload.secret_key_pass,
            "secret_key_token": payload.secret_key_token,
            "enc_password": _encrypt_password_or_400(payload.password),
            "last_test_status": "never",
            "created_at": now,
            "created_by": actor,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return get_connection(cid, sql)


@router.put("/{connection_id}", response_model=ConnectionOut, operation_id="updateConnection")
def update_connection(
    connection_id: str,
    payload: ConnectionIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ConnectionOut:
    import json
    s = get_settings()
    actor = _actor(user_ws)
    fields: dict = {
        "alias": payload.alias,
        "environment": payload.environment,
        "system_id": payload.system_id,
        "connection_type": payload.connection_type,
        "config_json": json.dumps(payload.config, ensure_ascii=False),
        "secret_scope": payload.secret_scope or s.secrets_scope,
        "secret_key_user": payload.secret_key_user,
        "secret_key_pass": payload.secret_key_pass,
        "secret_key_token": payload.secret_key_token,
        "updated_at": datetime.utcnow(),
        "updated_by": actor,
    }
    # Semântica da senha no update (evita apagar sem querer a senha já salva):
    #   None -> OMITE o campo (mantém a senha atual)
    #   ""   -> zera (enc_password = NULL)
    #   valor-> cifra e substitui
    if payload.password is not None:
        fields["enc_password"] = _encrypt_password_or_400(payload.password) if payload.password else None
    delta.update_by_id(sql, s.fq_table("connections"), "connection_id", connection_id, fields)
    return get_connection(connection_id, sql)


@router.delete("/{connection_id}", operation_id="deleteConnection")
def delete_connection(connection_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("connections"), "connection_id", connection_id)
    return {"deleted": connection_id}


@router.post(
    "/{connection_id}/test",
    response_model=ConnectionTestResult,
    operation_id="testConnection",
)
def test_connection(
    connection_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
) -> ConnectionTestResult:
    """Test a connection by actually probing the target.

    - DATABASE (v1.0058): opens a real connection via the embedded Python driver
      of the chosen engine (Postgres/Oracle/MySQL/SQL Server/DB2), runs a version
      probe and closes it. The password is decrypted at this moment from
      `enc_password` (Fernet, see crypto.py) — never stored/returned in clear.
    - ODBC (LEGADO): não suportado no runtime do Databricks Apps → devolve
      mensagem de descontinuação pedindo recadastro como DATABASE.
    - REST: issues a single GET to `config.base_url` with timeout=10s. 2xx/3xx
      = success. Token read from Databricks Secrets via the APP service principal
      (`app_ws`), because user OBO tokens typically lack the `secrets` scope.
    - DDL_IMPORT: trivially successful — no remote target.
    """
    conn = get_connection(connection_id, sql)
    s = get_settings()
    actor = _actor(user_ws)
    # Resolve secret_scope: per-connection override → app-wide default.
    scope = conn.secret_scope or s.secrets_scope

    if conn.connection_type == "DATABASE":
        # Motor nativo (v1.0058): decifra a senha guardada e testa via driver
        # Python embutido do engine. username não é sigiloso e vem no config.
        cfg = conn.config or {}
        enc = _fetch_enc_password(sql, connection_id)
        password: str | None = None
        if enc:
            try:
                password = crypto.decrypt(enc)
            except Exception:
                password = None
        if enc and password is None:
            # Só cai aqui se havia senha salva e a decifragem falhou (chave
            # trocada / dado corrompido) — mensagem acionável.
            outcome = testers.TesterOutcome(
                status="failure",
                latency_ms=1,
                error="Não foi possível decifrar a senha salva (chave alterada ou dado corrompido). Edite a conexão e informe a senha novamente.",
            )
        else:
            outcome = testers.test_database(
                engine=str(cfg.get("engine") or ""),
                config=cfg,
                username=cfg.get("username"),
                password=password,
            )
    elif conn.connection_type == "ODBC":
        # LEGADO — não roda no Databricks Apps (sem unixODBC). Ver DatabaseEngine.
        outcome = testers.TesterOutcome(
            status="failure",
            latency_ms=1,
            error="Conexão ODBC foi descontinuada (não suportada no runtime do Databricks Apps). Recadastre como conexão de banco nativa (Postgres, Oracle, MySQL, SQL Server ou DB2).",
        )
    elif conn.connection_type == "REST":
        outcome = testers.test_rest(
            ws=app_ws,
            config=conn.config or {},
            secret_scope=scope,
            secret_key_token=conn.secret_key_token,
            secret_key_user=conn.secret_key_user,
            secret_key_pass=conn.secret_key_pass,
        )
    elif conn.connection_type == "DDL_IMPORT":
        outcome = testers.test_ddl_import()
    else:
        outcome = testers.TesterOutcome(
            status="failure",
            latency_ms=1,
            error=f"unsupported connection_type: {conn.connection_type}",
        )

    now = datetime.utcnow()
    status: TestStatus = outcome.status  # type: ignore[assignment]
    delta.update_by_id(
        sql,
        s.fq_table("connections"),
        "connection_id",
        connection_id,
        {
            "last_test_status": status,
            "last_test_at": now,
            "last_test_latency_ms": outcome.latency_ms,
            "last_test_db_version": outcome.db_version,
            "last_test_error": outcome.error,
            "updated_at": now,
            "updated_by": actor,
        },
    )
    return ConnectionTestResult(
        status=status,
        latency_ms=outcome.latency_ms,
        db_version=outcome.db_version,
        error=outcome.error,
        tested_at=now,
    )
