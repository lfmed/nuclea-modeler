"""Pydantic models for Módulo 9 — Sincronização Unity Catalog."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SyncMode = Literal["INCREMENTAL", "FULL"]
SyncStatus = Literal["RUNNING", "SUCCESS", "PARTIAL", "FAILED"]
SyncObjectStatus = Literal["OK", "SKIPPED", "ERROR"]


class SyncRunRequest(BaseModel):
    """Payload to trigger a sync run (preview or apply)."""

    system_id: str = Field(min_length=1)
    target_catalog: str = Field(min_length=1)
    # Optional mapping {source_schema_name: target_schema_name}.
    # When absent, schema names are mapped to themselves.
    target_schema_map: dict[str, str] | None = None
    mode: SyncMode = "INCREMENTAL"
    dry_run: bool = False
    # Quando true, cria a tabela Delta no catálogo destino se ela ainda não
    # existir (materialização). Quando false (default), tabelas inexistentes são
    # apenas marcadas como SKIPPED — comportamento clássico do M9 (só COMMENT/TAGS).
    materialize: bool = False


class SyncObjectResult(BaseModel):
    """Result of syncing a single entity (target table) inside a run."""

    schema_name: str
    technical_name: str
    target_table: str
    status: SyncObjectStatus
    message: str | None = None
    # DDL de CREATE TABLE materializado/previsto (preenchido no preview quando
    # materialize=True, e no apply quando a tabela foi criada). Null caso contrário.
    ddl: str | None = None


class SyncRunResult(BaseModel):
    """Full outcome of a sync run, returned by /run and /preview."""

    sync_id: str
    status: SyncStatus
    objects_total: int
    objects_synced: int
    objects_failed: int
    # Quantas tabelas foram efetivamente criadas (materializadas) nesta run.
    objects_created: int = 0
    duration_ms: int
    target_catalog: str
    dry_run: bool
    materialize: bool = False
    errors: list[str] = Field(default_factory=list)
    objects: list[SyncObjectResult] = Field(default_factory=list)


class SyncLogListOut(BaseModel):
    """Row in the sync history list."""

    sync_id: str
    system_id: str
    started_at: datetime
    ended_at: datetime | None = None
    status: SyncStatus
    objects_total: int | None = None
    objects_synced: int | None = None
    objects_failed: int | None = None
    duration_ms: int | None = None
    target_catalog: str | None = None
    triggered_by: str | None = None
    error_summary: str | None = None


class SyncLogOut(SyncLogListOut):
    """Detailed sync run, including per-object results."""

    version_id: str
    objects: list[SyncObjectResult] = Field(default_factory=list)
