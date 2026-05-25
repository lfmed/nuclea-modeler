"""Models for Code Objects: Views (definition SQL), Procedures, Triggers, Sequences."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal["INSERT", "UPDATE", "DELETE"]
TriggerTiming = Literal["BEFORE", "AFTER", "INSTEAD_OF"]
RiskLevel = Literal["CRITICAL", "MODERATE", "LOW"]


# -------------------- Views --------------------

class ViewIn(BaseModel):
    view_entity_id: str = Field(description="FK -> entities.entity_id (entidade do tipo VIEW)")
    purpose: str | None = None
    definition_sql: str | None = None
    base_entity_ids: list[str] = Field(default_factory=list)


class ViewOut(BaseModel):
    view_entity_id: str
    entity_label: str | None = None
    system_id: str | None = None
    system_name: str | None = None
    purpose: str | None = None
    definition_sql: str | None = None
    base_entity_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


# -------------------- Procedures --------------------

class ProcedureParam(BaseModel):
    name: str
    type: str
    direction: Literal["IN", "OUT", "INOUT"] = "IN"
    description: str | None = None


class ProcedureIn(BaseModel):
    system_id: str
    schema_name: str = Field(min_length=1)
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    behavior_desc: str | None = None
    parameters: list[ProcedureParam] = Field(default_factory=list)
    source_code: str | None = None
    dependent_systems: list[str] = Field(default_factory=list)
    change_risk_level: RiskLevel | None = None


class ProcedureListOut(BaseModel):
    procedure_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    change_risk_level: RiskLevel | None = None
    updated_at: datetime


class ProcedureOut(ProcedureListOut):
    behavior_desc: str | None = None
    parameters: list[ProcedureParam] = Field(default_factory=list)
    source_code: str | None = None
    dependent_systems: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by: str
    updated_by: str


# -------------------- Triggers --------------------

class TriggerIn(BaseModel):
    system_id: str
    schema_name: str = Field(min_length=1)
    technical_name: str = Field(min_length=1)
    associated_entity_id: str | None = None
    event_type: EventType | None = None
    timing: TriggerTiming | None = None
    body: str | None = None
    behavior_desc: str | None = None
    change_risk_level: RiskLevel | None = None


class TriggerListOut(BaseModel):
    trigger_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    associated_entity_id: str | None = None
    associated_entity_label: str | None = None
    event_type: EventType | None = None
    timing: TriggerTiming | None = None
    change_risk_level: RiskLevel | None = None
    updated_at: datetime


class TriggerOut(TriggerListOut):
    body: str | None = None
    behavior_desc: str | None = None
    created_at: datetime
    created_by: str
    updated_by: str


# -------------------- Sequences --------------------

class SequenceIn(BaseModel):
    system_id: str
    schema_name: str = Field(min_length=1)
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    description_md: str | None = None
    start_value: int | None = None
    increment_by: int | None = None
    min_value: int | None = None
    max_value: int | None = None
    cache_size: int | None = None
    is_cycle: bool | None = None
    current_value: int | None = None
    used_by_entity_ids: list[str] = Field(default_factory=list)


class SequenceListOut(BaseModel):
    sequence_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    increment_by: int | None = None
    current_value: int | None = None
    updated_at: datetime


class SequenceOut(SequenceListOut):
    description_md: str | None = None
    start_value: int | None = None
    min_value: int | None = None
    max_value: int | None = None
    cache_size: int | None = None
    is_cycle: bool | None = None
    used_by_entity_ids: list[str] = Field(default_factory=list)
    native_comment: str | None = None
    created_at: datetime
    created_by: str
    updated_by: str
