"""Sync engine — apply COMMENT/TAGS to Unity Catalog tables (Módulo 9).

For each entity in the source `system_id`, we resolve a target table
under `target_catalog.<mapped_schema>.<technical_name>` and emit:
  - COMMENT ON TABLE  (logical_name + description_md / native_comment)
  - COMMENT ON COLUMN (per attribute)
  - ALTER TABLE SET TAGS (domain / criticality / business_owner)

The function never creates tables — when a target does not exist it is
recorded as SKIPPED. Per-object exceptions are caught and recorded as
ERROR, the rest of the run continues. Results are persisted to
`sync_log` (unless `dry_run=True`).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import (
    SyncObjectResult,
    SyncRunRequest,
    SyncRunResult,
    SyncStatus,
)


def _q(value: str | None) -> str:
    """Escape a value for safe inlining inside a SQL single-quoted literal."""
    return (value or "").replace("'", "''")


def _trim(value: str | None, limit: int = 1000) -> str | None:
    if value is None:
        return None
    v = str(value)
    return v if len(v) <= limit else v[: limit - 3] + "..."


def _build_table_comment(logical_name: str | None, description_md: str | None,
                         native_comment: str | None) -> str:
    """Compose the COMMENT ON TABLE body."""
    body = description_md or native_comment or ""
    if logical_name:
        return f"{logical_name}: {body}" if body else logical_name
    return body


def _build_column_comment(logical_name: str | None, description_md: str | None,
                          native_comment: str | None) -> str:
    body = description_md or native_comment or ""
    if logical_name:
        return f"{logical_name}: {body}" if body else logical_name
    return body


def _target_table_exists(sql: Sql, target_table: str) -> bool:
    """Cheap existence check via DESCRIBE TABLE EXTENDED."""
    try:
        delta.run(sql, f"DESCRIBE TABLE EXTENDED {target_table}")
        return True
    except Exception:
        return False


def _classify_status(objects_total: int, objects_failed: int,
                     objects_synced: int) -> SyncStatus:
    if objects_total == 0:
        return "SUCCESS"
    if objects_failed == 0:
        return "SUCCESS"
    if objects_synced == 0:
        return "FAILED"
    return "PARTIAL"


def run_sync(
    sql: Sql,
    payload: SyncRunRequest,
    actor: str,
) -> SyncRunResult:
    """Execute (or preview) a sync run for `payload.system_id`."""
    s = get_settings()
    started_at = datetime.utcnow()
    t0 = time.perf_counter()
    sync_id = delta.new_id("sync-")

    schema_map: dict[str, str] = dict(payload.target_schema_map or {})

    # 1) Pull entities for the system
    ent_rows = delta.fetch_all(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, logical_name,
               description_md, native_comment, domain, criticality,
               business_owner
        FROM {s.fq_table('entities')}
        WHERE system_id = '{_q(payload.system_id)}'
        ORDER BY schema_name, technical_name
        """,
    )

    objects: list[SyncObjectResult] = []
    errors: list[str] = []
    objects_synced = 0
    objects_failed = 0

    for r in ent_rows:
        (
            entity_id,
            schema_name,
            technical_name,
            logical_name,
            description_md,
            native_comment,
            domain,
            criticality,
            business_owner,
        ) = r

        target_schema = schema_map.get(schema_name, schema_name)
        target_table = f"{payload.target_catalog}.{target_schema}.{technical_name}"

        try:
            if not payload.dry_run:
                # Existence check — skip non-existent targets gracefully
                if not _target_table_exists(sql, target_table):
                    objects.append(
                        SyncObjectResult(
                            schema_name=schema_name,
                            technical_name=technical_name,
                            target_table=target_table,
                            status="SKIPPED",
                            message="target table not found in Unity Catalog",
                        )
                    )
                    continue

                # 2a) Table COMMENT
                tbl_comment = _trim(
                    _build_table_comment(logical_name, description_md, native_comment),
                    1000,
                )
                if tbl_comment:
                    delta.run(
                        sql,
                        f"COMMENT ON TABLE {target_table} IS '{_q(tbl_comment)}'",
                    )

                # 2b) Column COMMENTs
                attr_rows = delta.fetch_all(
                    sql,
                    f"""
                    SELECT technical_name, logical_name, description_md, native_comment
                    FROM {s.fq_table('attributes')}
                    WHERE entity_id = '{_q(entity_id)}'
                    """,
                )
                for ar in attr_rows:
                    col_name, col_logical, col_desc, col_native = ar
                    if not col_name:
                        continue
                    col_comment = _trim(
                        _build_column_comment(col_logical, col_desc, col_native),
                        1000,
                    )
                    if not col_comment:
                        continue
                    try:
                        delta.run(
                            sql,
                            f"ALTER TABLE {target_table} ALTER COLUMN "
                            f"{col_name} COMMENT '{_q(col_comment)}'",
                        )
                    except Exception as col_exc:
                        # column-level errors don't fail the whole entity
                        errors.append(
                            f"{schema_name}.{technical_name}.{col_name}: {col_exc}"
                        )

                # 2c) TAGS — only set the ones with a value
                tag_kv: dict[str, str] = {}
                if domain:
                    tag_kv["uc.tag.domain"] = str(domain)
                if criticality:
                    tag_kv["uc.tag.criticality"] = str(criticality)
                if business_owner:
                    tag_kv["uc.tag.business_owner"] = str(business_owner)
                if tag_kv:
                    pairs = ", ".join(
                        f"'{_q(k)}' = '{_q(v)}'" for k, v in tag_kv.items()
                    )
                    try:
                        delta.run(
                            sql,
                            f"ALTER TABLE {target_table} SET TAGS ({pairs})",
                        )
                    except Exception as tag_exc:
                        errors.append(
                            f"{schema_name}.{technical_name} (tags): {tag_exc}"
                        )

                objects.append(
                    SyncObjectResult(
                        schema_name=schema_name,
                        technical_name=technical_name,
                        target_table=target_table,
                        status="OK",
                        message=None,
                    )
                )
                objects_synced += 1
            else:
                # Dry-run: report what WOULD happen, no SQL executed
                objects.append(
                    SyncObjectResult(
                        schema_name=schema_name,
                        technical_name=technical_name,
                        target_table=target_table,
                        status="OK",
                        message="dry-run (no changes applied)",
                    )
                )
                objects_synced += 1
        except Exception as exc:  # per-object failure: keep going
            msg = f"{schema_name}.{technical_name}: {exc}"
            errors.append(msg)
            objects.append(
                SyncObjectResult(
                    schema_name=schema_name,
                    technical_name=technical_name,
                    target_table=target_table,
                    status="ERROR",
                    message=str(exc),
                )
            )
            objects_failed += 1

    objects_total = len(objects)
    status = _classify_status(objects_total, objects_failed, objects_synced)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    ended_at = datetime.utcnow()

    # 3) Persist sync_log (apply runs only — previews are stateless)
    if not payload.dry_run:
        try:
            error_summary = "; ".join(errors)[:1000] if errors else None
            details_json = json.dumps(
                {"objects": [o.model_dump() for o in objects]},
                default=str,
                ensure_ascii=False,
            )
            delta.insert(
                sql,
                s.fq_table("sync_log"),
                {
                    "sync_id": sync_id,
                    "version_id": payload.system_id,  # no versions module yet (M5 stub)
                    "system_id": payload.system_id,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "status": status,
                    "objects_total": objects_total,
                    "objects_synced": objects_synced,
                    "objects_failed": objects_failed,
                    "duration_ms": duration_ms,
                    "target_catalog": payload.target_catalog,
                    "triggered_by": actor,
                    "error_summary": error_summary,
                    "details_json": details_json,
                },
            )
        except Exception as log_exc:
            errors.append(f"failed to persist sync_log: {log_exc}")

    return SyncRunResult(
        sync_id=sync_id,
        status=status,
        objects_total=objects_total,
        objects_synced=objects_synced,
        objects_failed=objects_failed,
        duration_ms=duration_ms,
        target_catalog=payload.target_catalog,
        dry_run=payload.dry_run,
        errors=errors,
        objects=objects,
    )


def list_runs(sql: Sql, limit: int = 50) -> list[dict[str, Any]]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT sync_id, system_id, started_at, ended_at, status,
               objects_total, objects_synced, objects_failed,
               duration_ms, target_catalog, triggered_by, error_summary
        FROM {s.fq_table('sync_log')}
        ORDER BY started_at DESC
        LIMIT {int(limit)}
        """,
    )
    return [
        {
            "sync_id": r[0],
            "system_id": r[1],
            "started_at": r[2],
            "ended_at": r[3],
            "status": r[4],
            "objects_total": int(r[5]) if r[5] is not None else None,
            "objects_synced": int(r[6]) if r[6] is not None else None,
            "objects_failed": int(r[7]) if r[7] is not None else None,
            "duration_ms": int(r[8]) if r[8] is not None else None,
            "target_catalog": r[9],
            "triggered_by": r[10],
            "error_summary": r[11],
        }
        for r in rows
    ]


def get_run(sql: Sql, sync_id: str) -> dict[str, Any] | None:
    s = get_settings()
    row = delta.fetch_one(
        sql,
        f"""
        SELECT sync_id, version_id, system_id, started_at, ended_at, status,
               objects_total, objects_synced, objects_failed,
               duration_ms, target_catalog, triggered_by, error_summary,
               details_json
        FROM {s.fq_table('sync_log')}
        WHERE sync_id = '{_q(sync_id)}'
        """,
    )
    if not row:
        return None
    objects: list[SyncObjectResult] = []
    try:
        details = json.loads(row[13]) if row[13] else {}
        for obj in details.get("objects", []) or []:
            try:
                objects.append(SyncObjectResult(**obj))
            except Exception:
                continue
    except Exception:
        pass
    return {
        "sync_id": row[0],
        "version_id": row[1],
        "system_id": row[2],
        "started_at": row[3],
        "ended_at": row[4],
        "status": row[5],
        "objects_total": int(row[6]) if row[6] is not None else None,
        "objects_synced": int(row[7]) if row[7] is not None else None,
        "objects_failed": int(row[8]) if row[8] is not None else None,
        "duration_ms": int(row[9]) if row[9] is not None else None,
        "target_catalog": row[10],
        "triggered_by": row[11],
        "error_summary": row[12],
        "objects": objects,
    }
