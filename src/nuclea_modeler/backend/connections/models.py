"""Pydantic models for Connection — Módulo 1."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["HINT", "HEXT", "PROD"]
# DATABASE = conexão de banco nativa (v1.0058, rodada 8). ODBC fica como LEGADO:
# não funciona no runtime do Databricks Apps (sem unixODBC/driver) — mantido só
# para leitura de registros antigos; o teste devolve mensagem de descontinuação.
ConnectionType = Literal["DATABASE", "ODBC", "REST", "DDL_IMPORT"]
# Motores suportados por drivers Python EMBUTIDOS (sem anexar nada): Postgres
# (psycopg), Oracle (oracledb thin), MySQL (PyMySQL), SQL Server (python-tds),
# DB2 (ibm_db). Ver connections/testers.py::test_database.
DatabaseEngine = Literal["POSTGRES", "ORACLE", "MYSQL", "SQLSERVER", "DB2"]
TestStatus = Literal["success", "failure", "never"]


class ConnectionConfigDatabase(BaseModel):
    """Config (SEM senha) de uma conexão de banco nativa.

    A senha NUNCA vem/vai por aqui: é enviada em `ConnectionIn.password` (texto
    plano só no request), cifrada em repouso (`connections/crypto.py`) e guardada
    na coluna `enc_password`. `username` não é sigiloso e fica no config.
    """

    engine: DatabaseEngine
    host: str
    port: int | None = None
    database: str | None = None  # Oracle: service_name; MySQL/SQLServer: opcional
    username: str | None = None
    sslmode: str | None = None  # Postgres: prefer|require|... (default 'prefer')


class ConnectionConfigODBC(BaseModel):
    """LEGADO — ODBC não roda no runtime do Databricks Apps. Ver DatabaseEngine."""

    driver: str = Field(description="Nome do driver ODBC (ex: 'SQL Server', 'Oracle in OraClient')")
    host: str
    port: int | None = None
    database: str
    dsn: str | None = None
    additional_params: dict[str, str] = Field(default_factory=dict)


class ConnectionConfigREST(BaseModel):
    base_url: str
    auth_type: Literal["BASIC", "BEARER", "OAUTH2", "NONE"] = "NONE"
    oauth_token_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class ConnectionConfigDDL(BaseModel):
    """For DDL_IMPORT connections, config is empty — files are uploaded via the extractions API."""

    notes: str | None = None


class ConnectionIn(BaseModel):
    """Payload for creating/updating a connection."""

    alias: str = Field(min_length=1, max_length=120, description="Nome amigável")
    environment: Environment
    system_id: str = Field(min_length=1)
    connection_type: ConnectionType
    config: dict = Field(default_factory=dict, description="DATABASE/REST/DDL config (untyped JSON, SEM senha)")
    # Senha em texto plano — SOMENTE no request. Cifrada em repouso (crypto.py) e
    # gravada em `enc_password`; nunca retorna em ConnectionOut. Em update, omitir
    # (None) preserva a senha atual; "" limpa. Ver router.create/update_connection.
    password: str | None = Field(default=None, description="Senha do banco (write-only; cifrada em repouso)")
    secret_scope: str | None = Field(default=None, description="Default uses NUCLEA_SECRETS_SCOPE")
    secret_key_user: str | None = None
    secret_key_pass: str | None = None
    secret_key_token: str | None = None


class ConnectionOut(BaseModel):
    """Single-record output."""

    connection_id: str
    alias: str
    environment: Environment
    system_id: str
    system_name: str | None = None
    connection_type: ConnectionType
    config: dict = Field(default_factory=dict)
    # True se há senha cifrada guardada (enc_password não-nulo). A senha em si
    # NUNCA é retornada — só este booleano, para a UI mostrar "senha definida".
    has_password: bool = False
    secret_scope: str | None = None
    secret_key_user: str | None = None
    secret_key_pass: str | None = None
    secret_key_token: str | None = None
    last_test_status: TestStatus | None = None
    last_test_at: datetime | None = None
    last_test_latency_ms: int | None = None
    last_test_db_version: str | None = None
    last_test_error: str | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class ConnectionListOut(BaseModel):
    """Lightweight summary for the list page."""

    connection_id: str
    alias: str
    environment: Environment
    system_id: str
    system_name: str | None = None
    connection_type: ConnectionType
    last_test_status: TestStatus | None = None
    last_test_at: datetime | None = None
    last_test_latency_ms: int | None = None
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    status: TestStatus
    latency_ms: int | None = None
    db_version: str | None = None
    error: str | None = None
    tested_at: datetime
