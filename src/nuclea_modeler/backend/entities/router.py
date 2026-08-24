"""Module 3 — Entities + Attributes CRUD.

Modelo editorial: mutations (POST/PUT/DELETE) NÃO escrevem direto no catálogo.
Elas são staged num ticket OPEN de sessão do user para o sistema atual. O
ticket é aplicado depois via /tickets/{id}/apply quando aprovado.

Reads continuam lendo do catálogo (estado "comitado"). O frontend é responsável
por mostrar overlay do ticket OPEN se quiser refletir mudanças pendentes na UI.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies, delta
from ..core._nuclea_config import get_settings
from ..core.sql import SqlDependency
from ..rbac.router import _current_email
from ..tickets.overlay import (
    field_changes_by_target,
    index_session_diff,
    pick_entry,
)
from ..tickets.session import (
    find_open_session_ticket,
    get_or_create_session_ticket,
    stage_entity_change,
)
from .listings import escape_like, flags_by_entity
from .models import (
    AttributeIn, AttributeOut,
    EntityIn, EntityListOut, EntityOut, PaginatedEntities,
)

router = APIRouter(prefix=f"{api_prefix}/entities", tags=["entities"])

_ENT_COLS = [
    "entity_id", "system_id", "schema_name", "technical_name", "logical_name",
    "description_md", "domain", "business_owner", "technical_owner",
    "criticality", "tags", "notes", "entity_type", "native_comment",
    "row_count_approx", "last_extracted_at",
    "created_at", "created_by", "updated_at", "updated_by",
    "is_shared",
]

_ATTR_COLS = [
    "attribute_id", "entity_id", "technical_name", "logical_name",
    "ordinal_position", "native_data_type", "is_nullable", "default_value",
    "is_primary_key", "description_md", "business_rule", "sample_value",
    "glossary_term_id", "native_comment",
    "created_at", "created_by", "updated_at", "updated_by",
]

# Campos da Entity considerados "field_changes" no DiffEntity (op=change).
# Outros campos de input são propagados via payload completo (apply usa um
# subset deles ao materializar o add — ver tickets/service.py apply_ticket).
_ENT_DIFF_FIELDS = [
    "logical_name", "description_md", "domain", "business_owner",
    "technical_owner", "criticality", "tags", "notes", "entity_type",
    "native_comment", "row_count_approx", "is_shared",
]


def _ent_row_to_out(r: list, system_name: str | None = None, attr_count: int | None = None) -> EntityOut:
    return EntityOut(
        entity_id=r[0], system_id=r[1], system_name=system_name,
        schema_name=r[2], technical_name=r[3], logical_name=r[4],
        description_md=r[5], domain=r[6], business_owner=r[7],
        technical_owner=r[8], criticality=r[9] or None,
        tags=list(r[10]) if r[10] else [],
        notes=r[11], entity_type=r[12] or "TABLE",
        native_comment=r[13], row_count_approx=r[14], last_extracted_at=r[15],
        created_at=r[16], created_by=r[17], updated_at=r[18], updated_by=r[19],
        is_shared=delta.as_bool(r[20]) if len(r) > 20 and r[20] is not None else False,
        attributes_count=attr_count,
    )


def _attr_row_to_out(r: list) -> AttributeOut:
    return AttributeOut(
        attribute_id=r[0], entity_id=r[1], technical_name=r[2], logical_name=r[3],
        ordinal_position=r[4], native_data_type=r[5],
        is_nullable=delta.as_bool(r[6]) if r[6] is not None else None,
        default_value=r[7], is_primary_key=delta.as_bool(r[8]),
        description_md=r[9], business_rule=r[10], sample_value=r[11],
        glossary_term_id=r[12], native_comment=r[13],
        created_at=r[14], created_by=r[15], updated_at=r[16], updated_by=r[17],
    )


# Campos de attribute que o overlay de sessão espelha do payload staged sobre a
# linha do catálogo. Espelha o allowlist de apply em tickets/service.py
# (`attribute:NAME.update`) — se um entrar lá, entra aqui também.
_ATTR_OVERLAY_FIELDS = (
    "logical_name", "native_data_type", "is_nullable", "default_value",
    "is_primary_key", "ordinal_position", "description_md", "business_rule",
    "native_comment",
)


def _overlay_existing_attrs(
    sql, actor: str, entity_id: str, out: list[AttributeOut],
) -> list[AttributeOut]:
    """Aplica edições pendentes do ticket OPEN do user sobre os attributes já
    materializados de uma entity existente.

    PORQUÊ (bug v1.0030): sem isto, `list_attributes` devolve a linha CRUA do
    catálogo para entities existentes — as edições staged (PK, descrição, tipo…)
    NÃO aparecem. A UI então reconstrói o payload de update a partir de dados
    desatualizados; como o staging faz merge "última intenção vence" por field-key
    (`attribute:NAME.update`), uma 2ª edição da mesma coluna no mesmo ticket
    sobrescrevia a 1ª silenciosamente (ex.: editar descrição e depois togglar PK
    perdia a descrição). Com o overlay, `a` reflete o estado staged e cada payload
    reconstruído carrega os valores mais recentes.

    Espelha `_overlay_entity_out` (que já faz isso pra entity-level). Só leitura.
    """
    keys = _resolve_entity_keys(sql, entity_id)
    if not keys:
        return out
    system_id, schema_name, technical_name, _etype = keys
    found = find_open_session_ticket(sql, actor, system_id)
    if not found:
        return out
    ticket_id, diff = found
    entry = pick_entry(index_session_diff(diff), schema_name, technical_name)
    if not entry or entry.get("op") != "change":
        return out
    _ent_updates, attr_changes, attr_adds, attr_removes = field_changes_by_target(entry)

    by_name = {a.technical_name: a for a in out}
    # Updates: o payload completo do attribute fica em attr_changes[col]["update"]
    # (ver update_attribute → field "attribute:NAME.update", after=payload dict).
    for col, subs in attr_changes.items():
        a = by_name.get(col)
        payload = subs.get("update")
        if not a or not isinstance(payload, dict):
            continue
        for f in _ATTR_OVERLAY_FIELDS:
            # `is not None` espelha o filtro do apply — inclusive is_primary_key=False,
            # que É aplicado (False is not None), refletindo um "desmarcar PK" staged.
            if f in payload and payload[f] is not None:
                setattr(a, f, payload[f])
        a.pending_op = "change"

    remove_names = {r.get("technical_name") for r in attr_removes}
    for a in out:
        if a.technical_name in remove_names:
            a.pending_op = "remove"

    # Adds virtuais staged nesta MESMA entity (raro, mas possível) que ainda não
    # existem no catálogo — aparecem como pending "add".
    from datetime import datetime as _dt
    now = _dt.utcnow()
    existing = set(by_name.keys())
    for add in attr_adds:
        name = add.get("technical_name")
        if not name or name in existing:
            continue
        out.append(AttributeOut(
            attribute_id=add.get("attribute_id") or f"pending-attr-{name}",
            entity_id=entity_id,
            technical_name=name,
            logical_name=add.get("logical_name"),
            ordinal_position=add.get("ordinal_position"),
            native_data_type=add.get("native_data_type"),
            is_nullable=add.get("is_nullable"),
            default_value=add.get("default_value"),
            is_primary_key=bool(add.get("is_primary_key", False)),
            description_md=add.get("description_md"),
            business_rule=add.get("business_rule"),
            sample_value=None,
            glossary_term_id=None,
            native_comment=add.get("native_comment"),
            created_at=now, created_by=actor,
            updated_at=now, updated_by=actor,
            pending_op="add",
        ))
    return out


def _fetch_entity_row(sql, entity_id: str):
    """Lê uma entity do catálogo. Retorna a row crua ou None."""
    s = get_settings()
    return delta.fetch_one_params(
        sql,
        f"""
        SELECT {', '.join('e.'+c for c in _ENT_COLS)},
               sys.system_name,
               (SELECT COUNT(*) FROM {s.fq_table('attributes')} a WHERE a.entity_id = e.entity_id) AS attrs
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        WHERE e.entity_id = :entity_id
        """,
        [delta.param("entity_id", entity_id)],
    )


def _entity_in_to_payload(payload: EntityIn) -> dict:
    """Serializa um EntityIn como payload pronto pro DiffEntity.payload."""
    return {
        "logical_name": payload.logical_name,
        "description_md": payload.description_md,
        "domain": payload.domain,
        "business_owner": payload.business_owner,
        "technical_owner": payload.technical_owner,
        "criticality": payload.criticality,
        "tags": list(payload.tags) if payload.tags else [],
        "notes": payload.notes,
        "entity_type": payload.entity_type,
        "native_comment": payload.native_comment,
        "row_count_approx": payload.row_count_approx,
        "is_shared": bool(payload.is_shared),
    }


def _virtual_entity_out(
    entity_id: str,
    system_id: str,
    payload: EntityIn,
    actor: str,
    *,
    pending_op: str,
    pending_ticket_id: str | None = None,
) -> EntityOut:
    """Constrói uma EntityOut "virtual" pra refletir o estado pós-staging.

    Não consulta o catálogo. Marca timestamps com now(), attributes_count=0
    e popula pending_op/pending_ticket_id para a UI renderizar overlay.
    """
    now = datetime.utcnow()
    return EntityOut(
        entity_id=entity_id,
        system_id=system_id,
        system_name=None,
        schema_name=payload.schema_name,
        technical_name=payload.technical_name,
        logical_name=payload.logical_name,
        description_md=payload.description_md,
        domain=payload.domain,
        business_owner=payload.business_owner,
        technical_owner=payload.technical_owner,
        criticality=payload.criticality,
        tags=list(payload.tags) if payload.tags else [],
        notes=payload.notes,
        entity_type=payload.entity_type,
        native_comment=payload.native_comment,
        row_count_approx=payload.row_count_approx,
        last_extracted_at=None,
        created_at=now,
        created_by=actor,
        updated_at=now,
        updated_by=actor,
        attributes_count=0,
        is_shared=bool(payload.is_shared),
        pending_op=pending_op,  # type: ignore[arg-type]
        pending_ticket_id=pending_ticket_id,
    )


def _virtual_attribute_out(
    attribute_id: str,
    entity_id: str,
    payload: AttributeIn,
    actor: str,
    *,
    pending_op: str | None = None,
) -> AttributeOut:
    now = datetime.utcnow()
    return AttributeOut(
        attribute_id=attribute_id,
        entity_id=entity_id,
        technical_name=payload.technical_name,
        logical_name=payload.logical_name,
        ordinal_position=payload.ordinal_position,
        native_data_type=payload.native_data_type,
        is_nullable=payload.is_nullable,
        default_value=payload.default_value,
        is_primary_key=payload.is_primary_key,
        description_md=payload.description_md,
        business_rule=payload.business_rule,
        sample_value=payload.sample_value,
        glossary_term_id=payload.glossary_term_id,
        native_comment=payload.native_comment,
        created_at=now,
        created_by=actor,
        updated_at=now,
        updated_by=actor,
        pending_op=pending_op,  # type: ignore[arg-type]
    )


# -------------------- Session overlay helpers --------------------

def _get_session_diff(
    sql,
    user_ws,
    system_id: str | None,
) -> tuple[str | None, dict | None, str]:
    """Resolve (ticket_id, diff_dict, actor) para o user atual + system.

    Retorna (None, None, actor) se não há sessão OPEN. `system_id` None → não
    aplica overlay (impossível identificar a sessão sem o sistema). Idempotente
    e read-only (NÃO cria sessão).
    """
    actor = _current_email(user_ws) or "unknown"
    if not system_id or not actor or actor == "unknown":
        return None, None, actor
    found = find_open_session_ticket(sql, actor, system_id)
    if not found:
        return None, None, actor
    return found[0], found[1], actor


def _overlay_entity_list(
    items: list[EntityListOut],
    system_id: str | None,
    session_ticket_id: str | None,
    session_diff: dict | None,
) -> list[EntityListOut]:
    """Aplica pending ops em uma lista de EntityListOut e adiciona items
    virtuais para entries op=add cuja entity ainda não está no catálogo."""
    if not session_diff:
        return items
    indexed = index_session_diff(session_diff)
    consumed: set[tuple[str, str]] = set()
    out: list[EntityListOut] = []
    for it in items:
        entry = pick_entry(indexed, it.schema_name, it.technical_name)
        if not entry:
            out.append(it)
            continue
        op = entry.get("op")
        consumed.add((it.schema_name, it.technical_name))
        if op == "change":
            ent_updates, _attr_changes, _adds, _removes = field_changes_by_target(entry)
            for fld in ("logical_name", "domain", "criticality", "entity_type"):
                if fld in ent_updates and ent_updates[fld] is not None:
                    setattr(it, fld, ent_updates[fld])
            it.pending_op = "change"
            it.pending_ticket_id = session_ticket_id
        elif op == "remove":
            it.pending_op = "remove"
            it.pending_ticket_id = session_ticket_id
        else:
            it.pending_op = "add"
            it.pending_ticket_id = session_ticket_id
        out.append(it)
    # virtual adds
    for key, entries in indexed.items():
        if key in consumed:
            continue
        add_entry = next((e for e in entries if e.get("op") == "add"), None)
        if not add_entry:
            continue
        payload = add_entry.get("payload") or {}
        out.append(
            EntityListOut(
                entity_id=payload.get("pre_allocated_entity_id")
                    or f"pending-ent-{key[0]}.{key[1]}",
                system_id=system_id or "",
                system_name=None,
                schema_name=key[0],
                technical_name=key[1],
                logical_name=payload.get("logical_name"),
                entity_type=add_entry.get("entity_type", "TABLE") or "TABLE",
                domain=payload.get("domain"),
                criticality=payload.get("criticality"),
                attributes_count=len(add_entry.get("attributes") or []),
                updated_at=datetime.utcnow(),
                pending_op="add",
                pending_ticket_id=session_ticket_id,
            )
        )
    return out


def _overlay_entity_out(
    ent: EntityOut,
    session_ticket_id: str | None,
    session_diff: dict | None,
) -> EntityOut:
    """Aplica pending ops em um EntityOut (GET /entities/{id})."""
    if not session_diff:
        return ent
    indexed = index_session_diff(session_diff)
    entry = pick_entry(indexed, ent.schema_name, ent.technical_name)
    if not entry:
        return ent
    op = entry.get("op")
    if op == "change":
        ent_updates, _attr_changes, _adds, _removes = field_changes_by_target(entry)
        for fld in (
            "logical_name", "description_md", "domain", "business_owner",
            "technical_owner", "criticality", "tags", "notes", "entity_type",
            "native_comment", "row_count_approx",
        ):
            if fld in ent_updates and ent_updates[fld] is not None:
                setattr(ent, fld, ent_updates[fld])
        ent.pending_op = "change"
        ent.pending_ticket_id = session_ticket_id
    elif op == "remove":
        ent.pending_op = "remove"
        ent.pending_ticket_id = session_ticket_id
    else:
        ent.pending_op = "add"
        ent.pending_ticket_id = session_ticket_id
    return ent


# -------------------- Entities --------------------

@router.get("", response_model=list[EntityListOut], operation_id="listEntities")
def list_entities(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    system_id: str | None = None,
    domain: str | None = None,
) -> list[EntityListOut]:
    """Lista entities + aplica overlay da sessão editorial do user.

    Se `system_id` for fornecido e o user tiver ticket OPEN para ele, items
    recebem `pending_op` e items "add" virtuais aparecem na lista.
    """
    s = get_settings()
    where: list[str] = []
    params: list = []
    if system_id:
        where.append("e.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    if domain:
        where.append("e.domain = :domain")
        params.append(delta.param("domain", domain))
    # Esconde entidades de sistemas arquivados (soft-deleted). Subquery (não JOIN)
    # para funcionar também no COUNT do paginado, que não junta `systems`.
    where.append(
        f"e.system_id NOT IN "
        f"(SELECT system_id FROM {s.fq_table('systems')} WHERE archived_at IS NOT NULL)"
    )
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT e.entity_id, e.system_id, sys.system_name, e.schema_name,
               e.technical_name, e.logical_name, e.entity_type, e.domain,
               e.criticality, e.updated_at,
               (SELECT COUNT(*) FROM {s.fq_table('attributes')} a WHERE a.entity_id = e.entity_id) AS attrs
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        {where_clause}
        ORDER BY e.updated_at DESC
        LIMIT 1000
        """,
        params,
    )
    items = [
        EntityListOut(
            entity_id=r[0], system_id=r[1], system_name=r[2], schema_name=r[3],
            technical_name=r[4], logical_name=r[5], entity_type=r[6] or "TABLE",
            domain=r[7], criticality=r[8] or None,
            attributes_count=int(r[10]) if r[10] is not None else 0,
            updated_at=r[9],
        )
        for r in rows
    ]
    ticket_id, diff, _ = _get_session_diff(sql, user_ws, system_id)
    return _overlay_entity_list(items, system_id, ticket_id, diff)


# Mapeamento coluna-de-ordenação → expressão SQL. Whitelist explícita porque
# o valor de `sort_by` vem do cliente e é interpolado no ORDER BY (não dá pra
# parametrizar identificadores). Só chaves conhecidas passam; qualquer outra
# cai no default (updated_at). Isso fecha a porta pra SQL injection via sort.
_ENT_SORT_COLS = {
    "technical_name": "e.technical_name",
    "logical_name": "e.logical_name",
    "system_name": "sys.system_name",
    "schema_name": "e.schema_name",
    "entity_type": "e.entity_type",
    "domain": "e.domain",
    "criticality": "e.criticality",
    "updated_at": "e.updated_at",
}


@router.get(
    "/page",
    response_model=PaginatedEntities,
    operation_id="listEntitiesPaginated",
)
def list_entities_paginated(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    system_id: str | None = None,
    schema_name: str | None = None,
    entity_type: str | None = None,
    domain: str | None = None,
    criticality: str | None = None,
    q: str | None = Query(None, description="Busca textual (nome técnico/lógico)"),
    flag_id: str | None = Query(None, description="Filtra entidades com esta flag"),
    sort_by: str = Query("updated_at", description="Coluna de ordenação"),
    sort_dir: str = Query("desc", description="asc | desc"),
    page: int = 1,
    page_size: int = 50,
) -> PaginatedEntities:
    """Listagem paginada + filtros + busca + ordenação + coluna de flags.

    Suporta os filtros que a UI de listagem oferece (ponto 5 do plano):
    sistema, schema, tipo, domínio, criticidade, busca textual e "por flag".

    - `page` é 1-indexed; `page_size` é clamped em [1, 200].
    - `sort_by` é validado contra whitelist (`_ENT_SORT_COLS`); valor inválido
      volta pro default `updated_at`.
    - Filtro por flag usa EXISTS (não JOIN) para não duplicar linhas quando a
      entidade tem várias flags; aplicado igualmente no COUNT e na página para
      manter `total` coerente.
    """
    s = get_settings()
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size

    where: list[str] = []
    params: list = []
    if system_id:
        where.append("e.system_id = :system_id")
        params.append(delta.param("system_id", system_id))
    if schema_name:
        where.append("e.schema_name = :schema_name")
        params.append(delta.param("schema_name", schema_name))
    if entity_type:
        where.append("e.entity_type = :entity_type")
        params.append(delta.param("entity_type", entity_type))
    if domain:
        where.append("e.domain = :domain")
        params.append(delta.param("domain", domain))
    if criticality:
        where.append("e.criticality = :criticality")
        params.append(delta.param("criticality", criticality))
    if q and q.strip():
        pat = f"%{escape_like(q.strip().lower())}%"
        where.append(
            "(LOWER(COALESCE(e.technical_name, '')) LIKE :q ESCAPE '\\\\' "
            "OR LOWER(COALESCE(e.logical_name, '')) LIKE :q ESCAPE '\\\\')"
        )
        params.append(delta.param("q", pat))
    if flag_id:
        # EXISTS evita duplicação de linhas; casa flag direta ou propagada.
        where.append(
            f"EXISTS (SELECT 1 FROM {s.fq_table('entity_flags')} ef "
            f"WHERE ef.entity_id = e.entity_id AND ef.flag_id = :flag_id)"
        )
        params.append(delta.param("flag_id", flag_id))
    # Esconde entidades de sistemas arquivados (soft-deleted). Subquery (não JOIN)
    # para funcionar também no COUNT do paginado, que não junta `systems`.
    where.append(
        f"e.system_id NOT IN "
        f"(SELECT system_id FROM {s.fq_table('systems')} WHERE archived_at IS NOT NULL)"
    )
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    sort_col = _ENT_SORT_COLS.get(sort_by, "e.updated_at")
    direction = "ASC" if str(sort_dir).lower() == "asc" else "DESC"

    total_row = delta.fetch_one_params(
        sql,
        f"SELECT COUNT(*) FROM {s.fq_table('entities')} e {where_clause}",
        params,
    )
    total = int(total_row[0]) if total_row and total_row[0] is not None else 0

    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT e.entity_id, e.system_id, sys.system_name, e.schema_name,
               e.technical_name, e.logical_name, e.entity_type, e.domain,
               e.criticality, e.updated_at,
               (SELECT COUNT(*) FROM {s.fq_table('attributes')} a WHERE a.entity_id = e.entity_id) AS attrs,
               e.description_md, e.native_comment
        FROM {s.fq_table('entities')} e
        LEFT JOIN {s.fq_table('systems')} sys ON sys.system_id = e.system_id
        {where_clause}
        ORDER BY {sort_col} {direction}
        LIMIT {page_size} OFFSET {offset}
        """,
        params,
    )
    items = [
        EntityListOut(
            entity_id=r[0], system_id=r[1], system_name=r[2], schema_name=r[3],
            technical_name=r[4], logical_name=r[5], entity_type=r[6] or "TABLE",
            domain=r[7], criticality=r[8] or None,
            attributes_count=int(r[10]) if r[10] is not None else 0,
            updated_at=r[9],
            # r[11]/r[12] adicionados no SELECT (v1.0030) para o export CSV.
            description_md=r[11], native_comment=r[12],
        )
        for r in rows
    ]
    # Coluna de flags: 1 query agregada para a página inteira (evita N+1).
    flags_map = flags_by_entity(sql, [it.entity_id for it in items])
    for it in items:
        it.flags = flags_map.get(it.entity_id, [])
    ticket_id, diff, _ = _get_session_diff(sql, user_ws, system_id)
    items = _overlay_entity_list(items, system_id, ticket_id, diff)
    return PaginatedEntities(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )


@router.get("/{entity_id}", response_model=EntityOut, operation_id="getEntity")
def get_entity(
    entity_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityOut:
    """Lê uma entity + aplica overlay da sessão do user (se houver).

    Aceita também IDs virtuais/pré-alocados de entries `op=add` que ainda
    não foram aplicados — nesse caso reconstrói o EntityOut direto do diff.
    """
    actor = _current_email(user_ws) or "unknown"
    row = _fetch_entity_row(sql, entity_id)
    if row:
        ent = _ent_row_to_out(
            row[:-2],
            system_name=row[-2],
            attr_count=int(row[-1]) if row[-1] is not None else 0,
        )
        if actor and actor != "unknown":
            found = find_open_session_ticket(sql, actor, ent.system_id)
            if found:
                ticket_id, diff = found
                ent = _overlay_entity_out(ent, ticket_id, diff)
        return ent

    return _resolve_pending_entity(sql, actor, entity_id)


def _resolve_pending_entity(sql, actor: str, entity_id: str) -> EntityOut:
    """Reconstrói EntityOut a partir do diff staged em ticket OPEN.

    Útil quando o frontend chama GET /entities/{eid} usando um id virtual
    (`pending-ent-…`) ou o `pre_allocated_entity_id` retornado no POST
    create_entity. 404 se nada bateu.
    """
    if not actor or actor == "unknown":
        raise HTTPException(404, f"entity '{entity_id}' not found")
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT ticket_id, system_id, diff_json
        FROM {s.fq_table('reconciliation_tickets')}
        WHERE status = 'OPEN' AND created_by = :user
        ORDER BY created_at DESC
        LIMIT 10
        """,
        [delta.param("user", actor)],
    )
    import json as _json
    for r in rows:
        ticket_id, system_id, diff_raw = r[0], r[1], r[2]
        try:
            diff = _json.loads(diff_raw) if diff_raw else {}
        except _json.JSONDecodeError:
            continue
        for e in diff.get("entities") or []:
            if not isinstance(e, dict):
                continue
            payload = e.get("payload") or {}
            target_id = (
                payload.get("pre_allocated_entity_id")
                or payload.get("target_entity_id")
            )
            virt_id = (
                f"pending-ent-{e.get('schema_name')}.{e.get('technical_name')}"
            )
            if target_id != entity_id and entity_id != virt_id:
                continue
            now = datetime.utcnow()
            return EntityOut(
                entity_id=entity_id,
                system_id=system_id,
                system_name=None,
                schema_name=e.get("schema_name") or "",
                technical_name=e.get("technical_name") or "",
                logical_name=payload.get("logical_name"),
                description_md=payload.get("description_md"),
                domain=payload.get("domain"),
                business_owner=payload.get("business_owner"),
                technical_owner=payload.get("technical_owner"),
                criticality=payload.get("criticality"),
                tags=list(payload.get("tags") or []),
                notes=payload.get("notes"),
                entity_type=e.get("entity_type")
                    or payload.get("entity_type") or "TABLE",
                native_comment=payload.get("native_comment"),
                row_count_approx=payload.get("row_count_approx"),
                last_extracted_at=None,
                created_at=now,
                created_by=actor,
                updated_at=now,
                updated_by=actor,
                attributes_count=len(e.get("attributes") or []),
                pending_op=e.get("op") or "add",  # type: ignore[arg-type]
                pending_ticket_id=ticket_id,
            )
    raise HTTPException(404, f"entity '{entity_id}' not found")


@router.post("", response_model=EntityOut, operation_id="createEntity")
def create_entity(
    payload: EntityIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityOut:
    """Cria entity STAGING. NÃO grava no catálogo — vai pro ticket OPEN do user.

    Retorna um EntityOut "virtual" com `entity_id` pré-alocado. A entity só
    aparece em GET /entities/{id} depois que o ticket for aprovado e aplicado.
    """
    actor = _current_email(user_ws) or "unknown"
    ticket_id, diff = get_or_create_session_ticket(sql, actor, payload.system_id)
    eid = delta.new_id("ent-")
    entry = {
        "op": "add",
        "schema_name": payload.schema_name,
        "technical_name": payload.technical_name,
        "entity_type": payload.entity_type,
        "payload": {
            **_entity_in_to_payload(payload),
            # Mantemos o entity_id pré-alocado no payload para que o frontend
            # consiga referenciá-lo (ex: ligar relationships nele) antes do apply.
            "pre_allocated_entity_id": eid,
        },
        "attributes": [],
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return _virtual_entity_out(
        eid, payload.system_id, payload, actor,
        pending_op="add", pending_ticket_id=ticket_id,
    )


@router.put("/{entity_id}", response_model=EntityOut, operation_id="updateEntity")
def update_entity(
    entity_id: str,
    payload: EntityIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> EntityOut:
    """Stage update da entity no ticket OPEN do user.

    Lê o estado atual do catálogo para diff field-level. Se a entity não
    existir no catálogo (foi criada na sessão), trata como "change" sobre o
    add anterior — stage_entity_change deduplica pela chave (schema.tech.op),
    então um change posterior é independente do add e ambos coexistem.
    """
    actor = _current_email(user_ws) or "unknown"
    ticket_id, diff = get_or_create_session_ticket(sql, actor, payload.system_id)

    # Tenta pegar o estado atual do catálogo para construir field_changes.
    row = _fetch_entity_row(sql, entity_id)
    field_changes: list[dict] = []
    if row:
        current = _ent_row_to_out(
            row[:-2],
            system_name=row[-2],
            attr_count=int(row[-1]) if row[-1] is not None else 0,
        )
        new_payload = _entity_in_to_payload(payload)
        for fld in _ENT_DIFF_FIELDS:
            before = getattr(current, fld, None)
            after = new_payload.get(fld)
            if before != after:
                field_changes.append({"field": fld, "before": before, "after": after})
    else:
        # Entity ainda não no catálogo (provavelmente staged como add nesta
        # sessão). Empurra todos os campos como field_changes pra refletir
        # o estado desejado.
        new_payload = _entity_in_to_payload(payload)
        field_changes = [
            {"field": fld, "before": None, "after": new_payload.get(fld)}
            for fld in _ENT_DIFF_FIELDS
        ]

    # Tabela nova ainda NÃO aprovada (entidade virtual): em vez de criar uma
    # entry op=change separada (que não reflete no getEntity virtual, o qual lê
    # o payload do add), mescla os metadados na própria entry op=add do ticket
    # (fix v1.0035). Assim a edição aparece na hora e o apply cria a tabela já
    # com os metadados corretos.
    if not row:
        add = _find_open_add_entry(sql, actor, entity_id)
        if add:
            add_ticket_id, add_system_id, add_diff, add_entry = add
            add_entry["schema_name"] = payload.schema_name
            add_entry["technical_name"] = payload.technical_name
            add_entry["entity_type"] = payload.entity_type
            merged_payload = dict(add_entry.get("payload") or {})
            merged_payload.update(_entity_in_to_payload(payload))
            # preserva o id pré-alocado (não vem no EntityIn)
            merged_payload["pre_allocated_entity_id"] = entity_id
            add_entry["payload"] = merged_payload
            _save_session_diff(sql, add_ticket_id, add_diff)
            return _virtual_entity_out(
                entity_id, payload.system_id, payload, actor,
                pending_op="add", pending_ticket_id=add_ticket_id,
            )

    entry = {
        "op": "change",
        "schema_name": payload.schema_name,
        "technical_name": payload.technical_name,
        "entity_type": payload.entity_type,
        "payload": {
            **_entity_in_to_payload(payload),
            "target_entity_id": entity_id,
        },
        "field_changes": field_changes,
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return _virtual_entity_out(
        entity_id, payload.system_id, payload, actor,
        pending_op="change", pending_ticket_id=ticket_id,
    )


@router.delete("/{entity_id}", operation_id="deleteEntity")
def delete_entity(
    entity_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Stage delete da entity no ticket OPEN do user.

    Precisa ler schema_name/technical_name/system_id do catálogo (ou negar a
    operação se a entity nem existe).
    """
    actor = _current_email(user_ws) or "unknown"
    row = _fetch_entity_row(sql, entity_id)
    if not row:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    system_id = row[1]
    schema_name = row[2]
    technical_name = row[3]
    entity_type = row[12] or "TABLE"

    ticket_id, diff = get_or_create_session_ticket(sql, actor, system_id)
    entry = {
        "op": "remove",
        "schema_name": schema_name,
        "technical_name": technical_name,
        "entity_type": entity_type,
        "payload": {"target_entity_id": entity_id},
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return {"deleted": entity_id, "pending": True, "ticket_id": ticket_id}


# -------------------- Attributes --------------------

@router.get(
    "/{entity_id}/attributes",
    response_model=list[AttributeOut],
    operation_id="listAttributes",
)
def list_attributes(
    entity_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> list[AttributeOut]:
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT {', '.join(_ATTR_COLS)}
        FROM {s.fq_table('attributes')}
        WHERE entity_id = :entity_id
        ORDER BY COALESCE(ordinal_position, 999999), technical_name
        """,
        [delta.param("entity_id", entity_id)],
    )
    out = [_attr_row_to_out(r) for r in rows]
    actor = _current_email(user_ws)
    if rows:
        # Entity existente: espelha edições staged do ticket OPEN sobre o catálogo
        # (PK/descrição/tipo pendentes aparecem e o payload de update reconstruído
        # na UI usa valores frescos — impede clobber de edições sequenciais).
        if actor and actor != "unknown":
            out = _overlay_existing_attrs(sql, actor, entity_id, out)
    else:
        # Entity virtual (ainda não existe no catálogo): busca attributes do
        # ticket OPEN. Sem isso o EditEntityDialog fica vazio mesmo o user tendo
        # adicionado colunas na criação.
        if actor:
            virtual_attrs = _find_virtual_entity_attrs(sql, actor, entity_id)
            if virtual_attrs:
                out = virtual_attrs
    return out


def _find_virtual_entity_attrs(
    sql, user_email: str, entity_id: str,
) -> list[AttributeOut]:
    """Procura entity virtual (op=add com pre_allocated_entity_id == entity_id)
    em qualquer ticket OPEN do user e retorna os attributes do diff."""
    from ..tickets.session import find_open_session_ticket  # noqa
    from datetime import datetime
    s = get_settings()
    # Olha TODOS os tickets OPEN do user (multiple systems): pelo schema temos
    # que iterar pq find_open_session_ticket exige system_id. Aqui buscamos
    # via SQL direto a entity virtual em qualquer sessão.
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT diff_json
        FROM {s.fq_table('reconciliation_tickets')}
        WHERE status = 'OPEN'
          AND source_type = 'MANUAL'
          AND created_by = :user
        """,
        [delta.param("user", user_email)],
    )
    import json as _json
    now = datetime.utcnow()
    for r in rows:
        try:
            diff = _json.loads(r[0]) if r[0] else {}
        except Exception:
            continue
        for entry in diff.get("entities", []) or []:
            if not isinstance(entry, dict) or entry.get("op") != "add":
                continue
            payload = entry.get("payload") or {}
            if payload.get("pre_allocated_entity_id") == entity_id:
                # Match! Materializa attributes virtuais
                out: list[AttributeOut] = []
                for a in entry.get("attributes") or []:
                    out.append(AttributeOut(
                        attribute_id=a.get("attribute_id") or f"pending-attr-{a.get('technical_name','?')}",
                        entity_id=entity_id,
                        technical_name=a.get("technical_name") or "",
                        logical_name=a.get("logical_name"),
                        ordinal_position=a.get("ordinal_position"),
                        native_data_type=a.get("native_data_type"),
                        is_nullable=a.get("is_nullable"),
                        default_value=a.get("default_value"),
                        is_primary_key=bool(a.get("is_primary_key", False)),
                        description_md=None,
                        business_rule=None,
                        sample_value=None,
                        glossary_term_id=None,
                        native_comment=None,
                        created_at=now, created_by=user_email,
                        updated_at=now, updated_by=user_email,
                        pending_op="add",
                    ))
                return out
    return []


def _resolve_entity_keys(sql, entity_id: str) -> tuple[str, str, str, str] | None:
    """Retorna (system_id, schema_name, technical_name, entity_type) pra
    construir field_changes em attribute mutations. None se entity inexiste
    no catálogo (ex: pré-staged nesta sessão)."""
    row = _fetch_entity_row(sql, entity_id)
    if not row:
        return None
    return (row[1], row[2], row[3], row[12] or "TABLE")


def _find_open_add_entry(
    sql, user_email: str, entity_id: str,
) -> tuple[str, str, dict, dict] | None:
    """Localiza a entry op=add (tabela criada e ainda NÃO aprovada) do user
    cujo pre_allocated_entity_id == entity_id.

    Retorna (ticket_id, system_id, diff, entry) — onde `entry` é o MESMO objeto
    dentro de `diff` (mutar `entry` e salvar `diff` persiste a mudança). None se
    não houver.

    Fix v1.0035: editar uma tabela nova antes de aprovar dava 404 ("entity not
    found") porque a entidade é virtual (só existe na entry op=add do ticket, não
    no catálogo). Aqui resolvemos essa entry para MESCLAR metadados/atributos nela
    — assim a edição reflete na UI (que lê os atributos do add) e o apply cria a
    tabela já completa.
    """
    import json as _json
    s = get_settings()
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT ticket_id, system_id, diff_json
        FROM {s.fq_table('reconciliation_tickets')}
        WHERE status = 'OPEN' AND source_type = 'MANUAL' AND created_by = :user
        """,
        [delta.param("user", user_email)],
    )
    for r in rows:
        try:
            diff = _json.loads(r[2]) if r[2] else {}
        except Exception:
            continue
        for entry in diff.get("entities", []) or []:
            if not isinstance(entry, dict) or entry.get("op") != "add":
                continue
            payload = entry.get("payload") or {}
            if payload.get("pre_allocated_entity_id") == entity_id:
                return (r[0], r[1], diff, entry)
    return None


def _save_session_diff(sql, ticket_id: str, diff: dict) -> None:
    """Persiste um diff mutado de volta no ticket (recount + update)."""
    import json as _json
    s = get_settings()
    ents = diff.get("entities", []) or []
    a = sum(1 for e in ents if e.get("op") == "add")
    r = sum(1 for e in ents if e.get("op") == "remove")
    c = sum(1 for e in ents if e.get("op") == "change")
    diff["additions"], diff["removals"], diff["changes"] = a, r, c
    delta.update_by_id(
        sql, s.fq_table("reconciliation_tickets"), "ticket_id", ticket_id,
        {
            "diff_json": _json.dumps(diff, ensure_ascii=False, default=str),
            "additions_count": a, "removals_count": r, "changes_count": c,
            "applied_at": None,
        },
    )


def _stage_virtual_attr(
    sql, user_email: str, entity_id: str, *, kind: str, attr_payload: dict,
) -> tuple[str, str] | None:
    """Mescla um atributo (add/update/remove) na entry op=add de uma tabela
    virtual (ainda não aprovada). Retorna (ticket_id, system_id) ou None.

    `kind`: "add"/"update" (upsert por technical_name) ou "remove".
    """
    found = _find_open_add_entry(sql, user_email, entity_id)
    if not found:
        return None
    ticket_id, system_id, diff, entry = found
    attrs = list(entry.get("attributes") or [])
    name = attr_payload.get("technical_name")
    if kind == "remove":
        attrs = [a for a in attrs if a.get("technical_name") != name]
    else:
        # upsert por technical_name (merge de campos)
        idx = next((i for i, a in enumerate(attrs)
                    if a.get("technical_name") == name), None)
        if idx is None:
            if attr_payload.get("ordinal_position") is None:
                attr_payload = {**attr_payload, "ordinal_position": len(attrs) + 1}
            attrs.append(attr_payload)
        else:
            merged = {**attrs[idx], **{k: v for k, v in attr_payload.items() if v is not None}}
            attrs[idx] = merged
    entry["attributes"] = attrs
    _save_session_diff(sql, ticket_id, diff)
    return ticket_id, system_id


def _stage_attribute_change(
    sql,
    user_ws,
    *,
    entity_id: str,
    op: str,
    payload_dict: dict,
    field_changes: list[dict] | None = None,
) -> tuple[str, str] | None:
    """Empurra uma mudança de attribute pro ticket OPEN. Retorna
    (ticket_id, system_id) ou None se a entity-host não puder ser localizada.

    A mudança vai como um DiffEntity op=change sobre a entity host, com
    field_changes carregando metadados do attribute (chaves "attribute_add:NAME",
    "attribute_remove:NAME", "attribute:NAME.<field>"). Mantém compat com o
    contrato existente em apply_ticket para field-level changes.
    """
    keys = _resolve_entity_keys(sql, entity_id)
    if not keys:
        return None
    system_id, schema_name, technical_name, entity_type = keys
    actor = _current_email(user_ws) or "unknown"
    ticket_id, diff = get_or_create_session_ticket(sql, actor, system_id)
    entry = {
        "op": "change",
        "schema_name": schema_name,
        "technical_name": technical_name,
        "entity_type": entity_type,
        "payload": {
            "target_entity_id": entity_id,
            f"attribute_{op}": payload_dict,
        },
        "field_changes": field_changes or [],
    }
    stage_entity_change(sql, ticket_id, diff, entry)
    return ticket_id, system_id


@router.post(
    "/{entity_id}/attributes",
    response_model=AttributeOut,
    operation_id="createAttribute",
)
def create_attribute(
    entity_id: str,
    payload: AttributeIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AttributeOut:
    """Stage criação de attribute no ticket OPEN. Não grava no catálogo."""
    if payload.entity_id != entity_id:
        raise HTTPException(400, "entity_id in path and payload must match")
    actor = _current_email(user_ws) or "unknown"
    aid = delta.new_id("attr-")
    attr_payload = {
        "attribute_id": aid,
        "technical_name": payload.technical_name,
        "logical_name": payload.logical_name,
        "ordinal_position": payload.ordinal_position,
        "native_data_type": payload.native_data_type,
        "is_nullable": payload.is_nullable,
        "default_value": payload.default_value,
        "is_primary_key": payload.is_primary_key,
        "description_md": payload.description_md,
        "business_rule": payload.business_rule,
        "sample_value": payload.sample_value,
        "glossary_term_id": payload.glossary_term_id,
        "native_comment": payload.native_comment,
    }
    field_changes = [
        {
            "field": f"attribute_add:{payload.technical_name}",
            "before": None,
            "after": attr_payload,
        }
    ]
    res = _stage_attribute_change(
        sql, user_ws,
        entity_id=entity_id,
        op="add",
        payload_dict=attr_payload,
        field_changes=field_changes,
    )
    if not res:
        # Tabela nova ainda não aprovada (entidade virtual): mescla a coluna na
        # entry op=add do ticket em vez de 404 (fix v1.0035).
        res = _stage_virtual_attr(sql, actor, entity_id, kind="add", attr_payload=attr_payload)
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return _virtual_attribute_out(aid, entity_id, payload, actor, pending_op="add")


@router.put(
    "/{entity_id}/attributes/{attribute_id}",
    response_model=AttributeOut,
    operation_id="updateAttribute",
)
def update_attribute(
    entity_id: str,
    attribute_id: str,
    payload: AttributeIn,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> AttributeOut:
    """Stage update de attribute no ticket OPEN. Não grava no catálogo."""
    actor = _current_email(user_ws) or "unknown"
    attr_payload = {
        "attribute_id": attribute_id,
        "technical_name": payload.technical_name,
        "logical_name": payload.logical_name,
        "ordinal_position": payload.ordinal_position,
        "native_data_type": payload.native_data_type,
        "is_nullable": payload.is_nullable,
        "default_value": payload.default_value,
        "is_primary_key": payload.is_primary_key,
        "description_md": payload.description_md,
        "business_rule": payload.business_rule,
        "sample_value": payload.sample_value,
        "glossary_term_id": payload.glossary_term_id,
        "native_comment": payload.native_comment,
    }
    # Field-level changes — usa um campo agregado, downstream apply é o
    # responsável por detalhar por sub-field. Para staging basta a intenção.
    field_changes = [
        {
            "field": f"attribute:{payload.technical_name}.update",
            "before": None,
            "after": attr_payload,
        }
    ]
    res = _stage_attribute_change(
        sql, user_ws,
        entity_id=entity_id,
        op="change",
        payload_dict=attr_payload,
        field_changes=field_changes,
    )
    if not res:
        # Tabela nova ainda não aprovada: aplica a edição na entry op=add
        # (upsert por technical_name) em vez de 404 (fix v1.0035).
        res = _stage_virtual_attr(sql, actor, entity_id, kind="update", attr_payload=attr_payload)
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return _virtual_attribute_out(attribute_id, entity_id, payload, actor, pending_op="change")


@router.delete(
    "/{entity_id}/attributes/{attribute_id}",
    operation_id="deleteAttribute",
)
def delete_attribute(
    entity_id: str,
    attribute_id: str,
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
) -> dict:
    """Stage delete de attribute no ticket OPEN. Não grava no catálogo."""
    s = get_settings()
    # Try to read current attribute to populate the diff metadata.
    row = delta.fetch_one_params(
        sql,
        f"SELECT technical_name FROM {s.fq_table('attributes')} "
        f"WHERE attribute_id = :attribute_id",
        [delta.param("attribute_id", attribute_id)],
    )
    tech_name = row[0] if row else attribute_id
    attr_payload = {
        "attribute_id": attribute_id,
        "technical_name": tech_name,
    }
    field_changes = [
        {
            "field": f"attribute_remove:{tech_name}",
            "before": attr_payload,
            "after": None,
        }
    ]
    res = _stage_attribute_change(
        sql, user_ws,
        entity_id=entity_id,
        op="remove",
        payload_dict=attr_payload,
        field_changes=field_changes,
    )
    if not res:
        # Tabela nova ainda não aprovada: remove a coluna da entry op=add
        # (fix v1.0035). Casa por technical_name.
        actor = _current_email(user_ws) or "unknown"
        res = _stage_virtual_attr(sql, actor, entity_id, kind="remove", attr_payload=attr_payload)
    if not res:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    ticket_id, _ = res
    return {"deleted": attribute_id, "pending": True, "ticket_id": ticket_id}

