"""Pydantic models for Relationships CRUD."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RelType = Literal["1:1", "1:N", "N:M", "INHERIT"]
Cardinality = Literal["OPTIONAL", "MANDATORY"]
FKRule = Literal["NO ACTION", "CASCADE", "SET NULL", "SET DEFAULT", "RESTRICT"]
Origin = Literal["EXTRACTED", "MANUAL"]


class RelationshipIn(BaseModel):
    system_id: str
    source_entity_id: str
    target_entity_id: str
    source_attr_ids: list[str] = Field(default_factory=list)
    target_attr_ids: list[str] = Field(default_factory=list)
    rel_type: RelType = "1:N"
    source_cardinality: Cardinality = "OPTIONAL"
    target_cardinality: Cardinality = "MANDATORY"
    description: str | None = None
    fk_update_rule: FKRule | None = None
    fk_delete_rule: FKRule | None = None
    relationship_name: str | None = None  # Novo: nome/rótulo do relacionamento


class RelationshipOut(BaseModel):
    relationship_id: str
    system_id: str
    system_name: str | None = None
    source_entity_id: str
    source_entity_label: str | None = None
    target_entity_id: str
    target_entity_label: str | None = None
    source_attr_ids: list[str] = Field(default_factory=list)
    target_attr_ids: list[str] = Field(default_factory=list)
    rel_type: RelType | None = None
    source_cardinality: Cardinality | None = None
    target_cardinality: Cardinality | None = None
    description: str | None = None
    origin: Origin | None = None
    fk_update_rule: FKRule | None = None
    fk_delete_rule: FKRule | None = None
    relationship_name: str | None = None  # Novo: nome/rótulo do relacionamento
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class RelationshipListOut(BaseModel):
    relationship_id: str
    system_id: str
    system_name: str | None = None
    source_entity_id: str
    source_entity_label: str | None = None
    target_entity_id: str
    target_entity_label: str | None = None
    rel_type: RelType | None = None
    source_cardinality: Cardinality | None = None
    target_cardinality: Cardinality | None = None
    origin: Origin | None = None
    description: str | None = None
    relationship_name: str | None = None  # Novo: nome/rótulo do relacionamento
    updated_at: datetime
