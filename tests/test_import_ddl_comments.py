"""Import DDL: captura de comentários (item 2) e aviso de falha silenciosa (item 8).

- Comentários: o parser passava `native_comment=None` fixo. Agora captura
  comentário inline de coluna, comentário de tabela e `COMMENT ON TABLE/COLUMN`.
- Falha silenciosa: DDL sem nenhum CREATE TABLE/VIEW reconhecido devolvia
  SUCCESS com 0 objetos. Agora devolve FAILED com mensagem acionável — e SEM
  chamar o diff (um snapshot vazio marcaria tudo como removido → ticket destrutivo).
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from nuclea_modeler.backend.extractions import service as svc  # noqa: E402


@pytest.fixture
def capture_snapshot(monkeypatch):
    """Intercepta o snapshot montado pelo run_ddl_import (só chamado quando há objetos)."""
    captured = {}

    def fake_compute_diff(sql, system_id, snapshot):
        captured["snapshot"] = snapshot
        return (
            object(),
            {"found": len(snapshot.entities), "new": len(snapshot.entities),
             "changed": 0, "removed": 0, "relationships": len(snapshot.relationships)},
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


# ─── Item 2: comentários ────────────────────────────────────────────────────


def test_ddl_inline_column_comment(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (
      id INT PRIMARY KEY,
      nome VARCHAR(100) COMMENT 'nome completo do cliente'
    );
    """
    _run(ddl, dialect="MYSQL")
    snap = capture_snapshot["snapshot"]
    nome = next(a for a in snap.entities[0].attributes if a.technical_name == "nome")
    assert nome.native_comment == "nome completo do cliente"


def test_ddl_table_comment(capture_snapshot):
    ddl = "CREATE TABLE cliente (id INT PRIMARY KEY) COMMENT='cadastro de clientes';"
    _run(ddl, dialect="MYSQL")
    snap = capture_snapshot["snapshot"]
    assert snap.entities[0].native_comment == "cadastro de clientes"


def test_ddl_comment_on_table_and_column(capture_snapshot):
    ddl = """
    CREATE TABLE cliente (id INT PRIMARY KEY, email VARCHAR(200));
    COMMENT ON TABLE cliente IS 'cadastro de clientes';
    COMMENT ON COLUMN cliente.email IS 'email de contato';
    """
    _run(ddl, dialect="POSTGRES")
    snap = capture_snapshot["snapshot"]
    ent = snap.entities[0]
    assert ent.native_comment == "cadastro de clientes"
    email = next(a for a in ent.attributes if a.technical_name == "email")
    assert email.native_comment == "email de contato"


def test_ddl_no_comment_stays_none(capture_snapshot):
    ddl = "CREATE TABLE t (id INT PRIMARY KEY, x VARCHAR(10));"
    _run(ddl)
    snap = capture_snapshot["snapshot"]
    assert snap.entities[0].native_comment is None
    assert all(a.native_comment is None for a in snap.entities[0].attributes)


# ─── Item 8: falha silenciosa ───────────────────────────────────────────────


def test_ddl_no_objects_returns_failed(capture_snapshot):
    """DDL sem CREATE TABLE/VIEW → FAILED, sem ticket, sem chamar o diff."""
    result = _run("SELECT 1;")
    assert result.status == "FAILED"
    assert result.ticket_id is None
    assert result.objects_found == 0
    assert "dialeto" in result.summary_md.lower()
    # diff NÃO deve ter sido chamado (guard retorna antes)
    assert "snapshot" not in capture_snapshot


def test_ddl_empty_text_returns_failed(capture_snapshot):
    result = _run("   ")
    assert result.status == "FAILED"
    assert result.ticket_id is None
