"""Round 6 — pt 15 (COMMENT ON → descrição) + pt 21 (CHECK constraint).

Valida com os ARQUIVOS DO CLIENTE (`tests/fixtures/round6/programa_social*.sql`,
enviados na pasta ncleamodelerevoluo) + DDLs sintéticos:

- pt 15: `COMMENT ON TABLE/COLUMN … IS '…'` (e comentário inline) passa a popular
  `description_md` da coluna, além de `native_comment` — importa o descritivo do
  DDL para o modelo.
- pt 21: `CHECK (…)` de coluna E de tabela (`CONSTRAINT ck CHECK (col IN (0,1))`)
  é capturado em `check_constraint` e re-emitido no export de DDL.

Espelha `test_import_ddl_comments.py`: mocka o diff/persist/ticket e inspeciona o
snapshot que `run_ddl_import` monta a partir do parse sqlglot.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.ddl.generators import GENERATORS  # noqa: E402
from nuclea_modeler.backend.ddl.models import DDLExportRequest  # noqa: E402
from nuclea_modeler.backend.extractions import service as svc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "round6"


@pytest.fixture
def capture_snapshot(monkeypatch):
    captured = {}

    def fake_compute_diff(sql, system_id, snapshot):
        captured["snapshot"] = snapshot
        return (object(), {"found": len(snapshot.entities), "new": len(snapshot.entities),
                           "changed": 0, "removed": 0, "relationships": 0})

    monkeypatch.setattr(svc, "compute_diff_against_catalog", fake_compute_diff)
    monkeypatch.setattr(svc, "persist_extraction", lambda *a, **k: "ext-test")
    monkeypatch.setattr(svc, "open_ticket", lambda *a, **k: "tk-test")
    return captured


def _run(ddl: str, dialect: str = "POSTGRES"):
    return svc.run_ddl_import(
        object(), system_id="sys-1", dialect=dialect, ddl_text=ddl,
        actor="tester@x.com", open_ticket_on_diff=True,
    )


def _entity(snap, name):
    return next(e for e in snap.entities if e.technical_name.lower() == name.lower())


def _attr(ent, name):
    return next(a for a in ent.attributes if a.technical_name.lower() == name.lower())


# ─── pt 15: COMMENT ON → description_md ───────────────────────────────────────


def test_comment_on_column_becomes_description(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY, email VARCHAR(200));
    COMMENT ON TABLE cliente IS 'Cadastro de clientes';
    COMMENT ON COLUMN cliente.email IS 'Email de contato';
    """
    _run(ddl, dialect="POSTGRES")
    ent = _entity(capture_snapshot["snapshot"], "cliente")
    email = _attr(ent, "email")
    # pt 15: descrição de negócio importada do COMMENT ON (além do native_comment).
    assert email.description_md == "Email de contato"
    assert email.native_comment == "Email de contato"
    # Tabela: COMMENT ON TABLE → native_comment (o apply faz fallback p/ description_md).
    assert ent.native_comment == "Cadastro de clientes"


def test_client_file_postgres_descriptions(capture_snapshot):
    """Arquivo REAL do cliente: descrições de COMMENT ON chegam em description_md."""
    ddl = (FIXTURES / "programa_social.sql").read_text(encoding="utf-8")
    _run(ddl, dialect="POSTGRES")
    snap = capture_snapshot["snapshot"]
    pessoa = _entity(snap, "pessoa")
    assert pessoa.native_comment and "programas sociais" in pessoa.native_comment.lower()
    nome = _attr(pessoa, "nome_completo")
    # a descrição do cliente traz "… | CLASSIFICACAO=LGPD_IDENTIFICAVEL" (o token
    # de flag é tratado no pt 22; aqui basta a descrição ter sido importada).
    assert nome.description_md and "nome completo da pessoa" in nome.description_md.lower()


# ─── pt 21: CHECK constraint (coluna + tabela) ────────────────────────────────


def test_check_constraint_column_and_table_level(capture_snapshot):
    ddl = """
    CREATE TABLE conta (
      id INT PRIMARY KEY,
      situacao VARCHAR(10) CHECK (situacao IN ('A','I')),
      saldo INT,
      CONSTRAINT ck_saldo CHECK (saldo >= 0)
    );
    """
    _run(ddl, dialect="POSTGRES")
    ent = _entity(capture_snapshot["snapshot"], "conta")
    # CHECK de coluna (inline)
    situacao = _attr(ent, "situacao")
    assert situacao.check_constraint and "situacao" in situacao.check_constraint.lower()
    assert "in" in situacao.check_constraint.lower()
    # CHECK de tabela referenciando UMA coluna → associado a essa coluna
    saldo = _attr(ent, "saldo")
    assert saldo.check_constraint and ">=" in saldo.check_constraint


def test_no_check_stays_none(capture_snapshot):
    _run("CREATE TABLE t (id INT PRIMARY KEY, x VARCHAR(10));", dialect="POSTGRES")
    ent = _entity(capture_snapshot["snapshot"], "t")
    assert all(a.check_constraint is None for a in ent.attributes)


# ─── DEFAULT no import de DDL COLADO (v1.0050 — achado pelo smoke pós-deploy) ──
# O caminho de import via texto DDL nunca extraía o DEFAULT (só o Lakebase o
# fazia); o valor sumia e o fix de aspas do export (v1.0048) nunca disparava.
# Exercita o round-trip DDL→parse (não lista Python pronta) pra o CI travar a
# regressão que só aparecia no app deployado.


def test_default_value_captured_from_pasted_ddl(capture_snapshot):
    ddl = """
    CREATE TABLE conta (
      id INT PRIMARY KEY,
      situacao VARCHAR(20) DEFAULT 'ativo',
      saldo INT DEFAULT 0,
      criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    _run(ddl, dialect="POSTGRES")
    ent = _entity(capture_snapshot["snapshot"], "conta")
    # string → vem quotado do sqlglot ('ativo'); número → cru; keyword → cru.
    assert _attr(ent, "situacao").default_value == "'ativo'"
    assert _attr(ent, "saldo").default_value == "0"
    assert "CURRENT_TIMESTAMP" in (_attr(ent, "criado_em").default_value or "")
    # coluna sem DEFAULT continua None
    assert _attr(ent, "id").default_value is None


def test_default_roundtrips_through_export(capture_snapshot):
    """DEFAULT parseado de DDL colado deve re-emergir quotado no export DDL."""
    _run("CREATE TABLE t (id INT PRIMARY KEY, s VARCHAR(20) DEFAULT 'ativo');",
         dialect="POSTGRES")
    ent = _entity(capture_snapshot["snapshot"], "t")
    s = _attr(ent, "s")
    # simula o dict que o export recebe (leitura do catálogo) e confirma o render
    attrs = [
        {"technical_name": "id", "ordinal_position": 1, "native_data_type": "int",
         "is_primary_key": True, "is_nullable": False, "default_value": None},
        {"technical_name": "s", "ordinal_position": 2, "native_data_type": "varchar(20)",
         "is_primary_key": False, "is_nullable": True, "default_value": s.default_value},
    ]
    entity = {"schema_name": "public", "technical_name": "t", "entity_type": "TABLE",
              "description_md": None, "native_comment": None}
    ddl_out = GENERATORS["POSTGRES"](entity, attrs, DDLExportRequest(system_id="s", dialect="POSTGRES"))
    assert "DEFAULT 'ativo'" in ddl_out


# ─── pt 21: CHECK re-emitido no export de DDL ─────────────────────────────────


def test_generator_emits_check():
    entity = {"schema_name": "public", "technical_name": "conta",
              "entity_type": "TABLE", "description_md": None, "native_comment": None}
    attrs = [
        {"technical_name": "id", "ordinal_position": 1, "native_data_type": "int",
         "is_primary_key": True, "is_nullable": False, "default_value": None,
         "check_constraint": None},
        {"technical_name": "situacao", "ordinal_position": 2, "native_data_type": "varchar(10)",
         "is_primary_key": False, "is_nullable": True, "default_value": None,
         "check_constraint": "situacao IN ('A','I')"},
    ]
    ddl = GENERATORS["POSTGRES"](entity, attrs, DDLExportRequest(system_id="s", dialect="POSTGRES"))
    assert "CHECK (situacao IN ('A','I'))" in ddl
