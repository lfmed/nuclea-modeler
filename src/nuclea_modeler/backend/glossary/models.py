"""Pydantic models for the Corporate Data Dictionary — Módulo 6."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TermStatus = Literal["DRAFT", "IN_REVIEW", "APPROVED", "DEPRECATED"]
ConceptualType = Literal[
    "IDENTIFIER",
    "MONETARY",
    "DATE",
    "BOOLEAN",
    "TEXT",
    "NUMERIC",
    "CATEGORICAL",
    "OTHER",
]


# -------------------- Terms --------------------


class TermIn(BaseModel):
    canonical_name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    synonyms: list[str] = Field(default_factory=list)
    domain: str | None = None
    conceptual_type: ConceptualType | None = None
    valid_examples: list[str] = Field(default_factory=list)
    owner_person: str | None = None


class TermListOut(BaseModel):
    term_id: str
    canonical_name: str
    domain: str | None = None
    conceptual_type: ConceptualType | None = None
    status: TermStatus
    owner_person: str | None = None
    mappings_count: int = 0
    updated_at: datetime


class TermOut(BaseModel):
    term_id: str
    canonical_name: str
    definition: str
    synonyms: list[str] = Field(default_factory=list)
    domain: str | None = None
    conceptual_type: ConceptualType | None = None
    valid_examples: list[str] = Field(default_factory=list)
    owner_person: str | None = None
    status: TermStatus
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    mappings_count: int = 0


class TermTransition(BaseModel):
    to: TermStatus
    note: str | None = None


# -------------------- Mappings --------------------


class MappingIn(BaseModel):
    term_id: str
    attribute_id: str
    inherit_description: bool = True
    override_description: str | None = None


class MappingOut(BaseModel):
    mapping_id: str
    term_id: str
    attribute_id: str
    inherit_description: bool
    override_description: str | None = None
    type_compat_warning: bool = False
    created_at: datetime
    created_by: str

    # Term info (joined)
    term_canonical_name: str | None = None
    term_status: TermStatus | None = None
    term_conceptual_type: ConceptualType | None = None
    term_definition: str | None = None

    # Attribute info (joined)
    attribute_technical_name: str | None = None
    attribute_logical_name: str | None = None
    native_data_type: str | None = None

    # Entity info (joined)
    entity_id: str | None = None
    entity_technical_name: str | None = None
    schema_name: str | None = None

    # System info (joined)
    system_id: str | None = None
    system_name: str | None = None
