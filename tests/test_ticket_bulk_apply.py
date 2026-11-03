"""Apply EM LOTE de tickets grandes (rodada 9 consolidada, item 10).

RCA medida no app deployado: aplicar o ticket de um DDL de 358 tabelas dava 502
aos 300 s (proxy do Databricks Apps) com só 43 tabelas aplicadas — ~7 s por tabela
no caminho unitário (várias idas ao warehouse por item). `tickets/bulk_apply.py`
faz o mesmo com poucas idas (`insert_many` por grupo). Estes testes fixam:
- o lote só liga a partir de BULK_MIN_ADDS (tickets pequenos não mudam);
- poucas chamadas ao banco para muitas tabelas (o ponto do fix);
- FKs resolvidas por nome contra o mapa carregado UMA vez, órfã vira erro;
- falha de um lote cai no caminho unitário (resiliência/auto-cura preservadas);
- existente/homônimo vai para o unitário (reconcile).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from nuclea_modeler.backend.core import delta
from nuclea_modeler.backend.tickets import bulk_apply
from nuclea_modeler.backend.tickets import service as tsvc


class FakeDB:
    def __init__(self, diff: dict, existing_entities=()):
        self.diff = diff
        self.tables: dict[str, list[dict]] = {
            "entities": [dict(e) for e in existing_entities],
            "attributes": [], "schemas": [], "entity_indexes": [], "relationships": [],
        }
        self.calls = {"insert_many": 0, "insert": 0, "fetch_all": 0, "fetch_one": 0}
        self.fail_tables: set[str] = set()
        self.ticket_updates: list[dict] = []

    @staticmethod
    def _t(table: str) -> str:
        return table.split(".")[-1]

    def insert_many(self, sql, table, rows, *, chunk_size=200):
        self.calls["insert_many"] += 1
        if self._t(table) in self.fail_tables:
            raise RuntimeError(f"lote falhou em {table} (simulado)")
        self.tables[self._t(table)].extend(dict(r) for r in rows)

    def insert(self, sql, table, row):
        self.calls["insert"] += 1
        self.tables.setdefault(self._t(table), []).append(dict(row))

    def fetch_one_params(self, sql, query, params=None):
        self.calls["fetch_one"] += 1
        if "diff_json" in query:
            return (json.dumps(self.diff), "sys-1", "APPROVED", "DDL_IMPORT")
        return None

    def fetch_all_params(self, sql, query, params=None):
        self.calls["fetch_all"] += 1
        if "a.entity_id, a.technical_name, a.attribute_id" in query:
            return [(a["entity_id"], a["technical_name"], a["attribute_id"]) for a in self.tables["attributes"]]
        if "relationship_id FROM" in query:
            return [(r["relationship_id"],) for r in self.tables["relationships"]]
        if "schema_name FROM cat.sch.schemas" in query:
            return [(r["schema_name"],) for r in self.tables["schemas"]]
        if "entity_id, schema_name, technical_name FROM cat.sch.entities" in query:
            return [(e["entity_id"], e["schema_name"], e["technical_name"]) for e in self.tables["entities"]]
        return []

    def update_by_id(self, sql, table, key, key_val, fields):
        self.ticket_updates.append(dict(fields))


@pytest.fixture
def make_db(monkeypatch):
    counter = {"n": 0}

    def new_id(prefix=""):
        counter["n"] += 1
        return f"{prefix}{counter['n']}"

    def _make(diff, existing_entities=()):
        db = FakeDB(diff, existing_entities)
        for name in ("insert_many", "insert", "fetch_one_params", "fetch_all_params", "update_by_id"):
            monkeypatch.setattr(delta, name, getattr(db, name))
        monkeypatch.setattr(delta, "new_id", new_id)
        monkeypatch.setattr(delta, "param", lambda n, v: (n, v))
        monkeypatch.setattr(delta, "run_params", lambda *a, **k: None)
        settings = type("S", (), {"fq_table": staticmethod(lambda t: f"cat.sch.{t}")})()
        monkeypatch.setattr(tsvc, "get_settings", lambda: settings)
        monkeypatch.setattr(bulk_apply, "get_settings", lambda: settings)
        return db

    return _make


def _ent(i: int, n_cols: int = 5) -> dict:
    return {
        "op": "add", "schema_name": "c3l", "technical_name": f"t{i}", "entity_type": "TABLE",
        "payload": {"native_comment": f"tabela {i}"},
        "attributes": [
            {"technical_name": "id", "native_data_type": "bigint", "is_primary_key": True},
            *[{"technical_name": f"c{k}", "native_data_type": "int"} for k in range(1, n_cols)],
        ],
        "indexes": [{"index_name": f"ix_t{i}", "columns": [{"name": "c1"}]}],
    }


def _rel(i: int, parent: str, child: str) -> dict:
    return {
        "op": "add", "schema_name": "__relationship__", "technical_name": f"rel-{i}",
        "payload": {
            "system_id": "sys-1", "origin": "EXTRACTED",
            "source_ref": {"schema_name": "c3l", "technical_name": parent, "attr_names": ["id"]},
            "target_ref": {"schema_name": "c3l", "technical_name": child, "attr_names": ["c1"]},
        },
    }


def test_ticket_grande_usa_poucas_idas_ao_banco(make_db):
    n = 120
    diff = {"entities": [_ent(i) for i in range(n)] + [_rel(i, f"t{i - 1}", f"t{i}") for i in range(1, n)]}
    db = make_db(diff)
    r = tsvc.apply_ticket(MagicMock(), "tk-1", applied_by="u")

    assert r.status == "APPLIED", r.errors[:3]
    assert r.errors == []
    assert len(db.tables["entities"]) == n
    assert len(db.tables["attributes"]) == n * 5
    assert len(db.tables["entity_indexes"]) == n
    assert all(ix["origin"] == "EXTRACTED" for ix in db.tables["entity_indexes"])
    assert len(db.tables["relationships"]) == n - 1
    assert {s["schema_name"] for s in db.tables["schemas"]} == {"c3l"}
    # FKs resolvidas por nome → ids reais de entity/atributo
    ent_id = {e["technical_name"]: e["entity_id"] for e in db.tables["entities"]}
    rel = next(x for x in db.tables["relationships"] if x["relationship_id"] == "rel-1")
    assert rel["source_entity_id"] == ent_id["t0"] and rel["target_entity_id"] == ent_id["t1"]
    assert len(rel["source_attr_ids"]) == 1 and len(rel["target_attr_ids"]) == 1
    # contadores iguais ao unitário: entities + FKs em applied_entities
    assert r.applied_entities == n + (n - 1)
    assert r.applied_attributes == n * 5
    # O PONTO DO FIX: nenhum INSERT unitário e poucas idas no total (antes ~7/tabela).
    assert db.calls["insert"] == 0
    total = db.calls["insert_many"] + db.calls["fetch_all"] + db.calls["fetch_one"]
    assert total < 25, db.calls


def test_ticket_pequeno_nao_usa_o_lote(make_db, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("lote não deveria ser usado abaixo do limiar")

    monkeypatch.setattr(bulk_apply, "apply_entity_adds_bulk", boom)
    ents = [_ent(i) for i in range(tsvc.BULK_MIN_ADDS - 1)]
    for e in ents:  # sem índices: o caminho unitário de índice lê settings reais
        e.pop("indexes")
    make_db({"entities": ents})
    r = tsvc.apply_ticket(MagicMock(), "tk-1", applied_by="u")
    assert r.status == "APPLIED"


def test_falha_do_lote_cai_no_unitario(make_db, monkeypatch):
    db = make_db({"entities": [_ent(i) for i in range(30)]})
    db.fail_tables = {"attributes"}
    unit_calls: list[str] = []
    monkeypatch.setattr(tsvc, "_apply_op_add", lambda state, ch: unit_calls.append(ch["technical_name"]))
    tsvc.apply_ticket(MagicMock(), "tk-1", applied_by="u")
    # todas as 30 entidades do grupo que falhou foram reaplicadas pelo unitário
    assert sorted(unit_calls) == sorted(f"t{i}" for i in range(30))
    # entities e índices do grupo entraram antes da falha (o unitário reconcilia colunas)
    assert len(db.tables["entities"]) == 30 and len(db.tables["entity_indexes"]) == 30


def test_existente_e_homonimo_vao_para_o_unitario(make_db, monkeypatch):
    existing = [{"entity_id": "ent-old", "schema_name": "outro", "technical_name": "T3"}]
    diff = {"entities": [_ent(i) for i in range(25)] + [_ent(7)]}  # t7 duplicada no ticket
    db = make_db(diff, existing_entities=existing)
    unit_calls: list[str] = []
    monkeypatch.setattr(tsvc, "_apply_op_add", lambda state, ch: unit_calls.append(ch["technical_name"]))
    tsvc.apply_ticket(MagicMock(), "tk-1", applied_by="u")
    assert sorted(unit_calls) == ["t3", "t7"]  # t3 = homônimo (case-insensitive); t7 = duplicata
    names = [e["technical_name"] for e in db.tables["entities"] if e["entity_id"] != "ent-old"]
    assert "t3" not in names and names.count("t7") == 1


def test_fk_orfa_vira_erro_e_nao_grava(make_db):
    diff = {"entities": [_ent(i) for i in range(25)] + [_rel(1, "nao_existe", "t1")]}
    db = make_db(diff)
    r = tsvc.apply_ticket(MagicMock(), "tk-1", applied_by="u")
    assert db.tables["relationships"] == []
    assert any("FK não resolvida" in e and "nao_existe" in e for e in r.errors)
