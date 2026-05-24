"""Pydantic models for Reconciliation Tickets."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TicketStatus = Literal["OPEN", "APPROVED", "APPLIED", "REJECTED"]
TicketSource = Literal["REVERSE_ENG", "DDL_IMPORT", "LAKEBASE_ROUNDTRIP", "MANUAL"]


class DiffEntity(BaseModel):
    """One entity change inside the diff."""

    op: Literal["add", "remove", "change"]
    schema_name: str
    technical_name: str
    entity_type: str = "TABLE"
    # When op=add: full payload to materialize
    payload: dict[str, Any] | None = None
    # When op=change: list of field-level changes
    field_changes: list[dict[str, Any]] | None = None
    # When op=add: list of attributes (columns) to create with the entity
    attributes: list[dict[str, Any]] | None = None


class TicketDiff(BaseModel):
    """Structured diff payload — what the ticket asks to change."""

    entities: list[DiffEntity] = Field(default_factory=list)
    # Counters (denormalized on the ticket row for quick listings)
    additions: int = 0
    removals: int = 0
    changes: int = 0


class TicketIn(BaseModel):
    """Payload to open a ticket manually (eng. reversa abre internamente)."""

    title: str
    system_id: str
    source_type: TicketSource = "MANUAL"
    extraction_id: str | None = None
    summary_md: str | None = None
    diff: TicketDiff


class TicketListOut(BaseModel):
    ticket_id: str
    title: str
    system_id: str
    system_name: str | None = None
    source_type: TicketSource
    status: TicketStatus
    additions_count: int
    removals_count: int
    changes_count: int
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    applied_at: datetime | None = None


class TicketOut(BaseModel):
    ticket_id: str
    title: str
    system_id: str
    system_name: str | None = None
    extraction_id: str | None = None
    source_type: TicketSource
    status: TicketStatus
    summary_md: str | None = None
    diff: TicketDiff
    additions_count: int
    removals_count: int
    changes_count: int
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    applied_at: datetime | None = None
    applied_by: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    target_version_id: str | None = None


class TicketApprove(BaseModel):
    note: str | None = None


class TicketReject(BaseModel):
    reason: str = Field(min_length=1)


class TicketApplyResult(BaseModel):
    ticket_id: str
    status: TicketStatus
    applied_entities: int
    applied_attributes: int
    errors: list[str] = Field(default_factory=list)
