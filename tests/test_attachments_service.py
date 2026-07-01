"""Anexos (pedido do cliente #7) — validação, sanitização e caps do serviço.

Foca no que não depende de Volume/Delta reais: sanitização de nome, validação
de owner, e os guards de tamanho/arquivo-vazio do save_attachment (com Volume e
Delta mockados).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("databricks.sdk")

from fastapi import HTTPException

from nuclea_modeler.backend.attachments import service as svc


# ─── sanitização de nome de arquivo ─────────────────────────────────────────


def test_sanitize_filename_strips_path():
    assert svc._sanitize_filename("/etc/passwd") == "passwd"
    assert svc._sanitize_filename("..\\..\\win.ini") == "win.ini"


def test_sanitize_filename_replaces_bad_chars():
    out = svc._sanitize_filename("meu doc%estranho*.pdf")
    assert "%" not in out and "*" not in out
    assert out.endswith(".pdf")


def test_sanitize_filename_never_empty():
    assert svc._sanitize_filename("") == "arquivo"
    assert svc._sanitize_filename("///") == "arquivo"


# ─── validação de owner ─────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["entity", "schema", "diagram", "system"])
def test_validate_owner_accepts_known_kinds(kind):
    svc._validate_owner(kind, "ent-123_ABC")  # não levanta


def test_validate_owner_rejects_unknown_kind():
    with pytest.raises(HTTPException) as e:
        svc._validate_owner("banco", "ent-1")
    assert e.value.status_code == 400


def test_validate_owner_rejects_bad_id():
    with pytest.raises(HTTPException):
        svc._validate_owner("entity", "id com espaço/../x")


# ─── save_attachment guards ─────────────────────────────────────────────────


class _FakeSettings:
    catalog = "cat"
    schema_ = "sch"

    def fq_table(self, t):
        return f"cat.sch.{t}"


def test_save_attachment_rejects_empty(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _FakeSettings())
    with pytest.raises(HTTPException) as e:
        svc.save_attachment(
            object(), object(), owner_kind="entity", owner_id="ent-1",
            filename="x.pdf", content_type="application/pdf", data=b"",
            description=None, actor="a@x.com",
        )
    assert e.value.status_code == 400


def test_save_attachment_rejects_oversized(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _FakeSettings())
    big = b"x" * (svc.ATTACHMENT_MAX_BYTES + 1)
    with pytest.raises(HTTPException) as e:
        svc.save_attachment(
            object(), object(), owner_kind="entity", owner_id="ent-1",
            filename="x.bin", content_type=None, data=big,
            description=None, actor="a@x.com",
        )
    assert e.value.status_code == 413


def test_save_attachment_happy_path(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(svc.delta, "new_id", lambda p: f"{p}xyz")
    inserted = {}
    monkeypatch.setattr(svc.delta, "insert", lambda sql, table, row: inserted.update(row))

    class _Files:
        def __init__(self):
            self.uploaded = None

        def upload(self, path, contents, overwrite=False):
            self.uploaded = (path, overwrite)

    class _WS:
        files = _Files()

    ws = _WS()
    out = svc.save_attachment(
        ws, object(), owner_kind="entity", owner_id="ent-1",
        filename="../doc final.pdf", content_type="application/pdf",
        data=b"hello", description="nota", actor="a@x.com",
    )
    assert out.attachment_id == "att-xyz"
    assert out.original_filename == "doc final.pdf"
    assert out.file_size_bytes == 5
    # gravou no Volume sob o caminho esperado e inseriu metadados
    assert ws.files.uploaded[0].startswith("/Volumes/cat/sch/attachments/entity/ent-1/")
    assert inserted["owner_kind"] == "entity"
    assert inserted["created_by"] == "a@x.com"
