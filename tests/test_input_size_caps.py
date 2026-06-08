"""Tests para size caps nos endpoints de upload de arquivo.

Cap previne DoS via payloads gigantes que travariam o parser. Documentado
em SECURITY.md e nos docstrings de DDLImportIn / EmbarcaderoImportIn.
"""
from __future__ import annotations

import pytest

pydantic = pytest.importorskip("pydantic")

from pydantic import ValidationError

from nuclea_modeler.backend.extractions.models import (
    DDLImportIn,
    EmbarcaderoImportIn,
    LakebaseExtractionIn,
)


def test_ddl_import_accepts_small_payload():
    payload = DDLImportIn(
        system_id="sys-1",
        ddl_text="CREATE TABLE x (id INT);",
        dialect="POSTGRES",
    )
    assert payload.ddl_text.startswith("CREATE TABLE")


def test_ddl_import_accepts_payload_at_limit():
    """5 MB exato deve passar."""
    huge = "a" * 5_000_000
    payload = DDLImportIn(system_id="sys-1", ddl_text=huge)
    assert len(payload.ddl_text) == 5_000_000


def test_ddl_import_rejects_over_limit():
    """5 MB + 1 byte deve falhar."""
    huge = "a" * 5_000_001
    with pytest.raises(ValidationError) as exc_info:
        DDLImportIn(system_id="sys-1", ddl_text=huge)
    # Pydantic mensagem inclui max_length
    assert "max_length" in str(exc_info.value).lower() or "5000000" in str(exc_info.value)


def test_ddl_import_rejects_empty():
    """min_length=1: zero bytes não passa."""
    with pytest.raises(ValidationError):
        DDLImportIn(system_id="sys-1", ddl_text="")


def test_embarcadero_accepts_small_dm1():
    payload = EmbarcaderoImportIn(
        system_id="sys-1",
        dm1_text="Entity\nDiagramId,ModelId,EntityId\n1,1,1\n",
    )
    assert "Entity" in payload.dm1_text


def test_embarcadero_rejects_over_50mb():
    """Cap em .DM1 é 50 MB (formato ASCII pode ficar maior que .erx XML)."""
    huge = "x" * 50_000_001
    with pytest.raises(ValidationError):
        EmbarcaderoImportIn(system_id="sys-1", dm1_text=huge)


def test_lakebase_no_text_field_to_cap():
    """LakebaseExtractionIn não tem field de texto bruto — só metadados.
    Sanity: garantir que payload típico passa sem ValidationError."""
    payload = LakebaseExtractionIn(
        sandbox_id="sb-1",
        system_id="sys-1",
        schemas=["public", "comum"],
    )
    assert payload.sandbox_id == "sb-1"
