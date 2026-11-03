"""Import de modelo DynamoDB a partir de JSON (rodada 9 consolidada, item 17).

Pedido do cliente: "Suporte ao dialeto DynamoDB e outros não relacionais —
representação realizada por meio de arquivo JSON". O cliente não mandou exemplo,
então aceitamos os 3 formatos JSON em que um modelo DynamoDB costuma existir:

1. **describe-table** — saída de `aws dynamodb describe-table` (`{"Table": {...}}`),
   uma lista delas, `{"Tables": [...]}`, ou o `TableDescription` puro (também é o
   formato de entrada do `aws dynamodb create-table --cli-input-json`).
2. **NoSQL Workbench** — modelo exportado do NoSQL Workbench for DynamoDB
   (`{"ModelName":…, "DataModel":[{"TableName", "KeyAttributes", "NonKeyAttributes",
   "GlobalSecondaryIndexes", "TableData"}]}`). É o ÚNICO que traz os atributos
   não-chave declarados.
3. **CloudFormation / SAM** — template com recursos `AWS::DynamoDB::Table` /
   `AWS::DynamoDB::GlobalTable` (`Properties.KeySchema`, `AttributeDefinitions`…).

Por que DynamoDB "não cabe" direto no modelo relacional e como mapeamos:
- Não há schema: todas as tabelas entram no schema lógico `dynamodb`.
- Só os atributos-CHAVE (da tabela e dos índices) são declarados no DynamoDB; os
  demais são livres por item. Usamos `AttributeDefinitions` + `NonKeyAttributes`
  (Workbench) + atributos INFERIDOS dos itens de exemplo (`TableData`, quando há).
- PK = partition key (HASH) + sort key (RANGE), nessa ordem (PK composta).
- GSI / LSI viram índices com `index_type` "GSI"/"LSI" (colunas = chaves do índice).
- Não existem relacionamentos (FK) no DynamoDB — o usuário modela no DER se quiser.

Módulo PURO (sem banco): `parse_dynamodb_json` devolve o snapshot + avisos; o
service faz diff/ticket exatamente como no import do .DM1.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedIndex,
    ExtractedIndexColumn,
    ExtractionSnapshot,
)

DYNAMODB_SCHEMA = "dynamodb"

# Códigos de tipo do DynamoDB → tipo exibido no modelo (o mesmo vocabulário do
# TypePicker "DynamoDB" da UI e do export). Chaves só podem ser S/N/B.
TYPE_NAMES: dict[str, str] = {
    "S": "STRING",
    "N": "NUMBER",
    "B": "BINARY",
    "BOOL": "BOOLEAN",
    "NULL": "NULL",
    "M": "MAP",
    "L": "LIST",
    "SS": "STRING_SET",
    "NS": "NUMBER_SET",
    "BS": "BINARY_SET",
}
# Inverso (export): tipo do modelo → código do DynamoDB (só S/N/B valem em chave).
TYPE_CODES: dict[str, str] = {v: k for k, v in TYPE_NAMES.items()}


class DynamoDBFormatError(ValueError):
    """JSON válido mas que não é nenhum dos formatos de modelo DynamoDB suportados."""


def _type_name(code: Any) -> str:
    c = str(code or "").strip().upper()
    return TYPE_NAMES.get(c, c or "STRING")


def _infer_type(value: Any) -> str | None:
    """Tipo de um valor de item de exemplo. Aceita DynamoDB JSON tipado
    (`{"S": "x"}`) ou JSON simples (o Workbench exporta os dois jeitos)."""
    if isinstance(value, dict) and len(value) == 1:
        (code,) = value.keys()
        if str(code).upper() in TYPE_NAMES:
            return TYPE_NAMES[str(code).upper()]
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, (int, float)):
        return "NUMBER"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, dict):
        return "MAP"
    if isinstance(value, list):
        return "LIST"
    if value is None:
        return "NULL"
    return None


class _TableBuilder:
    """Acumula atributos/índices de uma tabela preservando a ordem (chaves primeiro)."""

    def __init__(self, name: str):
        self.name = name
        self.attrs: dict[str, ExtractedAttribute] = {}
        self.pk: list[tuple[str, str]] = []  # (nome, "HASH"|"RANGE")
        self.indexes: list[ExtractedIndex] = []
        self.comment_bits: list[str] = []

    def attr(self, name: str, type_name: str | None, *, comment: str | None = None) -> None:
        if not name:
            return
        a = self.attrs.get(name)
        if a is None:
            self.attrs[name] = ExtractedAttribute(
                technical_name=name,
                native_data_type=type_name or "STRING",
                is_nullable=True,
                native_comment=comment,
            )
        else:
            if type_name and not a.native_data_type:
                a.native_data_type = type_name
            if comment and not a.native_comment:
                a.native_comment = comment

    def key(self, name: str, key_type: str, type_name: str | None) -> None:
        kt = "RANGE" if str(key_type).upper() == "RANGE" else "HASH"
        label = "Partition key (HASH)" if kt == "HASH" else "Sort key (RANGE)"
        self.attr(name, type_name, comment=label)
        if name not in [n for n, _ in self.pk]:
            self.pk.append((name, kt))

    def index(self, name: str, kind: str, keys: list[tuple[str, str]], projection: str | None) -> None:
        self.indexes.append(
            ExtractedIndex(
                index_name=name,
                index_type=kind,
                is_unique=False,  # GSI/LSI não impõem unicidade
                columns=[ExtractedIndexColumn(name=n) for n, _ in keys],
                native_comment=f"Projeção: {projection}" if projection else None,
            )
        )

    def build(self) -> ExtractedEntity:
        # HASH antes de RANGE (ordem da PK composta) e chaves antes dos demais.
        pk_sorted = sorted(self.pk, key=lambda p: 0 if p[1] == "HASH" else 1)
        pk_names = [n for n, _ in pk_sorted]
        ordered = [self.attrs[n] for n in pk_names if n in self.attrs] + [
            a for n, a in self.attrs.items() if n not in pk_names
        ]
        for i, a in enumerate(ordered, start=1):
            a.ordinal_position = i
            if a.technical_name in pk_names:
                a.is_primary_key = True
                a.is_nullable = False
        return ExtractedEntity(
            schema_name=DYNAMODB_SCHEMA,
            technical_name=self.name,
            entity_type="TABLE",
            native_comment=" · ".join(self.comment_bits) or None,
            attributes=ordered,
            indexes=self.indexes,
        )


# ─── Formatos ────────────────────────────────────────────────────────────────


def _key_schema(ks: list[dict] | None) -> list[tuple[str, str]]:
    return [(k.get("AttributeName", ""), k.get("KeyType", "HASH")) for k in (ks or []) if k.get("AttributeName")]


def _from_table_description(t: dict, warnings: list[str]) -> ExtractedEntity | None:
    """describe-table (`TableDescription`) e CloudFormation `Properties` têm o
    MESMO shape (KeySchema / AttributeDefinitions / GlobalSecondaryIndexes / LSI)."""
    name = t.get("TableName")
    if not name:
        warnings.append("Tabela sem TableName ignorada.")
        return None
    b = _TableBuilder(str(name))
    types = {d.get("AttributeName"): _type_name(d.get("AttributeType")) for d in t.get("AttributeDefinitions") or []}
    ks = _key_schema(t.get("KeySchema"))
    if not ks:
        warnings.append(f"Tabela {name}: sem KeySchema — importada sem PK.")
    for n, kt in ks:
        b.key(n, kt, types.get(n))
    for kind, field in (("GSI", "GlobalSecondaryIndexes"), ("LSI", "LocalSecondaryIndexes")):
        for ix in t.get(field) or []:
            iks = _key_schema(ix.get("KeySchema"))
            for n, _ in iks:
                b.attr(n, types.get(n), comment=f"Chave do índice {ix.get('IndexName')}")
            b.index(str(ix.get("IndexName") or f"{kind.lower()}_{len(b.indexes) + 1}"), kind, iks,
                    (ix.get("Projection") or {}).get("ProjectionType"))
    # Atributos definidos que não são chave de nada (raro, mas o CFN aceita).
    for n, ty in types.items():
        b.attr(n, ty)
    billing = (t.get("BillingModeSummary") or {}).get("BillingMode") or t.get("BillingMode")
    if billing:
        b.comment_bits.append(f"Billing: {billing}")
    ttl = (t.get("TimeToLiveSpecification") or {}).get("AttributeName")
    if ttl:
        b.comment_bits.append(f"TTL: {ttl}")
        b.attr(ttl, "NUMBER", comment="Atributo de TTL (epoch)")
    if t.get("StreamSpecification", {}).get("StreamEnabled") or t.get("StreamSpecification", {}).get("StreamViewType"):
        b.comment_bits.append("Streams habilitado")
    return b.build()


def _from_workbench_table(t: dict, warnings: list[str]) -> ExtractedEntity | None:
    name = t.get("TableName")
    if not name:
        warnings.append("Tabela do NoSQL Workbench sem TableName ignorada.")
        return None
    b = _TableBuilder(str(name))
    ka = t.get("KeyAttributes") or {}
    for role, kt in (("PartitionKey", "HASH"), ("SortKey", "RANGE")):
        k = ka.get(role) or {}
        if k.get("AttributeName"):
            b.key(k["AttributeName"], kt, _type_name(k.get("AttributeType")))
    if not ka.get("PartitionKey"):
        warnings.append(f"Tabela {name}: sem PartitionKey — importada sem PK.")
    for a in t.get("NonKeyAttributes") or []:
        b.attr(a.get("AttributeName", ""), _type_name(a.get("AttributeType")))
    for ix in t.get("GlobalSecondaryIndexes") or []:
        ika = ix.get("KeyAttributes") or {}
        keys: list[tuple[str, str]] = []
        for role, kt in (("PartitionKey", "HASH"), ("SortKey", "RANGE")):
            k = ika.get(role) or {}
            if k.get("AttributeName"):
                keys.append((k["AttributeName"], kt))
                b.attr(k["AttributeName"], _type_name(k.get("AttributeType")),
                       comment=f"Chave do índice {ix.get('IndexName')}")
        b.index(str(ix.get("IndexName") or f"gsi_{len(b.indexes) + 1}"), "GSI", keys,
                (ix.get("Projection") or {}).get("ProjectionType"))
    # Itens de exemplo: revelam atributos não declarados (comum em single-table design).
    inferred = 0
    for item in t.get("TableData") or []:
        if not isinstance(item, dict):
            continue
        for k, v in item.items():
            if k not in b.attrs:
                inferred += 1
            b.attr(k, _infer_type(v))
    if inferred:
        b.comment_bits.append(f"{inferred} atributo(s) inferido(s) dos itens de exemplo")
    return b.build()


def _collect_tables(doc: Any) -> tuple[str, list[dict]]:
    """Detecta o formato e devolve (formato, lista de dicts de tabela)."""
    if isinstance(doc, list):
        out: list[dict] = []
        for el in doc:
            fmt, tabs = _collect_tables(el)
            out.extend(tabs)
        return "describe-table", out
    if not isinstance(doc, dict):
        raise DynamoDBFormatError("o JSON precisa ser um objeto ou uma lista de objetos")
    if isinstance(doc.get("DataModel"), list):
        return "nosql-workbench", [t for t in doc["DataModel"] if isinstance(t, dict)]
    if isinstance(doc.get("Resources"), dict):
        tabs = []
        for res in doc["Resources"].values():
            if isinstance(res, dict) and res.get("Type") in ("AWS::DynamoDB::Table", "AWS::DynamoDB::GlobalTable"):
                props = dict(res.get("Properties") or {})
                tabs.append(props)
        if not tabs:
            raise DynamoDBFormatError("template CloudFormation sem recursos AWS::DynamoDB::Table")
        return "cloudformation", tabs
    if isinstance(doc.get("Table"), dict):
        return "describe-table", [doc["Table"]]
    if isinstance(doc.get("Tables"), list):
        return "describe-table", [t.get("Table", t) for t in doc["Tables"] if isinstance(t, dict)]
    if "TableName" in doc and ("KeySchema" in doc or "AttributeDefinitions" in doc):
        return "describe-table", [doc]
    if "TableName" in doc and "KeyAttributes" in doc:
        return "nosql-workbench", [doc]
    raise DynamoDBFormatError(
        "formato não reconhecido: esperado saída do `aws dynamodb describe-table`, "
        "modelo do NoSQL Workbench (DataModel) ou template CloudFormation"
    )


def parse_dynamodb_json(text: str, system_id: str) -> tuple[ExtractionSnapshot, list[str], str]:
    """JSON (texto) → (snapshot, avisos, formato detectado). Levanta
    DynamoDBFormatError/ValueError com mensagem acionável se não for válido."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DynamoDBFormatError(f"JSON inválido (linha {exc.lineno}, coluna {exc.colno}): {exc.msg}") from exc
    fmt, tables = _collect_tables(doc)
    warnings: list[str] = []
    entities: list[ExtractedEntity] = []
    seen: set[str] = set()
    for t in tables:
        ent = _from_workbench_table(t, warnings) if "KeyAttributes" in t else _from_table_description(t, warnings)
        if ent is None:
            continue
        if ent.technical_name in seen:
            warnings.append(f"Tabela {ent.technical_name} repetida no arquivo — mantida a 1ª.")
            continue
        seen.add(ent.technical_name)
        entities.append(ent)
    snap = ExtractionSnapshot(
        source_kind="DYNAMODB",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=[DYNAMODB_SCHEMA] if entities else [],
        entities=entities,
        relationships=[],
    )
    return snap, warnings, fmt
