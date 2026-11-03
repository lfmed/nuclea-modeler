"""Apply EM LOTE de tickets grandes (rodada 9 consolidada, item 10).

RCA (medida no app deployado com `scripts/repro_large_ddl.py --real`): o import de
um DDL de 12 mil linhas (358 tabelas, ~9 mil colunas, 357 FKs) funcionava — o que
FALHAVA era aprovar/aplicar o ticket: 502 do proxy do Databricks Apps aos 300 s com
só 43 de 358 tabelas aplicadas (~7 s por tabela). O cliente via isso como "o import
de DDL extenso falha".

Por quê: o caminho unitário (`_apply_op_add` / `_apply_relationship_change`) faz
várias idas ao warehouse POR ITEM — garantir schema, checar existência, checar
duplicata, inserir entity, inserir cada índice, inserir atributos; e por FK:
resolver cada ponta por nome (+1 consulta por coluna), checar existência, inserir.
Cada ida é um submit+poll completo na Statement Execution API (~1 s).

Este módulo faz o MESMO trabalho com poucas idas: carrega UMA vez o que já existe
(entities, schemas, atributos, relacionamentos do sistema) e insere tudo com
`insert_many` em grupos. As linhas são montadas pelos MESMOS builders do caminho
unitário (`_entity_row`, `_attribute_row`, `_relationship_row`, `build_index_row`),
então o conteúdo gravado é idêntico.

Resiliência preservada: se o lote de um GRUPO falhar, aquele grupo é reaplicado
pelo caminho unitário (idempotente e auto-curável — reconcilia o que já entrou).
Itens que já existem no catálogo (reimport/dedup) vão direto para o caminho
unitário, que sabe reconciliar.

Só é usado para tickets com muitos `add` (ver BULK_MIN_ADDS em service.apply_ticket):
tickets pequenos (editor do DER, CSV) seguem exatamente o caminho de sempre.
"""
from __future__ import annotations

import logging
from typing import Any

from ..core import delta
from ..core._nuclea_config import get_settings

log = logging.getLogger(__name__)

# Entidades por grupo: 1 INSERT de entities + ceil(colunas/ATTR_CHUNK) de atributos
# + 1 de índices. 50 tabelas × ~25 colunas ≈ 1.250 linhas → 3 INSERTs de atributo.
ENTITY_GROUP = 50
ATTR_CHUNK = 500
REL_CHUNK = 200


def apply_entity_adds_bulk(state, adds: list[dict[str, Any]]) -> None:
    """Materializa vários op=add de entity em lote. Atualiza `state` (contadores e
    erros) exatamente como o caminho unitário faria."""
    from .service import (
        _apply_flag_keys_to_target,
        _apply_op_add,
        _attribute_row,
        _entity_row,
    )
    from ..entities.indexes import build_index_row

    if not adds:
        return
    s = get_settings()
    sql = state.sql

    # O que JÁ existe no sistema (1 consulta). Existente ou homônimo (dedup por
    # nome case-insensitive, igual ao _apply_op_add) → caminho unitário reconcilia.
    rows = delta.fetch_all_params(
        sql,
        f"SELECT entity_id, schema_name, technical_name FROM {s.fq_table('entities')} "
        f"WHERE system_id = :sid",
        [delta.param("sid", state.system_id)],
    )
    existing_lower = {str(r[2]).lower() for r in rows if r[2]}
    fresh: list[dict[str, Any]] = []
    reconcile: list[dict[str, Any]] = []
    seen_lower: set[str] = set()
    for ch in adds:
        lname = str(ch.get("technical_name", "")).lower()
        # Duplicado DENTRO do próprio ticket também vai para o unitário (o 2º vira
        # reconcile do 1º, como seria no loop original).
        if lname in existing_lower or lname in seen_lower:
            reconcile.append(ch)
        else:
            fresh.append(ch)
            seen_lower.add(lname)

    # Schemas de 1ª classe (navegador M6) — 1 consulta + 1 INSERT.
    try:
        have = {
            r[0]
            for r in delta.fetch_all_params(
                sql,
                f"SELECT schema_name FROM {s.fq_table('schemas')} WHERE system_id = :sid",
                [delta.param("sid", state.system_id)],
            )
        }
        new_schemas = sorted({ch.get("schema_name", "") for ch in fresh} - have - {""})
        if new_schemas:
            delta.insert_many(
                sql,
                s.fq_table("schemas"),
                [
                    {
                        "schema_id": delta.new_id("sch-"),
                        "system_id": state.system_id,
                        "schema_name": name,
                        "is_active": True,
                        "created_at": state.now, "created_by": state.applied_by,
                        "updated_at": state.now, "updated_by": state.applied_by,
                    }
                    for name in new_schemas
                ],
            )
    except Exception as exc:  # noqa: BLE001 — best-effort, igual ao _ensure_schema
        state.errors.append(f"ensure schemas (lote): {exc}")

    for start in range(0, len(fresh), ENTITY_GROUP):
        group = fresh[start : start + ENTITY_GROUP]
        ent_rows: list[dict[str, Any]] = []
        attr_rows: list[dict[str, Any]] = []
        idx_rows: list[dict[str, Any]] = []
        flag_jobs: list[tuple[str, list[str], str]] = []  # (kind, keys, id)
        for ch in group:
            payload = ch.get("payload") or {}
            eid = payload.get("pre_allocated_entity_id") or delta.new_id("ent-")
            ent_rows.append(_entity_row(state, ch, eid))
            if payload.get("flag_keys"):
                flag_jobs.append(("entity", payload["flag_keys"], eid))
            for idx, attr in enumerate(ch.get("attributes") or []):
                if not attr.get("technical_name"):
                    continue
                row = _attribute_row(state, attr, idx, eid)
                attr_rows.append(row)
                if attr.get("flag_keys"):
                    flag_jobs.append(("attribute", attr["flag_keys"], row["attribute_id"]))
            for ix in ch.get("indexes") or []:
                idx_rows.append(
                    build_index_row(
                        entity_id=eid, payload={**ix, "origin": "EXTRACTED"},
                        now=state.now, actor=state.applied_by,
                    )
                )
        # Ordem: entities → índices → atributos. Se só os ATRIBUTOS falharem (o lote
        # mais pesado), o unitário acha a entity já criada e reconcilia as colunas
        # que faltam — e os índices já estão gravados (o unitário só cria índice na
        # CRIAÇÃO da entity, então eles se perderiam se viessem por último).
        try:
            delta.insert_many(sql, s.fq_table("entities"), ent_rows)
            if idx_rows:
                delta.insert_many(sql, s.fq_table("entity_indexes"), idx_rows)
            if attr_rows:
                delta.insert_many(sql, s.fq_table("attributes"), attr_rows, chunk_size=ATTR_CHUNK)
        except Exception as exc:  # noqa: BLE001 — degrada o GRUPO para o unitário
            log.warning(
                "bulk_apply: lote de %d entidades falhou (%s) — reaplicando item a item.",
                len(group), exc,
            )
            reconcile.extend(group)
            continue
        state.applied_entities += len(ent_rows)
        state.applied_attributes += len(attr_rows)
        for kind, keys, target_id in flag_jobs:
            if kind == "entity":
                _apply_flag_keys_to_target(state, flag_keys=keys, entity_id=target_id)
            else:
                _apply_flag_keys_to_target(state, flag_keys=keys, attribute_id=target_id)

    # Existentes / homônimos / grupos que falharam: caminho unitário (reconcilia).
    for ch in reconcile:
        try:
            _apply_op_add(state, ch)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"add {ch.get('schema_name')}.{ch.get('technical_name')}: {exc}")


def apply_relationship_adds_bulk(state, rel_adds: list[dict[str, Any]]) -> None:
    """Materializa vários op=add de relacionamento em lote. Resolve as pontas por
    nome contra um mapa carregado UMA vez (depois das entities do ticket), com a
    mesma regra do `_resolve_entity_ref`, e insere com `insert_many`."""
    from .service import _apply_relationship_change, _relationship_row

    if not rel_adds:
        return
    s = get_settings()
    sql = state.sql
    sid = state.system_id

    ents = delta.fetch_all_params(
        sql,
        f"SELECT entity_id, schema_name, technical_name FROM {s.fq_table('entities')} "
        f"WHERE system_id = :sid",
        [delta.param("sid", sid)],
    )
    ent_by_key = {(r[1], r[2]): r[0] for r in ents}
    attrs = delta.fetch_all_params(
        sql,
        f"SELECT a.entity_id, a.technical_name, a.attribute_id "
        f"FROM {s.fq_table('attributes')} a "
        f"JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id "
        f"WHERE e.system_id = :sid",
        [delta.param("sid", sid)],
    )
    attr_by_key = {(r[0], r[1]): r[2] for r in attrs}
    existing_rels = {
        r[0]
        for r in delta.fetch_all_params(
            sql,
            f"SELECT relationship_id FROM {s.fq_table('relationships')} WHERE system_id = :sid",
            [delta.param("sid", sid)],
        )
    }

    def resolve(ref: dict | None) -> tuple[str | None, list[str]]:
        if not ref:
            return None, []
        eid = ent_by_key.get((ref.get("schema_name"), ref.get("technical_name")))
        if not eid:
            return None, []
        ids = [attr_by_key[(eid, n)] for n in (ref.get("attr_names") or []) if (eid, n) in attr_by_key]
        return eid, ids

    rows: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []  # entradas correspondentes a `rows` (fallback)
    for entry in rel_adds:
        rid = entry.get("technical_name")
        if not rid:
            state.errors.append("relationship add : relationship sem technical_name")
            continue
        if rid in existing_rels:
            continue  # idempotente, como no unitário
        payload = dict(entry.get("payload") or {})
        if not payload.get("source_entity_id") and payload.get("source_ref"):
            src_id, src_attrs = resolve(payload.get("source_ref"))
            if src_id:
                payload["source_entity_id"] = src_id
                if src_attrs and not payload.get("source_attr_ids"):
                    payload["source_attr_ids"] = src_attrs
        if not payload.get("target_entity_id") and payload.get("target_ref"):
            tgt_id, tgt_attrs = resolve(payload.get("target_ref"))
            if tgt_id:
                payload["target_entity_id"] = tgt_id
                if tgt_attrs and not payload.get("target_attr_ids"):
                    payload["target_attr_ids"] = tgt_attrs
        if not payload.get("source_entity_id") or not payload.get("target_entity_id"):
            src = payload.get("source_ref", {}) or {}
            tgt = payload.get("target_ref", {}) or {}
            # Mesma mensagem do caminho unitário (o usuário vê no resultado do apply).
            state.errors.append(
                f"relationship add {rid}: FK não resolvida — entity ausente no catálogo: "
                f"{src.get('schema_name')}.{src.get('technical_name')} → "
                f"{tgt.get('schema_name')}.{tgt.get('technical_name')}"
            )
            continue
        payload.setdefault("system_id", sid)
        rows.append(_relationship_row(rid, payload, state.applied_by, state.now))
        pending.append(entry)
        existing_rels.add(rid)  # duplicata dentro do mesmo ticket

    for start in range(0, len(rows), REL_CHUNK):
        chunk = rows[start : start + REL_CHUNK]
        try:
            delta.insert_many(sql, s.fq_table("relationships"), chunk, chunk_size=REL_CHUNK)
            state.applied_entities += len(chunk)  # o unitário conta FK em applied_entities
        except Exception as exc:  # noqa: BLE001 — degrada o lote para o unitário
            log.warning("bulk_apply: lote de %d FKs falhou (%s) — item a item.", len(chunk), exc)
            for entry in pending[start : start + REL_CHUNK]:
                try:
                    _apply_relationship_change(sql, entry, state.applied_by, state.now)
                    state.applied_entities += 1
                except Exception as exc_one:  # noqa: BLE001
                    state.errors.append(f"relationship add {entry.get('technical_name')}: {exc_one}")
