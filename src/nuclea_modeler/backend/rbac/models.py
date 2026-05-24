"""Pydantic models for RBAC."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RoleName = Literal[
    "DATA_ARCHITECT", "DATA_STEWARD", "DATA_ENGINEER", "CDE", "ADMIN"
]


class UserRoleIn(BaseModel):
    user_email: str = Field(min_length=3)
    role_name: RoleName


class UserRoleOut(BaseModel):
    user_role_id: str
    user_email: str
    role_name: RoleName
    granted_at: datetime
    granted_by: str
    is_active: bool


class MyRolesOut(BaseModel):
    user_email: str
    roles: list[RoleName]
    can_approve_tickets: bool
    can_apply_tickets: bool
    can_create_connections: bool
    is_admin: bool
