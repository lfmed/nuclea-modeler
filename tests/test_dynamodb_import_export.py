"""DynamoDB via JSON — import e export (rodada 9 consolidada, item 17).

Pedido: "suporte ao dialeto DynamoDB e outros não relacionais, representação por
arquivo JSON". Sem exemplo do cliente, cobrimos os 3 formatos JSON em que um
modelo DynamoDB existe (describe-table, NoSQL Workbench, CloudFormation) e o
export para o JSON de `create-table`. Estes testes documentam o mapeamento:
tabela → entidade no schema `dynamodb`; partition + sort key → PK composta (HASH
primeiro); GSI/LSI → índices; atributos não-chave do Workbench (declarados ou
inferidos dos itens).
"""
from __future__ import annotations

import json

import pytest

from nuclea_modeler.backend.ddl.dynamodb_gen import gen_dynamodb, key_type_code
from nuclea_modeler.backend.ddl.models import DDLExportRequest
from nuclea_modeler.backend.extractions import service as svc
from nuclea_modeler.backend.extractions.dynamodb import DynamoDBFormatError, parse_dynamodb_json

DESCRIBE = {
    "Table": {
        "TableName": "Pedidos",
        "AttributeDefinitions": [
            {"AttributeName": "cliente_id", "AttributeType": "S"},
            {"AttributeName": "pedido_ts", "AttributeType": "N"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        "KeySchema": [
            {"AttributeName": "pedido_ts", "KeyType": "RANGE"},  # ordem invertida de propósito
            {"AttributeName": "cliente_id", "KeyType": "HASH"},
        ],
        "GlobalSecondaryIndexes": [{
            "IndexName": "gsi_status",
            "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"},
                          {"AttributeName": "pedido_ts", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "KEYS_ONLY"},
        }],
        "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
    }
}

WORKBENCH = {
    "ModelName": "Loja",
    "DataModel": [{
        "TableName": "Clientes",
        "KeyAttributes": {"PartitionKey": {"AttributeName": "id", "AttributeType": "S"}},
        "NonKeyAttributes": [{"AttributeName": "nome", "AttributeType": "S"},
                             {"AttributeName": "ativo", "AttributeType": "BOOL"}],
        "TableData": [
            {"id": {"S": "1"}, "nome": {"S": "Ana"}, "enderecos": {"L": []}, "score": {"N": "9"}},
            {"id": "2", "nome": "Bia", "tags": ["a"]},
        ],
    }],
}

CFN = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Resources": {
        "TabelaEventos": {
            "Type": "AWS::DynamoDB::Table",
            "Properties": {
                "TableName": "Eventos",
                "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"},
                                         {"AttributeName": "sk", "AttributeType": "S"},
                                         {"AttributeName": "data", "AttributeType": "S"}],
                "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"},
                              {"AttributeName": "sk", "KeyType": "RANGE"}],
                "LocalSecondaryIndexes": [{
                    "IndexName": "lsi_data",
                    "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"},
                                  {"AttributeName": "data", "KeyType": "RANGE"}],
                    "Projection": {"ProjectionType": "ALL"},
                }],
                "TimeToLiveSpecification": {"AttributeName": "expira_em", "Enabled": True},
            },
        },
        "Bucket": {"Type": "AWS::S3::Bucket"},
    },
}


def _ent(snap, name):
    return next(e for e in snap.entities if e.technical_name == name)


# ─── import ──────────────────────────────────────────────────────────────────

def test_describe_table_pk_hash_primeiro_tipos_e_gsi():
    snap, warns, fmt = parse_dynamodb_json(json.dumps(DESCRIBE), "sys-1")
    assert fmt == "describe-table" and warns == []
    e = _ent(snap, "Pedidos")
    assert e.schema_name == "dynamodb"
    pk = [(a.technical_name, a.ordinal_position) for a in e.attributes if a.is_primary_key]
    assert pk == [("cliente_id", 1), ("pedido_ts", 2)]  # HASH antes de RANGE
    types = {a.technical_name: a.native_data_type for a in e.attributes}
    assert types == {"cliente_id": "STRING", "pedido_ts": "NUMBER", "status": "STRING"}
    (ix,) = e.indexes
    assert (ix.index_name, ix.index_type, [c.name for c in ix.columns]) == ("gsi_status", "GSI", ["status", "pedido_ts"])
    assert "KEYS_ONLY" in (ix.native_comment or "")
    assert "PAY_PER_REQUEST" in (e.native_comment or "")


def test_lista_e_tables_de_describe():
    two = [DESCRIBE, {"Table": {**DESCRIBE["Table"], "TableName": "Outra"}}]
    snap, _, _ = parse_dynamodb_json(json.dumps(two), "s")
    assert {e.technical_name for e in snap.entities} == {"Pedidos", "Outra"}
    snap2, _, _ = parse_dynamodb_json(json.dumps({"Tables": two}), "s")
    assert len(snap2.entities) == 2


def test_nosql_workbench_nao_chave_e_inferidos():
    snap, warns, fmt = parse_dynamodb_json(json.dumps(WORKBENCH), "sys-1")
    assert fmt == "nosql-workbench"
    e = _ent(snap, "Clientes")
    types = {a.technical_name: a.native_data_type for a in e.attributes}
    assert types["id"] == "STRING" and types["ativo"] == "BOOLEAN"
    # inferidos dos itens: DynamoDB JSON tipado ({"L": []}, {"N": "9"}) e JSON simples
    assert types["enderecos"] == "LIST" and types["score"] == "NUMBER" and types["tags"] == "LIST"
    assert [a.technical_name for a in e.attributes if a.is_primary_key] == ["id"]
    assert "inferido" in (e.native_comment or "")


def test_cloudformation_lsi_e_ttl_ignora_outros_recursos():
    snap, _, fmt = parse_dynamodb_json(json.dumps(CFN), "sys-1")
    assert fmt == "cloudformation" and [e.technical_name for e in snap.entities] == ["Eventos"]
    e = snap.entities[0]
    assert [a.technical_name for a in e.attributes if a.is_primary_key] == ["pk", "sk"]
    assert e.indexes[0].index_type == "LSI"
    assert any(a.technical_name == "expira_em" for a in e.attributes)


def test_erros_acionaveis():
    with pytest.raises(DynamoDBFormatError, match="JSON inválido"):
        parse_dynamodb_json("{ nope", "s")
    with pytest.raises(DynamoDBFormatError, match="formato não reconhecido"):
        parse_dynamodb_json(json.dumps({"foo": 1}), "s")
    with pytest.raises(DynamoDBFormatError, match="AWS::DynamoDB::Table"):
        parse_dynamodb_json(json.dumps({"Resources": {"B": {"Type": "AWS::S3::Bucket"}}}), "s")


def test_tabela_sem_chave_gera_aviso():
    snap, warns, _ = parse_dynamodb_json(json.dumps({"TableName": "X", "AttributeDefinitions": []}), "s")
    assert snap.entities[0].technical_name == "X"
    assert any("sem KeySchema" in w for w in warns)


def test_run_dynamodb_import_vazio_nao_faz_diff(monkeypatch):
    """Guard: arquivo sem tabelas NÃO pode chegar no diff (marcaria tudo como removido)."""
    called = []
    monkeypatch.setattr(svc, "compute_diff_against_catalog", lambda *a: called.append(1))
    r = svc.run_dynamodb_import(object(), system_id="s", json_text=json.dumps({"DataModel": []}),
                                actor="t", open_ticket_on_diff=True)
    assert r.status == "FAILED" and not called


# ─── export (create-table JSON) ──────────────────────────────────────────────

def _attrs_from(entity):
    return [
        {"technical_name": a.technical_name, "native_data_type": a.native_data_type,
         "is_primary_key": a.is_primary_key, "ordinal_position": a.ordinal_position}
        for a in entity.attributes
    ]


def test_round_trip_import_export():
    snap, _, _ = parse_dynamodb_json(json.dumps(DESCRIBE), "s")
    e = _ent(snap, "Pedidos")
    ent = {"technical_name": e.technical_name,
           "_indexes": [{"index_name": i.index_name, "index_type": i.index_type,
                         "columns": [{"name": c.name} for c in i.columns]} for i in e.indexes]}
    out = json.loads(gen_dynamodb(ent, _attrs_from(e), DDLExportRequest(system_id="s", dialect="DYNAMODB")))
    assert out["TableName"] == "Pedidos"
    assert out["KeySchema"] == [{"AttributeName": "cliente_id", "KeyType": "HASH"},
                                {"AttributeName": "pedido_ts", "KeyType": "RANGE"}]
    assert {d["AttributeName"]: d["AttributeType"] for d in out["AttributeDefinitions"]} == {
        "cliente_id": "S", "pedido_ts": "N", "status": "S"}
    assert out["GlobalSecondaryIndexes"][0]["IndexName"] == "gsi_status"
    assert out["BillingMode"] == "PAY_PER_REQUEST"


def test_export_de_modelo_relacional_mapeia_tipos_e_ignora_btree():
    attrs = [
        {"technical_name": "id", "native_data_type": "BIGINT", "is_primary_key": True},
        {"technical_name": "nome", "native_data_type": "VARCHAR(100)", "is_primary_key": False},
    ]
    ent = {"technical_name": "cliente", "_indexes": [{"index_name": "ix", "index_type": "BTREE",
                                                       "columns": [{"name": "nome"}]}]}
    out = json.loads(gen_dynamodb(ent, attrs, DDLExportRequest(system_id="s", dialect="DYNAMODB")))
    assert out["AttributeDefinitions"] == [{"AttributeName": "id", "AttributeType": "N"}]
    assert "GlobalSecondaryIndexes" not in out


def test_export_valida_quantidade_de_pk():
    req = DDLExportRequest(system_id="s", dialect="DYNAMODB")
    with pytest.raises(ValueError, match="exige chave"):
        gen_dynamodb({"technical_name": "t"}, [{"technical_name": "a", "is_primary_key": False}], req)
    three = [{"technical_name": n, "is_primary_key": True} for n in "abc"]
    with pytest.raises(ValueError, match="no máximo 2"):
        gen_dynamodb({"technical_name": "t"}, three, req)


@pytest.mark.parametrize("native,code", [
    ("STRING", "S"), ("NUMBER", "N"), ("BINARY", "B"), ("varchar(10)", "S"), ("NUMERIC(18,2)", "N"),
    ("bytea", "B"), ("TIMESTAMP", "S"), (None, "S"),
])
def test_key_type_code(native, code):
    assert key_type_code(native) == code
