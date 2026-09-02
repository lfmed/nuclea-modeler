#!/usr/bin/env python3
"""Validação read-only do Round 5 no app DEPLOYADO (nuclea-modeler).

Por que existe: o cliente evolui o app em sessões separadas; este script documenta
COMO validar os 10 pontos do Round 5 contra o app no ar sem escrever dados novos.
Ele exercita apenas endpoints read-only ou que não persistem (list/get + ddl/preview
+ ddl/export + versions/diff). Os pontos que exigem WRITE (import de DDL/.DM1, criar
relacionamento c/ transporte de FK, editar default) NÃO são feitos aqui — devem ser
rodados num sistema descartável e depois limpos (ver README no fim).

Uso:
    export DATABRICKS_CONFIG_PROFILE=DEFAULT
    TOKEN=$(databricks auth token --profile DEFAULT | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
    python3 scripts/round5_validate.py "$TOKEN"
"""
import json
import sys
import urllib.request

BASE = "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""


def call(method, path, body=None):
    """GET/POST autenticado; devolve (status, headers, json|texto)."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        # nosec B310: URL é a constante HTTPS do nosso próprio app (BASE), não
        # entrada de usuário — script interno de validação, sem schemes file:/custom.
        with urllib.request.urlopen(req, timeout=60) as r:  # nosec B310
            raw = r.read().decode("utf-8", "replace")
            hdrs = dict(r.headers)
            try:
                return r.status, hdrs, json.loads(raw)
            except Exception:
                return r.status, hdrs, raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, {}, str(e)


def head(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ── pt 12: vocabulário canônico de dialetos ──────────────────────────────────
head("pt 12 — GET /api/ddl/dialects (vocabulário canônico)")
st, _, dialects = call("GET", "/api/ddl/dialects")
print("status", st)
print(json.dumps(dialects, ensure_ascii=False, indent=2)[:1500])

# ── inventário: sistemas ─────────────────────────────────────────────────────
head("Inventário — GET /api/systems")
st, _, systems = call("GET", "/api/systems")
print("status", st, "| nº sistemas:", len(systems) if isinstance(systems, list) else "?")
counts = {}  # system_id -> (n_ents, n_rels)
if isinstance(systems, list):
    for s in systems:
        sid = s.get("system_id")
        _, _, es = call("GET", f"/api/entities?system_id={sid}")
        _, _, rs = call("GET", f"/api/relationships?system_id={sid}")
        ne = len(es) if isinstance(es, list) else 0
        nr = len(rs) if isinstance(rs, list) else 0
        counts[sid] = (ne, nr)
        print(
            f"  - {sid!s:<26} {s.get('system_name')!r:<32} "
            f"tech={s.get('technology')!r:<26} entities={ne} rels={nr}"
        )
    # escolhe o sistema com mais RELACIONAMENTOS (melhor p/ testar FK/DDL)
    picked = max(systems, key=lambda s: counts.get(s.get("system_id"), (0, 0))[1]) if systems else None
    print("\n>> sistema escolhido p/ drill-down:", picked.get("system_name") if picked else None)
else:
    print(json.dumps(systems, ensure_ascii=False)[:800])
    picked = None

SID = picked["system_id"] if picked else None

# ── pt 19: badge de tecnologia (dado por trás) ───────────────────────────────
head("pt 19 — tecnologia por sistema (badge no Navegador)")
if isinstance(systems, list):
    for s in systems:
        print(f"  {s.get('system_name')!r:<34} -> technology={s.get('technology')!r}")

# ── drill-down num sistema real (read-only) ──────────────────────────────────
if SID is not None:
    head(f"Drill-down sistema {SID} ({picked.get('system_name')})")

    st, _, ents = call("GET", f"/api/entities?system_id={SID}")
    n_ents = len(ents) if isinstance(ents, list) else "?"
    print("entities:", st, "| n=", n_ents)
    first_ent = ents[0] if isinstance(ents, list) and ents else None

    # pt 20: default_value nos atributos
    head("pt 20 — coluna 'Padrão' (default_value) nos atributos")
    if first_ent:
        eid = first_ent.get("entity_id") or first_ent.get("id")
        ename = first_ent.get("entity_name") or first_ent.get("name")
        st, _, attrs = call("GET", f"/api/entities/{eid}/attributes")
        print(f"entity {ename!r} attrs status={st} n={len(attrs) if isinstance(attrs,list) else '?'}")
        if isinstance(attrs, list):
            has_field = any("default_value" in a for a in attrs)
            print("  -> campo default_value presente no schema:", has_field)
            for a in attrs[:8]:
                print(
                    f"     {a.get('name')!r:<22} type={a.get('data_type')!r:<14} "
                    f"pk={a.get('is_primary_key')} default={a.get('default_value')!r}"
                )

    # pt 14 + relationship_name + semântica FK (source=PAI)
    head("pt 14 / relationship_name / semântica FK — GET /api/relationships")
    st, _, rels = call("GET", f"/api/relationships?system_id={SID}")
    print("relationships:", st, "| n=", len(rels) if isinstance(rels, list) else "?")
    if isinstance(rels, list):
        has_relname = any("relationship_name" in r for r in rels)
        print("  -> campo relationship_name presente:", has_relname)
        for r in rels[:10]:
            print(
                f"     name={r.get('relationship_name')!r:<24} "
                f"src_attrs={r.get('source_attr_ids')} tgt_attrs={r.get('target_attr_ids')} "
                f"card={r.get('cardinality')!r}"
            )

    # pt 11: FK emitida no DDL (preview NÃO persiste)
    head("pt 11 — FK no DDL: POST /api/ddl/preview")
    for dialect in ("SPARKSQL", "POSTGRES"):
        st, _, prev = call("POST", "/api/ddl/preview", {"system_id": SID, "dialect": dialect})
        txt = prev if isinstance(prev, str) else json.dumps(prev)
        ddl = prev.get("ddl") if isinstance(prev, dict) else txt
        ddl = ddl or ""
        n_fk = ddl.upper().count("FOREIGN KEY")
        n_alter = ddl.upper().count("ALTER TABLE")
        print(f"  [{dialect}] status={st} | ALTER TABLE={n_alter} | FOREIGN KEY={n_fk}")
        # mostra as linhas de FK
        for line in ddl.splitlines():
            if "FOREIGN KEY" in line.upper() or ("ALTER TABLE" in line.upper() and "ADD CONSTRAINT" in line.upper()):
                print("     " + line.strip()[:120])

    # pt 17: nome do arquivo do export = nome do sistema
    head("pt 17 — export: nome do arquivo = nome do sistema (Content-Disposition)")
    st, hdrs, _ = call("POST", "/api/ddl/export", {"system_id": SID, "dialect": "SPARKSQL"})
    cd = hdrs.get("Content-Disposition") or hdrs.get("content-disposition")
    print(f"  status={st} | Content-Disposition={cd!r}")

# ── pt 18: versões + diff vs. atual ──────────────────────────────────────────
head("pt 18 — Versões + diff vs. modelo atual")
st, _, versions = call("GET", "/api/versions")
print("versions list status", st, "| n=", len(versions) if isinstance(versions, list) else "?")
if isinstance(versions, list) and versions:
    for v in versions[:8]:
        print(f"  - id={v.get('id')} v={v.get('version_label') or v.get('label')!r} system={v.get('system_id')} status={v.get('status')!r}")
    vid = versions[0]["id"]
    vsys = versions[0].get("system_id")
    st, _, diff = call("GET", f"/api/versions/diff?from_version={vid}&to=current&system_id={vsys}")
    print(f"\n  diff from_version={vid} to=current -> status {st}")
    print("  " + json.dumps(diff, ensure_ascii=False)[:900])
else:
    print("  (nenhuma versão publicada ainda — diff vs. atual precisa de ao menos 1 versão)")

print("\nOK — validação read-only concluída.")
