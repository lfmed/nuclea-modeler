"""Model Versions HTTP endpoints — list / get / publish / restore / diff."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, ROLE_DATA_ARCHITECT, require_role
from .models import (
    PublishRequest,
    VersionDiff,
    VersionListOut,
    VersionOut,
)
from .service import (
    _get_version,
    compute_diff,
    deprecate_version,
    publish_version,
    restore_version,
)

router = APIRouter(prefix=f"{api_prefix}/versions", tags=["versions"])

_PUBLISH_ROLES = (ROLE_DATA_ARCHITECT, ROLE_ADMIN)


@router.get("", response_model=list[VersionListOut], operation_id="listVersions")
def list_versions(
    sql: SqlDependency,
    system_id: str | None = Query(None),
) -> list[VersionListOut]:
    s = get_settings()
    where = ""
    if system_id:
        safe = system_id.replace("'", "''")
        where = f"WHERE v.system_id = '{safe}'"

    rows = delta.fetch_all(
        sql,
        f"""
        SELECT v.version_id, v.system_id, sys.system_name, v.version_number,
               v.title, v.status, v.published_at, v.published_by,
               v.created_at, v.created_by
        FROM {s.fq_table('model_versions')} v
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = v.system_id
        {where}
        ORDER BY COALESCE(v.published_at, v.created_at) DESC,
                 v.created_at DESC
        LIMIT 100
        """,
    )
    return [
        VersionListOut(
            version_id=r[0],
            system_id=r[1],
            system_name=r[2],
            version_number=r[3],
            title=r[4],
            status=r[5],
            published_at=r[6],
            published_by=r[7],
            created_at=r[8],
            created_by=r[9],
        )
        for r in rows
    ]


@router.get("/diff", response_model=VersionDiff, operation_id="versionDiff")
def get_diff(
    sql: SqlDependency,
    from_: str = Query(..., alias="from", min_length=1),
    to: str = Query(..., min_length=1),
) -> VersionDiff:
    if from_ == to:
        raise HTTPException(400, "from and to versions must be different")
    return compute_diff(sql, from_, to)


@router.get("/{version_id}", response_model=VersionOut, operation_id="getVersion")
def get_version(version_id: str, sql: SqlDependency) -> VersionOut:
    return _get_version(sql, version_id)


@router.post("/publish", response_model=VersionOut, operation_id="publishVersion")
def publish(
    payload: PublishRequest,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> VersionOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *_PUBLISH_ROLES)
    return publish_version(
        sql,
        system_id=payload.system_id,
        title=payload.title,
        changelog=payload.changelog,
        make_active=payload.make_active,
        actor=actor or "unknown",
    )


@router.post(
    "/{version_id}/restore",
    response_model=VersionOut,
    operation_id="restoreVersion",
)
def restore(
    version_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> VersionOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *_PUBLISH_ROLES)
    return restore_version(sql, version_id, actor or "unknown")


@router.post(
    "/{version_id}/deprecate",
    response_model=VersionOut,
    operation_id="deprecateVersion",
)
def deprecate(
    version_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> VersionOut:
    actor = _current_email(user_ws)
    require_role(sql, actor, *_PUBLISH_ROLES)
    return deprecate_version(sql, version_id, actor or "unknown")
