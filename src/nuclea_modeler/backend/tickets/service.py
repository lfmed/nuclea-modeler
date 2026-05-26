"""Ticket service — application logic for opening, approving, applying tickets."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import TicketApplyResult, TicketDiff, TicketSource


def open_ticket(
    sql: Sql,
    *,
    title: str,
    system_id: str,
    source_type: TicketSource,
    diff: TicketDiff,
    extraction_id: str | None = None,
    summary_md: str | None = None,
    created_by: str,
) -> str:
    """Persist a new ticket in OPEN status. Returns the ticket_id."""
    s = get_settings()
    tid = delta.new_id("ticket-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("reconciliation_tickets"),
        {
            "ticket_id": tid,
            "title": title,
            "system_id": system_id,
            "extraction_id": extraction_id,
            "source_type": source_type,
            "status": "OPEN",
            "summary_md": summary_md,
            "diff_json": json.dumps(diff.model_dump(), default=str, ensure_ascii=False),
            "additions_count": diff.additions or len([e for e in diff.entities if e.op == "add"]),
            "removals_count": diff.removals or len([e for e in diff.entities if e.op == "remove"]),
            "changes_count": diff.changes or len([e for e in diff.entities if e.op == "change"]),
            "created_at": now,
            "created_by": created_by,
        },
    )
    return tid


def apply_ticket(sql: Sql, ticket_id: str, applied_by: str) -> TicketApplyResult:
    """Apply the diff in the ticket to the entities/attributes catalog.

    Idempotent at the entity level: existing entities with same (system_id,
    schema_name, technical_name) are skipped on `add` ops.
    """
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT diff_json, system_id, status FROM {s.fq_table('reconciliation_tickets')} "
        f"WHERE ticket_id = :ticket_id",
        [delta.param("ticket_id", ticket_id)],
    )
    if not row:
        return TicketApplyResult(ticket_id=ticket_id, status="OPEN",
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"ticket '{ticket_id}' not found"])
    diff_json, system_id, status = row
    if status != "APPROVED":
        return TicketApplyResult(ticket_id=ticket_id, status=status,
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"ticket must be APPROVED to apply (current: {status})"])
    try:
        diff = json.loads(diff_json) if diff_json else {"entities": []}
    except json.JSONDecodeError as exc:
        return TicketApplyResult(ticket_id=ticket_id, status=status,
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"invalid diff_json: {exc}"])

    applied_entities = 0
    applied_attributes = 0
    errors: list[str] = []
    now = datetime.utcnow()

    for ent_change in diff.get("entities", []):
        op = ent_change.get("op")
        schema_name = ent_change.get("schema_name", "")
        technical_name = ent_change.get("technical_name", "")
        try:
            if op == "add":
                # Skip if an entity with same key already exists
                existing = delta.fetch_one_params(
                    sql,
                    f"SELECT entity_id FROM {s.fq_table('entities')} "
                    f"WHERE system_id = :system_id "
                    f"AND schema_name = :schema_name "
                    f"AND technical_name = :technical_name",
                    [
                        delta.param("system_id", system_id),
                        delta.param("schema_name", schema_name),
                        delta.param("technical_name", technical_name),
                    ],
                )
                if existing:
                    continue
                payload = ent_change.get("payload") or {}
                eid = delta.new_id("ent-")
                delta.insert(
                    sql,
                    s.fq_table("entities"),
                    {
                        "entity_id": eid,
                        "system_id": system_id,
                        "schema_name": schema_name,
                        "technical_name": technical_name,
                        "logical_name": payload.get("logical_name"),
                        "description_md": payload.get("description_md") or payload.get("native_comment"),
                        "domain": payload.get("domain"),
                        "entity_type": ent_change.get("entity_type", "TABLE"),
                        "native_comment": payload.get("native_comment"),
                        "row_count_approx": payload.get("row_count_approx"),
                        "tags": payload.get("tags", []),
                        "last_extracted_at": now,
                        "created_at": now, "created_by": applied_by,
                        "updated_at": now, "updated_by": applied_by,
                    },
                )
                applied_entities += 1
                # Insert attributes (if provided in `attributes`)
                for idx, attr in enumerate(ent_change.get("attributes") or []):
                    aid = delta.new_id("attr-")
                    delta.insert(
                        sql,
                        s.fq_table("attributes"),
                        {
                            "attribute_id": aid,
                            "entity_id": eid,
                            "technical_name": attr.get("technical_name", ""),
                            "logical_name": attr.get("logical_name"),
                            "ordinal_position": attr.get("ordinal_position", idx + 1),
                            "native_data_type": attr.get("native_data_type"),
                            "is_nullable": attr.get("is_nullable"),
                            "default_value": attr.get("default_value"),
                            "is_primary_key": bool(attr.get("is_primary_key", False)),
                            "native_comment": attr.get("native_comment"),
                            "created_at": now, "created_by": applied_by,
                            "updated_at": now, "updated_by": applied_by,
                        },
                    )
                    applied_attributes += 1
            elif op == "remove":
                # Soft remove: just mark? For now, leave existing data alone but log.
                # Future: introduce a `deprecated_at` column.
                errors.append(
                    f"remove of {schema_name}.{technical_name} not auto-applied "
                    "(soft-delete not implemented; remove manually from /entities)."
                )
            elif op == "change":
                # Apply field-level changes when target entity exists
                existing = delta.fetch_one_params(
                    sql,
                    f"SELECT entity_id FROM {s.fq_table('entities')} "
                    f"WHERE system_id = :system_id "
                    f"AND schema_name = :schema_name "
                    f"AND technical_name = :technical_name",
                    [
                        delta.param("system_id", system_id),
                        delta.param("schema_name", schema_name),
                        delta.param("technical_name", technical_name),
                    ],
                )
                if not existing:
                    errors.append(f"change target not found: {schema_name}.{technical_name}")
                    continue
                eid = existing[0]
                updates: dict[str, Any] = {}
                for fc in ent_change.get("field_changes") or []:
                    fld = fc.get("field")
                    new_val = fc.get("after")
                    if fld in {"logical_name", "description_md", "native_comment", "row_count_approx", "domain"}:
                        updates[fld] = new_val
                if updates:
                    updates["updated_at"] = now
                    updates["updated_by"] = applied_by
                    updates["last_extracted_at"] = now
                    delta.update_by_id(sql, s.fq_table("entities"), "entity_id", eid, updates)
                    applied_entities += 1
        except Exception as exc:  # keep going on per-entity errors
            errors.append(f"{op} {schema_name}.{technical_name}: {exc}")

    # Update ticket status to APPLIED (or stay APPROVED if all errored)
    final_status = "APPLIED"
    delta.update_by_id(
        sql,
        s.fq_table("reconciliation_tickets"),
        "ticket_id",
        ticket_id,
        {
            "status": final_status,
            "applied_at": now,
            "applied_by": applied_by,
        },
    )
    return TicketApplyResult(
        ticket_id=ticket_id,
        status=final_status,
        applied_entities=applied_entities,
        applied_attributes=applied_attributes,
        errors=errors,
    )
