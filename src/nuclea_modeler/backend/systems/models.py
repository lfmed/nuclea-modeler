"""Pydantic models for System (sistema de origem)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SystemEnvironment = Literal["DEV", "HINT", "PRD"]


class SystemIn(BaseModel):
    system_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    domain: str | None = None
    owner_team: str | None = None
    technology: str | None = None
    environment: SystemEnvironment | None = None
    is_active: bool = True


class SystemTechnologyIn(BaseModel):
    """Payload do PATCH /systems/{id}/technology (rodada 9 item 7) — só o dialeto."""

    technology: str | None = Field(default=None, max_length=50)


class SystemOut(BaseModel):
    system_id: str
    system_name: str
    description: str | None = None
    domain: str | None = None
    owner_team: str | None = None
    technology: str | None = None
    environment: SystemEnvironment | None = None
    is_active: bool
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class SystemListOut(BaseModel):
    system_id: str
    system_name: str
    domain: str | None = None
    technology: str | None = None
    environment: SystemEnvironment | None = None
    is_active: bool
