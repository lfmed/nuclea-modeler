"""Import DDL: paridade com o fluxo DM1 (Embarcadero).

Cobre o Bloco 1 do feedback do cliente (jul/2026), onde "Subida via DDL" e a
"Representação de entidades/relacionamentos via DDL" foram reportadas NÃO OK,
enquanto o import via .DM1 já servia de referência de paridade:

1. CREATE INDEX / CREATE UNIQUE INDEX passam a ser extraídos e casados à entity
   (antes o parser só olhava CREATE TABLE/VIEW).
2. FK declarada ANTES da tabela-alvo é resolvida (parser agora faz 2 passes; a
   ordem dos CREATE deixou de importar).
3. FK para tabela inexistente no DDL e no catálogo gera WARNING (não é mais
   descartada em silêncio) — padrão do DM1.
4. `parent_columns` é inferido da PK da tabela-alvo quando o REFERENCES não traz
   coluna explícita.
5. `SET search_path TO a, b, c` respeita a lista inteira (não só o 1º schema).

Estratégia idêntica a `test_import_relationships.py`: mocka
compute_diff/persist/open_ticket e captura o `ExtractionSnapshot` montado, além
de inspecionar o `ExtractionResult` (status/errors) quando o comportamento
observável é o aviso.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.extractions import service as svc  # noqa: E402


@pytest.fixture
def capture_snapshot(monkeypatch):
    """Intercepta o snapshot montado pelo run_ddl_import.

    `compute_diff_against_catalog` é substituída, então o catálogo real nunca é
    tocado. A leitura de `catalog_keys` dentro de run_ddl_import é defensiva
    (try/except) — com `sql=object()` ela falha e cai em conjunto vazio, que é
    exatamente o cenário "só o DDL define as tabelas".
    """
    captured = {}

    def fake_compute_diff(sql, system_id, snapshot):
        captured["snapshot"] = snapshot
        return (
            object(),
            {
                "found": len(snapshot.entities),
                "new": len(snapshot.entities),
                "changed": 0,
                "removed": 0,
                "relationships": len(snapshot.relationships),
            },
        )

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "persist_extraction", lambda *a, **k: "ext-test")
    monkeypatch.setattr(svc, "open_ticket", lambda *a, **k: "tk-test")
    return captured


def _run(ddl: str, dialect: str = "POSTGRES"):
    return svc.run_ddl_import(
        object(),
        system_id="sys-1",
        dialect=dialect,
        ddl_text=ddl,
        actor="tester@x.com",
        open_ticket_on_diff=True,
    )


def _index_by_name(entity, name):
    return next(ix for ix in entity.indexes if ix.index_name == name)


# ─── 1. CREATE INDEX é extraído ──────────────────────────────────────────────


def test_ddl_extracts_create_index(capture_snapshot):
    ddl = """
    CREATE TABLE pedido (id INT PRIMARY KEY, cliente_id INT, data_pedido DATE);
    CREATE INDEX ix_pedido_cliente ON pedido (cliente_id);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    ent = next(e for e in snap.entities if e.technical_name == "pedido")
    assert len(ent.indexes) == 1
    ix = ent.indexes[0]
    assert ix.index_name == "ix_pedido_cliente"
    assert ix.is_unique is False
    assert [c.name for c in ix.columns] == ["cliente_id"]


def test_ddl_extracts_unique_index(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY, email VARCHAR(200));
    CREATE UNIQUE INDEX uq_cliente_email ON cliente (email);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    ent = next(e for e in snap.entities if e.technical_name == "cliente")
    ix = _index_by_name(ent, "uq_cliente_email")
    assert ix.is_unique is True
    assert ix.index_type == "UNIQUE"


def test_ddl_multi_column_index_preserves_order(capture_snapshot):
    ddl = """
    CREATE TABLE evento (a INT, b INT, c INT);
    CREATE INDEX ix_evento_abc ON evento (a, b, c);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    ent = next(e for e in snap.entities if e.technical_name == "evento")
    ix = _index_by_name(ent, "ix_evento_abc")
    assert [c.name for c in ix.columns] == ["a", "b", "c"]


def test_ddl_index_declared_before_table(capture_snapshot):
    """O índice pode vir ANTES do CREATE TABLE — casamento é na 2ª passe."""
    ddl = """
    CREATE INDEX ix_conteudo_titulo ON conteudo (titulo);
    CREATE TABLE conteudo (id INT PRIMARY KEY, titulo VARCHAR(200));
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    ent = next(e for e in snap.entities if e.technical_name == "conteudo")
    assert _index_by_name(ent, "ix_conteudo_titulo") is not None


def test_ddl_index_for_missing_table_warns(capture_snapshot):
    """Índice apontando pra tabela ausente no DDL → aviso, não silêncio."""
    ddl = """
    CREATE TABLE pedido (id INT PRIMARY KEY);
    CREATE INDEX ix_fantasma ON tabela_inexistente (coluna);
    """
    result = _run(ddl)
    assert result.status == "PARTIAL"
    assert any("ix_fantasma" in e for e in result.errors)


# ─── 2. FK resolvida em 2 passes (ordem não importa) ─────────────────────────


def test_ddl_fk_declared_before_target_is_resolved(capture_snapshot):
    """FK cuja tabela-alvo é criada DEPOIS não pode mais ser perdida."""
    ddl = """
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT NOT NULL,
      CONSTRAINT fk_cliente FOREIGN KEY (cliente_id) REFERENCES cliente (id)
    );
    CREATE TABLE cliente (id INT PRIMARY KEY);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    assert len(snap.relationships) == 1
    rel = snap.relationships[0]
    assert rel.parent_entity == "cliente"
    assert rel.child_entity == "pedido"
    assert rel.child_columns == ["cliente_id"]
    assert rel.parent_columns == ["id"]


def test_ddl_inline_fk_before_target_is_resolved(capture_snapshot):
    ddl = """
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT REFERENCES cliente (id)
    );
    CREATE TABLE cliente (id INT PRIMARY KEY);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    assert len(snap.relationships) == 1
    assert snap.relationships[0].parent_entity == "cliente"


# ─── 3. FK órfã gera warning ─────────────────────────────────────────────────


def test_ddl_fk_to_unknown_table_warns(capture_snapshot):
    """Tabela-alvo não existe no DDL nem no catálogo → warning + PARTIAL, mas o
    relacionamento ainda é emitido (resolvido por nome no apply)."""
    ddl = """
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT,
      CONSTRAINT fk_c FOREIGN KEY (cliente_id) REFERENCES cliente_externo (id)
    );
    """
    result = _run(ddl)
    snap = capture_snapshot["snapshot"]
    # Relacionamento não é descartado.
    assert len(snap.relationships) == 1
    assert snap.relationships[0].parent_entity == "cliente_externo"
    # Aviso emitido + status PARTIAL (padrão DM1).
    assert result.status == "PARTIAL"
    assert any("cliente_externo" in e for e in result.errors)


def test_ddl_valid_fk_no_orphan_warning(capture_snapshot):
    """FK bem-formada com alvo presente → SUCCESS, sem avisos."""
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY);
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT,
      CONSTRAINT fk_c FOREIGN KEY (cliente_id) REFERENCES cliente (id)
    );
    """
    result = _run(ddl)
    assert result.status == "SUCCESS"
    assert result.errors == []


# ─── 4. parent_columns inferido da PK ────────────────────────────────────────


def test_ddl_fk_without_columns_infers_target_pk(capture_snapshot):
    """`REFERENCES cliente` (sem coluna) → assume a PK da tabela-alvo."""
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY, nome VARCHAR(50));
    CREATE TABLE pedido (
      id INT PRIMARY KEY,
      cliente_id INT,
      CONSTRAINT fk_c FOREIGN KEY (cliente_id) REFERENCES cliente
    );
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    rel = snap.relationships[0]
    assert rel.parent_entity == "cliente"
    assert rel.parent_columns == ["id"]  # inferido da PK de cliente


def test_ddl_fk_without_columns_composite_pk(capture_snapshot):
    """PK composta na tabela-alvo → todas as colunas da PK viram parent_columns."""
    ddl = """
    CREATE TABLE item (
      pedido_id INT,
      linha INT,
      PRIMARY KEY (pedido_id, linha)
    );
    CREATE TABLE detalhe (
      id INT PRIMARY KEY,
      pedido_id INT,
      linha INT,
      CONSTRAINT fk_item FOREIGN KEY (pedido_id, linha) REFERENCES item
    );
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    rel = next(r for r in snap.relationships if r.parent_entity == "item")
    assert sorted(rel.parent_columns) == ["linha", "pedido_id"]


# ─── 5. search_path multi-schema ─────────────────────────────────────────────


def test_ddl_multi_schema_search_path_default_is_first(capture_snapshot):
    """`SET search_path TO streaming, public` → tabelas não-qualificadas caem no
    PRIMEIRO schema (streaming), não em public."""
    ddl = """
    SET search_path TO streaming, public;
    CREATE TABLE conteudo (id INT PRIMARY KEY);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    ent = next(e for e in snap.entities if e.technical_name == "conteudo")
    assert ent.schema_name == "streaming"


def test_ddl_multi_schema_fk_resolves_across_list(capture_snapshot):
    """FK sem schema-hint para uma tabela que vive em OUTRO schema do
    search_path é resolvida percorrendo a lista."""
    ddl = """
    SET search_path TO app, ref;
    CREATE TABLE ref.pais (id INT PRIMARY KEY);
    CREATE TABLE cidade (
      id INT PRIMARY KEY,
      pais_id INT,
      CONSTRAINT fk_pais FOREIGN KEY (pais_id) REFERENCES pais (id)
    );
    """
    result = _run(ddl)
    snap = capture_snapshot["snapshot"]
    # cidade cai no 1º schema (app); pais foi qualificado como ref.pais.
    cidade = next(e for e in snap.entities if e.technical_name == "cidade")
    assert cidade.schema_name == "app"
    rel = snap.relationships[0]
    assert rel.parent_entity == "pais"
    assert rel.parent_schema == "ref"  # resolvido via search_path
    # FK bem resolvida (alvo existe) → sem aviso de órfã.
    assert result.status == "SUCCESS"


def test_ddl_search_path_ignores_dollar_user_token(capture_snapshot):
    """`SET search_path TO "$user", vendas` → ignora $user, default = vendas."""
    ddl = """
    SET search_path TO "$user", vendas;
    CREATE TABLE nota (id INT PRIMARY KEY);
    """
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    assert snap.entities[0].schema_name == "vendas"


# ─── Helper unitário: _ddl_search_path_schemas ───────────────────────────────


def test_search_path_helper_parses_list():
    """Documenta o contrato do helper: lista na ordem, sem $user, sem aspas."""
    import sqlglot

    (stmt,) = sqlglot.parse("SET search_path TO a, b, c", dialect="postgres")
    assert svc._ddl_search_path_schemas(stmt, "postgres") == ["a", "b", "c"]


def test_search_path_helper_non_search_path_returns_empty():
    import sqlglot

    (stmt,) = sqlglot.parse("SET work_mem = '64MB'", dialect="postgres")
    assert svc._ddl_search_path_schemas(stmt, "postgres") == []
