"""Read-side overlay helpers — aplica o diff de uma sessão OPEN do user
em cima do catálogo committed para que as leituras já reflitam as edições
pendentes (criar/editar/remover entity, attribute).

A escrita NÃO acontece aqui; isso é puramente uma camada de view.
O staging real fica em `session.py`/`service.py`.
"""
from __future__ import annotations

from typing import Any


def _entity_match_key(schema_name: str | None, technical_name: str | None) -> tuple[str, str]:
    return (schema_name or "", technical_name or "")


def index_session_diff(
    diff: dict[str, Any] | None,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index entries do diff por (schema_name, technical_name).

    Retorna mapping (schema, tech) -> lista de entries (preserva ordem).
    Lista porque o diff pode ter múltiplas ops para a mesma entity (raro,
    mas possível em add+change).
    """
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if not diff:
        return out
    for e in diff.get("entities", []) or []:
        if not isinstance(e, dict):
            continue
        key = _entity_match_key(e.get("schema_name"), e.get("technical_name"))
        out.setdefault(key, []).append(e)
    return out


def pick_entry(
    indexed: dict[tuple[str, str], list[dict[str, Any]]],
    schema_name: str | None,
    technical_name: str | None,
) -> dict[str, Any] | None:
    """Retorna o primeiro entry do diff que casa com a entity. Prioriza
    `remove` > `change` > `add` na decisão de "qual flag mostrar" porque
    remove é a operação mais visível para o usuário (item já marcado pra
    sair). Se há add+change, mostra change (o add ainda não foi commitado).
    """
    key = _entity_match_key(schema_name, technical_name)
    entries = indexed.get(key)
    if not entries:
        return None
    priority = {"remove": 0, "change": 1, "add": 2}
    return sorted(entries, key=lambda e: priority.get(e.get("op", ""), 99))[0]


def field_changes_by_target(
    entry: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Quebra `field_changes` de um entry op=change em:
    - entity_level_updates: {field: after} para campos diretos da entity
    - attribute_changes_by_name: {attribute_technical_name: {field: after}}
    - attribute_adds: [{technical_name, ...meta}]   (field == "attribute_add:NAME")
    - attribute_removes: [{technical_name, ...}]    (field == "attribute_remove:NAME")
    """
    entity_updates: dict[str, Any] = {}
    attr_changes: dict[str, dict[str, Any]] = {}
    attr_adds: list[dict[str, Any]] = []
    attr_removes: list[dict[str, Any]] = []
    if not entry:
        return entity_updates, attr_changes, attr_adds, attr_removes
    for fc in entry.get("field_changes") or []:
        if not isinstance(fc, dict):
            continue
        fld = fc.get("field") or ""
        after = fc.get("after")
        if fld.startswith("attribute_add:"):
            name = fld.split(":", 1)[1]
            # Convenção atual do app: payload completo do attribute está em `after`
            # (ver entities/router.py:create_attribute). Aceita também `payload`
            # como fallback pra compatibilidade com tickets antigos.
            payload_dict: dict[str, Any] = {}
            if isinstance(after, dict):
                payload_dict = after
            elif isinstance(fc.get("payload"), dict):
                payload_dict = fc.get("payload") or {}
            merged = {"technical_name": name, **payload_dict}
            merged["technical_name"] = merged.get("technical_name") or name
            attr_adds.append(merged)
        elif fld.startswith("attribute_remove:"):
            name = fld.split(":", 1)[1]
            attr_removes.append({"technical_name": name})
        elif fld.startswith("attribute:"):
            # "attribute:COL.field"
            rest = fld.split(":", 1)[1]
            if "." in rest:
                col, sub = rest.split(".", 1)
                attr_changes.setdefault(col, {})[sub] = after
        else:
            entity_updates[fld] = after
    return entity_updates, attr_changes, attr_adds, attr_removes


def diff_counts(diff: dict[str, Any] | None) -> tuple[int, int, int]:
    """(additions, changes, removals) — conta entries pelo op."""
    if not diff:
        return (0, 0, 0)
    ents = diff.get("entities", []) or []
    a = sum(1 for e in ents if isinstance(e, dict) and e.get("op") == "add")
    c = sum(1 for e in ents if isinstance(e, dict) and e.get("op") == "change")
    r = sum(1 for e in ents if isinstance(e, dict) and e.get("op") == "remove")
    return (a, c, r)
