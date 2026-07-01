"""Sync engine — apply COMMENT/TAGS to Unity Catalog tables (Módulo 9).

For each entity in the source `system_id`, we resolve a target table
under `target_catalog.<mapped_schema>.<technical_name>` and emit:
  - COMMENT ON TABLE  (logical_name + description_md / native_comment)
  - COMMENT ON COLUMN (per attribute)
  - ALTER TABLE SET TAGS (domain / criticality / business_owner)

When `materialize=True` and the target does not exist, the table is CREATEd
in the destination catalog (Delta, type-mapped via the M10 Spark generator)
and the source entity is flagged as materialized (is_materialized /
materialized_at / materialized_catalog). When `materialize=False` (default,
classic M9) a missing target is recorded as SKIPPED. Per-object exceptions are
caught and recorded as ERROR, the rest of the run continues. Results are
persisted to `sync_log` (unless `dry_run=True`).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from ..ddl.generators import map_type
from .models import (
    SyncObjectResult,
    SyncRunRequest,
    SyncRunResult,
    SyncStatus,
)


# Identifier validator for catalog/schema/table/column names. UC accepts a
# wider grammar with backticks, but we restrict the app to ASCII identifiers
# so we can safely interpolate without quoting.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _require_ident(value: str, field: str) -> str:
    if not _IDENT_RE.match(value or ""):
        raise HTTPException(400, f"invalid {field}: must match {_IDENT_RE.pattern}")
    return value


def _esc(value: str | None) -> str:
    """Last-resort SQL-literal escape for places where parameters cannot be
    used. Only used for trusted internal values."""
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
    """Cheap existence check via DESCRIBE TABLE EXTENDED.

    `target_table` is built from validated identifiers (catalog.schema.table),
    so direct interpolation is safe.
    """
    try:
        delta.run(sql, f"DESCRIBE TABLE EXTENDED {target_table}")
        return True
    except Exception:
        return False


def _build_create_table_sql(sql: Sql, target_table: str, entity_id: str) -> str | None:
    """Monta um `CREATE TABLE IF NOT EXISTS ... USING DELTA` para materializar
    a entidade no catálogo destino.

    Reusa o type-mapping do gerador DDL Spark (M10) para manter os tipos o mais
    próximo possível do modelo. Comentários e tags são aplicados logo depois pelo
    bloco de sync (COMMENT ON / ALTER ... SET TAGS), então aqui só a estrutura.
    Retorna None quando a entidade não tem colunas válidas (nada a materializar).
    """
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT technical_name, native_data_type, is_nullable
        FROM {s.fq_table('attributes')}
        WHERE entity_id = :entity_id
        ORDER BY ordinal_position, technical_name
        """,
        [delta.param("entity_id", entity_id)],
    )
    cols: list[str] = []
    for tech_name, native_dt, is_nullable in rows:
        if not tech_name or not _IDENT_RE.match(tech_name):
            continue
        spark_type = map_type(native_dt, "SPARKSQL") or "STRING"
        null_clause = "" if (is_nullable is None or is_nullable) else " NOT NULL"
        cols.append(f"  {tech_name} {spark_type}{null_clause}")
    if not cols:
        return None
    return (
        f"CREATE TABLE IF NOT EXISTS {target_table} (\n"
        + ",\n".join(cols)
        + "\n) USING DELTA"
    )


def _mark_entity_materialized(sql: Sql, entity_id: str, target_catalog: str) -> None:
    """Grava na entity que ela foi materializada no catálogo destino (pedido #9)."""
    s = get_settings()
    delta.run_params(
        sql,
        f"""
        UPDATE {s.fq_table('entities')}
        SET is_materialized = true,
            materialized_at = current_timestamp(),
            materialized_catalog = :cat
        WHERE entity_id = :eid
        """,
        [delta.param("cat", target_catalog), delta.param("eid", entity_id)],
    )


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

    # Validate the catalog name once — it goes into every DDL we emit.
    _require_ident(payload.target_catalog, "target_catalog")
    schema_map: dict[str, str] = dict(payload.target_schema_map or {})

    # 1) Pull entities for the system
    ent_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, logical_name,
               description_md, native_comment, domain, criticality,
               business_owner
        FROM {s.fq_table('entities')}
        WHERE system_id = :system_id
        ORDER BY schema_name, technical_name
        """,
        [delta.param("system_id", payload.system_id)],
    )

    objects: list[SyncObjectResult] = []
    errors: list[str] = []
    objects_synced = 0
    objects_failed = 0
    objects_created = 0

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
        # Validate identifiers from the catalog before composing DDL. Entities
        # whose names violate the grammar are surfaced as ERROR.
        try:
            _require_ident(target_schema, "target_schema")
            _require_ident(technical_name, "technical_name")
        except HTTPException as exc:
            objects.append(
                SyncObjectResult(
                    schema_name=schema_name,
                    technical_name=technical_name,
                    target_table=f"{payload.target_catalog}.{target_schema}.{technical_name}",
                    status="ERROR",
                    message=exc.detail,
                )
            )
            objects_failed += 1
            continue

        target_table = f"{payload.target_catalog}.{target_schema}.{technical_name}"

        try:
            if not payload.dry_run:
                # Existence check. Se não existe: materializa (CREATE) quando
                # payload.materialize, senão marca SKIPPED (comportamento clássico).
                created = False
                if not _target_table_exists(sql, target_table):
                    if not payload.materialize:
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
                    create_sql = _build_create_table_sql(sql, target_table, entity_id)
                    if create_sql is None:
                        objects.append(
                            SyncObjectResult(
                                schema_name=schema_name,
                                technical_name=technical_name,
                                target_table=target_table,
                                status="ERROR",
                                message="entidade sem colunas — nada a materializar",
                            )
                        )
                        objects_failed += 1
                        continue
                    delta.run(sql, create_sql)
                    created = True

                # 2a) Table COMMENT — parameterise the body so quotes never break us
                tbl_comment = _trim(
                    _build_table_comment(logical_name, description_md, native_comment),
                    1000,
                )
                if tbl_comment:
                    delta.run_params(
                        sql,
                        f"COMMENT ON TABLE {target_table} IS :comment_body",
                        [delta.param("comment_body", tbl_comment)],
                    )

                # 2b) Column COMMENTs
                attr_rows = delta.fetch_all_params(
                    sql,
                    f"""
                    SELECT technical_name, logical_name, description_md, native_comment
                    FROM {s.fq_table('attributes')}
                    WHERE entity_id = :entity_id
                    """,
                    [delta.param("entity_id", entity_id)],
                )
                for ar in attr_rows:
                    col_name, col_logical, col_desc, col_native = ar
                    if not col_name:
                        continue
                    # Column name is an identifier — validate, don't quote.
                    if not _IDENT_RE.match(col_name):
                        errors.append(
                            f"{schema_name}.{technical_name}.{col_name}: "
                            "invalid column identifier; skipped"
                        )
                        continue
                    col_comment = _trim(
                        _build_column_comment(col_logical, col_desc, col_native),
                        1000,
                    )
                    if not col_comment:
                        continue
                    try:
                        delta.run_params(
                            sql,
                            f"ALTER TABLE {target_table} ALTER COLUMN "
                            f"{col_name} COMMENT :col_comment",
                            [delta.param("col_comment", col_comment)],
                        )
                    except Exception as col_exc:
                        # column-level errors don't fail the whole entity
                        errors.append(
                            f"{schema_name}.{technical_name}.{col_name}: {col_exc}"
                        )

                # 2c) TAGS — only set the ones with a value. SET TAGS requires
                # literal map syntax: ALTER TABLE x SET TAGS ('k' = 'v', ...).
                # Tag keys are constants we control; values may contain quotes
                # so we escape defensively.
                tag_kv: dict[str, str] = {}
                if domain:
                    tag_kv["uc.tag.domain"] = str(domain)
                if criticality:
                    tag_kv["uc.tag.criticality"] = str(criticality)
                if business_owner:
                    tag_kv["uc.tag.business_owner"] = str(business_owner)
                if tag_kv:
                    pairs = ", ".join(
                        f"'{_esc(k)}' = '{_esc(v)}'" for k, v in tag_kv.items()
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

                # Marca a entity como materializada (só no modo materialize).
                if payload.materialize:
                    try:
                        _mark_entity_materialized(sql, entity_id, payload.target_catalog)
                    except Exception as mk_exc:
                        errors.append(
                            f"{schema_name}.{technical_name} (flag materializado): {mk_exc}"
                        )
                objects.append(
                    SyncObjectResult(
                        schema_name=schema_name,
                        technical_name=technical_name,
                        target_table=target_table,
                        status="OK",
                        message=(
                            "materializada (tabela Delta criada)" if created
                            else ("sincronizada (materialize)" if payload.materialize else None)
                        ),
                    )
                )
                objects_synced += 1
                if created:
                    objects_created += 1
            else:
                # Dry-run: report what WOULD happen, no SQL executed
                objects.append(
                    SyncObjectResult(
                        schema_name=schema_name,
                        technical_name=technical_name,
                        target_table=target_table,
                        status="OK",
                        message=(
                            "dry-run: materializaria a tabela se não existir"
                            if payload.materialize
                            else "dry-run (no changes applied)"
                        ),
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
        objects_created=objects_created,
        duration_ms=duration_ms,
        target_catalog=payload.target_catalog,
        dry_run=payload.dry_run,
        materialize=payload.materialize,
        errors=errors,
        objects=objects,
    )


def list_runs(sql: Sql, limit: int = 50) -> list[dict[str, Any]]:
    s = get_settings()
    safe_limit = max(1, min(int(limit), 500))
    rows = delta.fetch_all(
        sql,
        f"""
        SELECT sync_id, system_id, started_at, ended_at, status,
               objects_total, objects_synced, objects_failed,
               duration_ms, target_catalog, triggered_by, error_summary
        FROM {s.fq_table('sync_log')}
        ORDER BY started_at DESC
        LIMIT {safe_limit}
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
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT sync_id, version_id, system_id, started_at, ended_at, status,
               objects_total, objects_synced, objects_failed,
               duration_ms, target_catalog, triggered_by, error_summary,
               details_json
        FROM {s.fq_table('sync_log')}
        WHERE sync_id = :sync_id
        """,
        [delta.param("sync_id", sync_id)],
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
