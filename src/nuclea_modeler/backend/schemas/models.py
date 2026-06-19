"""Pydantic models para Schemas (M6) — padrão In/Out."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SchemaIn(BaseModel):
    """Payload para criar/editar um schema."""

    system_id: str
    schema_name: str = Field(min_length=1, max_length=255)
    logical_name: str | None = None
    domain: str | None = None
    owner_team: str | None = None
    description_md: str | None = None
    is_active: bool = True


class SchemaOut(BaseModel):
    schema_id: str
    system_id: str
    schema_name: str
    logical_name: str | None = None
    domain: str | None = None
    owner_team: str | None = None
    description_md: str | None = None
    is_active: bool
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class SchemaListOut(BaseModel):
    """Item de listagem com contagens agregadas (pra sidebar/árvore)."""

    schema_id: str
    system_id: str
    schema_name: str
    logical_name: str | None = None
    domain: str | None = None
    is_active: bool
    entity_count: int = 0
    diagram_count: int = 0
