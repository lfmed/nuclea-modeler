#!/usr/bin/env python3
"""Validação ENXUTA pt 22 (xlsx Embarcadero + flags LGPD) + pt 19 (tecnologia) no
app deployado. UMA única import de DDL (as tabelas que a xlsx referencia), depois
importa a xlsx real do cliente e confere as flags LGPD do CLASSIFICACAO.

    python3 scripts/round6_pt22_validate.py "$TOKEN" [--no-cleanup]
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
TOKEN = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ""
CLEANUP = "--no-cleanup" not in sys.argv
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "round6"
_fail: list[str] = []


def call(m, p, b=None, timeout=240):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + p, data=data, method=m)
    r.add_header("Authorization", f"Bearer {TOKEN}")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:  # nosec B310
            raw = x.read().decode("utf-8", "replace")
            try:
                return x.status, json.loads(raw)
            except Exception:
                return x.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as exc:  # noqa: BLE001
        return 0, f"EXCEPTION: {exc}"


def check(name, ok, detail=""):
    print(f"[{'PASS ✅' if ok else 'FALHOU ❌'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    if not ok:
        _fail.append(name)


print("== criando sistema ==", flush=True)
_, s = call("POST", "/api/systems",
            {"system_name": f"VALIDACAO-R6-PT22-{int(time.time())}", "technology": "Embarcadero", "domain": "R6"})
sid = s.get("system_id") if isinstance(s, dict) else None
tech = s.get("technology") if isinstance(s, dict) else None
check("pt 19 — sistema criado com technology (badge)", bool(sid) and bool(tech), f"id={sid} tech={tech!r}")

if sid:
    print("== import DDL (uma vez) p/ materializar as tabelas da xlsx ==", flush=True)
    ddl = (FIXTURES / "programa_social.sql").read_text(encoding="utf-8")
    st, r = call("POST", "/api/extractions/ddl/run",
                 {"system_id": sid, "dialect": "POSTGRES", "ddl_text": ddl, "open_ticket": True})
    print(f"  runDDLImport status={st} found={r.get('objects_found') if isinstance(r,dict) else '?'}", flush=True)
    tkt = r.get("ticket_id") if isinstance(r, dict) else None
    if tkt:
        sta, _ = call("POST", f"/api/tickets/{tkt}/approve-apply", {})
        print(f"  apply status={sta}", flush=True)
        time.sleep(2)

    print("== import xlsx Embarcadero (arquivo real do cliente) ==", flush=True)
    xlsx_b64 = base64.b64encode((FIXTURES / "descricoes_embarcadero.xlsx").read_bytes()).decode()
    st, imp = call("POST", "/api/entities/import/xlsx", {"system_id": sid, "xlsx_base64": xlsx_b64})
    print(f"  importSystemXlsx status={st} -> {json.dumps(imp)[:220] if isinstance(imp,dict) else str(imp)[:220]}", flush=True)
    if isinstance(imp, dict):
        if imp.get("ticket_id"):
            sta, _ = call("POST", f"/api/tickets/{imp['ticket_id']}/approve-apply", {})
            print(f"  apply xlsx ticket status={sta}", flush=True)
            time.sleep(2)
        check("pt 22 — xlsx importado (200)", st == 200,
              f"entities_changed={imp.get('entities_changed')} columns_changed={imp.get('columns_changed')}")
        check("pt 22 — flags LGPD aplicadas (CLASSIFICACAO)", (imp.get("flags_applied") or 0) >= 1,
              f"flags_applied={imp.get('flags_applied')}")
    else:
        check("pt 22 — xlsx importado (200)", False, str(imp)[:150])

    if CLEANUP:
        call("POST", f"/api/systems/{sid}/clear", {})
        call("DELETE", f"/api/systems/{sid}")
        print(f"== apagado {sid} ==", flush=True)

print("\n== RESULTADO ==", flush=True)
if _fail:
    print(f"❌ falhas: {_fail}", flush=True)
    sys.exit(1)
print("✅ pt 22 (xlsx + flags LGPD) + pt 19 (tecnologia): PASS ao vivo.", flush=True)
sys.exit(0)
