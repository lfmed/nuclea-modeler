"""Model Versioning service — snapshot, publish, diff, restore."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import DiffEntry, VersionDiff, VersionOut


# Entity-level fields tracked for change detection.
_ENTITY_DIFF_FIELDS = (
    "logical_name",
    "description_md",
    "domain",
    "criticality",
    "business_owner",
    "entity_type",
    "native_comment",
)

# Attribute-level fields tracked for change detection.
_ATTR_DIFF_FIELDS = (
    "native_data_type",
    "is_nullable",
    "default_value",
    "is_primary_key",
    "logical_name",
    "description_md",
)


def _quote_id(value: str) -> str:
    """Quote a trusted ID (from a prior DB query) for inlining in an IN list."""
    return "'" + (value or "").replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def build_snapshot(sql: Sql, system_id: str) -> dict[str, Any]:
    """Build an immutable, comparison-friendly snapshot of the current model.

    Returns a dict with stable key ordering and volatile fields stripped, so
    that two equivalent snapshots compare equal.
    """
    s = get_settings()

    ent_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT entity_id, system_id, schema_name, technical_name, logical_name,
               description_md, domain, business_owner, technical_owner,
               criticality, tags, notes, entity_type, native_comment,
               row_count_approx
        FROM {s.fq_table('entities')}
        WHERE system_id = :system_id
        ORDER BY schema_name, technical_name
        """,
        [delta.param("system_id", system_id)],
    )
    entities = []
    entity_ids: list[str] = []
    for r in ent_rows:
        entities.append({
            "entity_id": r[0],
            "system_id": r[1],
            "schema_name": r[2],
            "technical_name": r[3],
            "logical_name": r[4],
            "description_md": r[5],
            "domain": r[6],
            "business_owner": r[7],
            "technical_owner": r[8],
            "criticality": r[9],
            "tags": list(r[10]) if r[10] else [],
            "notes": r[11],
            "entity_type": r[12] or "TABLE",
            "native_comment": r[13],
            "row_count_approx": r[14],
        })
        entity_ids.append(r[0])

    attributes_by_entity: dict[str, list[dict[str, Any]]] = {}
    if entity_ids:
        # entity_ids come from the trusted DB query above — safe to inline.
        ids_in = ", ".join(_quote_id(eid) for eid in entity_ids)
        attr_rows = delta.fetch_all(
            sql,
            f"""
            SELECT attribute_id, entity_id, technical_name, logical_name,
                   ordinal_position, native_data_type, is_nullable,
                   default_value, is_primary_key, description_md,
                   business_rule, sample_value, glossary_term_id,
                   native_comment
            FROM {s.fq_table('attributes')}
            WHERE entity_id IN ({ids_in})
            ORDER BY entity_id, COALESCE(ordinal_position, 999999), technical_name
            """,
        )
        for r in attr_rows:
            attributes_by_entity.setdefault(r[1], []).append({
                "attribute_id": r[0],
                "entity_id": r[1],
                "technical_name": r[2],
                "logical_name": r[3],
                "ordinal_position": r[4],
                "native_data_type": r[5],
                "is_nullable": delta.as_bool(r[6]) if r[6] is not None else None,
                "default_value": r[7],
                "is_primary_key": delta.as_bool(r[8]) if r[8] is not None else False,
                "description_md": r[9],
                "business_rule": r[10],
                "sample_value": r[11],
                "glossary_term_id": r[12],
                "native_comment": r[13],
            })

    rel_rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT relationship_id, system_id, source_entity_id, target_entity_id,
               source_attr_ids, target_attr_ids, rel_type, source_cardinality,
               target_cardinality, description, origin
        FROM {s.fq_table('relationships')}
        WHERE system_id = :system_id
        ORDER BY relationship_id
        """,
        [delta.param("system_id", system_id)],
    )
    relationships = [
        {
            "relationship_id": r[0],
            "system_id": r[1],
            "source_entity_id": r[2],
            "target_entity_id": r[3],
            "source_attr_ids": list(r[4]) if r[4] else [],
            "target_attr_ids": list(r[5]) if r[5] else [],
            "rel_type": r[6],
            "source_cardinality": r[7],
            "target_cardinality": r[8],
            "description": r[9],
            "origin": r[10],
        }
        for r in rel_rows
    ]

    views_rows: list[list[Any]] = []
    if entity_ids:
        ids_in = ", ".join(_quote_id(eid) for eid in entity_ids)
        views_rows = delta.fetch_all(
            sql,
            f"""
            SELECT view_entity_id, purpose, definition_sql, base_entity_ids
            FROM {s.fq_table('views_catalog')}
            WHERE view_entity_id IN ({ids_in})
            ORDER BY view_entity_id
            """,
        )
    views = [
        {
            "view_entity_id": r[0],
            "purpose": r[1],
            "definition_sql": r[2],
            "base_entity_ids": list(r[3]) if r[3] else [],
        }
        for r in views_rows
    ]

    return {
        "system_id": system_id,
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "entities": entities,
        "attributes_by_entity": attributes_by_entity,
        "relationships": relationships,
        "views": views,
    }


# ---------------------------------------------------------------------------
# Version numbering
# ---------------------------------------------------------------------------

def next_version_number(sql: Sql, system_id: str) -> str:
    """Compute the next vMAJOR.MINOR number for the given system."""
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT version_number
        FROM {s.fq_table('model_versions')}
        WHERE system_id = :system_id
        """,
        [delta.param("system_id", system_id)],
    )
    best_major = 0
    best_minor = -1
    for r in rows:
        v = (r[0] or "").strip().lstrip("vV")
        if not v:
            continue
        parts = v.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            continue
        if (major, minor) > (best_major, best_minor):
            best_major, best_minor = major, minor
    if best_minor < 0:
        return "v1.0"
    return f"v{best_major}.{best_minor + 1}"


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def publish_version(
    sql: Sql,
    *,
    system_id: str,
    title: str,
    changelog: str,
    make_active: bool,
    actor: str,
) -> VersionOut:
    """Persist a new model version (snapshot of current state)."""
    s = get_settings()

    # Ensure the system exists (better error than a silent insert)
    sys_row = delta.fetch_one_params(
        sql,
        f"SELECT system_id FROM {s.fq_table('systems')} "
        f"WHERE system_id = :system_id",
        [delta.param("system_id", system_id)],
    )
    if not sys_row:
        raise HTTPException(404, f"system '{system_id}' not found")

    snapshot = build_snapshot(sql, system_id)
    vid = delta.new_id("ver-")
    now = datetime.utcnow()
    version_number = next_version_number(sql, system_id)

    if make_active:
        # Demote any ACTIVE version of this system to PUBLISHED.
        delta.run_params(
            sql,
            f"UPDATE {s.fq_table('model_versions')} "
            f"SET status = 'PUBLISHED', updated_at = current_timestamp(), "
            f"    updated_by = :actor "
            f"WHERE system_id = :system_id AND status = 'ACTIVE'",
            [
                delta.param("actor", actor),
                delta.param("system_id", system_id),
            ],
        )

    status = "ACTIVE" if make_active else "PUBLISHED"
    delta.insert(
        sql,
        s.fq_table("model_versions"),
        {
            "version_id": vid,
            "system_id": system_id,
            "version_number": version_number,
            "title": title,
            "changelog": changelog,
            "status": status,
            "published_at": now,
            "published_by": actor,
            "snapshot_json": json.dumps(snapshot, ensure_ascii=False, default=str),
            "based_on_version": None,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return _get_version(sql, vid)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def _entity_key(e: dict[str, Any]) -> str:
    return f"{e.get('schema_name', '')}.{e.get('technical_name', '')}"


def _index_entities(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_entity_key(e): e for e in snapshot.get("entities", [])}


def _index_attrs(snapshot: dict[str, Any], entity_id: str) -> dict[str, dict[str, Any]]:
    items = (snapshot.get("attributes_by_entity") or {}).get(entity_id) or []
    return {a.get("technical_name", ""): a for a in items}


def compute_diff(sql: Sql, from_version_id: str, to_version_id: str) -> VersionDiff:
    """Compare two snapshots and produce categorized diff entries."""
    snap_from = _load_snapshot(sql, from_version_id)
    snap_to = _load_snapshot(sql, to_version_id)

    from_idx = _index_entities(snap_from)
    to_idx = _index_entities(snap_to)

    additions: list[DiffEntry] = []
    removals: list[DiffEntry] = []
    changes: list[DiffEntry] = []

    # Entity-level diffs
    from_keys = set(from_idx.keys())
    to_keys = set(to_idx.keys())

    for k in sorted(to_keys - from_keys):
        ent = to_idx[k]
        additions.append(DiffEntry(
            type="entity_added",
            entity_key=k,
            after={f: ent.get(f) for f in _ENTITY_DIFF_FIELDS},
        ))
        # Attributes inside the added entity also count as additions
        for attr in (snap_to.get("attributes_by_entity") or {}).get(ent.get("entity_id"), []):
            additions.append(DiffEntry(
                type="attribute_added",
                entity_key=k,
                attribute_key=attr.get("technical_name"),
                after={f: attr.get(f) for f in _ATTR_DIFF_FIELDS},
            ))

    for k in sorted(from_keys - to_keys):
        ent = from_idx[k]
        removals.append(DiffEntry(
            type="entity_removed",
            entity_key=k,
            before={f: ent.get(f) for f in _ENTITY_DIFF_FIELDS},
        ))
        for attr in (snap_from.get("attributes_by_entity") or {}).get(ent.get("entity_id"), []):
            removals.append(DiffEntry(
                type="attribute_removed",
                entity_key=k,
                attribute_key=attr.get("technical_name"),
                before={f: attr.get(f) for f in _ATTR_DIFF_FIELDS},
            ))

    # Entities present in both: field-level + attribute-level diffs
    for k in sorted(from_keys & to_keys):
        before_e = from_idx[k]
        after_e = to_idx[k]
        for field in _ENTITY_DIFF_FIELDS:
            b = before_e.get(field)
            a = after_e.get(field)
            if b != a:
                changes.append(DiffEntry(
                    type="entity_changed",
                    entity_key=k,
                    field=field,
                    before=b,
                    after=a,
                ))

        # Attribute diffs
        from_attrs = _index_attrs(snap_from, before_e.get("entity_id", ""))
        to_attrs = _index_attrs(snap_to, after_e.get("entity_id", ""))
        attr_from_keys = set(from_attrs.keys())
        attr_to_keys = set(to_attrs.keys())

        for ak in sorted(attr_to_keys - attr_from_keys):
            attr = to_attrs[ak]
            additions.append(DiffEntry(
                type="attribute_added",
                entity_key=k,
                attribute_key=ak,
                after={f: attr.get(f) for f in _ATTR_DIFF_FIELDS},
            ))
        for ak in sorted(attr_from_keys - attr_to_keys):
            attr = from_attrs[ak]
            removals.append(DiffEntry(
                type="attribute_removed",
                entity_key=k,
                attribute_key=ak,
                before={f: attr.get(f) for f in _ATTR_DIFF_FIELDS},
            ))
        for ak in sorted(attr_from_keys & attr_to_keys):
            b_attr = from_attrs[ak]
            a_attr = to_attrs[ak]
            for field in _ATTR_DIFF_FIELDS:
                b = b_attr.get(field)
                a = a_attr.get(field)
                if b != a:
                    changes.append(DiffEntry(
                        type="attribute_changed",
                        entity_key=k,
                        attribute_key=ak,
                        field=field,
                        before=b,
                        after=a,
                    ))

    return VersionDiff(
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        additions=additions,
        removals=removals,
        changes=changes,
        totals={
            "additions": len(additions),
            "removals": len(removals),
            "changes": len(changes),
        },
    )


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def restore_version(sql: Sql, version_id: str, actor: str) -> VersionOut:
    """Create a new DRAFT entry based on an existing version's snapshot.

    Non-destructive: does NOT touch entities/attributes tables. The new DRAFT
    is purely a placeholder for the architect to work on.
    """
    s = get_settings()
    src = delta.fetch_one_params(
        sql,
        f"SELECT version_id, system_id, version_number, snapshot_json "
        f"FROM {s.fq_table('model_versions')} "
        f"WHERE version_id = :version_id",
        [delta.param("version_id", version_id)],
    )
    if not src:
        raise HTTPException(404, f"version '{version_id}' not found")

    src_version_id, system_id, src_number, snapshot_json = src
    new_vid = delta.new_id("ver-")
    now = datetime.utcnow()
    version_number = next_version_number(sql, system_id)

    delta.insert(
        sql,
        s.fq_table("model_versions"),
        {
            "version_id": new_vid,
            "system_id": system_id,
            "version_number": version_number,
            "title": f"Restauração de {src_number}",
            "changelog": f"Rascunho criado a partir da versão {src_number} "
                          f"(version_id={src_version_id}).",
            "status": "DRAFT",
            "published_at": None,
            "published_by": None,
            "snapshot_json": snapshot_json or "{}",
            "based_on_version": src_version_id,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return _get_version(sql, new_vid)


# ---------------------------------------------------------------------------
# Deprecate
# ---------------------------------------------------------------------------

def deprecate_version(sql: Sql, version_id: str, actor: str) -> VersionOut:
    """Soft-mark a version as DEPRECATED. Rejects ACTIVE versions."""
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT status FROM {s.fq_table('model_versions')} "
        f"WHERE version_id = :version_id",
        [delta.param("version_id", version_id)],
    )
    if not row:
        raise HTTPException(404, f"version '{version_id}' not found")
    if row[0] == "ACTIVE":
        raise HTTPException(
            409,
            "ACTIVE versions cannot be deprecated. Publish a new ACTIVE version first.",
        )
    if row[0] == "DEPRECATED":
        return _get_version(sql, version_id)

    delta.update_by_id(
        sql,
        s.fq_table("model_versions"),
        "version_id",
        version_id,
        {
            "status": "DEPRECATED",
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return _get_version(sql, version_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_snapshot(sql: Sql, version_id: str) -> dict[str, Any]:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT snapshot_json FROM {s.fq_table('model_versions')} "
        f"WHERE version_id = :version_id",
        [delta.param("version_id", version_id)],
    )
    if not row:
        raise HTTPException(404, f"version '{version_id}' not found")
    raw = row[0] or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"invalid snapshot_json for version '{version_id}': {exc}")


def _get_version(sql: Sql, version_id: str) -> VersionOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT v.version_id, v.system_id, sys.system_name, v.version_number,
               v.title, v.changelog, v.status, v.published_at, v.published_by,
               v.based_on_version, v.snapshot_json,
               v.created_at, v.created_by, v.updated_at, v.updated_by
        FROM {s.fq_table('model_versions')} v
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = v.system_id
        WHERE v.version_id = :version_id
        """,
        [delta.param("version_id", version_id)],
    )
    if not row:
        raise HTTPException(404, f"version '{version_id}' not found")
    try:
        snapshot = json.loads(row[10]) if row[10] else {}
    except json.JSONDecodeError:
        snapshot = {}
    return VersionOut(
        version_id=row[0],
        system_id=row[1],
        system_name=row[2],
        version_number=row[3],
        title=row[4],
        changelog=row[5],
        status=row[6],  # type: ignore[arg-type]
        published_at=row[7],
        published_by=row[8],
        based_on_version=row[9],
        snapshot_json=snapshot,
        created_at=row[11],
        created_by=row[12],
        updated_at=row[13],
        updated_by=row[14],
    )
