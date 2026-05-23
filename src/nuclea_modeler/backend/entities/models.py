"""Pydantic models for Entities, Attributes, Relationships — Módulo 3."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Criticality = Literal["HIGH", "MEDIUM", "LOW"]
EntityType = Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"]
RelType = Literal["1:1", "1:N", "N:M", "INHERIT"]
Cardinality = Literal["OPTIONAL", "MANDATORY"]


# -------------------- Entities --------------------

class EntityIn(BaseModel):
    system_id: str
    schema_name: str = Field(min_length=1)
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    description_md: str | None = None
    domain: str | None = None
    business_owner: str | None = None
    technical_owner: str | None = None
    criticality: Criticality | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    entity_type: EntityType = "TABLE"
    native_comment: str | None = None
    row_count_approx: int | None = None


class EntityOut(BaseModel):
    entity_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    description_md: str | None = None
    domain: str | None = None
    business_owner: str | None = None
    technical_owner: str | None = None
    criticality: Criticality | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    entity_type: EntityType
    native_comment: str | None = None
    row_count_approx: int | None = None
    last_extracted_at: datetime | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    attributes_count: int | None = None


class EntityListOut(BaseModel):
    entity_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    entity_type: EntityType
    domain: str | None = None
    criticality: Criticality | None = None
    attributes_count: int | None = None
    updated_at: datetime


# -------------------- Attributes --------------------

class AttributeIn(BaseModel):
    entity_id: str
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool = False
    description_md: str | None = None
    business_rule: str | None = None
    sample_value: str | None = None
    glossary_term_id: str | None = None
    native_comment: str | None = None


class AttributeOut(BaseModel):
    attribute_id: str
    entity_id: str
    technical_name: str
    logical_name: str | None = None
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool
    description_md: str | None = None
    business_rule: str | None = None
    sample_value: str | None = None
    glossary_term_id: str | None = None
    native_comment: str | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
