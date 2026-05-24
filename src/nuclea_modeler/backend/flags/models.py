"""Pydantic models for the Flagging module (Módulo 5)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FlagCategory = Literal["LGPD", "USE", "QUALITY", "CUSTOM"]


# -------------------- Flag catalog --------------------

class FlagOut(BaseModel):
    flag_id: str
    flag_key: str
    category: FlagCategory
    display_name: str
    description: str | None = None
    color_hex: str | None = None
    requires_justification: bool = False
    is_system: bool = False
    is_active: bool = True
    uc_tag_key: str | None = None


class FlagIn(BaseModel):
    """Payload for creating a CUSTOM flag (system flags are seeded via SQL)."""

    flag_key: str = Field(min_length=1, max_length=120)
    category: FlagCategory = "CUSTOM"
    display_name: str = Field(min_length=1)
    description: str | None = None
    color_hex: str | None = Field(default="#6C757D")
    requires_justification: bool = False


class FlagPatch(BaseModel):
    """Patch payload — used to toggle is_active or update color/description."""

    is_active: bool | None = None
    display_name: str | None = None
    description: str | None = None
    color_hex: str | None = None
    requires_justification: bool | None = None


# -------------------- Entity flags --------------------

class EntityFlagApplyIn(BaseModel):
    flag_id: str
    justification: str | None = None


class EntityFlagOut(BaseModel):
    entity_flag_id: str
    entity_id: str
    flag_id: str
    flag: FlagOut
    justification: str | None = None
    applied_at: datetime
    applied_by: str
    applied_in_version: str | None = None
    is_propagated: bool = False


# -------------------- Attribute flags --------------------

class AttributeFlagApplyIn(BaseModel):
    flag_id: str
    justification: str | None = None


class AttributeFlagOut(BaseModel):
    attribute_flag_id: str
    attribute_id: str
    flag_id: str
    flag: FlagOut
    justification: str | None = None
    applied_at: datetime
    applied_by: str
    applied_in_version: str | None = None
