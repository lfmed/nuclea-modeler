"""Reproduz, no app DEPLOYADO, a falha de import CSV reportada pelo cliente (#6)
usando os ARQUIVOS REAIS de `ncleamodelerevoluo/`.

Hipótese (confirmada no código `entities/roundtrip.py:223-229`): o import CSV casa
as linhas por `schema.table` ESTRITO. O DDL do cliente força schema `social`
(`SET search_path TO social` / `SET CURRENT SCHEMA SOCIAL`), mas o CSV
`descricoes_databricks_preenchido.csv` usa schema `dbo` em todas as linhas →
nenhuma tabela casa → tudo vira `unknown_tables` → "não carregou todas as
informações".

Fluxo (num sistema DESCARTÁVEL, apagado no fim):
  1. cria sistema RETESTE-CSV-<ts>
  2. importa programa_social.sql (POSTGRES) + approve-apply
  3. lê as entidades → mostra em que SCHEMA caíram
  4. importa o CSV do cliente (schema dbo)  → mostra unknown_tables (a FALHA)
  5. importa o MESMO CSV com schema corrigido p/ o schema real → mostra que casa
     (prova a direção do fix: fallback por nome de tabela quando o schema difere)
  6. apaga o sistema

Uso:
  TOKEN=$(databricks auth token --profile DEFAULT | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
  python3 scripts/reproduce_csv_import.py "$TOKEN"
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get(
    "BASE_URL", "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
)
TOKEN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TOKEN", "")
FILES = Path(__file__).resolve().parent.parent / "ncleamodelerevoluo"


def call(method: str, path: str, body: dict | None = None, timeout: int = 300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def head(t: str) -> None:
    print(f"\n{'=' * 4} {t} {'=' * 4}")


sid = None
try:
    head("1. cria sistema descartável")
    ts = int(time.time())
    st, res = call("POST", "/api/systems", {
        "system_name": f"RETESTE-CSV-{ts}", "domain": "Reteste",
        "technology": "PostgreSQL", "is_active": True,
    })
    sid = res.get("system_id") if isinstance(res, dict) else None
    print(f"  status={st} system_id={sid}")
    if not sid:
        print("  ABORTA: não criou sistema"); sys.exit(1)

    head("2. importa programa_social.sql (POSTGRES) + apply")
    ddl = (FILES / "programa_social.sql").read_text(encoding="utf-8")
    st, res = call("POST", "/api/extractions/ddl/run", {
        "system_id": sid, "dialect": "POSTGRES", "ddl_text": ddl, "open_ticket": True,
    })
    tkt = res.get("ticket_id") if isinstance(res, dict) else None
    print(f"  ddl/run status={st} ticket={tkt} "
          f"objetos={res.get('objects_found') if isinstance(res, dict) else '?'}")
    if tkt:
        st_a, res_a = call("POST", f"/api/tickets/{tkt}/approve-apply", {})
        print(f"  approve-apply status={st_a} "
              f"applied={res_a.get('applied_count') if isinstance(res_a, dict) else res_a}")

    head("3. em que schema as entidades caíram?")
    st, ents = call("GET", f"/api/entities?system_id={sid}")
    schemas = sorted({e.get("schema_name") for e in ents}) if isinstance(ents, list) else []
    print(f"  entidades={len(ents) if isinstance(ents, list) else '?'} schemas={schemas}")
    real_schema = schemas[0] if schemas else "social"

    head("4. importa o CSV do cliente (schema dbo) — a FALHA reportada")
    csv_text = (FILES / "descricoes_databricks_preenchido.csv").read_text(encoding="utf-8")
    st, res = call("POST", "/api/entities/import/csv", {"system_id": sid, "csv_text": csv_text})
    if isinstance(res, dict):
        print(f"  status={st} entities_changed={res.get('entities_changed')} "
              f"columns_changed={res.get('columns_changed')} flags_applied={res.get('flags_applied')}")
        print(f"  unknown_tables ({len(res.get('unknown_tables', []))}): {res.get('unknown_tables')}")
        print(f"  message: {res.get('message')}")
    else:
        print(f"  status={st} body={res}")

    head("5. mesmo CSV com schema corrigido p/ o real → deveria CASAR")
    fixed = csv_text.replace("\ndbo,", f"\n{real_schema},")
    st, res = call("POST", "/api/entities/import/csv", {"system_id": sid, "csv_text": fixed})
    if isinstance(res, dict):
        print(f"  status={st} entities_changed={res.get('entities_changed')} "
              f"columns_changed={res.get('columns_changed')} flags_applied={res.get('flags_applied')}")
        print(f"  unknown_tables ({len(res.get('unknown_tables', []))}): {res.get('unknown_tables')}")
        print(f"  message: {res.get('message')}")
    else:
        print(f"  status={st} body={res}")

finally:
    if sid:
        head("6. limpeza — apaga o sistema descartável")
        st1, _ = call("POST", f"/api/systems/{sid}/clear", {})
        st2, _ = call("DELETE", f"/api/systems/{sid}")
        print(f"  clear={st1} delete={st2}")
