"""Lineage (M7) — upstream + downstream models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IntegrationType = Literal["CDC", "BATCH", "API_PULL", "API_PUSH", "FILE"]
Periodicity = Literal["REAL_TIME", "DAILY", "WEEKLY", "MONTHLY", "ON_DEMAND"]
ConsumptionType = Literal["DIRECT_READ", "API", "REPORT", "ML_MODEL"]
SLALevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
DetectedVia = Literal["MANUAL", "UC_LINEAGE"]


class UpstreamIn(BaseModel):
    entity_id: str
    source_system: str = Field(min_length=1)
    source_entity: str | None = None
    integration_type: IntegrationType | None = None
    periodicity: Periodicity | None = None
    transformations: str | None = None
    pipeline_link: str | None = None


class UpstreamOut(BaseModel):
    lineage_id: str
    entity_id: str
    source_system: str
    source_entity: str | None = None
    integration_type: IntegrationType | None = None
    periodicity: Periodicity | None = None
    transformations: str | None = None
    pipeline_link: str | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class DownstreamIn(BaseModel):
    entity_id: str
    consumer_system: str = Field(min_length=1)
    consumption_type: ConsumptionType | None = None
    responsible_team: str | None = None
    sla_dependency: SLALevel | None = None
    detected_via: DetectedVia = "MANUAL"


class DownstreamOut(BaseModel):
    consumer_id: str
    entity_id: str
    consumer_system: str
    consumption_type: ConsumptionType | None = None
    responsible_team: str | None = None
    sla_dependency: SLALevel | None = None
    detected_via: DetectedVia
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class LineageGraphNode(BaseModel):
    id: str  # entity_id (or external system pseudo-id)
    label: str  # display name
    kind: Literal["entity", "upstream_system", "downstream_system"]
    schema_name: str | None = None
    system_name: str | None = None
    domain: str | None = None
    entity_type: str | None = None


class LineageGraphEdge(BaseModel):
    source: str
    target: str
    edge_kind: Literal["upstream", "downstream"]
    label: str | None = None
    sla_dependency: SLALevel | None = None


class LineageGraph(BaseModel):
    center_entity_id: str
    nodes: list[LineageGraphNode]
    edges: list[LineageGraphEdge]
    depth: int
