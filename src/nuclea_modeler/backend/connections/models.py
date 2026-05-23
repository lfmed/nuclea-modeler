"""Pydantic models for Connection — Módulo 1."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["HINT", "HEXT", "PROD"]
ConnectionType = Literal["ODBC", "REST", "DDL_IMPORT"]
TestStatus = Literal["success", "failure", "never"]


class ConnectionConfigODBC(BaseModel):
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
    config: dict = Field(default_factory=dict, description="ODBC/REST/DDL config (untyped JSON)")
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
