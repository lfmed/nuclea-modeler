"""Round-trip CSV → ticket editorial (v1.0035).

Valida que parse_and_stage_csv compara o CSV com o catálogo e monta as entries
do ticket no formato editorial (attribute:NOME.update / attribute_add / campos de
entidade), pulando o que não mudou e ignorando tabelas inexistentes.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.entities import roundtrip


@pytest.fixture
def patched(monkeypatch):
    """Mocka catálogo + staging; captura as entries montadas."""
    captured: dict = {"entries": []}

    catalog = {
        "public.cliente": {
            "entity_id": "ent-cli", "schema_name": "public", "technical_name": "cliente",
            "logical_name": "Cliente", "description_md": None, "domain": None,
            "criticality": None, "entity_type": "TABLE",
            "attrs": {
                "id": {"logical_name": None, "native_data_type": "INTEGER",
                       "is_primary_key": True, "is_nullable": False,
                       "description_md": None, "ordinal_position": 1},
                "nome": {"logical_name": None, "native_data_type": "VARCHAR(100)",
                         "is_primary_key": False, "is_nullable": True,
                         "description_md": None, "ordinal_position": 2},
            },
        },
    }
    monkeypatch.setattr(roundtrip, "_load_catalog", lambda sql, sid: catalog)
    monkeypatch.setattr(
        roundtrip, "get_or_create_session_ticket",
        lambda sql, actor, sid, title_hint=None: ("ticket-1", {"entities": []}),
    )

    def fake_stage(sql, ticket_id, diff, entry):
        captured["entries"].append(entry)
        return diff

    monkeypatch.setattr(roundtrip, "stage_entity_change", fake_stage)
    return captured


def _fields(entry) -> set[str]:
    return {fc["field"] for fc in entry["field_changes"]}


def test_changes_and_add_and_unknown(patched):
    csv_text = (
        "schema,table,table_logical,table_description,table_domain,table_criticality,"
        "column,column_logical,data_type,is_pk,is_nullable,column_description\n"
        # id: sem mudança → não deve gerar field_change
        "public,cliente,,Cadastro de clientes,,,id,,INTEGER,true,false,\n"
        # nome: muda logical + descrição
        "public,cliente,,,,,nome,Nome do cliente,VARCHAR(100),false,true,Nome completo\n"
        # email: coluna nova → attribute_add
        "public,cliente,,,,,email,E-mail,VARCHAR(255),false,true,Contato\n"
        # tabela inexistente → ignorada
        "public,fantasma,,,,,x,,INTEGER,false,true,\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "tester@nuclea", "sys-1", csv_text)

    assert res["ticket_id"] == "ticket-1"
    assert "public.fantasma" in res["unknown_tables"]
    assert len(patched["entries"]) == 1
    entry = patched["entries"][0]
    assert entry["op"] == "change"
    assert entry["technical_name"] == "cliente"
    # descrição da tabela virou field_change + payload
    assert "description_md" in _fields(entry)
    assert entry["payload"]["description_md"] == "Cadastro de clientes"
    assert entry["payload"]["target_entity_id"] == "ent-cli"
    # nome mudou → attribute:nome.update ; email novo → attribute_add:email
    assert "attribute:nome.update" in _fields(entry)
    assert "attribute_add:email" in _fields(entry)
    # id NÃO mudou → não deve haver update de id
    assert "attribute:id.update" not in _fields(entry)
    assert res["columns_changed"] == 2  # nome (update) + email (add)


def test_no_changes_returns_no_ticket(patched):
    csv_text = (
        "schema,table,column,data_type,is_pk,is_nullable\n"
        "public,cliente,id,INTEGER,true,false\n"
        "public,cliente,nome,VARCHAR(100),false,true\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "tester@nuclea", "sys-1", csv_text)
    assert res["ticket_id"] is None
    assert res["entities_changed"] == 0
    assert patched["entries"] == []


def test_missing_required_columns_raises(patched):
    with pytest.raises(ValueError):
        roundtrip.parse_and_stage_csv(object(), "t@n", "sys-1", "foo,bar\n1,2\n")


# ─── Fallback de SCHEMA (bug do reteste: CSV `dbo` × modelo `social`) ──────────
# Reproduzido com os arquivos reais do cliente: o DDL punha as tabelas em `social`
# (SET search_path) e o CSV trazia `dbo` → match estrito derrubava TUDO em
# unknown_tables ("não carregou nada"). O fix casa por nome de tabela ÚNICO.

def test_schema_mismatch_matches_by_unique_table_name(patched):
    # catálogo tem public.cliente; CSV traz o MESMO objeto sob schema 'dbo'.
    csv_text = (
        "schema,table,column,column_logical,data_type,is_pk,is_nullable,column_description\n"
        "dbo,cliente,nome,Nome do cliente,VARCHAR(100),false,true,Nome completo\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "t@n", "sys-1", csv_text)
    assert res["unknown_tables"] == []  # NÃO caiu em desconhecido
    assert len(patched["entries"]) == 1
    entry = patched["entries"][0]
    # o diff usa o schema/nome REAIS do catálogo, não o 'dbo' do CSV
    assert entry["schema_name"] == "public"
    assert entry["technical_name"] == "cliente"
    assert "attribute:nome.update" in _fields(entry)


def test_case_insensitive_schema_and_table_match(patched):
    # DB2 grava SOCIAL.PESSOA (upper); aqui: catálogo public.cliente, CSV em CAIXA ALTA.
    csv_text = (
        "schema,table,column,column_logical,data_type,is_pk,is_nullable,column_description\n"
        "PUBLIC,CLIENTE,nome,Nome,VARCHAR(100),false,true,Desc\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "t@n", "sys-1", csv_text)
    assert res["unknown_tables"] == []
    assert len(patched["entries"]) == 1
    assert patched["entries"][0]["technical_name"] == "cliente"


def test_all_unknown_message_warns_about_schema(patched):
    # nome de tabela que NÃO existe no modelo → continua desconhecido e a mensagem
    # avisa (antes dizia enganosamente "nenhuma mudança detectada").
    csv_text = (
        "schema,table,column,data_type,is_pk,is_nullable\n"
        "dbo,inexistente,x,INTEGER,false,true\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "t@n", "sys-1", csv_text)
    assert res["ticket_id"] is None
    assert res["unknown_tables"] == ["dbo.inexistente"]
    assert "não reconhecida" in res["message"]
    assert "public" in res["message"]  # lista o schema real do modelo


def test_ambiguous_table_name_stays_unknown(monkeypatch):
    # Duas tabelas com o MESMO nome em schemas diferentes → não dá pra adivinhar
    # qual o CSV (schema divergente) quer: fica desconhecido (seguro).
    catalog = {
        "social.pessoa": {
            "entity_id": "ent-a", "schema_name": "social", "technical_name": "pessoa",
            "logical_name": None, "description_md": None, "domain": None,
            "criticality": None, "entity_type": "TABLE",
            "attrs": {"id": {"logical_name": None, "native_data_type": "INT",
                             "is_primary_key": True, "is_nullable": False,
                             "description_md": None, "ordinal_position": 1}},
        },
        "outro.pessoa": {
            "entity_id": "ent-b", "schema_name": "outro", "technical_name": "pessoa",
            "logical_name": None, "description_md": None, "domain": None,
            "criticality": None, "entity_type": "TABLE",
            "attrs": {"id": {"logical_name": None, "native_data_type": "INT",
                             "is_primary_key": True, "is_nullable": False,
                             "description_md": None, "ordinal_position": 1}},
        },
    }
    monkeypatch.setattr(roundtrip, "_load_catalog", lambda sql, sid: catalog)
    csv_text = (
        "schema,table,column,column_logical,data_type,is_pk,is_nullable,column_description\n"
        "dbo,pessoa,id,ID,INT,true,false,muda desc\n"
    )
    res = roundtrip.parse_and_stage_csv(object(), "t@n", "sys-1", csv_text)
    assert res["unknown_tables"] == ["dbo.pessoa"]  # ambíguo → não casou


def test_slugify():
    assert roundtrip._slugify("Banco Digital — Lakebase Demo") == "banco-digital-lakebase-demo"
    assert roundtrip._slugify("  Núclea/Modeler!!  ") == "n-clea-modeler"
    assert roundtrip._slugify("") == "sistema"
    assert roundtrip._slugify(None) == "sistema"  # type: ignore[arg-type]
