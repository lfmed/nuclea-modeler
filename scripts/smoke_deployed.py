#!/usr/bin/env python3
"""Smoke test do app DEPLOYADO (pós-deploy) — pega o gap "CI verde, prod quebrada".

PORQUÊ: o CI roda os testes com deps pinadas, mas houve casos em que o DEPLOY
resolvia outra versão (ex.: sqlglot) e um recurso passava no CI e falhava em
produção — o `COMMENT ON TABLE` (round 6) foi assim. Este script exercita, NO APP
JÁ DEPLOYADO, o caminho de escrita ponta-a-ponta e confere o resultado. Rode logo
após um deploy; se algo divergir do CI, ele acusa na hora.

O que valida (num sistema DESCARTÁVEL `SMOKE-<ts>`, apagado no fim):
  1. saúde:        GET /api/version e /api/readyz
  2. dry-run:      POST /api/extractions/ddl/preview NÃO cria ticket e devolve `preview`
  3. import DDL:   COMMENT ON TABLE  → descrição da ENTIDADE  (a classe de bug do drift)
                   COMMENT ON COLUMN → descrição da COLUNA
                   CHECK / FK / DEFAULT string  capturados e re-emitidos no export DDL

Uso:
    TOKEN=$(databricks auth token --profile DEFAULT | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
    python3 scripts/smoke_deployed.py "$TOKEN"                 # full + cleanup
    python3 scripts/smoke_deployed.py "$TOKEN" --health-only   # só /version e /readyz
    python3 scripts/smoke_deployed.py "$TOKEN" --no-cleanup    # deixa o sistema p/ debug
    BASE_URL=https://... python3 scripts/smoke_deployed.py "$TOKEN"

Saída: exit code 0 = tudo PASS; 1 = alguma falha (bom p/ CI/`workflow_dispatch`).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get(
    "BASE_URL",
    "https://nuclea-modeler-7474646973581105.aws.databricksapps.com",
).rstrip("/")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
ARGS = sys.argv[1:]
if ARGS and not ARGS[0].startswith("--"):
    TOKEN = ARGS[0]
HEALTH_ONLY = "--health-only" in ARGS
CLEANUP = "--no-cleanup" not in ARGS

_created: list[str] = []
_failures: list[str] = []


def call(method: str, path: str, body: dict | None = None, timeout: int = 120):
    """HTTP helper — devolve (status_code, parsed_json_ou_texto)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as exc:  # noqa: BLE001 — rede/timeout viram falha do smoke
        return 0, f"EXCEPTION: {exc}"


def check(name: str, passed: bool, detail: str = "") -> None:
    """Registra e imprime um item do smoke; acumula falhas p/ o exit code."""
    mark = "PASS ✅" if passed else "FALHOU ❌"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not passed:
        _failures.append(name)


def head(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ── 1. saúde ──────────────────────────────────────────────────────────────────
head("1. Saúde do app deployado")
st, ver = call("GET", "/api/version", timeout=30)
check("GET /api/version = 200", st == 200, f"status={st} body={str(ver)[:120]}")
st_r, ready = call("GET", "/api/readyz", timeout=30)
# readyz pode devolver 200 (ok) ou 503 (degradado) — o importante é responder.
check("GET /api/readyz responde", st_r in (200, 503), f"status={st_r}")

if HEALTH_ONLY:
    head("Resultado (health-only)")
    print("  Falhas:", _failures or "nenhuma")
    sys.exit(1 if _failures else 0)

if not TOKEN:
    print("\n⚠️  Sem TOKEN — só dá pra rodar --health-only. Abortando o full.")
    sys.exit(1 if _failures else 0)

# ── sistema descartável ─────────────────────────────────────────────────────
head("2. Sistema descartável para o teste ponta-a-ponta")
name = f"SMOKE-{int(time.time())}"
st, sysres = call("POST", "/api/systems",
                  {"system_name": name, "technology": "PostgreSQL", "domain": "Smoke"})
sid = sysres.get("system_id") if isinstance(sysres, dict) else None
if sid:
    _created.append(sid)
check("POST /api/systems cria sistema", bool(sid), f"id={sid} status={st}")

# DDL sintético que cobre os recursos sensíveis a drift de versão do sqlglot:
# COMMENT ON TABLE/COLUMN, CHECK (coluna), DEFAULT string, FK entre 2 tabelas.
DDL = """
CREATE TABLE public.cliente (
  id INTEGER PRIMARY KEY,
  nome VARCHAR(120) NOT NULL,
  situacao VARCHAR(20) DEFAULT 'ativo' CHECK (situacao IN ('A','I'))
);
CREATE TABLE public.pedido (
  id INTEGER PRIMARY KEY,
  cliente_id INTEGER,
  CONSTRAINT fk_pedido_cliente FOREIGN KEY (cliente_id) REFERENCES public.cliente (id)
);
COMMENT ON TABLE public.cliente IS 'Cadastro mestre de clientes (smoke test)';
COMMENT ON COLUMN public.cliente.nome IS 'Nome completo do cliente';
"""

if sid:
    # ── 3. dry-run: NÃO cria ticket, devolve preview ─────────────────────────
    head("3. Dry-run / preview (read-only, não cria ticket)")
    st, prev = call("POST", "/api/extractions/ddl/preview",
                    {"system_id": sid, "dialect": "POSTGRES", "ddl_text": DDL, "open_ticket": False})
    prev_ok = (
        st == 200 and isinstance(prev, dict)
        and prev.get("ticket_id") in (None, "")
        and (prev.get("objects_new") or 0) >= 2
        and len(prev.get("preview") or []) >= 2
    )
    check("preview: 200, sem ticket, >=2 objetos em `preview`", prev_ok,
          f"status={st} ticket={isinstance(prev,dict) and prev.get('ticket_id')} "
          f"new={isinstance(prev,dict) and prev.get('objects_new')} "
          f"preview_len={len(prev.get('preview') or []) if isinstance(prev,dict) else 'n/a'}")

    # ── 4. import de verdade + apply ─────────────────────────────────────────
    head("4. Import DDL real + apply do ticket")
    st, res = call("POST", "/api/extractions/ddl/run",
                   {"system_id": sid, "dialect": "POSTGRES", "ddl_text": DDL, "open_ticket": True})
    found = res.get("objects_found") if isinstance(res, dict) else None
    tkt = res.get("ticket_id") if isinstance(res, dict) else None
    check("runDDLImport: 200 e >=2 objetos", st == 200 and (found or 0) >= 2,
          f"status={st} found={found} ticket={tkt}")
    if tkt:
        st_a, _ = call("POST", f"/api/tickets/{tkt}/approve-apply", {})
        check("approve-apply do ticket = 200", st_a == 200, f"status={st_a}")
        time.sleep(1)

    # ── 5. leitura: COMMENT ON → descrição (a classe de bug do drift) ────────
    head("5. Confere descrições importadas (COMMENT ON → description_md)")
    st, ents = call("GET", f"/api/entities?system_id={sid}")
    cliente = None
    if isinstance(ents, list):
        cliente = next((e for e in ents if str(e.get("technical_name", "")).lower() == "cliente"), None)
    desc = (cliente or {}).get("description_md") if cliente else None
    check("COMMENT ON TABLE → descrição da entidade `cliente`",
          bool(desc) and "cadastro mestre" in str(desc).lower(),
          f"description_md={str(desc)[:80]!r}")
    # descrição da coluna `nome`
    col_ok = False
    if cliente:
        st, cols = call("GET", f"/api/entities/{cliente['entity_id']}/attributes")
        if isinstance(cols, list):
            nome = next((c for c in cols if str(c.get("technical_name", "")).lower() == "nome"), None)
            col_ok = bool(nome) and "nome completo" in str((nome or {}).get("description_md", "")).lower()
    check("COMMENT ON COLUMN → descrição da coluna `nome`", col_ok)

    # ── 6. export DDL: FK + CHECK + DEFAULT re-emitidos ──────────────────────
    head("6. Export DDL do sistema (FK / CHECK / DEFAULT)")
    st, exp = call("POST", "/api/ddl/export", {"system_id": sid, "dialect": "POSTGRES"})
    ct = exp.get("combined_text", "") if isinstance(exp, dict) else ""
    up = ct.upper()
    check("FK emitida no DDL (FOREIGN KEY ... REFERENCES)", "FOREIGN KEY" in up and "REFERENCES" in up)
    check("CHECK emitido no DDL", "CHECK (" in up)
    check("DEFAULT string com aspas ('ativo')", "DEFAULT 'ativo'" in ct)

# ── cleanup ──────────────────────────────────────────────────────────────────
head("CLEANUP" if CLEANUP else "SISTEMA DEIXADO (--no-cleanup)")
for s in _created:
    if CLEANUP:
        st1, _ = call("POST", f"/api/systems/{s}/clear", {})
        st2, _ = call("DELETE", f"/api/systems/{s}")
        print(f"  {s}: clear={st1} delete={st2}")
    else:
        print(f"  {s}  (apague manualmente quando terminar)")

# ── resultado ─────────────────────────────────────────────────────────────────
head("RESULTADO DO SMOKE")
if _failures:
    print(f"  ❌ {len(_failures)} verificação(ões) falharam:")
    for f in _failures:
        print(f"     - {f}")
    sys.exit(1)
print("  ✅ Todas as verificações passaram — o deploy está saudável.")
sys.exit(0)
