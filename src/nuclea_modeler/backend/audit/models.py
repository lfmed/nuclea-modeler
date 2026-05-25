"""Pydantic models for the audit log API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEntry(BaseModel):
    """Lightweight row for list/grid views."""

    audit_id: str
    occurred_at: datetime
    actor_email: str
    actor_role: str | None = None
    action: str
    object_type: str
    object_id: str | None = None
    request_id: str | None = None
    client_ip: str | None = None


class AuditDetailEntry(AuditEntry):
    """Full audit row including before/after payloads and user agent."""

    before_json: str | None = None
    after_json: str | None = None
    user_agent: str | None = None


class AuditCount(BaseModel):
    key: str
    count: int


class AuditStats(BaseModel):
    since: datetime
    until: datetime
    by_action: list[AuditCount]
    by_object_type: list[AuditCount]
    total: int
