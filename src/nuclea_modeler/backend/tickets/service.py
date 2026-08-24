"""Ticket service — application logic for opening, approving, applying tickets."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from databricks.sdk import WorkspaceClient

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import EntityDecision, TicketApplyResult, TicketDiff, TicketSource

log = logging.getLogger(__name__)


@dataclass
class _ApplyState:
    """State compartilhado pelos sub-handlers de apply_ticket.

    Centraliza contadores + dependências (sql, ws, sandbox_info) pra que
    handlers privados sejam testáveis individualmente.
    """
    sql: Sql
    system_id: str
    applied_by: str
    now: datetime
    decisions: list[EntityDecision] | None
    ws: WorkspaceClient | None
    sandbox_info: dict[str, Any] | None
    applied_entities: int = 0
    applied_attributes: int = 0
    reversed_items: int = 0
    ignored_items: int = 0
    errors: list[str] = field(default_factory=list)


def _decision_for_entity(
    decisions: list[EntityDecision] | None,
    schema_name: str,
    technical_name: str,
    op: str,
) -> EntityDecision | None:
    """Lookup decisão para um entity diff. Retorna None se não há decisão (= default apply)."""
    if not decisions:
        return None
    for d in decisions:
        if d.schema_name == schema_name and d.technical_name == technical_name and d.op == op:
            return d
    return None


def _decision_for_field(
    entity_dec: EntityDecision | None, field: str
) -> str:
    """Para op=change, busca decisão por field. Fallback é a action da entity, default 'apply'."""
    if not entity_dec:
        return "apply"
    for fd in entity_dec.field_decisions:
        if fd.field == field:
            return fd.action
    return entity_dec.action  # fallback


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


def apply_ticket(
    sql: Sql,
    ticket_id: str,
    applied_by: str,
    *,
    decisions: list[EntityDecision] | None = None,
    ws: WorkspaceClient | None = None,
    reverse_sandbox_id: str | None = None,
) -> TicketApplyResult:
    """Apply the diff in the ticket to the entities/attributes catalog.

    `decisions`: lista opcional de decisões por entity. Se None ou vazio, comporta-se
    como antes (apply tudo seguindo a fonte). Decisões individuais podem ser:
      - "apply" (default): cataloga segue a fonte
      - "ignore": skip — catálogo fica como está
      - "reverse": gera DDL e propaga do catálogo PRA fonte (Postgres do Lakebase).
        Requer `ws` e `reverse_sandbox_id`.

    Idempotent at the entity level: existing entities with same (system_id,
    schema_name, technical_name) are skipped on `add` ops.
    """
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT diff_json, system_id, status, source_type "
        f"FROM {s.fq_table('reconciliation_tickets')} "
        f"WHERE ticket_id = :ticket_id",
        [delta.param("ticket_id", ticket_id)],
    )
    if not row:
        return TicketApplyResult(ticket_id=ticket_id, status="OPEN",
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"ticket '{ticket_id}' not found"])
    # Tolerante a linhas de 3 col (testes antigos) — source_type é opcional.
    diff_json, system_id, status = row[0], row[1], row[2]
    source_type = row[3] if len(row) > 3 else None
    if status != "APPROVED":
        return TicketApplyResult(ticket_id=ticket_id, status=status,
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"ticket must be APPROVED to apply (current: {status})"])

    # Ticket de EXCLUSÃO DEFINITIVA de sistema (gate de aprovação): aprovado →
    # purga o modelo e remove o registro do sistema. Só um sistema já arquivado
    # chega aqui (ver systems/router.request_system_deletion).
    if source_type == "SYSTEM_DELETE":
        from ..systems.service import purge_system_model

        now = datetime.utcnow()
        try:
            purge_system_model(sql, system_id)
            delta.delete_by_id(sql, s.fq_table("systems"), "system_id", system_id)
        except Exception as exc:  # noqa: BLE001
            return TicketApplyResult(
                ticket_id=ticket_id, status=status,
                applied_entities=0, applied_attributes=0,
                errors=[f"falha ao excluir o sistema: {exc}"],
            )
        delta.update_by_id(
            sql, s.fq_table("reconciliation_tickets"), "ticket_id", ticket_id,
            {"status": "APPLIED", "applied_at": now, "applied_by": applied_by},
        )
        return TicketApplyResult(
            ticket_id=ticket_id, status="APPLIED",
            applied_entities=0, applied_attributes=0, errors=[],
        )
    try:
        diff = json.loads(diff_json) if diff_json else {"entities": []}
    except json.JSONDecodeError as exc:
        return TicketApplyResult(ticket_id=ticket_id, status=status,
                                 applied_entities=0, applied_attributes=0,
                                 errors=[f"invalid diff_json: {exc}"])

    # Resolve sandbox info uma única vez se vai precisar de reverse
    sandbox_info = None
    if decisions and any(
        d.action == "reverse" or any(fd.action == "reverse" for fd in d.field_decisions)
        for d in decisions
    ):
        if not ws or not reverse_sandbox_id:
            return TicketApplyResult(
                ticket_id=ticket_id, status=status,
                applied_entities=0, applied_attributes=0,
                errors=["reverse requested but ws/reverse_sandbox_id missing"],
            )
        sb = delta.fetch_one_params(
            sql,
            f"SELECT instance_name, database_name FROM {s.fq_table('lakebase_sandboxes')} "
            f"WHERE sandbox_id = :sandbox_id",
            [delta.param("sandbox_id", reverse_sandbox_id)],
        )
        if not sb:
            return TicketApplyResult(
                ticket_id=ticket_id, status=status,
                applied_entities=0, applied_attributes=0,
                errors=[f"sandbox '{reverse_sandbox_id}' not found"],
            )
        sandbox_info = {
            "instance_name": sb[0],
            "database": sb[1] or "databricks_postgres",
        }

    now = datetime.utcnow()
    state = _ApplyState(
        sql=sql, system_id=system_id, applied_by=applied_by, now=now,
        decisions=decisions, ws=ws, sandbox_info=sandbox_info,
    )

    # Ordem: entities primeiro, relationships depois — pra que FKs com source
    # virtual encontrem a entity recém-materializada com o id pré-alocado.
    entries_sorted = sorted(
        diff.get("entities", []),
        key=lambda e: 1 if e.get("schema_name") == "__relationship__" else 0,
    )
    for ent_change in entries_sorted:
        op = ent_change.get("op")
        schema_name = ent_change.get("schema_name", "")
        technical_name = ent_change.get("technical_name", "")

        # Relationships sintéticos vêm com schema_name="__relationship__".
        # `technical_name` é o relationship_id; payload tem todos os campos.
        if schema_name == "__relationship__":
            try:
                _apply_relationship_change(sql, ent_change, applied_by, now)
                if op in ("add", "change", "remove"):
                    state.applied_entities += 1
            except Exception as exc:
                state.errors.append(f"relationship {op} {technical_name}: {exc}")
            continue

        ent_dec = _decision_for_entity(decisions, schema_name, technical_name, op)

        # Para op=add/remove: decisão é da entity inteira (sem field-level split).
        # Para op=change: decisão é por field — entity-level action é fallback.
        if op in ("add", "remove") and ent_dec and ent_dec.action == "ignore":
            state.ignored_items += 1
            continue
        if op in ("add", "remove") and ent_dec and ent_dec.action == "reverse":
            try:
                _apply_reverse_entity(ws, sandbox_info, ent_change)  # type: ignore[arg-type]
                state.reversed_items += 1
            except Exception as exc:
                state.errors.append(f"reverse {op} {schema_name}.{technical_name}: {exc}")
            continue

        try:
            if op == "add":
                _apply_op_add(state, ent_change)
            elif op == "remove":
                _apply_op_remove(state, ent_change)
            elif op == "change":
                _apply_op_change(state, ent_change, ent_dec)
        except Exception as exc:  # keep going on per-entity errors
            state.errors.append(f"{op} {schema_name}.{technical_name}: {exc}")

    # Compatibilidade com código antigo abaixo: aliases pra contadores.
    applied_entities = state.applied_entities
    applied_attributes = state.applied_attributes
    reversed_items = state.reversed_items
    ignored_items = state.ignored_items
    errors = state.errors

    # Update ticket status:
    # - APPLIED se houve ao menos 1 entity/attribute/reverse aplicado E nenhum erro
    # - Mantém APPROVED se tudo errored (user pode tentar reaplicar)
    # - PARTIAL_APPLIED não existe no enum hoje; usa APPLIED e errors pra discriminar.
    total_applied = applied_entities + applied_attributes + reversed_items
    has_errors = bool(errors)
    if total_applied == 0 and has_errors:
        final_status = status  # mantém APPROVED — não toca o ticket no Delta
        log.warning(
            f"[apply_ticket] ticket={ticket_id} 0 applied, {len(errors)} errors — "
            f"mantendo {final_status} para reaplicação. errors={errors[:3]}"
        )
    else:
        final_status = "APPLIED"
        if has_errors:
            log.warning(
                f"[apply_ticket] ticket={ticket_id} aplicado parcialmente: "
                f"{total_applied} ok / {len(errors)} erros. errors={errors[:3]}"
            )
        else:
            log.info(
                f"[apply_ticket] ticket={ticket_id} aplicado: "
                f"entities={applied_entities} attrs={applied_attributes} "
                f"reverse={reversed_items} ignored={ignored_items}"
            )
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
        reversed_items=reversed_items,
        ignored_items=ignored_items,
        errors=errors,
    )


# ─── Reverse engineering helpers ─────────────────────────────────────────────
# Para propagar mudanças do catálogo para a fonte (Postgres do Lakebase).
# Cobre os casos comuns; combinações exóticas retornam erro pra revisão manual.


def _pg_ident(name: str) -> str:
    """Quote a Postgres identifier safely."""
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError(f"identifier inválido: {name!r}")
    return '"' + name + '"'


def _pg_type_for(catalog_type: str | None) -> str:
    """Map a catalog data_type to a reasonable Postgres type.
    Defensive: se vier vazio ou desconhecido, default TEXT."""
    if not catalog_type:
        return "TEXT"
    t = catalog_type.strip().upper()
    # Tipos comuns mapeados; o resto vai como está se parecer válido.
    table = {
        "STRING": "TEXT", "VARCHAR": "TEXT", "CHAR": "TEXT",
        "INT": "INTEGER", "INTEGER": "INTEGER", "BIGINT": "BIGINT",
        "FLOAT": "REAL", "DOUBLE": "DOUBLE PRECISION",
        "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
        "DATE": "DATE", "TIMESTAMP": "TIMESTAMPTZ",
        "DECIMAL": "NUMERIC", "NUMERIC": "NUMERIC",
    }
    if t in table:
        return table[t]
    # VARCHAR(N) e similares — repassar
    if t.startswith(("VARCHAR(", "CHAR(", "DECIMAL(", "NUMERIC(")):
        return t
    return "TEXT"


def _apply_reverse_field(
    ws: WorkspaceClient | None,
    sandbox_info: dict | None,
    schema_name: str,
    technical_name: str,
    field_change: dict,
    sql: Sql,
    entity_id: str,
) -> None:
    """Propagar uma mudança de field do catálogo para a fonte Postgres.

    Cobre:
    - field='attribute_remove:X' → catálogo tem coluna que falta na fonte;
      reverse = ALTER TABLE schema.t ADD COLUMN X <type>;
    - field='attribute:X.native_data_type' → tipo diverge;
      reverse = ALTER TABLE schema.t ALTER COLUMN X TYPE <new_type>; (perigoso, valida)

    Outras formas levantam ValueError para revisão manual.
    """
    from ..lakebase.service import open_connection

    if not ws or not sandbox_info:
        raise ValueError("ws/sandbox_info ausente — reverse precisa de conexão Postgres")

    field = field_change.get("field") or ""
    schema_sql = _pg_ident(schema_name)
    table_sql = _pg_ident(technical_name)

    if field.startswith("attribute_remove:"):
        # Coluna está no catálogo mas não na fonte → ADD COLUMN.
        col_name = field.split(":", 1)[1]
        col_sql = _pg_ident(col_name)
        # Buscar tipo do catálogo
        s = get_settings()
        attr_row = delta.fetch_one_params(
            sql,
            f"SELECT native_data_type FROM {s.fq_table('attributes')} "
            f"WHERE entity_id = :entity_id AND technical_name = :name",
            [delta.param("entity_id", entity_id), delta.param("name", col_name)],
        )
        cat_type = attr_row[0] if attr_row else None
        pg_type = _pg_type_for(cat_type)
        ddl = f"ALTER TABLE {schema_sql}.{table_sql} ADD COLUMN IF NOT EXISTS {col_sql} {pg_type}"
        log.info(f"[ticket-reverse] executing: {ddl}")
        with open_connection(
            ws,
            instance_name=sandbox_info["instance_name"],
            database=sandbox_info["database"],
            user_email=None,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        return

    if field.startswith("attribute:") and field.endswith(".native_data_type"):
        col_name = field.split(":", 1)[1].rsplit(".", 1)[0]
        before = field_change.get("before")
        # Catálogo quer "before" — então o ALTER faz a fonte voltar pro before do diff.
        # (No diff, before=catalog, after=source)
        pg_type = _pg_type_for(before)
        col_sql = _pg_ident(col_name)
        ddl = f"ALTER TABLE {schema_sql}.{table_sql} ALTER COLUMN {col_sql} TYPE {pg_type}"
        log.info(f"[ticket-reverse] executing: {ddl}")
        with open_connection(
            ws,
            instance_name=sandbox_info["instance_name"],
            database=sandbox_info["database"],
            user_email=None,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        return

    raise ValueError(f"reverse não suportado para field={field!r}")


def _apply_reverse_entity(
    ws: WorkspaceClient | None,
    sandbox_info: dict | None,
    ent_change: dict,
) -> None:
    """Propagar add/remove de entity inteira para a fonte.

    - op='remove' (entity no catálogo, falta na fonte) → CREATE TABLE.
    - op='add' (entity na fonte, falta no catálogo) → reverse não faz sentido (já existe);
      levanta ValueError pra forçar o user a escolher apply ou ignore.
    """
    from ..lakebase.service import open_connection

    if not ws or not sandbox_info:
        raise ValueError("ws/sandbox_info ausente — reverse precisa de conexão Postgres")

    op = ent_change.get("op")
    schema_name = ent_change.get("schema_name", "")
    technical_name = ent_change.get("technical_name", "")

    if op == "add":
        raise ValueError("reverse de op=add não faz sentido (entity já está na fonte)")

    if op == "remove":
        # entity está no catálogo mas não na fonte → CREATE TABLE.
        # Atributos do diff vêm em ent_change['attributes'].
        attrs = ent_change.get("attributes") or []
        if not attrs:
            raise ValueError("entity sem atributos no diff — CREATE TABLE precisa de colunas")
        cols_sql = []
        for a in attrs:
            n = a.get("technical_name")
            t = _pg_type_for(a.get("native_data_type"))
            nullable = "" if a.get("is_nullable", True) else " NOT NULL"
            cols_sql.append(f"{_pg_ident(n)} {t}{nullable}")
        # PRIMARY KEY?
        pks = [a.get("technical_name") for a in attrs if a.get("is_primary_key")]
        if pks:
            cols_sql.append("PRIMARY KEY (" + ", ".join(_pg_ident(p) for p in pks) + ")")
        schema_sql = _pg_ident(schema_name)
        table_sql = _pg_ident(technical_name)
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {schema_sql}.{table_sql} (\n  "
            + ",\n  ".join(cols_sql)
            + "\n)"
        )
        log.info(f"[ticket-reverse] executing:\n{ddl}")
        with open_connection(
            ws,
            instance_name=sandbox_info["instance_name"],
            database=sandbox_info["database"],
            user_email=None,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        return

    raise ValueError(f"reverse não suportado para op={op!r}")


# ─── Relationship materialization ─────────────────────────────────────────────
# Aplica entries sintéticos do diff (schema_name="__relationship__") na tabela
# relationships. Suporta op=add/change/remove. Payload do entry tem o shape
# definido em _relationship_in_to_payload (relationships/router.py).


def _resolve_entity_ref(sql: Sql, system_id: str | None, ref: dict | None) -> tuple[str | None, list[str]]:
    """Resolve uma ref por nome ({schema_name, technical_name, attr_names}) para
    (entity_id, [attribute_id]). Usado por relacionamentos extraídos (import),
    onde as FKs vêm por nome e as entities só ganham id no apply.

    Retorna (None, []) se a entity não existir no catálogo (FK órfã)."""
    if not ref:
        return None, []
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT entity_id FROM {s.fq_table('entities')} "
        f"WHERE system_id = :sid AND schema_name = :sch AND technical_name = :tech",
        [
            delta.param("sid", system_id),
            delta.param("sch", ref.get("schema_name")),
            delta.param("tech", ref.get("technical_name")),
        ],
    )
    if not row:
        return None, []
    eid = row[0]
    attr_ids: list[str] = []
    for name in ref.get("attr_names") or []:
        arow = delta.fetch_one_params(
            sql,
            f"SELECT attribute_id FROM {s.fq_table('attributes')} "
            f"WHERE entity_id = :eid AND technical_name = :name",
            [delta.param("eid", eid), delta.param("name", name)],
        )
        if arow:
            attr_ids.append(arow[0])
    return eid, attr_ids


def _apply_relationship_change(
    sql: Sql,
    entry: dict,
    applied_by: str,
    now: datetime,
) -> None:
    op = entry.get("op")
    rid = entry.get("technical_name")
    if not rid:
        raise ValueError("relationship sem technical_name")
    s = get_settings()
    payload = entry.get("payload") or {}

    # Relacionamentos extraídos (import) trazem source_ref/target_ref por nome
    # em vez de entity_id. Resolve agora que as entities já foram materializadas.
    if op in ("add", "change"):
        if not payload.get("source_entity_id") and payload.get("source_ref"):
            src_id, src_attrs = _resolve_entity_ref(
                sql, payload.get("system_id"), payload.get("source_ref")
            )
            if src_id:
                payload = {**payload, "source_entity_id": src_id}
                if src_attrs and not payload.get("source_attr_ids"):
                    payload["source_attr_ids"] = src_attrs
        if not payload.get("target_entity_id") and payload.get("target_ref"):
            tgt_id, tgt_attrs = _resolve_entity_ref(
                sql, payload.get("system_id"), payload.get("target_ref")
            )
            if tgt_id:
                payload = {**payload, "target_entity_id": tgt_id}
                if tgt_attrs and not payload.get("target_attr_ids"):
                    payload["target_attr_ids"] = tgt_attrs
        # FK órfã: alguma ponta não existe no catálogo → não persiste (erro
        # capturado pelo loop do apply_ticket e reportado no resultado).
        if op == "add" and (
            not payload.get("source_entity_id") or not payload.get("target_entity_id")
        ):
            src = payload.get("source_ref", {})
            tgt = payload.get("target_ref", {})
            raise ValueError(
                "FK não resolvida — entity ausente no catálogo: "
                f"{src.get('schema_name')}.{src.get('technical_name')} → "
                f"{tgt.get('schema_name')}.{tgt.get('technical_name')}"
            )

    if op == "remove":
        delta.run_params(
            sql,
            f"DELETE FROM {s.fq_table('relationships')} WHERE relationship_id = :rid",
            [delta.param("rid", rid)],
        )
        return

    if op == "add":
        # Idempotente: skip se já existe
        existing = delta.fetch_one_params(
            sql,
            f"SELECT relationship_id FROM {s.fq_table('relationships')} "
            f"WHERE relationship_id = :rid",
            [delta.param("rid", rid)],
        )
        if existing:
            return
        delta.insert(
            sql,
            s.fq_table("relationships"),
            {
                "relationship_id": rid,
                "system_id": payload.get("system_id"),
                "source_entity_id": payload.get("source_entity_id"),
                "target_entity_id": payload.get("target_entity_id"),
                "source_attr_ids": payload.get("source_attr_ids") or [],
                "target_attr_ids": payload.get("target_attr_ids") or [],
                "rel_type": payload.get("rel_type"),
                "source_cardinality": payload.get("source_cardinality"),
                "target_cardinality": payload.get("target_cardinality"),
                "description": payload.get("description"),
                "origin": payload.get("origin", "MANUAL"),
                "fk_update_rule": payload.get("fk_update_rule"),
                "fk_delete_rule": payload.get("fk_delete_rule"),
                "created_at": now, "created_by": applied_by,
                "updated_at": now, "updated_by": applied_by,
            },
        )
        return

    if op == "change":
        # Para change, payload (atualizado) é a fonte de verdade.
        updates = {
            "source_entity_id": payload.get("source_entity_id"),
            "target_entity_id": payload.get("target_entity_id"),
            "source_attr_ids": payload.get("source_attr_ids") or [],
            "target_attr_ids": payload.get("target_attr_ids") or [],
            "rel_type": payload.get("rel_type"),
            "source_cardinality": payload.get("source_cardinality"),
            "target_cardinality": payload.get("target_cardinality"),
            "description": payload.get("description"),
            "fk_update_rule": payload.get("fk_update_rule"),
            "fk_delete_rule": payload.get("fk_delete_rule"),
            "updated_at": now,
            "updated_by": applied_by,
        }
        # filtra None pra não sobrescrever com null não-intencional
        updates = {k: v for k, v in updates.items() if v is not None}
        if not updates:
            return
        delta.update_by_id(
            sql, s.fq_table("relationships"), "relationship_id", rid, updates,
        )
        return

    raise ValueError(f"op de relationship desconhecida: {op!r}")


# ─── Sub-handlers de apply_ticket (extraídos do bloco gigante) ──────────────


def _ensure_schema(sql: Sql, system_id: str, schema_name: str, actor: str, now: datetime) -> None:
    """Garante a linha de schema de 1ª classe (tabela `schemas`) para
    (system_id, schema_name).

    Assim modelos importados (DDL/Embarcadero) aparecem no navegador M6 e no
    dropdown de schema do DER sem ajuste manual — o `listSchemas` lê da tabela
    `schemas`, então sem essa linha o schema não aparece. Idempotente: no-op se
    já existir. Best-effort: o chamador deve tolerar falha (não abortar o apply).
    """
    if not schema_name:
        return
    s = get_settings()
    existing = delta.fetch_one_params(
        sql,
        f"SELECT schema_id FROM {s.fq_table('schemas')} "
        f"WHERE system_id = :sid AND schema_name = :sch",
        [delta.param("sid", system_id), delta.param("sch", schema_name)],
    )
    if existing:
        return
    delta.insert(
        sql,
        s.fq_table("schemas"),
        {
            "schema_id": delta.new_id("sch-"),
            "system_id": system_id,
            "schema_name": schema_name,
            "is_active": True,
            "created_at": now, "created_by": actor,
            "updated_at": now, "updated_by": actor,
        },
    )


def _apply_op_add(state: _ApplyState, ent_change: dict[str, Any]) -> None:
    """Materializa um entity novo + attributes + indexes (op='add').

    Idempotente E AUTO-CURÁVEL: se a entity já existe (ex: um apply anterior
    criou a entity mas falhou nos atributos por erro transitório de warehouse),
    NÃO pula — reconcilia, inserindo apenas os atributos que faltam. Cada
    atributo é inserido de forma resiliente: uma falha pontual não aborta os
    demais (fica registrada em ``errors`` e é curada num re-apply). Isso evita o
    estado "entity materializada sem colunas" que antes ficava preso, já que o
    skip por idempotência impedia o conserto.

    Preserva ``pre_allocated_entity_id`` quando presente (necessário pra FKs
    entre entities criadas na mesma sessão).
    """
    s = get_settings()
    schema_name = ent_change.get("schema_name", "")
    technical_name = ent_change.get("technical_name", "")

    # Registra o schema de 1ª classe (navegador M6) — best-effort, não aborta o apply.
    try:
        _ensure_schema(state.sql, state.system_id, schema_name, state.applied_by, state.now)
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"ensure schema {schema_name}: {exc}")

    existing = delta.fetch_one_params(
        state.sql,
        f"SELECT entity_id FROM {s.fq_table('entities')} "
        f"WHERE system_id = :system_id "
        f"AND schema_name = :schema_name "
        f"AND technical_name = :technical_name",
        [
            delta.param("system_id", state.system_id),
            delta.param("schema_name", schema_name),
            delta.param("technical_name", technical_name),
        ],
    )

    if existing:
        # Entity já existe → reconcilia atributos faltantes (não recria a entity
        # nem reaplica índices).
        eid = existing[0]
        new_entity = False
    else:
        # DEDUP GUARD: mesma technical_name no sistema, mas em schema diferente?
        # Pode ocorrer em reimport com search_path divergente. Detecta e reutiliza
        # a entity existente (actualiza schema para consistência, if needed).
        # Razão: Delta NÃO enforça UNIQUE/PK → barreira tem que ser aplicação.
        dedup_existing = delta.fetch_one_params(
            state.sql,
            f"SELECT entity_id, schema_name FROM {s.fq_table('entities')} "
            f"WHERE system_id = :system_id "
            f"AND LOWER(technical_name) = LOWER(:technical_name) "
            f"LIMIT 1",
            [
                delta.param("system_id", state.system_id),
                delta.param("technical_name", technical_name),
            ],
        )
        if dedup_existing:
            # Reutiliza a entity existente (dedup)
            eid = dedup_existing[0]
            new_entity = False
            if dedup_existing[1] != schema_name:
                log.info(
                    "_apply_op_add: dedup detectado — entidade '%s' existe em schema '%s', "
                    "agora em schema '%s' (search_path divergente?). Reutilizando.",
                    technical_name, dedup_existing[1], schema_name
                )
        else:
            payload = ent_change.get("payload") or {}
            eid = payload.get("pre_allocated_entity_id") or delta.new_id("ent-")
            delta.insert(
                state.sql,
                s.fq_table("entities"),
                {
                    "entity_id": eid,
                    "system_id": state.system_id,
                    "schema_name": schema_name,
                    "technical_name": technical_name,
                    "logical_name": payload.get("logical_name"),
                    "description_md": payload.get("description_md") or payload.get("native_comment"),
                    "domain": payload.get("domain"),
                    "entity_type": ent_change.get("entity_type", "TABLE"),
                    "native_comment": payload.get("native_comment"),
                    "row_count_approx": payload.get("row_count_approx"),
                    "tags": payload.get("tags", []),
                    "is_shared": bool(payload.get("is_shared", False)),
                    "last_extracted_at": state.now,
                    "created_at": state.now, "created_by": state.applied_by,
                    "updated_at": state.now, "updated_by": state.applied_by,
                },
            )
            state.applied_entities += 1
            new_entity = True

            # Índices (eng. reversa) — só na criação; origin=EXTRACTED diferencia
            # da criação manual via UI.
            for ix_payload in ent_change.get("indexes") or []:
                try:
                    from ..entities.indexes import apply_index_add
                    apply_index_add(
                        state.sql, entity_id=eid,
                        payload={**ix_payload, "origin": "EXTRACTED"},
                        now=state.now, actor=state.applied_by,
                    )
                except Exception as exc:
                    state.errors.append(
                        f"index {schema_name}.{technical_name}."
                        f"{ix_payload.get('index_name')}: {exc}"
                    )

    # Atributos: insere só os que ainda não existem (reconcile/idempotência por
    # technical_name). Cada insert é resiliente — uma falha não derruba o resto.
    existing_attr_names: set[str] = set()
    if not new_entity:
        attr_rows = delta.fetch_all_params(
            state.sql,
            f"SELECT technical_name FROM {s.fq_table('attributes')} WHERE entity_id = :eid",
            [delta.param("eid", eid)],
        )
        existing_attr_names = {r[0] for r in attr_rows}

    for idx, attr in enumerate(ent_change.get("attributes") or []):
        name = attr.get("technical_name", "")
        if name in existing_attr_names:
            continue
        try:
            aid = attr.get("attribute_id") or delta.new_id("attr-")
            delta.insert(
                state.sql,
                s.fq_table("attributes"),
                {
                    "attribute_id": aid,
                    "entity_id": eid,
                    "technical_name": name,
                    "logical_name": attr.get("logical_name"),
                    "ordinal_position": attr.get("ordinal_position", idx + 1),
                    "native_data_type": attr.get("native_data_type"),
                    "is_nullable": attr.get("is_nullable"),
                    "default_value": attr.get("default_value"),
                    "is_primary_key": bool(attr.get("is_primary_key", False)),
                    "native_comment": attr.get("native_comment"),
                    "created_at": state.now, "created_by": state.applied_by,
                    "updated_at": state.now, "updated_by": state.applied_by,
                },
            )
            state.applied_attributes += 1
        except Exception as exc:  # noqa: BLE001 — resiliente: cura no re-apply
            state.errors.append(
                f"attribute {schema_name}.{technical_name}.{name}: {exc}"
            )


def _apply_op_remove(state: _ApplyState, ent_change: dict[str, Any]) -> None:
    """Hard-delete entity + attributes (op='remove'). Idempotente."""
    s = get_settings()
    schema_name = ent_change.get("schema_name", "")
    technical_name = ent_change.get("technical_name", "")

    existing = delta.fetch_one_params(
        state.sql,
        f"SELECT entity_id FROM {s.fq_table('entities')} "
        f"WHERE system_id = :system_id "
        f"AND schema_name = :schema_name "
        f"AND technical_name = :technical_name",
        [
            delta.param("system_id", state.system_id),
            delta.param("schema_name", schema_name),
            delta.param("technical_name", technical_name),
        ],
    )
    if not existing:
        return
    eid = existing[0]
    delta.run_params(
        state.sql,
        f"DELETE FROM {s.fq_table('attributes')} WHERE entity_id = :entity_id",
        [delta.param("entity_id", eid)],
    )
    delta.run_params(
        state.sql,
        f"DELETE FROM {s.fq_table('entities')} WHERE entity_id = :entity_id",
        [delta.param("entity_id", eid)],
    )
    state.applied_entities += 1


def _apply_op_change(
    state: _ApplyState,
    ent_change: dict[str, Any],
    ent_dec: EntityDecision | None,
) -> None:
    """Aplica field_changes (op='change'). Acumula entity-level updates e
    despacha field_changes por prefixo (attribute_*, index_*, partitioning:set)."""
    s = get_settings()
    schema_name = ent_change.get("schema_name", "")
    technical_name = ent_change.get("technical_name", "")

    existing = delta.fetch_one_params(
        state.sql,
        f"SELECT entity_id FROM {s.fq_table('entities')} "
        f"WHERE system_id = :system_id "
        f"AND schema_name = :schema_name "
        f"AND technical_name = :technical_name",
        [
            delta.param("system_id", state.system_id),
            delta.param("schema_name", schema_name),
            delta.param("technical_name", technical_name),
        ],
    )
    if not existing:
        state.errors.append(
            f"change target not found: {schema_name}.{technical_name}"
        )
        return
    eid = existing[0]

    updates: dict[str, Any] = {}
    for fc in ent_change.get("field_changes") or []:
        fld = fc.get("field")
        new_val = fc.get("after")
        field_action = _decision_for_field(ent_dec, fld or "")

        if field_action == "ignore":
            state.ignored_items += 1
            continue
        if field_action == "reverse":
            try:
                _apply_reverse_field(
                    state.ws, state.sandbox_info,  # type: ignore[arg-type]
                    schema_name, technical_name, fc, state.sql, eid,
                )
                state.reversed_items += 1
            except Exception as exc:
                state.errors.append(
                    f"reverse {schema_name}.{technical_name}.{fld}: {exc}"
                )
            continue
        # action == "apply" — dispatch por prefixo
        _dispatch_field_change(state, eid, fld, new_val, updates)

    if updates:
        updates["updated_at"] = state.now
        updates["updated_by"] = state.applied_by
        updates["last_extracted_at"] = state.now
        delta.update_by_id(
            state.sql, s.fq_table("entities"), "entity_id", eid, updates,
        )
        state.applied_entities += 1


def _dispatch_field_change(
    state: _ApplyState,
    eid: str,
    fld: str | None,
    new_val: Any,
    updates_acc: dict[str, Any],
) -> None:
    """Despacha 1 field_change pelo prefixo do nome do campo.

    - Entity metadata (allowlist) → acumula em ``updates_acc`` (batch update no fim)
    - ``attribute_add:NAME`` → INSERT em attributes
    - ``attribute_remove:NAME`` → DELETE em attributes
    - ``attribute:NAME.update`` → UPDATE em attributes (subset de fields)
    - ``index_add:NAME`` / ``index_remove:NAME`` / ``index_change:ID``
    - ``partitioning:set``
    """
    if not fld:
        return
    s = get_settings()
    ENTITY_FIELDS = {
        "logical_name", "description_md", "native_comment",
        "row_count_approx", "domain", "is_shared",
    }

    if fld in ENTITY_FIELDS:
        updates_acc[fld] = new_val
        return

    if fld.startswith("attribute_add:"):
        attr_payload = new_val or {}
        aid = delta.new_id("attr-")
        delta.insert(
            state.sql,
            s.fq_table("attributes"),
            {
                "attribute_id": aid,
                "entity_id": eid,
                "technical_name": attr_payload.get(
                    "technical_name", fld.split(":", 1)[1]
                ),
                "logical_name": attr_payload.get("logical_name"),
                "ordinal_position": attr_payload.get("ordinal_position"),
                "native_data_type": attr_payload.get("native_data_type"),
                "is_nullable": attr_payload.get("is_nullable"),
                "default_value": attr_payload.get("default_value"),
                "is_primary_key": bool(attr_payload.get("is_primary_key", False)),
                # description_md/business_rule persistem na CRIAÇÃO de coluna
                # (v1.0030) — ex.: coluna criada já com descrição no modal do DER.
                "description_md": attr_payload.get("description_md"),
                "business_rule": attr_payload.get("business_rule"),
                "native_comment": attr_payload.get("native_comment"),
                "created_at": state.now, "created_by": state.applied_by,
                "updated_at": state.now, "updated_by": state.applied_by,
            },
        )
        state.applied_attributes += 1
        return

    if fld.startswith("attribute_remove:"):
        name = fld.split(":", 1)[1]
        delta.run_params(
            state.sql,
            f"DELETE FROM {s.fq_table('attributes')} "
            f"WHERE entity_id = :entity_id AND technical_name = :name",
            [delta.param("entity_id", eid), delta.param("name", name)],
        )
        state.applied_attributes += 1
        return

    if fld.startswith("attribute:") and fld.endswith(".update"):
        name = fld.split(":", 1)[1].rsplit(".", 1)[0]
        attr_payload = new_val or {}
        attr_updates = {
            k: v for k, v in {
                "logical_name": attr_payload.get("logical_name"),
                "native_data_type": attr_payload.get("native_data_type"),
                "is_nullable": attr_payload.get("is_nullable"),
                "default_value": attr_payload.get("default_value"),
                "is_primary_key": attr_payload.get("is_primary_key"),
                # ordinal_position entra no allowlist para persistir a
                # REORDENAÇÃO de PK composta (drag na UI). Sem ele o novo
                # número da PK não sobreviveria ao apply do ticket.
                "ordinal_position": attr_payload.get("ordinal_position"),
                # description_md/business_rule entram no allowlist (v1.0030) para
                # a EDIÇÃO de descrição por coluna (no modal do DER e na tela do
                # objeto) sobreviver ao apply. Antes eram descartados aqui e a
                # descrição staged nunca chegava ao catálogo. Gotcha: o filtro
                # `v is not None` impede LIMPAR pra NULL — string vazia ("") passa
                # e zera o texto; isso é intencional (edição só adiciona/troca).
                "description_md": attr_payload.get("description_md"),
                "business_rule": attr_payload.get("business_rule"),
                "native_comment": attr_payload.get("native_comment"),
            }.items() if v is not None
        }
        if attr_updates:
            attr_updates["updated_at"] = state.now
            attr_updates["updated_by"] = state.applied_by
            sets = ", ".join(f"{k} = :{k}" for k in attr_updates.keys())
            params = [delta.param(k, v) for k, v in attr_updates.items()]
            params.append(delta.param("entity_id", eid))
            params.append(delta.param("name", name))
            delta.run_params(
                state.sql,
                f"UPDATE {s.fq_table('attributes')} SET {sets} "
                f"WHERE entity_id = :entity_id AND technical_name = :name",
                params,
            )
            state.applied_attributes += 1
        return

    if fld.startswith("index_add:"):
        from ..entities.indexes import apply_index_add
        apply_index_add(
            state.sql, entity_id=eid, payload=(new_val or {}),
            now=state.now, actor=state.applied_by,
        )
        return

    if fld.startswith("index_remove:"):
        from ..entities.indexes import apply_index_remove
        name = fld.split(":", 1)[1]
        apply_index_remove(state.sql, entity_id=eid, index_name=name)
        return

    if fld.startswith("index_change:"):
        from ..entities.indexes import apply_index_change
        index_id = fld.split(":", 1)[1]
        apply_index_change(
            state.sql, entity_id=eid, index_id=index_id,
            payload=(new_val or {}), now=state.now, actor=state.applied_by,
        )
        return

    if fld == "partitioning:set":
        from ..entities.indexes import apply_partitioning_set
        apply_partitioning_set(
            state.sql, entity_id=eid, payload=(new_val or {}),
            now=state.now, actor=state.applied_by,
        )
        return
