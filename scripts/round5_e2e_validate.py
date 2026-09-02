#!/usr/bin/env python3
"""Validação END-TO-END do Round 5 no app DEPLOYADO, em sistemas DESCARTÁVEIS.

Ao contrário do round5_validate.py (read-only), este script EXECUTA os fluxos de
escrita que o cliente reportou como falha — import DDL colado (pt 12), import .DM1
com FK (pt 14), emissão de FK no DDL (pt 11), default no DDL (pt 20) e versões
(pt 18) — criando sistemas `VALIDACAO-R5-*` e APAGANDO-os no fim (--cleanup).

Uso:
    TOKEN=$(databricks auth token --profile DEFAULT | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
    python3 scripts/round5_e2e_validate.py "$TOKEN"            # roda a bateria (deixa os sistemas)
    python3 scripts/round5_e2e_validate.py "$TOKEN" --cleanup  # roda e apaga no fim
"""
import json
import sys
import time
import urllib.request

BASE = "https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
CLEANUP = "--cleanup" in sys.argv[2:]

created_systems: list[str] = []


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


def head(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def mk_system(name, tech):
    st, s = call("POST", "/api/systems", {"system_name": name, "technology": tech, "domain": "Validação"})
    sid = s.get("system_id") if isinstance(s, dict) else None
    if sid:
        created_systems.append(sid)
    print(f"  criado sistema {name!r} -> id={sid} (status {st})")
    return sid


def apply_ticket(ticket_id):
    if not ticket_id:
        return None
    st, res = call("POST", f"/api/tickets/{ticket_id}/approve-apply", {})
    print(f"  approve-apply ticket {ticket_id} -> status {st}")
    return res


# ── pt 12 — import de DDL colado (cliente + pedido, ambos PK `id`, com DEFAULT) ──
head("pt 12 — import de DDL COLADO (deve parsear, não falhar)")
sid_ddl = mk_system("VALIDACAO-R5 (DDL colado)", "PostgreSQL")
DDL = """
CREATE TABLE cliente (
  id INTEGER PRIMARY KEY,
  nome VARCHAR(100) NOT NULL,
  situacao VARCHAR(20) DEFAULT 'ativo'
);
CREATE TABLE pedido (
  id INTEGER PRIMARY KEY,
  valor DECIMAL(10,2) NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
st, res = call("POST", "/api/extractions/ddl/run",
               {"system_id": sid_ddl, "dialect": "POSTGRES", "ddl_text": DDL, "open_ticket": True})
print(f"  runDDLImport status={st}")
if isinstance(res, dict):
    print(f"  objects_found={res.get('objects_found')} objects_new={res.get('objects_new')} "
          f"ticket_id={res.get('ticket_id')} error={res.get('error_summary')}")
    ddl_ticket = res.get("ticket_id")
    ok_pt12 = (st == 200 and (res.get("objects_found") or 0) >= 2)
    print("  >> pt 12:", "PASS ✅ (DDL colado parseou " + str(res.get("objects_found")) + " objetos)" if ok_pt12 else "FALHOU ❌")
    apply_ticket(ddl_ticket)
else:
    ok_pt12 = False
    print("  resposta:", str(res)[:400], "\n  >> pt 12: FALHOU ❌")

# ── pt 20 + pt 11 — export DDL do sistema importado ──────────────────────────
head("pt 20 (DEFAULT no DDL) — export do sistema importado")
st, exp = call("POST", "/api/ddl/export", {"system_id": sid_ddl, "dialect": "POSTGRES"})
ct = exp.get("combined_text", "") if isinstance(exp, dict) else ""
has_default = "DEFAULT 'ativo'" in ct or "DEFAULT" in ct.upper()
print(f"  export status={st} | contém DEFAULT? {has_default}")
for l in ct.splitlines():
    if "DEFAULT" in l.upper():
        print("   |", l.strip()[:110])
print("  >> pt 20:", "PASS ✅ (default no DDL)" if has_default else "sem default ❌")

# ── pt 14 — import .DM1 com FK + índice de apoio KeyType='F' ─────────────────
head("pt 14 — import .DM1: FK vira RELACIONAMENTO, índice 'F' é PULADO (não vira IDX)")
sid_dm1 = mk_system("VALIDACAO-R5 (DM1)", "DB2")
DM1 = (
    "Entity\n"
    "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
    "1,1,10,100,100,0,0\n"
    "1,1,11,101,101,0,0\n"
    "\n"
    "Attribute\n"
    "DiagramId,ModelId,EntityId,AttributeId,AttributeNameId,DatatypeId,Length,Scale,Nullable,DefinitionId\n"
    "1,1,10,1,200,8,-2,-1,N,0\n"
    "1,1,10,2,201,10,80,-1,Y,0\n"
    "1,1,11,1,210,8,-2,-1,N,0\n"
    "\n"
    "PrimaryKey\n"
    "DiagramId,ModelId,EntityId,AttributeId,PrimaryKey_ID,Attribute_ID,SequenceNo,Global_User_ID,Row_Time_Stamp\n"
    "1,1,10,1,1,200,1,0,0\n"
    "1,1,11,1,2,210,1,0,0\n"
    "\n"
    "ForeignKey\n"
    "DiagramId,ModelId,RelationshipId,ForeignKey_ID,ParentEntityId,ChildEntityId,Global_User_ID,Row_Time_Stamp\n"
    "1,1,1,1,10,11,0,0\n"
    "\n"
    "Indexes\n"
    "DiagramId,ModelId,EntityId,IndexId,Indexes_ID,Entity_ID,IsUniqueId,IndexTypeId,KeyType,HashSize,HashSizeTypeId,IgnoreDupKeyId,DupRowId,NoSortId,SortOrderingId,IndexNameId,Flags,NSTFlag,CompareFlags,Global_User_ID,Row_Time_Stamp,ColumnStoreId\n"
    "1,1,10,1,1,10,13,0,U,0,0,0,0,0,0,300,0,0,0,0,0,0\n"
    "1,1,11,3,3,11,13,0,F,0,0,0,0,0,0,302,0,0,0,0,0,0\n"
    "\n"
    "IndexColumn\n"
    "DiagramId,ModelId,EntityId,IndexId,AttributeId,IndexColumn_ID,Attribute_ID,Indexes_ID,SequenceNo,SortOrdering,ColumnName_PDId,Global_User_ID,Row_Time_Stamp\n"
    "1,1,10,1,2,1,201,1,1,A,0,0,0\n"
    "1,1,11,3,1,3,210,3,1,A,0,0,0\n"
    "\n"
    "SmallString\n"
    "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
    "100,pedido,0,0,0\n"
    "101,item_pedido,0,0,0\n"
    "200,id_pedido,0,0,0\n"
    "201,email,0,0,0\n"
    "210,id_item,0,0,0\n"
    "300,ix_email_unico,0,0,0\n"
    "302,fk_idx_apoio,0,0,0\n"
)
st, res = call("POST", "/api/extractions/embarcadero/run",
               {"system_id": sid_dm1, "dm1_text": DM1, "open_ticket": True})
print(f"  runEmbarcaderoImport status={st}")
if isinstance(res, dict):
    print(f"  objects_found={res.get('objects_found')} ticket_id={res.get('ticket_id')} error={res.get('error_summary')}")
    apply_ticket(res.get("ticket_id"))
time.sleep(1)
# valida: existe relacionamento? existe índice de apoio 'F' virando IDX?
_, rels = call("GET", f"/api/relationships?system_id={sid_dm1}")
_, ents = call("GET", f"/api/entities?system_id={sid_dm1}")
n_rels = len(rels) if isinstance(rels, list) else 0
idx_names = []
if isinstance(ents, list):
    for e in ents:
        _, ix = call("GET", f"/api/entities/{e['entity_id']}/indexes")
        if isinstance(ix, list):
            idx_names += [i.get("index_name") for i in ix]
print(f"  relacionamentos criados={n_rels} (esperado >=1) | índices={idx_names} (esperado sem 'fk_idx_apoio')")
ok_pt14 = n_rels >= 1 and "fk_idx_apoio" not in idx_names
print("  >> pt 14:", "PASS ✅ (FK virou relacionamento; índice de apoio 'F' pulado)" if ok_pt14 else "FALHOU ❌")

# ── pt 18 — publica versão + diff to=current ─────────────────────────────────
head("pt 18 — publicar versão do sistema importado + diff vs. atual")
st, ver = call("POST", "/api/versions/publish", {"system_id": sid_ddl, "title": "Snapshot validação R5"})
print(f"  publishVersion status={st} -> {json.dumps(ver)[:160] if isinstance(ver,dict) else ver}")
vid = ver.get("version_id") if isinstance(ver, dict) else None
if vid:
    st, diff = call("GET", f"/api/versions/diff?from={vid}&to=current")
    print(f"  diff from={vid[:14]} to=current -> status {st}")
    if isinstance(diff, dict):
        print(f"  totals={diff.get('totals')} (0 mudanças esperado logo após publicar)")
    print("  >> pt 18:", "PASS ✅ (versão publicada + diff vs. atual)" if st == 200 else "FALHOU ❌")

# ── cleanup ──────────────────────────────────────────────────────────────────
head("CLEANUP" if CLEANUP else "SISTEMAS CRIADOS (use --cleanup para apagar)")
for sid in created_systems:
    if CLEANUP:
        st, _ = call("POST", f"/api/systems/{sid}/clear", {})
        st2, _ = call("DELETE", f"/api/systems/{sid}")
        print(f"  {sid}: clear={st} delete={st2}")
    else:
        print(f"  {sid}")

print("\n>> IDs (para pt 9/11 na UI ou cleanup):", created_systems)
