"""Diagram (M4 DER) — view models combining entities, attributes, relationships, layout."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiagramAttribute(BaseModel):
    attribute_id: str
    technical_name: str
    logical_name: str | None = None
    native_data_type: str | None = None
    is_primary_key: bool = False
    is_nullable: bool | None = None
    ordinal_position: int | None = None
    has_lgpd_flag: bool = False


class DiagramEntity(BaseModel):
    entity_id: str
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    entity_type: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"] = "TABLE"
    domain: str | None = None
    criticality: str | None = None
    attributes: list[DiagramAttribute] = Field(default_factory=list)
    has_lgpd_flag: bool = False  # propagated from columns or applied at entity level


class DiagramRelationship(BaseModel):
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    rel_type: str | None = None
    source_cardinality: str | None = None
    target_cardinality: str | None = None
    source_attrs: list[str] = Field(default_factory=list)
    target_attrs: list[str] = Field(default_factory=list)
    description: str | None = None
    origin: str | None = None


class NodePosition(BaseModel):
    x: float
    y: float


class DiagramView(BaseModel):
    system_id: str
    system_name: str | None = None
    entities: list[DiagramEntity]
    relationships: list[DiagramRelationship]
    layout: dict[str, NodePosition] = Field(default_factory=dict)
    layout_name: str = "default"


class LayoutSaveIn(BaseModel):
    layout_name: str = "default"
    positions: dict[str, NodePosition]


class LayoutOut(BaseModel):
    layout_id: str
    system_id: str
    layout_name: str
    positions: dict[str, NodePosition]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
