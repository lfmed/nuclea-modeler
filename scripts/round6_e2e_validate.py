#!/usr/bin/env python3
"""Validação END-TO-END do Round 6 (itens 15/16/21/22 + dry-run + tecnologia) no
app DEPLOYADO, com os ARQUIVOS REAIS DO CLIENTE (tests/fixtures/round6/*).

Cria sistemas VALIDACAO-R6-* descartáveis e APAGA-os no fim (--no-cleanup mantém).

  pt 15 — COMMENT ON TABLE/COLUMN → descrição (arquivo programa_social.sql)
  pt 21 — CHECK numérico do cliente (programa_social_db2.sql, CK PRINCIPAL IN (0,1))
  pt 22 — import .xlsx Embarcadero + flags LGPD do CLASSIFICACAO
  dry-run — preview não cria ticket
  pt 19 — sistema tem technology (badge de tecnologia)

Uso:
    TOKEN=$(databricks auth token --profile DEFAULT | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
    python3 scripts/round6_e2e_validate.py "$TOKEN"
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

_created: list[str] = []
_fail: list[str] = []


def call(m, p, b=None, timeout=180):
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


def mk(name, tech):
    _, s = call("POST", "/api/systems", {"system_name": name, "technology": tech, "domain": "Validação R6"})
    sid = s.get("system_id") if isinstance(s, dict) else None
    if sid:
        _created.append(sid)
    return sid, (s.get("technology") if isinstance(s, dict) else None)


def apply_tkt(tid):
    if tid:
        call("POST", f"/api/tickets/{tid}/approve-apply", {})
        time.sleep(1)


def check(name, ok, detail=""):
    print(f"  [{'PASS ✅' if ok else 'FALHOU ❌'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _fail.append(name)


def head(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def ents_of(sid):
    st, e = call("GET", f"/api/entities?system_id={sid}")
    return e if isinstance(e, list) else []


def attrs_of(eid):
    st, c = call("GET", f"/api/entities/{eid}/attributes")
    return c if isinstance(c, list) else []


# ── pt 15 — COMMENT ON via arquivo real do cliente (Postgres) ────────────────
head("pt 15 — COMMENT ON TABLE/COLUMN → descrição (programa_social.sql do cliente)")
sid15, tech15 = mk("VALIDACAO-R6 (pt15 Postgres)", "PostgreSQL")
ddl15 = (FIXTURES / "programa_social.sql").read_text(encoding="utf-8")
st, r = call("POST", "/api/extractions/ddl/run",
             {"system_id": sid15, "dialect": "POSTGRES", "ddl_text": ddl15, "open_ticket": True})
print(f"  runDDLImport status={st} found={r.get('objects_found') if isinstance(r,dict) else '?'}")
apply_tkt(r.get("ticket_id") if isinstance(r, dict) else None)
ents = ents_of(sid15)
pessoa = next((e for e in ents if str(e.get("technical_name", "")).lower() == "pessoa"), None)
desc = (pessoa or {}).get("description_md")
check("COMMENT ON TABLE pessoa → descrição da entidade",
      bool(desc) and "program" in str(desc).lower(), f"desc={str(desc)[:70]!r}")
col_ok = False
if pessoa:
    nome = next((c for c in attrs_of(pessoa["entity_id"])
                 if str(c.get("technical_name", "")).lower() == "nome_completo"), None)
    d = str((nome or {}).get("description_md", "")).lower()
    col_ok = "nome completo" in d
check("COMMENT ON COLUMN nome_completo → descrição da coluna", col_ok)
# pt 19 — technology presente (badge)
check("pt 19 — sistema tem technology (badge)", bool(tech15), f"technology={tech15!r}")

# ── pt 21 — CHECK numérico do cliente (DB2) ──────────────────────────────────
head("pt 21 — CHECK do cliente (programa_social_db2.sql: PRINCIPAL IN (0,1))")
sid21, _ = mk("VALIDACAO-R6 (pt21 DB2)", "DB2")
ddl21 = (FIXTURES / "programa_social_db2.sql").read_text(encoding="utf-8")
st, r = call("POST", "/api/extractions/ddl/run",
             {"system_id": sid21, "dialect": "DB2", "ddl_text": ddl21, "open_ticket": True})
print(f"  runDDLImport status={st} found={r.get('objects_found') if isinstance(r,dict) else '?'}")
apply_tkt(r.get("ticket_id") if isinstance(r, dict) else None)
# procura alguma coluna com check_constraint capturado
found_check = None
for e in ents_of(sid21):
    for c in attrs_of(e["entity_id"]):
        if c.get("check_constraint"):
            found_check = (e["technical_name"], c["technical_name"], c["check_constraint"])
            break
    if found_check:
        break
check("CHECK capturado em alguma coluna", bool(found_check), f"{found_check}")
# re-emissão no export
st, exp = call("POST", "/api/ddl/export", {"system_id": sid21, "dialect": "DB2"})
ct = exp.get("combined_text", "") if isinstance(exp, dict) else ""
check("CHECK re-emitido no export DDL", "CHECK (" in ct.upper())

# ── pt 22 — import .xlsx Embarcadero + flags LGPD ────────────────────────────
head("pt 22 — import .xlsx Embarcadero (descricoes_embarcadero.xlsx) + flags LGPD")
sid22, _ = mk("VALIDACAO-R6 (pt22 xlsx)", "Embarcadero")
# a xlsx casa por NOME de tabela → precisa que as tabelas já existam. Importa o
# DDL do cliente primeiro (mesmas tabelas), depois aplica as descrições via xlsx.
st, r = call("POST", "/api/extractions/ddl/run",
             {"system_id": sid22, "dialect": "POSTGRES", "ddl_text": ddl15, "open_ticket": True})
apply_tkt(r.get("ticket_id") if isinstance(r, dict) else None)
xlsx_b64 = base64.b64encode((FIXTURES / "descricoes_embarcadero.xlsx").read_bytes()).decode()
st, imp = call("POST", "/api/entities/import/xlsx", {"system_id": sid22, "xlsx_base64": xlsx_b64})
print(f"  importSystemXlsx status={st} -> {json.dumps(imp)[:200] if isinstance(imp,dict) else str(imp)[:200]}")
if isinstance(imp, dict):
    apply_tkt(imp.get("ticket_id"))
    flags_applied = imp.get("flags_applied", 0)
    check("xlsx importado (200)", st == 200, f"entities_changed={imp.get('entities_changed')} columns_changed={imp.get('columns_changed')}")
    check("flags LGPD aplicadas a partir do CLASSIFICACAO", (flags_applied or 0) >= 1,
          f"flags_applied={flags_applied}")
else:
    check("xlsx importado (200)", False, str(imp)[:120])

# ── dry-run — preview NÃO cria ticket ────────────────────────────────────────
head("dry-run — preview do import DDL não cria ticket (read-only)")
sid_dry, _ = mk("VALIDACAO-R6 (dry-run)", "PostgreSQL")
st, prev = call("POST", "/api/extractions/ddl/preview",
                {"system_id": sid_dry, "dialect": "POSTGRES", "ddl_text": ddl15, "open_ticket": False})
prev_ok = st == 200 and isinstance(prev, dict) and not prev.get("ticket_id") and len(prev.get("preview") or []) >= 1
check("preview: 200, sem ticket, com lista `preview`", prev_ok,
      f"status={st} ticket={isinstance(prev,dict) and prev.get('ticket_id')} "
      f"preview_len={len(prev.get('preview') or []) if isinstance(prev,dict) else '?'}")
# confirma que NADA foi persistido (sistema continua vazio)
check("dry-run não materializou entidades", len(ents_of(sid_dry)) == 0,
      f"entidades no sistema após preview={len(ents_of(sid_dry))}")

# ── cleanup ──────────────────────────────────────────────────────────────────
head("CLEANUP" if CLEANUP else "SISTEMAS DEIXADOS (--no-cleanup)")
for s in _created:
    if CLEANUP:
        call("POST", f"/api/systems/{s}/clear", {})
        call("DELETE", f"/api/systems/{s}")
        print(f"  apagado {s}")
    else:
        print(f"  {s}")

head("RESULTADO ROUND 6")
if _fail:
    print(f"  ❌ {len(_fail)} falha(s): {_fail}")
    sys.exit(1)
print("  ✅ Round 6 (15/16/21/22 + dry-run + tecnologia): tudo PASS ao vivo.")
sys.exit(0)
