"""HTTP endpoints for Views, Procedures, Triggers, Sequences (M3 complementar)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from .models import (
    ProcedureIn,
    ProcedureListOut,
    ProcedureOut,
    ProcedureParam,
    SequenceIn,
    SequenceListOut,
    SequenceOut,
    TriggerIn,
    TriggerListOut,
    TriggerOut,
    ViewIn,
    ViewOut,
)


# =============================================================================
# Views (rich detail on top of an existing entity with entity_type=VIEW)
# =============================================================================

views_router = APIRouter(prefix=f"{api_prefix}/views", tags=["views"])


@views_router.get("", response_model=list[ViewOut], operation_id="listViews")
def list_views(sql: SqlDependency, system_id: str | None = None) -> list[ViewOut]:
    s = get_settings()
    where = "WHERE e.entity_type = 'VIEW'"
    params: list = []
    if system_id:
        where += " AND e.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT e.entity_id, e.schema_name, e.technical_name, e.system_id,
               sys.system_name,
               v.purpose, v.definition_sql, v.base_entity_ids,
               v.created_at, v.created_by, v.updated_at, v.updated_by
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('views_catalog')} v ON v.view_entity_id = e.entity_id
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        {where}
        ORDER BY e.schema_name, e.technical_name
        """,
        params,
    )
    return [
        ViewOut(
            view_entity_id=r[0],
            entity_label=f"{r[1]}.{r[2]}",
            system_id=r[3], system_name=r[4],
            purpose=r[5], definition_sql=r[6],
            base_entity_ids=delta.as_str_list(r[7]),  # ARRAY<STRING> via string JSON
            created_at=r[8], created_by=r[9],
            updated_at=r[10], updated_by=r[11],
        )
        for r in rows
    ]


@views_router.get(
    "/{view_entity_id}",
    response_model=ViewOut,
    operation_id="getView",
)
def get_view(view_entity_id: str, sql: SqlDependency) -> ViewOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT e.entity_id, e.schema_name, e.technical_name, e.system_id,
               sys.system_name,
               v.purpose, v.definition_sql, v.base_entity_ids,
               v.created_at, v.created_by, v.updated_at, v.updated_by
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('views_catalog')} v ON v.view_entity_id = e.entity_id
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE e.entity_id = :entity_id
        """,
        [delta.param("entity_id", view_entity_id)],
    )
    if not row:
        raise HTTPException(404, f"view '{view_entity_id}' not found")
    return ViewOut(
        view_entity_id=row[0],
        entity_label=f"{row[1]}.{row[2]}",
        system_id=row[3], system_name=row[4],
        purpose=row[5], definition_sql=row[6],
        base_entity_ids=delta.as_str_list(row[7]),  # ARRAY<STRING> via string JSON
        created_at=row[8], created_by=row[9],
        updated_at=row[10], updated_by=row[11],
    )


@views_router.put(
    "/{view_entity_id}",
    response_model=ViewOut,
    operation_id="upsertView",
)
def upsert_view(
    view_entity_id: str,
    payload: ViewIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ViewOut:
    """Upsert view metadata. The entity itself must already exist with entity_type=VIEW."""
    s = get_settings()
    # Verify entity exists and is a view
    ent = delta.fetch_one_params(
        sql,
        f"SELECT entity_id, entity_type FROM {s.fq_table('entities')} "
        f"WHERE entity_id = :entity_id",
        [delta.param("entity_id", view_entity_id)],
    )
    if not ent:
        raise HTTPException(404, f"entity '{view_entity_id}' not found — crie a entidade primeiro com entity_type=VIEW")
    if ent[1] not in ("VIEW", "MATERIALIZED_VIEW"):
        raise HTTPException(400, f"entity type is '{ent[1]}', expected VIEW or MATERIALIZED_VIEW")
    actor = _current_email(user_ws)
    now = datetime.utcnow()
    # Delete + insert (simple upsert)
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('views_catalog')} "
        f"WHERE view_entity_id = :view_entity_id",
        [delta.param("view_entity_id", view_entity_id)],
    )
    delta.insert(
        sql,
        s.fq_table("views_catalog"),
        {
            "view_entity_id": view_entity_id,
            "purpose": payload.purpose,
            "definition_sql": payload.definition_sql,
            "base_entity_ids": payload.base_entity_ids,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_view(view_entity_id, sql)


@views_router.delete(
    "/{view_entity_id}",
    operation_id="clearViewSql",
)
def clear_view(view_entity_id: str, sql: SqlDependency) -> dict:
    """Clear the views_catalog row (the underlying entity is preserved)."""
    s = get_settings()
    delta.run_params(
        sql,
        f"DELETE FROM {s.fq_table('views_catalog')} "
        f"WHERE view_entity_id = :view_entity_id",
        [delta.param("view_entity_id", view_entity_id)],
    )
    return {"cleared": view_entity_id}


# =============================================================================
# Procedures
# =============================================================================

procedures_router = APIRouter(prefix=f"{api_prefix}/procedures", tags=["procedures"])

_PROC_COLS = [
    "procedure_id", "system_id", "schema_name", "technical_name", "logical_name",
    "behavior_desc", "parameters_json", "source_code",
    "dependent_systems", "change_risk_level",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _proc_row_to_out(r: list, system_name: str | None = None) -> ProcedureOut:
    try:
        params = [ProcedureParam(**p) for p in json.loads(r[6] or "[]")]
    except Exception:
        params = []
    return ProcedureOut(
        procedure_id=r[0], system_id=r[1], system_name=system_name,
        schema_name=r[2], technical_name=r[3], logical_name=r[4],
        behavior_desc=r[5], parameters=params, source_code=r[7],
        dependent_systems=delta.as_str_list(r[8]),  # ARRAY<STRING> via string JSON
        change_risk_level=cast(any, r[9]) if r[9] else None,
        created_at=r[10], created_by=r[11],
        updated_at=r[12], updated_by=r[13],
    )


@procedures_router.get(
    "",
    response_model=list[ProcedureListOut],
    operation_id="listProcedures",
)
def list_procedures(
    sql: SqlDependency,
    system_id: str | None = None,
) -> list[ProcedureListOut]:
    s = get_settings()
    where = ""
    params: list = []
    if system_id:
        where = "WHERE p.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT p.procedure_id, p.system_id, sys.system_name,
               p.schema_name, p.technical_name, p.logical_name,
               p.change_risk_level, p.updated_at
        FROM {s.fq_table('procedures_catalog')} p
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = p.system_id
        {where}
        ORDER BY p.schema_name, p.technical_name
        """,
        params,
    )
    return [
        ProcedureListOut(
            procedure_id=r[0], system_id=r[1], system_name=r[2],
            schema_name=r[3], technical_name=r[4], logical_name=r[5],
            change_risk_level=cast(any, r[6]) if r[6] else None,
            updated_at=r[7],
        )
        for r in rows
    ]


@procedures_router.get(
    "/{procedure_id}",
    response_model=ProcedureOut,
    operation_id="getProcedure",
)
def get_procedure(procedure_id: str, sql: SqlDependency) -> ProcedureOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('p.'+c for c in _PROC_COLS)}, sys.system_name
        FROM {s.fq_table('procedures_catalog')} p
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = p.system_id
        WHERE p.procedure_id = :procedure_id
        """,
        [delta.param("procedure_id", procedure_id)],
    )
    if not row:
        raise HTTPException(404, f"procedure '{procedure_id}' not found")
    return _proc_row_to_out(row[:-1], system_name=row[-1])


@procedures_router.post(
    "",
    response_model=ProcedureOut,
    operation_id="createProcedure",
)
def create_procedure(
    payload: ProcedureIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ProcedureOut:
    s = get_settings()
    actor = _current_email(user_ws)
    pid = delta.new_id("proc-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("procedures_catalog"),
        {
            "procedure_id": pid,
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "behavior_desc": payload.behavior_desc,
            "parameters_json": json.dumps(
                [p.model_dump() for p in payload.parameters], ensure_ascii=False,
            ),
            "source_code": payload.source_code,
            "dependent_systems": payload.dependent_systems,
            "change_risk_level": payload.change_risk_level,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_procedure(pid, sql)


@procedures_router.put(
    "/{procedure_id}",
    response_model=ProcedureOut,
    operation_id="updateProcedure",
)
def update_procedure(
    procedure_id: str,
    payload: ProcedureIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> ProcedureOut:
    s = get_settings()
    actor = _current_email(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("procedures_catalog"),
        "procedure_id",
        procedure_id,
        {
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "behavior_desc": payload.behavior_desc,
            "parameters_json": json.dumps(
                [p.model_dump() for p in payload.parameters], ensure_ascii=False,
            ),
            "source_code": payload.source_code,
            "dependent_systems": payload.dependent_systems,
            "change_risk_level": payload.change_risk_level,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_procedure(procedure_id, sql)


@procedures_router.delete(
    "/{procedure_id}",
    operation_id="deleteProcedure",
)
def delete_procedure(procedure_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("procedures_catalog"), "procedure_id", procedure_id)
    return {"deleted": procedure_id}


# =============================================================================
# Triggers
# =============================================================================

triggers_router = APIRouter(prefix=f"{api_prefix}/triggers", tags=["triggers"])

_TRG_COLS = [
    "trigger_id", "system_id", "schema_name", "technical_name",
    "associated_entity_id", "event_type", "timing", "body",
    "behavior_desc", "change_risk_level",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _trg_row_to_out(
    r: list,
    system_name: str | None = None,
    entity_label: str | None = None,
) -> TriggerOut:
    return TriggerOut(
        trigger_id=r[0], system_id=r[1], system_name=system_name,
        schema_name=r[2], technical_name=r[3],
        associated_entity_id=r[4],
        associated_entity_label=entity_label,
        event_type=cast(any, r[5]) if r[5] else None,
        timing=cast(any, r[6]) if r[6] else None,
        body=r[7], behavior_desc=r[8],
        change_risk_level=cast(any, r[9]) if r[9] else None,
        created_at=r[10], created_by=r[11],
        updated_at=r[12], updated_by=r[13],
    )


@triggers_router.get(
    "",
    response_model=list[TriggerListOut],
    operation_id="listTriggers",
)
def list_triggers(sql: SqlDependency, system_id: str | None = None) -> list[TriggerListOut]:
    s = get_settings()
    where = ""
    params: list = []
    if system_id:
        where = "WHERE t.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT t.trigger_id, t.system_id, sys.system_name,
               t.schema_name, t.technical_name,
               t.associated_entity_id, e.technical_name AS ent_name, e.schema_name AS ent_schema,
               t.event_type, t.timing, t.change_risk_level, t.updated_at
        FROM {s.fq_table('triggers_catalog')} t
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = t.system_id
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = t.associated_entity_id
        {where}
        ORDER BY t.schema_name, t.technical_name
        """,
        params,
    )
    return [
        TriggerListOut(
            trigger_id=r[0], system_id=r[1], system_name=r[2],
            schema_name=r[3], technical_name=r[4],
            associated_entity_id=r[5],
            associated_entity_label=f"{r[7]}.{r[6]}" if r[6] and r[7] else None,
            event_type=cast(any, r[8]) if r[8] else None,
            timing=cast(any, r[9]) if r[9] else None,
            change_risk_level=cast(any, r[10]) if r[10] else None,
            updated_at=r[11],
        )
        for r in rows
    ]


@triggers_router.get(
    "/{trigger_id}",
    response_model=TriggerOut,
    operation_id="getTrigger",
)
def get_trigger(trigger_id: str, sql: SqlDependency) -> TriggerOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('t.'+c for c in _TRG_COLS)},
               sys.system_name,
               CONCAT(e.schema_name, '.', e.technical_name) AS entity_label
        FROM {s.fq_table('triggers_catalog')} t
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = t.system_id
        LEFT JOIN {s.fq_table('entities')} e ON e.entity_id = t.associated_entity_id
        WHERE t.trigger_id = :trigger_id
        """,
        [delta.param("trigger_id", trigger_id)],
    )
    if not row:
        raise HTTPException(404, f"trigger '{trigger_id}' not found")
    return _trg_row_to_out(row[:-2], system_name=row[-2], entity_label=row[-1])


@triggers_router.post(
    "",
    response_model=TriggerOut,
    operation_id="createTrigger",
)
def create_trigger(
    payload: TriggerIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TriggerOut:
    s = get_settings()
    actor = _current_email(user_ws)
    tid = delta.new_id("trg-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("triggers_catalog"),
        {
            "trigger_id": tid,
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "associated_entity_id": payload.associated_entity_id,
            "event_type": payload.event_type,
            "timing": payload.timing,
            "body": payload.body,
            "behavior_desc": payload.behavior_desc,
            "change_risk_level": payload.change_risk_level,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_trigger(tid, sql)


@triggers_router.put(
    "/{trigger_id}",
    response_model=TriggerOut,
    operation_id="updateTrigger",
)
def update_trigger(
    trigger_id: str,
    payload: TriggerIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> TriggerOut:
    s = get_settings()
    actor = _current_email(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("triggers_catalog"),
        "trigger_id",
        trigger_id,
        {
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "associated_entity_id": payload.associated_entity_id,
            "event_type": payload.event_type,
            "timing": payload.timing,
            "body": payload.body,
            "behavior_desc": payload.behavior_desc,
            "change_risk_level": payload.change_risk_level,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_trigger(trigger_id, sql)


@triggers_router.delete(
    "/{trigger_id}",
    operation_id="deleteTrigger",
)
def delete_trigger(trigger_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("triggers_catalog"), "trigger_id", trigger_id)
    return {"deleted": trigger_id}


# =============================================================================
# Sequences
# =============================================================================

sequences_router = APIRouter(prefix=f"{api_prefix}/sequences", tags=["sequences"])

_SEQ_COLS = [
    "sequence_id", "system_id", "schema_name", "technical_name", "logical_name",
    "description_md", "start_value", "increment_by", "min_value", "max_value",
    "cache_size", "is_cycle", "current_value", "used_by_entity_ids", "native_comment",
    "created_at", "created_by", "updated_at", "updated_by",
]


def _seq_row_to_out(r: list, system_name: str | None = None) -> SequenceOut:
    return SequenceOut(
        sequence_id=r[0], system_id=r[1], system_name=system_name,
        schema_name=r[2], technical_name=r[3], logical_name=r[4],
        description_md=r[5],
        start_value=int(r[6]) if r[6] is not None else None,
        increment_by=int(r[7]) if r[7] is not None else None,
        min_value=int(r[8]) if r[8] is not None else None,
        max_value=int(r[9]) if r[9] is not None else None,
        cache_size=int(r[10]) if r[10] is not None else None,
        is_cycle=delta.as_bool(r[11]) if r[11] is not None else None,
        current_value=int(r[12]) if r[12] is not None else None,
        used_by_entity_ids=delta.as_str_list(r[13]),  # ARRAY<STRING> via string JSON
        native_comment=r[14],
        created_at=r[15], created_by=r[16],
        updated_at=r[17], updated_by=r[18],
    )


@sequences_router.get(
    "",
    response_model=list[SequenceListOut],
    operation_id="listSequences",
)
def list_sequences(sql: SqlDependency, system_id: str | None = None) -> list[SequenceListOut]:
    s = get_settings()
    where = ""
    params: list = []
    if system_id:
        where = "WHERE q.system_id = :system_id"
        params.append(delta.param("system_id", system_id))
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT q.sequence_id, q.system_id, sys.system_name,
               q.schema_name, q.technical_name, q.logical_name,
               q.increment_by, q.current_value, q.updated_at
        FROM {s.fq_table('sequences_catalog')} q
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = q.system_id
        {where}
        ORDER BY q.schema_name, q.technical_name
        """,
        params,
    )
    return [
        SequenceListOut(
            sequence_id=r[0], system_id=r[1], system_name=r[2],
            schema_name=r[3], technical_name=r[4], logical_name=r[5],
            increment_by=int(r[6]) if r[6] is not None else None,
            current_value=int(r[7]) if r[7] is not None else None,
            updated_at=r[8],
        )
        for r in rows
    ]


@sequences_router.get(
    "/{sequence_id}",
    response_model=SequenceOut,
    operation_id="getSequence",
)
def get_sequence(sequence_id: str, sql: SqlDependency) -> SequenceOut:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('q.'+c for c in _SEQ_COLS)}, sys.system_name
        FROM {s.fq_table('sequences_catalog')} q
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = q.system_id
        WHERE q.sequence_id = :sequence_id
        """,
        [delta.param("sequence_id", sequence_id)],
    )
    if not row:
        raise HTTPException(404, f"sequence '{sequence_id}' not found")
    return _seq_row_to_out(row[:-1], system_name=row[-1])


@sequences_router.post(
    "",
    response_model=SequenceOut,
    operation_id="createSequence",
)
def create_sequence(
    payload: SequenceIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SequenceOut:
    s = get_settings()
    actor = _current_email(user_ws)
    sid = delta.new_id("seq-")
    now = datetime.utcnow()
    delta.insert(
        sql,
        s.fq_table("sequences_catalog"),
        {
            "sequence_id": sid,
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "description_md": payload.description_md,
            "start_value": payload.start_value,
            "increment_by": payload.increment_by,
            "min_value": payload.min_value,
            "max_value": payload.max_value,
            "cache_size": payload.cache_size,
            "is_cycle": payload.is_cycle,
            "current_value": payload.current_value,
            "used_by_entity_ids": payload.used_by_entity_ids,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )
    return get_sequence(sid, sql)


@sequences_router.put(
    "/{sequence_id}",
    response_model=SequenceOut,
    operation_id="updateSequence",
)
def update_sequence(
    sequence_id: str,
    payload: SequenceIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> SequenceOut:
    s = get_settings()
    actor = _current_email(user_ws)
    delta.update_by_id(
        sql,
        s.fq_table("sequences_catalog"),
        "sequence_id",
        sequence_id,
        {
            "system_id": payload.system_id,
            "schema_name": payload.schema_name,
            "technical_name": payload.technical_name,
            "logical_name": payload.logical_name,
            "description_md": payload.description_md,
            "start_value": payload.start_value,
            "increment_by": payload.increment_by,
            "min_value": payload.min_value,
            "max_value": payload.max_value,
            "cache_size": payload.cache_size,
            "is_cycle": payload.is_cycle,
            "current_value": payload.current_value,
            "used_by_entity_ids": payload.used_by_entity_ids,
            "updated_at": datetime.utcnow(),
            "updated_by": actor,
        },
    )
    return get_sequence(sequence_id, sql)


@sequences_router.delete(
    "/{sequence_id}",
    operation_id="deleteSequence",
)
def delete_sequence(sequence_id: str, sql: SqlDependency) -> dict:
    s = get_settings()
    delta.delete_by_id(sql, s.fq_table("sequences_catalog"), "sequence_id", sequence_id)
    return {"deleted": sequence_id}
