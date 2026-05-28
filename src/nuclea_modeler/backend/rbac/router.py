"""RBAC HTTP endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from .models import MyRolesOut, UserRoleIn, UserRoleOut
from .service import (
    ROLE_ADMIN,
    ROLE_DATA_ENGINEER,
    TICKET_APPLIERS,
    TICKET_APPROVERS,
    get_user_roles,
    require_role,
)

router = APIRouter(prefix=f"{api_prefix}/rbac", tags=["rbac"])


def _current_email(user_ws: Dependencies.UserClient) -> str:
    try:
        me = user_ws.current_user.me()
        if me.user_name:
            return me.user_name
        if me.emails:
            primary = next((e for e in me.emails if e.primary), None)
            if primary and primary.value:
                return primary.value
            return me.emails[0].value or ""
        return me.display_name or ""
    except Exception:
        return ""


@router.get("/me", response_model=MyRolesOut, operation_id="myRoles")
def my_roles(sql: SqlDependency, user_ws: Dependencies.UserClient) -> MyRolesOut:
    email = _current_email(user_ws)
    roles = get_user_roles(sql, email)
    return MyRolesOut(
        user_email=email,
        roles=roles,  # type: ignore[arg-type]
        can_approve_tickets=any(r in TICKET_APPROVERS for r in roles),
        can_apply_tickets=any(r in TICKET_APPLIERS for r in roles),
        can_create_connections=any(
            r in (ROLE_DATA_ENGINEER, ROLE_ADMIN) for r in roles
        ),
        is_admin=ROLE_ADMIN in roles,
    )


@router.get("", response_model=list[UserRoleOut], operation_id="listRoles")
def list_roles(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> list[UserRoleOut]:
    require_role(sql, _current_email(user_ws), ROLE_ADMIN)
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT user_role_id, user_email, role_name, granted_at, granted_by, is_active
        FROM {s.fq_table('user_roles')}
        WHERE is_active = true
        ORDER BY user_email, role_name
        """,
    )
    return [
        UserRoleOut(
            user_role_id=r[0], user_email=r[1], role_name=r[2],
            granted_at=r[3], granted_by=r[4], is_active=bool(r[5]),
        )
        for r in rows
    ]


@router.post("", response_model=UserRoleOut, operation_id="grantRole")
def grant_role(
    payload: UserRoleIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> UserRoleOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_ADMIN)
    s = get_settings()
    rid = delta.new_id("role-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("user_roles"),
        {
            "user_role_id": rid,
            "user_email": payload.user_email,
            "role_name": payload.role_name,
            "granted_at": now,
            "granted_by": actor,
            "is_active": True,
        },
    )
    return UserRoleOut(
        user_role_id=rid,
        user_email=payload.user_email,
        role_name=payload.role_name,  # type: ignore[arg-type]
        granted_at=now,
        granted_by=actor,
        is_active=True,
    )


@router.delete("/{user_role_id}", operation_id="revokeRole")
def revoke_role(
    user_role_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_ADMIN)
    s = get_settings()
    delta.update_by_id(
        sql,
        s.fq_table("user_roles"),
        "user_role_id",
        user_role_id,
        {"is_active": False},
    )
    return {"revoked": user_role_id}
