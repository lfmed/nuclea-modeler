"""Fiação do `relationship_name` de ponta a ponta (round 5).

A coluna `relationship_name` existe desde a migration 019, mas o valor digitado
se PERDIA entre o request e o catálogo: o builder de payload e o "virtual out"
(resposta otimista antes do apply) não incluíam o campo. Este teste trava o lado
do router (payload + virtual out); o INSERT/UPDATE do apply em tickets/service.py
passaram a gravar `payload.get("relationship_name")` (mudança trivial de dict) e o
read path (`_rel_row_to_out`) já mapeava a coluna — coberto por
test_relationships_list_mapping.py.
"""
from __future__ import annotations

from nuclea_modeler.backend.relationships.models import RelationshipIn
from nuclea_modeler.backend.relationships.router import (
    _relationship_in_to_payload,
    _virtual_relationship_out,
)


def _make_in(**over) -> RelationshipIn:
    base = dict(
        system_id="sys-1",
        source_entity_id="ent-pai",
        target_entity_id="ent-filho",
        relationship_name="Pedido → Cliente",
    )
    base.update(over)
    return RelationshipIn(**base)


def test_payload_includes_relationship_name():
    payload = _relationship_in_to_payload(_make_in())
    assert payload["relationship_name"] == "Pedido → Cliente"


def test_payload_relationship_name_none_is_preserved():
    # None é válido (relacionamento sem rótulo) e não deve virar KeyError.
    payload = _relationship_in_to_payload(_make_in(relationship_name=None))
    assert payload["relationship_name"] is None


def test_virtual_out_carries_relationship_name():
    out = _virtual_relationship_out("rel-1", _make_in(), "actor@x")
    assert out.relationship_name == "Pedido → Cliente"
