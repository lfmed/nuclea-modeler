"""Lineage (M7) HTTP endpoints — upstream + downstream + graph."""
from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .models import (
    DownstreamIn,
    DownstreamOut,
    LineageGraph,
    LineageGraphEdge,
    LineageGraphNode,
    UpstreamIn,
    UpstreamOut,
)

router = APIRouter(prefix=f"{api_prefix}/lineage", tags=["lineage"])

_UP_COLS = [
    "lineage_id", "entity_id", "source_system", "source_entity",
    "integration_type", "periodicity", "transformations", "pipeline_link",
    "created_at", "created_by", "updated_at", "updated_by",
]
_DOWN_COLS = [
    "consumer_id", "entity_id", "consumer_system", "consumption_type",
    "responsible_team", "sla_dependency", "detected_via",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _up_row_to_out(r: list) -> UpstreamOut:
    return UpstreamOut(
        lineage_id=r[0], entity_id=r[1], source_system=r[2],
        source_entity=r[3], integration_type=cast(any, r[4]) if r[4] else None,
        periodicity=cast(any, r[5]) if r[5] else None,
        transformations=r[6], pipeline_link=r[7],
        created_at=r[8], created_by=r[9],
        updated_at=r[10], updated_by=r[11],
    )


def _down_row_to_out(r: list) -> DownstreamOut:
    return DownstreamOut(
        consumer_id=r[0], entity_id=r[1], consumer_system=r[2],
        consumption_type=cast(any, r[3]) if r[3] else None,
        responsible_team=r[4],
        sla_dependency=cast(any, r[5]) if r[5] else None,
        detected_via=cast(any, r[6] or "MANUAL"),
        created_at=r[7], created_by=r[8],
        updated_at=r[9], updated_by=r[10],
    )


# ─── Upstream CRUD ──────────────────────────────────────────────────────────

@router.get(
    "/entities/{entity_id}/upstream",
    response_model=list[UpstreamOut],
    operation_id="listUpstream",
)
def list_upstream(entity_id: str, sql: SqlDependency) -> list[UpstreamOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"SELECT {', '.join(_UP_COLS)} FROM {s.fq_table('lineage_upstream')} "
        f"WHERE entity_id = :entity_id ORDER BY source_system",
        [delta.param("entity_id", entity_id)],
    )
    return [_up_row_to_out(r) for r in rows]


@router.post(
    "/entities/{entity_id}/upstream",
    response_model=UpstreamOut,
    operation_id="createUpstream",
)
def create_upstream(
    entity_id: str,
    payload: UpstreamIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> UpstreamOut:
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id mismatch between path and payload")
    s = get_settings()
    actor = _current_email(user_ws)
    lid = delta.new_id("up-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("lineage_upstream"),
        {
            "lineage_id": lid,
            "entity_id": entity_id,
            "source_system": payload.source_system,
            "source_entity": payload.source_entity,
            "integration_type": payload.integration_type,
            "periodicity": payload.periodicity,
            "transformations": payload.transformations,
            "pipeline_link": payload.pipeline_link,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_UP_COLS)} FROM {s.fq_table('lineage_upstream')} "
        f"WHERE lineage_id = :lineage_id",
        [delta.param("lineage_id", lid)],
    )
    if not row:
        raise HTTPException(500, "upstream creation failed")
    return _up_row_to_out(row)


@router.delete(
    "/upstream/{lineage_id}",
    operation_id="deleteUpstream",
)
def delete_upstream(lineage_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("lineage_upstream"), "lineage_id", lineage_id)
    return {"deleted": lineage_id}


# ─── Downstream CRUD ────────────────────────────────────────────────────────

@router.get(
    "/entities/{entity_id}/downstream",
    response_model=list[DownstreamOut],
    operation_id="listDownstream",
)
def list_downstream(entity_id: str, sql: SqlDependency) -> list[DownstreamOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"SELECT {', '.join(_DOWN_COLS)} FROM {s.fq_table('lineage_downstream')} "
        f"WHERE entity_id = :entity_id ORDER BY consumer_system",
        [delta.param("entity_id", entity_id)],
    )
    return [_down_row_to_out(r) for r in rows]


@router.post(
    "/entities/{entity_id}/downstream",
    response_model=DownstreamOut,
    operation_id="createDownstream",
)
def create_downstream(
    entity_id: str,
    payload: DownstreamIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> DownstreamOut:
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id mismatch between path and payload")
    s = get_settings()
    actor = _current_email(user_ws)
    cid = delta.new_id("cons-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("lineage_downstream"),
        {
            "consumer_id": cid,
            "entity_id": entity_id,
            "consumer_system": payload.consumer_system,
            "consumption_type": payload.consumption_type,
            "responsible_team": payload.responsible_team,
            "sla_dependency": payload.sla_dependency,
            "detected_via": payload.detected_via,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    row = delta.fetch_one_params(
        sql,
        f"SELECT {', '.join(_DOWN_COLS)} FROM {s.fq_table('lineage_downstream')} "
        f"WHERE consumer_id = :consumer_id",
        [delta.param("consumer_id", cid)],
    )
    if not row:
        raise HTTPException(500, "downstream creation failed")
    return _down_row_to_out(row)


@router.delete(
    "/downstream/{consumer_id}",
    operation_id="deleteDownstream",
)
def delete_downstream(consumer_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("lineage_downstream"), "consumer_id", consumer_id)
    return {"deleted": consumer_id}


# ─── Graph ──────────────────────────────────────────────────────────────────

@router.get(
    "/entities/{entity_id}/graph",
    response_model=LineageGraph,
    operation_id="getLineageGraph",
)
def get_graph(
    entity_id: str,
    sql: SqlDependency,
    depth: int = 1,
) -> LineageGraph:
    """Build a 1- or 2-hop graph centered on the entity."""
    s = get_settings()
    depth = max(1, min(depth, 3))
    nodes: dict[str, LineageGraphNode] = {}
    edges: list[LineageGraphEdge] = []

    def add_entity_node(eid: str):
        if eid in nodes:
            return
        row = delta.fetch_one_params(
            sql,
            f"""
            SELECT e.entity_id, e.schema_name, e.technical_name, e.entity_type, e.domain,
                   sys.system_name
            FROM {s.fq_table('entities')} e
            LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
            WHERE e.entity_id = :entity_id
            """,
            [delta.param("entity_id", eid)],
        )
        if not row:
            return
        nodes[eid] = LineageGraphNode(
            id=eid,
            label=f"{row[1]}.{row[2]}",
            kind="entity",
            schema_name=row[1],
            system_name=row[5],
            domain=row[4],
            entity_type=row[3],
        )

    def add_external_node(prefix: str, system: str, kind: str):
        nid = f"{prefix}:{system}"
        if nid in nodes:
            return nid
        nodes[nid] = LineageGraphNode(
            id=nid,
            label=system,
            kind=cast(any, kind),
            system_name=system,
        )
        return nid

    def expand(eid: str, remaining: int):
        if remaining <= 0:
            return
        # Upstream
        ups = delta.fetch_all_params(
            sql,
            f"""
            SELECT source_system, source_entity, integration_type
            FROM {s.fq_table('lineage_upstream')}
            WHERE entity_id = :entity_id
            """,
            [delta.param("entity_id", eid)],
        )
        for u in ups:
            src_node = add_external_node("up", u[0], "upstream_system")
            edges.append(LineageGraphEdge(
                source=src_node, target=eid,
                edge_kind="upstream",
                label=u[2] if u[2] else (u[1] or None),
            ))
        # Downstream
        downs = delta.fetch_all_params(
            sql,
            f"""
            SELECT consumer_system, consumption_type, sla_dependency
            FROM {s.fq_table('lineage_downstream')}
            WHERE entity_id = :entity_id
            """,
            [delta.param("entity_id", eid)],
        )
        for d in downs:
            cons_node = add_external_node("down", d[0], "downstream_system")
            edges.append(LineageGraphEdge(
                source=eid, target=cons_node,
                edge_kind="downstream",
                label=d[1] if d[1] else None,
                sla_dependency=cast(any, d[2]) if d[2] else None,
            ))

    add_entity_node(entity_id)
    expand(entity_id, depth)
    return LineageGraph(
        center_entity_id=entity_id,
        nodes=list(nodes.values()),
        edges=edges,
        depth=depth,
    )
