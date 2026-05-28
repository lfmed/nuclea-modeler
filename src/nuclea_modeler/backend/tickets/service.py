"""Ticket service — application logic for opening, approving, applying tickets."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from databricks.sdk import WorkspaceClient

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql
from .models import EntityDecision, TicketApplyResult, TicketDiff, TicketSource

log = logging.getLogger(__name__)


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

    applied_entities = 0
    applied_attributes = 0
    reversed_items = 0
    ignored_items = 0
    errors: list[str] = []
    now = datetime.utcnow()

    for ent_change in diff.get("entities", []):
        op = ent_change.get("op")
        schema_name = ent_change.get("schema_name", "")
        technical_name = ent_change.get("technical_name", "")

        # Relationships sintéticos vêm com schema_name="__relationship__".
        # `technical_name` é o relationship_id; payload tem todos os campos.
        if schema_name == "__relationship__":
            try:
                _apply_relationship_change(sql, ent_change, applied_by, now)
                if op == "add":
                    applied_entities += 1
                elif op == "change":
                    applied_entities += 1
                elif op == "remove":
                    applied_entities += 1
            except Exception as exc:
                errors.append(f"relationship {op} {technical_name}: {exc}")
            continue

        ent_dec = _decision_for_entity(decisions, schema_name, technical_name, op)

        # Para op=add/remove: decisão é da entity inteira (sem field-level split).
        # Para op=change: decisão é por field — entity-level action é fallback.
        if op in ("add", "remove") and ent_dec and ent_dec.action == "ignore":
            ignored_items += 1
            continue
        if op in ("add", "remove") and ent_dec and ent_dec.action == "reverse":
            try:
                _apply_reverse_entity(ws, sandbox_info, ent_change)  # type: ignore[arg-type]
                reversed_items += 1
            except Exception as exc:
                errors.append(f"reverse {op} {schema_name}.{technical_name}: {exc}")
            continue

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
                        "is_shared": bool(payload.get("is_shared", False)),
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
                # Lookup entity and hard-delete entity + attributes.
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
                    # Já não está no catálogo — nada a fazer.
                    continue
                eid = existing[0]
                delta.run_params(
                    sql,
                    f"DELETE FROM {s.fq_table('attributes')} WHERE entity_id = :entity_id",
                    [delta.param("entity_id", eid)],
                )
                delta.run_params(
                    sql,
                    f"DELETE FROM {s.fq_table('entities')} WHERE entity_id = :entity_id",
                    [delta.param("entity_id", eid)],
                )
                applied_entities += 1
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
                    field_action = _decision_for_field(ent_dec, fld or "")

                    if field_action == "ignore":
                        ignored_items += 1
                        continue
                    if field_action == "reverse":
                        try:
                            _apply_reverse_field(
                                ws, sandbox_info,  # type: ignore[arg-type]
                                schema_name, technical_name, fc, sql, eid,
                            )
                            reversed_items += 1
                        except Exception as exc:
                            errors.append(
                                f"reverse {schema_name}.{technical_name}.{fld}: {exc}"
                            )
                        continue
                    # action == "apply" (default):
                    # 1. Metadados de entity (field na allowlist) → batch em updates
                    # 2. attribute_add:NAME → INSERT em attributes
                    # 3. attribute_remove:NAME → DELETE em attributes
                    # 4. attribute:NAME.update → UPDATE em attributes
                    if fld in {
                        "logical_name", "description_md", "native_comment",
                        "row_count_approx", "domain", "is_shared",
                    }:
                        updates[fld] = new_val
                    elif fld and fld.startswith("attribute_add:"):
                        attr_payload = new_val or {}
                        aid = delta.new_id("attr-")
                        delta.insert(
                            sql,
                            s.fq_table("attributes"),
                            {
                                "attribute_id": aid,
                                "entity_id": eid,
                                "technical_name": attr_payload.get("technical_name", fld.split(":", 1)[1]),
                                "logical_name": attr_payload.get("logical_name"),
                                "ordinal_position": attr_payload.get("ordinal_position"),
                                "native_data_type": attr_payload.get("native_data_type"),
                                "is_nullable": attr_payload.get("is_nullable"),
                                "default_value": attr_payload.get("default_value"),
                                "is_primary_key": bool(attr_payload.get("is_primary_key", False)),
                                "native_comment": attr_payload.get("native_comment"),
                                "created_at": now, "created_by": applied_by,
                                "updated_at": now, "updated_by": applied_by,
                            },
                        )
                        applied_attributes += 1
                    elif fld and fld.startswith("attribute_remove:"):
                        name = fld.split(":", 1)[1]
                        delta.run_params(
                            sql,
                            f"DELETE FROM {s.fq_table('attributes')} "
                            f"WHERE entity_id = :entity_id AND technical_name = :name",
                            [delta.param("entity_id", eid), delta.param("name", name)],
                        )
                        applied_attributes += 1
                    elif fld and fld.startswith("attribute:") and fld.endswith(".update"):
                        name = fld.split(":", 1)[1].rsplit(".", 1)[0]
                        attr_payload = new_val or {}
                        attr_updates = {
                            k: v for k, v in {
                                "logical_name": attr_payload.get("logical_name"),
                                "native_data_type": attr_payload.get("native_data_type"),
                                "is_nullable": attr_payload.get("is_nullable"),
                                "default_value": attr_payload.get("default_value"),
                                "is_primary_key": attr_payload.get("is_primary_key"),
                                "native_comment": attr_payload.get("native_comment"),
                            }.items() if v is not None
                        }
                        if attr_updates:
                            attr_updates["updated_at"] = now
                            attr_updates["updated_by"] = applied_by
                            # update_by_id requer key+key_val. attributes não tem
                            # PK conhecida aqui — usamos um UPDATE explícito.
                            sets = ", ".join(f"{k} = :{k}" for k in attr_updates.keys())
                            params = [delta.param(k, v) for k, v in attr_updates.items()]
                            params.append(delta.param("entity_id", eid))
                            params.append(delta.param("name", name))
                            delta.run_params(
                                sql,
                                f"UPDATE {s.fq_table('attributes')} SET {sets} "
                                f"WHERE entity_id = :entity_id AND technical_name = :name",
                                params,
                            )
                            applied_attributes += 1
                if updates:
                    updates["updated_at"] = now
                    updates["updated_by"] = applied_by
                    updates["last_extracted_at"] = now
                    delta.update_by_id(sql, s.fq_table("entities"), "entity_id", eid, updates)
                    applied_entities += 1
        except Exception as exc:  # keep going on per-entity errors
            errors.append(f"{op} {schema_name}.{technical_name}: {exc}")

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
