"""Import de DDL extenso / estilo dump (rodada 9 consolidada, item 10).

Ponta a ponta no `run_ddl_import` (com sqlglot, banco mockado). Prova que:
- uma instrução que o sqlglot não entende NÃO contamina o resto (antes caía num
  split por ';' cru → 2.207 erros num DDL sintético de 12 mil linhas);
- COMMENT ON com ';' dentro do texto chega inteiro;
- INSERT/GRANT/functions são ignorados sem virar erro e aparecem no resumo;
- PK/FK via `ALTER TABLE ONLY … ADD CONSTRAINT` (formato do pg_dump) são importadas;
- erro de parse aponta o número da linha.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.extractions import service as svc


@pytest.fixture
def snap(monkeypatch):
    captured = {}

    def fake_compute_diff(sql, system_id, snapshot):
        captured["snapshot"] = snapshot
        n = len(snapshot.entities)
        return object(), {"found": n, "new": n, "changed": 0, "removed": 0,
                          "relationships": len(snapshot.relationships)}

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "persist_extraction", lambda *a, **k: "ext-test")
    monkeypatch.setattr(svc, "open_ticket", lambda *a, **k: "tk-test")
    return captured


def _run(ddl: str, dialect: str = "POSTGRES"):
    return svc.run_ddl_import(
        object(), system_id="sys-1", dialect=dialect, ddl_text=ddl,
        actor="t@x.com", open_ticket_on_diff=True,
    )


DUMP = """-- pg_dump
\\connect c3l
SET statement_timeout = 0;
SET search_path TO c3l;
CREATE TABLESPACE ts_dados OWNER app LOCATION '/data/ts';
CREATE TABLE c3l.pedido (
    id bigint NOT NULL,
    status char(1) DEFAULT 'A'
);
CREATE TABLE c3l.item (
    id bigint NOT NULL,
    pedido_id bigint NOT NULL
);
COMMENT ON TABLE c3l.pedido IS 'Pedidos; inclui cancelados';
CREATE FUNCTION c3l.fn() RETURNS void AS $$
BEGIN
  UPDATE c3l.pedido SET status = 'I';
END;
$$ LANGUAGE plpgsql;
INSERT INTO c3l.pedido VALUES (1, 'A');
GRANT SELECT ON c3l.pedido TO bi;
ALTER TABLE ONLY c3l.pedido
    ADD CONSTRAINT pedido_pkey PRIMARY KEY (id);
ALTER TABLE ONLY c3l.item
    ADD CONSTRAINT item_pkey PRIMARY KEY (id);
ALTER TABLE ONLY c3l.item
    ADD CONSTRAINT fk_item_pedido FOREIGN KEY (pedido_id) REFERENCES c3l.pedido(id);
ALTER TABLE c3l.pedido OWNER TO app;
"""


def test_dump_estilo_pg_dump(snap):
    r = _run(DUMP)
    s = snap["snapshot"]
    ents = {e.technical_name: e for e in s.entities}
    assert set(ents) == {"pedido", "item"}
    # nenhuma instrução estranha virou erro
    assert not [e for e in r.errors if "instrução ignorada" in e], r.errors
    # COMMENT ON com ';' chega inteiro
    assert ents["pedido"].native_comment == "Pedidos; inclui cancelados"
    # PK via ALTER TABLE
    assert [a.technical_name for a in ents["pedido"].attributes if a.is_primary_key] == ["id"]
    assert [a.technical_name for a in ents["item"].attributes if a.is_primary_key] == ["id"]
    # FK via ALTER TABLE
    rel = next(x for x in s.relationships if x.child_entity == "item")
    assert (rel.parent_entity, rel.parent_columns, rel.child_columns) == ("pedido", ["id"], ["pedido_id"])
    # o que foi ignorado aparece no resumo
    assert "Ignoradas" in r.summary_md and "INSERT" in r.summary_md


def test_alter_antes_do_create_e_sem_schema(snap):
    ddl = """SET search_path TO vendas;
ALTER TABLE cliente ADD CONSTRAINT pk_cliente PRIMARY KEY (id);
CREATE TABLE cliente (id int NOT NULL, nome varchar(50));
"""
    _run(ddl)
    ent = snap["snapshot"].entities[0]
    assert ent.schema_name == "vendas"
    assert [a.technical_name for a in ent.attributes if a.is_primary_key] == ["id"]


def test_erro_de_parse_aponta_a_linha_e_nao_derruba_o_resto(snap):
    ddl = "CREATE TABLE ok1 (id int);\n\nCREATE TABLE quebrada (id int;\nCREATE TABLE ok2 (id int);\n"
    r = _run(ddl)
    names = {e.technical_name for e in snap["snapshot"].entities}
    assert {"ok1", "ok2"} <= names
    bad = [e for e in r.errors if "Linha 3" in e]
    assert bad, r.errors


def _synthetic(n_tables: int) -> str:
    out = ["\\connect c3l", "SET search_path TO c3l;"]
    for t in range(1, n_tables + 1):
        out.append(f"CREATE TABLE c3l.t{t} (id bigint NOT NULL, a varchar(10), b int);")
        out.append(f"COMMENT ON TABLE c3l.t{t} IS 'tabela {t}; ok';")
        out.append(f"INSERT INTO c3l.t{t} VALUES (1, 'x;y', 2);")
        out.append(f"ALTER TABLE ONLY c3l.t{t} ADD CONSTRAINT t{t}_pkey PRIMARY KEY (id);")
        if t > 1:
            out.append(
                f"ALTER TABLE ONLY c3l.t{t} ADD CONSTRAINT fk{t} FOREIGN KEY (b) REFERENCES c3l.t{t - 1}(id);"
            )
    return "\n".join(out) + "\n"


def test_volume_sem_erros(snap):
    r = _run(_synthetic(300))
    s = snap["snapshot"]
    assert len(s.entities) == 300
    assert r.status == "SUCCESS", r.errors[:5]
    assert all(any(a.is_primary_key for a in e.attributes) for e in s.entities)
    assert len(s.relationships) == 299
    assert all(e.native_comment and e.native_comment.endswith("; ok") for e in s.entities)
