"""Pydantic models for Lakebase Sandboxes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SandboxIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    instance_name: str = Field(min_length=1)
    database_name: str = "databricks_postgres"
    default_schema: str = "public"
    description: str | None = None


class SandboxListOut(BaseModel):
    sandbox_id: str
    name: str
    instance_name: str
    database_name: str
    default_schema: str
    pg_version: str | None = None
    last_test_status: str | None = None
    last_test_at: datetime | None = None
    is_active: bool


class SandboxOut(SandboxListOut):
    instance_uid: str | None = None
    read_write_dns: str | None = None
    description: str | None = None
    last_test_error: str | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class SandboxTestResult(BaseModel):
    status: Literal["success", "failure"]
    server_version: str | None = None
    current_db: str | None = None
    schemas_visible: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class ListAvailableInstancesOut(BaseModel):
    """Lakebase instances available in the workspace (from Databricks SDK)."""

    instance_name: str
    state: str
    capacity: str | None = None
    pg_version: str | None = None
    read_write_dns: str | None = None
    uid: str | None = None
