"""Overlay editorial pra DiagramView.

Aplica o diff do ticket OPEN do user sobre a lista de DiagramEntity carregada
do catálogo. Função pura (não toca em Delta) — testável isolada.

Espelha o pattern já adotado em ``entities/index_overlay.py``.
"""
from __future__ import annotations

from typing import Any

from ..tickets.overlay import (
    field_changes_by_target,
    index_session_diff,
    pick_entry,
)
from .models import DiagramAttribute, DiagramEntity


def apply_session_overlay(
    entities: list[DiagramEntity],
    *,
    system_id: str,
    session_ticket_id: str | None,
    session_diff: dict[str, Any],
) -> list[DiagramEntity]:
    """Aplica o diff do ticket de sessão na lista de DiagramEntity.

    NÃO altera o catálogo Delta — apenas devolve uma view enriquecida com
    flags ``pending_op``/``pending_ticket_id``. Entries ``add`` para entities
    que ainda não existem viram entities virtuais com ``entity_id`` sintético
    ``pending-ent-{schema}.{tech}`` (ou ``pre_allocated_entity_id`` se vier no
    payload — usado pra que FKs criados na mesma sessão batam após apply).
    """
    indexed = index_session_diff(session_diff)
    consumed: set[tuple[str, str]] = set()
    out: list[DiagramEntity] = []
    for ent in entities:
        entry = pick_entry(indexed, ent.schema_name, ent.technical_name)
        if not entry:
            out.append(ent)
            continue
        op = entry.get("op")
        consumed.add((ent.schema_name, ent.technical_name))
        if op == "remove":
            ent.pending_op = "remove"
            ent.pending_ticket_id = session_ticket_id
            out.append(ent)
        elif op == "change":
            _apply_change_to_entity(ent, entry)
            ent.pending_op = "change"
            ent.pending_ticket_id = session_ticket_id
            out.append(ent)
        else:
            ent.pending_op = "add"
            ent.pending_ticket_id = session_ticket_id
            out.append(ent)

    # Entries op=add pra entities ainda inexistentes viram virtuais.
    for key, entries in indexed.items():
        if key in consumed:
            continue
        # Skip entries de relationship sintéticos (schema_name="__relationship__")
        # — não são entities e quebram a validação de DiagramEntity.entity_type.
        if key[0] == "__relationship__":
            continue
        add_entry = next((e for e in entries if e.get("op") == "add"), None)
        if not add_entry:
            continue
        out.append(_build_virtual_entity(key, add_entry, system_id, session_ticket_id))

    return out


def _apply_change_to_entity(ent: DiagramEntity, entry: dict[str, Any]) -> None:
    """Mescla field_changes do entry no DiagramEntity in-place."""
    ent_updates, attr_changes, attr_adds, attr_removes = field_changes_by_target(entry)
    for fld in ("logical_name", "domain", "criticality", "entity_type"):
        if fld in ent_updates and ent_updates[fld] is not None:
            setattr(ent, fld, ent_updates[fld])

    attrs_by_name: dict[str, DiagramAttribute] = {
        a.technical_name: a for a in ent.attributes
    }
    for col_name, sub_changes in attr_changes.items():
        target = attrs_by_name.get(col_name)
        if not target:
            continue
        for sub, after in sub_changes.items():
            if sub == "logical_name":
                target.logical_name = after
            elif sub == "native_data_type":
                target.native_data_type = after
            elif sub == "is_nullable":
                target.is_nullable = bool(after) if after is not None else None
            elif sub == "is_primary_key":
                target.is_primary_key = bool(after)
            elif sub == "ordinal_position":
                try:
                    target.ordinal_position = int(after) if after is not None else None
                except (TypeError, ValueError):
                    pass
        target.pending_op = "change"

    for raw in attr_adds:
        ent.attributes.append(
            DiagramAttribute(
                attribute_id=(
                    f"pending-attr-{ent.schema_name}."
                    f"{ent.technical_name}.{raw.get('technical_name')}"
                ),
                technical_name=raw.get("technical_name") or "",
                logical_name=raw.get("logical_name"),
                native_data_type=raw.get("native_data_type"),
                is_primary_key=bool(raw.get("is_primary_key", False)),
                is_nullable=raw.get("is_nullable"),
                ordinal_position=raw.get("ordinal_position"),
                has_lgpd_flag=False,
                pending_op="add",
            )
        )

    removed_names = {r.get("technical_name") for r in attr_removes}
    for a in ent.attributes:
        if a.technical_name in removed_names and a.pending_op is None:
            a.pending_op = "remove"


def _build_virtual_entity(
    key: tuple[str, str],
    add_entry: dict[str, Any],
    system_id: str,
    session_ticket_id: str | None,
) -> DiagramEntity:
    """Constrói uma DiagramEntity virtual (op=add ainda não aplicado)."""
    payload = add_entry.get("payload") or {}
    attrs_raw = add_entry.get("attributes") or []
    # Prioriza pre_allocated_entity_id pra que FKs entre virtuais batam após apply.
    virtual_id = (
        payload.get("pre_allocated_entity_id")
        or f"pending-ent-{key[0]}.{key[1]}"
    )
    virt_attrs: list[DiagramAttribute] = []
    for idx, a in enumerate(attrs_raw):
        virt_attrs.append(
            DiagramAttribute(
                attribute_id=(
                    a.get("attribute_id")
                    or f"pending-attr-{key[0]}.{key[1]}."
                    f"{a.get('technical_name', idx)}"
                ),
                technical_name=a.get("technical_name") or "",
                logical_name=a.get("logical_name"),
                native_data_type=a.get("native_data_type"),
                is_primary_key=bool(a.get("is_primary_key", False)),
                is_nullable=a.get("is_nullable"),
                ordinal_position=a.get("ordinal_position", idx + 1),
                has_lgpd_flag=False,
                pending_op="add",
            )
        )
    return DiagramEntity(
        entity_id=virtual_id,
        system_id=system_id,
        schema_name=key[0],
        technical_name=key[1],
        logical_name=payload.get("logical_name"),
        entity_type=add_entry.get("entity_type", "TABLE") or "TABLE",
        domain=payload.get("domain"),
        criticality=payload.get("criticality"),
        attributes=virt_attrs,
        has_lgpd_flag=False,
        pending_op="add",
        pending_ticket_id=session_ticket_id,
    )
