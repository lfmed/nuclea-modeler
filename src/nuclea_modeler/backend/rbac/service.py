"""RBAC service — fetch and check user roles persisted in Delta `user_roles`."""
from __future__ import annotations

from functools import lru_cache
from typing import Final

from fastapi import HTTPException

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql


# Canonical role names. Keep in sync with the COMMENT in 005_tickets_and_roles.sql.
ROLE_DATA_ARCHITECT: Final = "DATA_ARCHITECT"
ROLE_DATA_STEWARD: Final = "DATA_STEWARD"
ROLE_DATA_ENGINEER: Final = "DATA_ENGINEER"
ROLE_CDE: Final = "CDE"
ROLE_ADMIN: Final = "ADMIN"

ALL_ROLES = (
    ROLE_DATA_ARCHITECT,
    ROLE_DATA_STEWARD,
    ROLE_DATA_ENGINEER,
    ROLE_CDE,
    ROLE_ADMIN,
)

# Permissions: who can approve reconciliation tickets
TICKET_APPROVERS = (ROLE_DATA_ARCHITECT, ROLE_DATA_STEWARD, ROLE_ADMIN)
TICKET_APPLIERS = (ROLE_DATA_ARCHITECT, ROLE_ADMIN)


def get_user_roles(sql: Sql, user_email: str) -> list[str]:
    """Return the active role names for a given user email."""
    if not user_email:
        return []
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"SELECT role_name FROM {s.fq_table('user_roles')} "
        f"WHERE user_email = :user_email AND is_active = true",
        [delta.param("user_email", user_email)],
    )
    return [r[0] for r in rows]


def has_role(sql: Sql, user_email: str, *required: str) -> bool:
    """Check if the user has at least one of the required roles."""
    if not required:
        return True
    roles = set(get_user_roles(sql, user_email))
    return any(r in roles for r in required)


def require_role(sql: Sql, user_email: str, *required: str) -> None:
    """Raise 403 if the user lacks all of `required`."""
    if has_role(sql, user_email, *required):
        return
    raise HTTPException(
        status_code=403,
        detail=(
            f"User '{user_email}' does not have any of the required roles: "
            f"{', '.join(required)}"
        ),
    )
