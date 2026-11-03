#!/usr/bin/env python3
"""Reprodução do "import de DDL falha com script extenso" (rodada 9 consolidada, item 10).

O cliente reportou falha num DDL de ~12 mil linhas ("c3l") mas não enviou o arquivo.
Este script gera um DDL SINTÉTICO com a mesma ordem de grandeza e a mistura típica
de um dump real (tabelas, COMMENT ON, índices, FKs via ALTER TABLE, functions com
corpo `$$ … ; … $$` e INSERTs) e chama o PREVIEW (dry-run) do app deployado:
`POST /api/extractions/ddl/preview` — faz parse + diff mas NÃO abre ticket nem grava
nada (read-only). Mede tempo, status HTTP e o resultado.

Uso (local, logo após um deploy):
    # só leitura (dry-run) contra um sistema existente:
    python3 scripts/repro_large_ddl.py --system-id <id> [--lines 12000] [--poison]
    # ponta a ponta (GRAVA): cria um sistema descartável SMOKE-DDL-<ts>, importa de
    # verdade, aprova+aplica o ticket, mede cada etapa e limpa/arquiva no fim:
    python3 scripts/repro_large_ddl.py --real [--lines 12000]

O token vem de `databricks auth token -p <profile>`. Sem --real, nada é gravado.
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


def gen_ddl(target_lines: int) -> str:
    """DDL Postgres sintético com ~target_lines linhas."""
    out: list[str] = ["SET search_path TO c3l;", ""]
    t = 0
    while len(out) < target_lines:
        t += 1
        name = f"tb_obj_{t:04d}"
        out.append(f"CREATE TABLE c3l.{name} (")
        out.append("  id BIGINT NOT NULL,")
        for c in range(1, 22):
            out.append(f"  col_{c:02d} VARCHAR({20 + c}) NULL,")
        out.append("  status CHAR(1) NOT NULL DEFAULT 'A' CHECK (status IN ('A','I')),")
        out.append(f"  CONSTRAINT pk_{name} PRIMARY KEY (id)")
        out.append(");")
        out.append(f"COMMENT ON TABLE c3l.{name} IS 'Tabela {t}; descrição com ponto-e-vírgula';")
        out.append(f"COMMENT ON COLUMN c3l.{name}.col_01 IS 'Coluna 1 da tabela {t}';")
        out.append(f"CREATE INDEX ix_{name}_c1 ON c3l.{name} (col_01);")
        if t > 1:
            out.append(
                f"ALTER TABLE c3l.{name} ADD CONSTRAINT fk_{name}_prev "
                f"FOREIGN KEY (id) REFERENCES c3l.tb_obj_{t - 1:04d} (id);"
            )
        if t % 10 == 0:
            # function com corpo $$ contendo ';' — o split ingênuo por ';' quebra isto
            out.append(f"CREATE OR REPLACE FUNCTION c3l.fn_{t:04d}() RETURNS void AS $$")
            out.append("BEGIN")
            out.append(f"  UPDATE c3l.{name} SET status = 'I' WHERE col_01 IS NULL;")
            out.append(f"  DELETE FROM c3l.{name} WHERE status = 'X';")
            out.append("END;")
            out.append("$$ LANGUAGE plpgsql;")
        if t % 5 == 0:
            for i in range(10):
                out.append(f"INSERT INTO c3l.{name} (id, col_01, status) VALUES ({i}, 'v;{i}', 'A');")
        out.append("")
    return "\n".join(out) + "\n"


def token(profile: str) -> str:
    raw = subprocess.check_output(["databricks", "auth", "token", "-p", profile], text=True)
    return json.loads(raw)["access_token"]


def _call(tok: str, method: str, path: str, body: dict | None, timeout: int):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{APP_URL}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — URL fixa https do app
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {}), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read()[:600].decode(errors="replace")}, time.monotonic() - t0
    except Exception as e:  # noqa: BLE001 — timeout/conexão é o que medimos
        return -1, {"detail": f"{type(e).__name__}: {e}"}, time.monotonic() - t0


def run_real(ddl: str, profile: str, timeout: int) -> int:
    """Import REAL + apply num sistema descartável; mede cada etapa e limpa."""
    tok = token(profile)
    name = f"SMOKE-DDL-{int(time.time())}"
    st, sysres, _ = _call(tok, "POST", "/api/systems",
                          {"system_name": name, "technology": "PostgreSQL", "domain": "Smoke"}, 60)
    sid = sysres.get("system_id") if isinstance(sysres, dict) else None
    print(f"sistema descartável: {name} → {sid} (HTTP {st})")
    if not sid:
        return 1
    rc = 0
    try:
        st, res, dt = _call(tok, "POST", "/api/extractions/ddl/run",
                            {"system_id": sid, "dialect": "POSTGRES", "ddl_text": ddl, "open_ticket": True},
                            timeout)
        print(f"[import] HTTP {st} em {dt:.1f}s · found={res.get('objects_found')} "
              f"status={res.get('status')} ticket={res.get('ticket_id')} {str(res.get('detail',''))[:300]}")
        tkt = res.get("ticket_id")
        if st != 200 or not tkt:
            return 1
        st, res2, dt = _call(tok, "POST", f"/api/tickets/{tkt}/approve-apply", {}, timeout)
        print(f"[apply]  HTTP {st} em {dt:.1f}s · {str(res2)[:300]}")
        if st != 200:
            rc = 1
        st, ents, dt = _call(tok, "GET", f"/api/entities?system_id={sid}&page_size=1", None, 120)
        total = ents.get("total") if isinstance(ents, dict) else (len(ents) if isinstance(ents, list) else None)
        print(f"[check]  entidades no sistema após apply: {total} (HTTP {st})")
    finally:
        st1, _, _ = _call(tok, "POST", f"/api/systems/{sid}/clear", {}, timeout)
        st2, _, _ = _call(tok, "DELETE", f"/api/systems/{sid}", None, 120)
        print(f"[cleanup] clear={st1} arquivar={st2} (exclusão definitiva: Navegador → arquivados)")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system-id", help="sistema existente para o dry-run (sem --real)")
    ap.add_argument("--real", action="store_true", help="import REAL + apply num sistema descartável")
    ap.add_argument("--lines", type=int, default=12000)
    ap.add_argument("--profile", default="DEFAULT")
    ap.add_argument("--dialect", default="POSTGRES")
    ap.add_argument("--save", help="grava o DDL gerado neste caminho")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument(
        "--poison", action="store_true",
        help="insere instruções que o sqlglot não parseia (meta-comando psql, "
        "TABLESPACE) para forçar o caminho de fallback statement-a-statement",
    )
    args = ap.parse_args()

    ddl = gen_ddl(args.lines)
    if args.poison:
        # Comum em dumps reais (pg_dump / scripts de DBA): o parse GLOBAL falha e o
        # import cai no split por ';'.
        ddl = (
            "\\connect c3l\n"
            "CREATE TABLESPACE ts_dados OWNER app LOCATION '/data/ts';\n" + ddl
        )
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(ddl)
    n_lines = ddl.count("\n")
    print(f"DDL sintético: {n_lines} linhas, {len(ddl.encode()) / 1024:.0f} KB")

    if args.real:
        return run_real(ddl, args.profile, args.timeout)
    if not args.system_id:
        ap.error("--system-id é obrigatório no modo dry-run (ou use --real)")

    body = json.dumps({
        "system_id": args.system_id, "dialect": args.dialect,
        "ddl_text": ddl, "open_ticket": False,
    }).encode()
    req = urllib.request.Request(
        f"{APP_URL}/api/extractions/ddl/preview", data=body, method="POST",
        headers={"Authorization": f"Bearer {token(args.profile)}", "Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:  # nosec B310 — URL fixa https do app
            dt = time.monotonic() - t0
            data = json.loads(resp.read())
            print(f"HTTP {resp.status} em {dt:.1f}s")
            print(f"status={data.get('status')} found={data.get('objects_found')} "
                  f"new={data.get('objects_new')} changed={data.get('objects_changed')} "
                  f"duration_ms(servidor)={data.get('duration_ms')}")
            errs = data.get("errors") or []
            print(f"erros/avisos: {len(errs)}")
            for e in errs[:10]:
                print("  -", e[:160])
    except urllib.error.HTTPError as e:
        dt = time.monotonic() - t0
        print(f"HTTP {e.code} em {dt:.1f}s: {e.read()[:600]!r}")
        return 1
    except Exception as e:  # noqa: BLE001 — timeout/conexão: é justamente o que medimos
        dt = time.monotonic() - t0
        print(f"FALHA após {dt:.1f}s: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
