"""Pydantic models for Reverse Engineering (M2) — extractions and snapshots."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["LAKEBASE", "DDL_FILE", "ODBC", "REST"]
ExtractionStatus = Literal["RUNNING", "SUCCESS", "PARTIAL", "FAILED"]


class LakebaseExtractionIn(BaseModel):
    """Trigger an extraction from a Lakebase sandbox."""

    sandbox_id: str
    system_id: str
    schemas: list[str] = Field(default_factory=list, description="empty list = all visible schemas")
    object_kinds: list[Literal["TABLE", "VIEW"]] = Field(default_factory=lambda: ["TABLE", "VIEW"])
    open_ticket: bool = True


class DDLImportIn(BaseModel):
    """Trigger an extraction from raw DDL text."""

    system_id: str
    dialect: str = "ANSI"
    ddl_text: str = Field(min_length=1)
    open_ticket: bool = True


class ExtractedAttribute(BaseModel):
    technical_name: str
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool = False
    native_comment: str | None = None


class ExtractedEntity(BaseModel):
    schema_name: str
    technical_name: str
    entity_type: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"] = "TABLE"
    native_comment: str | None = None
    row_count_approx: int | None = None
    attributes: list[ExtractedAttribute] = Field(default_factory=list)


class ExtractionSnapshot(BaseModel):
    source_kind: SourceKind
    sandbox_id: str | None = None
    connection_id: str | None = None
    system_id: str
    captured_at: datetime
    schemas: list[str] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)


class ExtractionListOut(BaseModel):
    extraction_id: str
    source_kind: SourceKind
    system_id: str
    system_name: str | None = None
    status: ExtractionStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    objects_found: int | None = None
    objects_new: int | None = None
    objects_changed: int | None = None
    objects_removed: int | None = None
    ticket_id: str | None = None
    created_by: str


class ExtractionOut(ExtractionListOut):
    connection_id: str | None = None
    lakebase_sandbox_id: str | None = None
    requested_schemas: str | None = None
    requested_kinds: str | None = None
    error_summary: str | None = None
    snapshot: ExtractionSnapshot | None = None
    diff_summary: dict | None = None


class ExtractionResult(BaseModel):
    extraction_id: str
    status: ExtractionStatus
    objects_found: int
    objects_new: int
    objects_changed: int
    objects_removed: int
    duration_ms: int
    ticket_id: str | None = None
    summary_md: str
    errors: list[str] = Field(default_factory=list)
