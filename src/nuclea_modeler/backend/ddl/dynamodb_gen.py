"""Export "DDL" para DynamoDB = JSON de `create-table` (rodada 9 consolidada, item 17).

DynamoDB não tem DDL SQL; a "representação por arquivo JSON" pedida pelo cliente
é o formato de entrada do `aws dynamodb create-table --cli-input-json` (o mesmo
`TableDescription` que o import aceita — round-trip import → export fecha).

Regras do DynamoDB que o modelo relacional não garante (e por isso validamos):
- a chave é 1 ou 2 atributos: partition key (HASH) + sort key (RANGE) opcional —
  usamos as colunas PK na ordem (`ordinal_position`); mais de 2 PKs é ERRO;
- atributos de chave só podem ser S/N/B; tipos SQL são mapeados (VARCHAR→S,
  NUMERIC→N, BLOB→B…);
- `AttributeDefinitions` só pode listar atributos usados em chaves (tabela e
  índices) — o DynamoDB rejeita definições "sobrando";
- LSI usa a MESMA partition key da tabela; GSI tem chaves próprias.
Relacionamentos (FK) não existem no DynamoDB — o export não os emite.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .models import DDLExportRequest

_DYNAMO_CODES = {
    "STRING": "S", "NUMBER": "N", "BINARY": "B",
    "S": "S", "N": "N", "B": "B",
}
_NUMERIC_SQL = re.compile(
    r"^(INT|INTEGER|BIGINT|SMALLINT|TINYINT|NUMERIC|DECIMAL|NUMBER|FLOAT|DOUBLE|REAL|SERIAL|BIGSERIAL|MONEY)\b",
    re.I,
)
_BINARY_SQL = re.compile(r"^(BINARY|VARBINARY|BLOB|BYTEA|RAW|LONG RAW|IMAGE)\b", re.I)


def key_type_code(native: str | None) -> str:
    """Tipo do modelo → código de atributo de CHAVE do DynamoDB (S/N/B)."""
    t = (native or "").strip()
    up = t.upper()
    if up in _DYNAMO_CODES:
        return _DYNAMO_CODES[up]
    if _NUMERIC_SQL.match(t):
        return "N"
    if _BINARY_SQL.match(t):
        return "B"
    return "S"  # texto, datas, UUID, etc. — chave como string


def gen_dynamodb(entity: dict[str, Any], attrs: list[dict[str, Any]], opts: DDLExportRequest) -> str:
    name = entity.get("technical_name") or ""
    by_name = {a["technical_name"]: a for a in attrs}
    pks = [a["technical_name"] for a in attrs if a.get("is_primary_key")]
    if not pks:
        raise ValueError(
            f"{name}: DynamoDB exige chave — marque 1 (partition) ou 2 (partition + sort) colunas como PK"
        )
    if len(pks) > 2:
        raise ValueError(
            f"{name}: DynamoDB aceita no máximo 2 atributos de chave (partition + sort); "
            f"a tabela tem {len(pks)} PKs ({', '.join(pks)})"
        )
    key_schema = [{"AttributeName": pks[0], "KeyType": "HASH"}]
    if len(pks) == 2:
        key_schema.append({"AttributeName": pks[1], "KeyType": "RANGE"})
    used: list[str] = list(pks)

    gsis: list[dict[str, Any]] = []
    lsis: list[dict[str, Any]] = []
    for ix in entity.get("_indexes") or []:
        kind = str(ix.get("index_type") or "").upper()
        cols = [c.get("name") for c in (ix.get("columns") or []) if c.get("name")]
        if kind not in ("GSI", "LSI") or not cols:
            continue  # índices relacionais (BTREE…) não têm equivalente no DynamoDB
        if kind == "LSI":
            # LSI: partition key da TABELA + sort key alternativa (a coluna do índice
            # que não é a partition key).
            sort = next((c for c in cols if c != pks[0]), None)
            if not sort:
                continue
            ks = [{"AttributeName": pks[0], "KeyType": "HASH"}, {"AttributeName": sort, "KeyType": "RANGE"}]
        else:
            ks = [{"AttributeName": cols[0], "KeyType": "HASH"}]
            if len(cols) > 1:
                ks.append({"AttributeName": cols[1], "KeyType": "RANGE"})
        for k in ks:
            if k["AttributeName"] not in used:
                used.append(k["AttributeName"])
        spec = {
            "IndexName": ix.get("index_name") or f"{kind.lower()}_{len(gsis) + len(lsis) + 1}",
            "KeySchema": ks,
            "Projection": {"ProjectionType": "ALL"},
        }
        (lsis if kind == "LSI" else gsis).append(spec)

    out: dict[str, Any] = {
        "TableName": name,
        # Só atributos usados em chaves — o DynamoDB rejeita definições extras.
        "AttributeDefinitions": [
            {"AttributeName": n, "AttributeType": key_type_code((by_name.get(n) or {}).get("native_data_type"))}
            for n in used
        ],
        "KeySchema": key_schema,
        # On-demand: dispensa ProvisionedThroughput (inclusive nos GSIs).
        "BillingMode": "PAY_PER_REQUEST",
    }
    if gsis:
        out["GlobalSecondaryIndexes"] = gsis
    if lsis:
        out["LocalSecondaryIndexes"] = lsis
    return json.dumps(out, indent=2, ensure_ascii=False)
