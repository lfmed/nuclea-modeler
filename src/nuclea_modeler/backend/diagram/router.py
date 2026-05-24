"""Diagram (M4 DER) HTTP endpoints — view + layout persistence."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .models import (
    DiagramAttribute,
    DiagramEntity,
    DiagramRelationship,
    DiagramView,
    LayoutOut,
    LayoutSaveIn,
    NodePosition,
)

router = APIRouter(prefix=f"{api_prefix}/diagram", tags=["diagram"])


def _q(s: str) -> str:
    return (s or "").replace("'", "''")


def _build_diagram(sql, system_id: str, layout_name: str = "default") -> DiagramView:
    s = get_settings()
    sys_row = delta.fetch_one(
        sql,
        f"SELECT system_name FROM {s.fq_table('systems')} "
        f"WHERE system_id = '{_q(system_id)}'",
    )
    system_name = sys_row[0] if sys_row else None

    ent_rows = delta.fetch_all(
        sql,
        f"""
        SELECT entity_id, schema_name, technical_name, logical_name,
               entity_type, domain, criticality
        FROM {s.fq_table('entities')}
        WHERE system_id = '{_q(system_id)}'
        ORDER BY schema_name, technical_name
        """,
    )
    entities_by_id: dict[str, DiagramEntity] = {}
    for r in ent_rows:
        eid = r[0]
        entities_by_id[eid] = DiagramEntity(
            entity_id=eid, schema_name=r[1], technical_name=r[2], logical_name=r[3],
            entity_type=r[4] or "TABLE", domain=r[5], criticality=r[6],
        )

    if entities_by_id:
        ids_csv = ", ".join(f"'{eid}'" for eid in entities_by_id)
        attr_rows = delta.fetch_all(
            sql,
            f"""
            SELECT attribute_id, entity_id, technical_name, logical_name,
                   native_data_type, is_primary_key, is_nullable, ordinal_position
            FROM {s.fq_table('attributes')}
            WHERE entity_id IN ({ids_csv})
            ORDER BY entity_id, COALESCE(ordinal_position, 999999), technical_name
            """,
        )
        # Mark LGPD flagged attributes
        lgpd_attr_ids: set[str] = set()
        if attr_rows:
            attr_ids_csv = ", ".join(f"'{r[0]}'" for r in attr_rows)
            flagged_rows = delta.fetch_all(
                sql,
                f"""
                SELECT DISTINCT af.attribute_id
                FROM {s.fq_table('attribute_flags')} af
                JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
                WHERE af.attribute_id IN ({attr_ids_csv})
                  AND f.category = 'LGPD'
                """,
            )
            lgpd_attr_ids = {r[0] for r in flagged_rows}

        for r in attr_rows:
            attr_id, entity_id = r[0], r[1]
            ent = entities_by_id.get(entity_id)
            if not ent:
                continue
            attr = DiagramAttribute(
                attribute_id=attr_id,
                technical_name=r[2],
                logical_name=r[3],
                native_data_type=r[4],
                is_primary_key=bool(r[5]),
                is_nullable=bool(r[6]) if r[6] is not None else None,
                ordinal_position=int(r[7]) if r[7] is not None else None,
                has_lgpd_flag=attr_id in lgpd_attr_ids,
            )
            ent.attributes.append(attr)
            if attr.has_lgpd_flag:
                ent.has_lgpd_flag = True

        # Also flag entities with direct entity_flags LGPD
        lgpd_entity_rows = delta.fetch_all(
            sql,
            f"""
            SELECT DISTINCT ef.entity_id
            FROM {s.fq_table('entity_flags')} ef
            JOIN {s.fq_table('flags')} f ON f.flag_id = ef.flag_id
            WHERE ef.entity_id IN ({ids_csv}) AND f.category = 'LGPD'
            """,
        )
        for r in lgpd_entity_rows:
            ent = entities_by_id.get(r[0])
            if ent:
                ent.has_lgpd_flag = True

    rel_rows = delta.fetch_all(
        sql,
        f"""
        SELECT relationship_id, source_entity_id, target_entity_id,
               rel_type, source_cardinality, target_cardinality,
               source_attr_ids, target_attr_ids, description, origin
        FROM {s.fq_table('relationships')}
        WHERE system_id = '{_q(system_id)}'
        """,
    )
    relationships: list[DiagramRelationship] = []
    for r in rel_rows:
        relationships.append(DiagramRelationship(
            relationship_id=r[0],
            source_entity_id=r[1], target_entity_id=r[2],
            rel_type=r[3], source_cardinality=r[4], target_cardinality=r[5],
            source_attrs=list(r[6]) if r[6] else [],
            target_attrs=list(r[7]) if r[7] else [],
            description=r[8], origin=r[9],
        ))

    layout = _load_layout_dict(sql, system_id, layout_name)

    return DiagramView(
        system_id=system_id,
        system_name=system_name,
        entities=list(entities_by_id.values()),
        relationships=relationships,
        layout={k: NodePosition(**v) for k, v in layout.items()} if layout else {},
        layout_name=layout_name,
    )


def _load_layout_dict(sql, system_id: str, layout_name: str) -> dict[str, dict[str, Any]] | None:
    s = get_settings()
    row = delta.fetch_one(
        sql,
        f"""
        SELECT layout_json FROM {s.fq_table('der_layouts')}
        WHERE system_id = '{_q(system_id)}' AND layout_name = '{_q(layout_name)}'
        ORDER BY updated_at DESC LIMIT 1
        """,
    )
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


@router.get("/{system_id}", response_model=DiagramView, operation_id="getDiagram")
def get_diagram(
    system_id: str,
    sql: SqlDependency,
    layout_name: str = "default",
) -> DiagramView:
    return _build_diagram(sql, system_id, layout_name)


@router.post(
    "/{system_id}/layout",
    response_model=LayoutOut,
    operation_id="saveLayout",
)
def save_layout(
    system_id: str,
    payload: LayoutSaveIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> LayoutOut:
    s = get_settings()
    actor = _current_email(user_ws)
    layout_json = json.dumps(
        {k: {"x": v.x, "y": v.y} for k, v in payload.positions.items()},
        ensure_ascii=False,
    )
    # Upsert by (system_id, layout_name): delete then insert (simple).
    delta.run(
        sql,
        f"""
        DELETE FROM {s.fq_table('der_layouts')}
        WHERE system_id = '{_q(system_id)}' AND layout_name = '{_q(payload.layout_name)}'
        """,
    )
    lid = delta.new_id("layout-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("der_layouts"),
        {
            "layout_id": lid,
            "system_id": system_id,
            "layout_name": payload.layout_name,
            "layout_json": layout_json,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return LayoutOut(
        layout_id=lid,
        system_id=system_id,
        layout_name=payload.layout_name,
        positions=payload.positions,
        created_at=now, created_by=actor,
        updated_at=now, updated_by=actor,
    )


@router.get(
    "/{system_id}/layouts",
    response_model=list[str],
    operation_id="listLayoutNames",
)
def list_layouts(system_id: str, sql: SqlDependency) -> list[str]:
    s = get_settings()
    rows = delta.fetch_all(
        sql,
        f"SELECT DISTINCT layout_name FROM {s.fq_table('der_layouts')} "
        f"WHERE system_id = '{_q(system_id)}' ORDER BY layout_name",
    )
    return [r[0] for r in rows]


@router.delete(
    "/{system_id}/layouts/{layout_name}",
    operation_id="deleteLayout",
)
def delete_layout(system_id: str, layout_name: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.run(
        sql,
        f"""
        DELETE FROM {s.fq_table('der_layouts')}
        WHERE system_id = '{_q(system_id)}' AND layout_name = '{_q(layout_name)}'
        """,
    )
    return {"deleted": layout_name}
