#!/usr/bin/env python3
"""Smoke pós-deploy do suporte DynamoDB via JSON (rodada 9 consolidada, item 17).

Roda LOCAL contra o app deployado (mesmo padrão de smoke_deployed.py /
repro_large_ddl.py). GRAVA num sistema DESCARTÁVEL `SMOKE-DYNAMO-<ts>`:
  1. cria o sistema (tecnologia DynamoDB);
  2. importa um JSON do NoSQL Workbench + um describe-table (POST /extractions/dynamodb/run);
  3. aprova+aplica o ticket;
  4. confere entidades, PK composta e LEITURA dos índices GSI (o Literal IndexType
     sem GSI/LSI faria essa leitura dar 500);
  5. exporta como DYNAMODB e valida que é JSON de create-table;
  6. limpa e arquiva o sistema.

Uso: python3 scripts/smoke_dynamodb.py [--profile DEFAULT]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_URL = "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"

WORKBENCH = {
    "ModelName": "Smoke",
    "DataModel": [{
        "TableName": "SmokeClientes",
        "KeyAttributes": {"PartitionKey": {"AttributeName": "cliente_id", "AttributeType": "S"},
                          "SortKey": {"AttributeName": "criado_em", "AttributeType": "N"}},
        "NonKeyAttributes": [{"AttributeName": "nome", "AttributeType": "S"},
                             {"AttributeName": "email", "AttributeType": "S"}],
        "GlobalSecondaryIndexes": [{
            "IndexName": "gsi_email",
            "KeyAttributes": {"PartitionKey": {"AttributeName": "email", "AttributeType": "S"}},
            "Projection": {"ProjectionType": "ALL"},
        }],
        "TableData": [{"cliente_id": {"S": "1"}, "criado_em": {"N": "1"}, "score": {"N": "7"}}],
    }],
}

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="DEFAULT")
    args = ap.parse_args()
    tok = json.loads(subprocess.check_output(["databricks", "auth", "token", "-p", args.profile], text=True))["access_token"]

    def call(method, path, body=None, timeout=180):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{APP_URL}{path}", data=data, method=method,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 — URL fixa https do app
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            return e.code, {"detail": e.read()[:500].decode(errors="replace")}

    st, sysres = call("POST", "/api/systems", {"system_name": f"SMOKE-DYNAMO-{int(time.time())}",
                                                "technology": "DynamoDB", "domain": "Smoke"})
    sid = sysres.get("system_id")
    check("cria sistema descartável", st == 200 and bool(sid), f"{sid}")
    if not sid:
        return 1
    try:
        st, res = call("POST", "/api/extractions/dynamodb/run",
                       {"system_id": sid, "json_text": json.dumps(WORKBENCH), "open_ticket": True})
        check("import NoSQL Workbench = 200", st == 200, f"status={res.get('status')} found={res.get('objects_found')} {res.get('detail','')}")
        tkt = res.get("ticket_id")
        if tkt:
            st, ap_res = call("POST", f"/api/tickets/{tkt}/approve-apply", {})
            check("approve-apply = 200", st == 200 and ap_res.get("status") == "APPLIED", str(ap_res)[:200])
        st, ents = call("GET", f"/api/entities?system_id={sid}")
        items = ents.get("items", ents) if isinstance(ents, dict) else ents
        ent = next((e for e in (items or []) if e.get("technical_name") == "SmokeClientes"), None)
        check("entidade SmokeClientes no schema dynamodb", bool(ent) and ent.get("schema_name") == "dynamodb",
              str(ent and ent.get("schema_name")))
        if ent:
            st, attrs = call("GET", f"/api/entities/{ent['entity_id']}/attributes")
            pk = [a["technical_name"] for a in attrs if a.get("is_primary_key")] if isinstance(attrs, list) else []
            check("PK composta HASH+RANGE", pk == ["cliente_id", "criado_em"], str(pk))
            names = {a["technical_name"] for a in attrs} if isinstance(attrs, list) else set()
            check("atributo inferido dos itens (score)", "score" in names, str(sorted(names)))
            st, idx = call("GET", f"/api/entities/{ent['entity_id']}/indexes")
            kinds = [(i.get("index_name"), i.get("index_type")) for i in idx] if isinstance(idx, list) else idx
            check("LER índices GSI = 200 (Literal IndexType)", st == 200 and ("gsi_email", "GSI") in kinds, str(kinds)[:200])
        st, exp = call("POST", "/api/ddl/export", {"system_id": sid, "dialect": "DYNAMODB"})
        try:
            tables = json.loads(exp.get("combined_text", ""))
            t0 = tables[0]
            ok = t0["TableName"] == "SmokeClientes" and t0["KeySchema"][0] == {"AttributeName": "cliente_id", "KeyType": "HASH"}
            check("export DYNAMODB = JSON de create-table", st == 200 and ok, json.dumps(t0)[:200])
        except Exception as e:  # noqa: BLE001
            check("export DYNAMODB = JSON de create-table", False, f"{st} {e} {str(exp)[:200]}")
    finally:
        st1, _ = call("POST", f"/api/systems/{sid}/clear", {})
        st2, _ = call("DELETE", f"/api/systems/{sid}")
        print(f"  cleanup: clear={st1} arquivar={st2}")
    print("RESULTADO:", "OK" if not _failures else f"{len(_failures)} falha(s): {_failures}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
