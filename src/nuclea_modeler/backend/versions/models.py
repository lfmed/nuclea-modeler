"""Pydantic models for Model Versioning — Módulo 8."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VersionStatus = Literal["DRAFT", "PUBLISHED", "ACTIVE", "DEPRECATED"]

DiffType = Literal[
    "entity_added",
    "entity_removed",
    "entity_changed",
    "attribute_added",
    "attribute_removed",
    "attribute_changed",
]


class VersionListOut(BaseModel):
    version_id: str
    system_id: str
    system_name: str | None = None
    version_number: str
    title: str | None = None
    status: VersionStatus
    published_at: datetime | None = None
    published_by: str | None = None
    created_at: datetime
    created_by: str


class VersionOut(BaseModel):
    version_id: str
    system_id: str
    system_name: str | None = None
    version_number: str
    title: str | None = None
    changelog: str | None = None
    status: VersionStatus
    published_at: datetime | None = None
    published_by: str | None = None
    based_on_version: str | None = None
    snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class PublishRequest(BaseModel):
    system_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    changelog: str = ""
    make_active: bool = True


class RestoreRequest(BaseModel):
    version_id: str = Field(min_length=1)


class DiffEntry(BaseModel):
    type: DiffType
    entity_key: str  # schema_name.technical_name
    attribute_key: str | None = None
    field: str | None = None
    before: Any | None = None
    after: Any | None = None


class VersionDiff(BaseModel):
    from_version_id: str
    to_version_id: str
    additions: list[DiffEntry] = Field(default_factory=list)
    removals: list[DiffEntry] = Field(default_factory=list)
    changes: list[DiffEntry] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
