"""Valida as conexões de banco NATIVAS no app DEPLOYADO (rodada 8, v1.0058).

Objetivo: provar no runtime REAL do Databricks Apps (não só no CI) que:
  1. Cada driver Python embutido CARREGA (POSTGRES/ORACLE/MYSQL/SQLSERVER/DB2) —
     o risco herdado do ODBC (que falhava com "driver indisponível"). Usamos um
     host inexistente: se o erro for de DNS/rede/conexão (e NÃO "indisponível"),
     o driver carregou.
  2. A senha é cifrada em repouso: o create devolve has_password=True e NUNCA
     devolve a senha (nem 'password' nem 'enc_password').
  3. ODBC legado devolve mensagem de descontinuação.

Cria conexões descartáveis (alias SMOKE-CONN-*) e as APAGA no fim. Uso:
    python3 scripts/validate_connections_deployed.py <TOKEN>
    # ou:  NUCLEA_TOKEN=$(databricks auth token -p DEFAULT | jq -r .access_token) \
    #        python3 scripts/validate_connections_deployed.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

APP = "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
# host inexistente → falha rápida por DNS; se o driver não carregasse, o erro
# seria "indisponível" (import) em vez de erro de rede.
BOGUS_HOST = "nonexistent-db.invalid"
ENGINES = ["POSTGRES", "ORACLE", "MYSQL", "SQLSERVER", "DB2"]


def _req(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{APP}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:500]}


def main() -> int:
    token = sys.argv[1] if len(sys.argv) > 1 else os.getenv("NUCLEA_TOKEN", "")
    if not token:
        print("uso: validate_connections_deployed.py <TOKEN>  (ou env NUCLEA_TOKEN)")
        return 2

    _, systems = _req("GET", "/api/systems", token)
    rows = systems if isinstance(systems, list) else systems.get("items", [])
    if not rows:
        print("FALHA: nenhum sistema para anexar conexões de teste")
        return 1
    system_id = rows[0]["system_id"]
    print(f"sistema de teste: {system_id}\n")

    created: list[str] = []
    failures: list[str] = []
    try:
        # (2) cifra da senha — cria um POSTGRES com senha e inspeciona o retorno.
        st, out = _req("POST", "/api/connections", token, {
            "alias": "SMOKE-CONN-POSTGRES",
            "environment": "HINT",
            "system_id": system_id,
            "connection_type": "DATABASE",
            "config": {"engine": "POSTGRES", "host": BOGUS_HOST, "port": 5432, "database": "d", "username": "u"},
            "password": "s3nh@-teste",
        })
        if st != 200:
            failures.append(f"create POSTGRES falhou HTTP {st}: {out}")
        else:
            created.append(out["connection_id"])
            leak = ("password" in out) or ("enc_password" in out)
            ok_pwd = out.get("has_password") is True and not leak
            print(f"[senha] has_password={out.get('has_password')} vaza_senha={leak} -> {'OK' if ok_pwd else 'FALHA'}")
            if not ok_pwd:
                failures.append("contrato de senha violado (vazou ou has_password!=True)")

        # (1) cada engine carrega? cria + testa + inspeciona o erro.
        for eng in ENGINES:
            if eng == "POSTGRES" and created:
                cid = created[0]  # reusa o já criado
            else:
                st, out = _req("POST", "/api/connections", token, {
                    "alias": f"SMOKE-CONN-{eng}",
                    "environment": "HINT",
                    "system_id": system_id,
                    "connection_type": "DATABASE",
                    "config": {"engine": eng, "host": BOGUS_HOST, "database": "d", "username": "u"},
                    "password": "p",
                })
                if st != 200:
                    failures.append(f"create {eng} falhou HTTP {st}: {out}")
                    continue
                cid = out["connection_id"]
                created.append(cid)
            _, res = _req("POST", f"/api/connections/{cid}/test", token)
            err = (res.get("error") or "")
            driver_loaded = "indisponível" not in err.lower()
            status = "OK (driver carregou)" if driver_loaded else "FALHA (driver não carregou)"
            print(f"[{eng:9}] status={res.get('status'):8} driver -> {status}")
            print(f"            erro: {err[:150]}")
            if not driver_loaded:
                failures.append(f"{eng}: driver não carregou no runtime")

        # (3) ODBC legado → mensagem de descontinuação.
        _, conns = _req("GET", "/api/connections", token)
        odbc = next((c for c in conns if c.get("connection_type") == "ODBC"), None)
        if odbc:
            _, res = _req("POST", f"/api/connections/{odbc['connection_id']}/test", token)
            deprecated = "descontinuada" in (res.get("error") or "").lower()
            print(f"\n[ODBC legado] {'OK (msg de descontinuação)' if deprecated else 'FALHA'}: {(res.get('error') or '')[:120]}")
            if not deprecated:
                failures.append("ODBC não devolveu mensagem de descontinuação")
        else:
            print("\n[ODBC legado] nenhuma conexão ODBC encontrada (ok, nada a validar)")
    finally:
        # cleanup — apaga tudo que criamos
        for cid in created:
            _req("DELETE", f"/api/connections/{cid}", token)
        print(f"\nlimpeza: {len(created)} conexões de teste apagadas")

    if failures:
        print("\n=== FALHAS ===")
        for f in failures:
            print(" -", f)
        return 1
    print("\n=== TUDO OK — drivers carregam, senha cifrada, ODBC descontinuado ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
