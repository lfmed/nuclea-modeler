"""Pydantic models para anexos (documentos em entidades/modelos)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Alvos possíveis de um anexo. "entity" = tabela; os demais = modelos de dados.
AttachmentOwnerKind = Literal["entity", "schema", "diagram", "system"]


class AttachmentOut(BaseModel):
    """Metadados completos de um anexo."""

    attachment_id: str
    owner_kind: AttachmentOwnerKind
    owner_id: str
    original_filename: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    description: str | None = None
    created_at: datetime
    created_by: str


class AttachmentListOut(BaseModel):
    """Item de listagem (mesmos campos — o objeto é leve)."""

    attachment_id: str
    owner_kind: AttachmentOwnerKind
    owner_id: str
    original_filename: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    description: str | None = None
    created_at: datetime
    created_by: str
