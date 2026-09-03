"""Bug D (aprovação de ticket ilegível): o diff de um RELACIONAMENTO só tinha ids
(entity_id/attribute_id), então o ticket mostrava `__relationship__.rel-xxx` sem
dizer QUAIS tabelas/colunas estão sendo ligadas.

Estes testes cobrem o enriquecimento do payload com rótulos legíveis
(`_attr_names` + `_enrich_rel_payload_labels`), que a tela de aprovação usa para
renderizar "pai → filho (colunas)".
"""
from __future__ import annotations

from nuclea_modeler.backend.relationships import router as rrouter


def _patch_delta(monkeypatch, entities, attrs):
    """Mocka o delta do router: entities = {id:(schema,tech)}, attrs = {id:name}."""
    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(rrouter, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(rrouter.delta, "param", lambda k, v: (k, v))

    def fake_fetch_all(sql, query, params=None):
        if "FROM cat.sch.entities" in query:
            return [[eid, sch, tech] for eid, (sch, tech) in entities.items()]
        if "FROM cat.sch.attributes" in query:
            return [[aid, name] for aid, name in attrs.items()]
        return []

    monkeypatch.setattr(rrouter.delta, "fetch_all_params", fake_fetch_all)


def test_attr_names_preserves_order_and_skips_unknown(monkeypatch):
    _patch_delta(monkeypatch, {}, {"a2": "cliente_id", "a1": "id"})
    # pede na ordem [a1, a2, aX]; aX não existe → omitido; ordem pedida preservada
    assert rrouter._attr_names(object(), ["a1", "a2", "aX"]) == ["id", "cliente_id"]


def test_attr_names_empty():
    assert rrouter._attr_names(object(), []) == []
    assert rrouter._attr_names(object(), None) == []


def test_enrich_adds_readable_labels(monkeypatch):
    _patch_delta(
        monkeypatch,
        entities={"ent-cli": ("public", "cliente"), "ent-con": ("public", "conta")},
        attrs={"a-id": "id", "a-cli": "cliente_id"},
    )
    payload = {
        "source_entity_id": "ent-cli",
        "target_entity_id": "ent-con",
        "source_attr_ids": ["a-id"],
        "target_attr_ids": ["a-cli"],
    }
    rrouter._enrich_rel_payload_labels(object(), payload)
    assert payload["source_label"] == "public.cliente"
    assert payload["target_label"] == "public.conta"
    assert payload["source_columns"] == ["id"]
    assert payload["target_columns"] == ["cliente_id"]


def test_enrich_is_best_effort_on_error(monkeypatch):
    # Se a leitura falhar, NÃO derruba o staging — só não popula rótulos.
    def boom(*a, **k):
        raise RuntimeError("warehouse down")

    fake_settings = type("S", (), {})()
    fake_settings.fq_table = lambda t: f"cat.sch.{t}"
    monkeypatch.setattr(rrouter, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(rrouter.delta, "param", lambda k, v: (k, v))
    monkeypatch.setattr(rrouter.delta, "fetch_all_params", boom)

    payload = {"source_entity_id": "x", "target_entity_id": "y",
               "source_attr_ids": [], "target_attr_ids": []}
    rrouter._enrich_rel_payload_labels(object(), payload)  # não levanta
    # rótulos podem ficar ausentes/None, mas o payload original permanece intacto
    assert payload["source_entity_id"] == "x"
