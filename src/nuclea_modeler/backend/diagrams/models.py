"""Pydantic models para Diagrams (M6) — padrão In/Out."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DiagramIn(BaseModel):
    system_id: str
    schema_id: str
    diagram_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_default: bool = False


class DiagramOut(BaseModel):
    diagram_id: str
    system_id: str
    schema_id: str
    diagram_name: str
    description: str | None = None
    is_default: bool
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    entity_count: int = 0


class DiagramListOut(BaseModel):
    diagram_id: str
    system_id: str
    schema_id: str
    diagram_name: str
    is_default: bool
    entity_count: int = 0


class DiagramMemberOut(BaseModel):
    """Uma entidade pertencente a um diagrama + posição salva (NULL = auto)."""

    entity_id: str
    schema_name: str | None = None
    technical_name: str | None = None
    logical_name: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class DiagramDetailOut(DiagramOut):
    """Diagrama + lista de membros (entities) com posição."""

    members: list[DiagramMemberOut] = []


class DiagramMemberIn(BaseModel):
    entity_id: str
    pos_x: float | None = None
    pos_y: float | None = None


class DiagramMembersIn(BaseModel):
    """Membership em lote — substitui ou adiciona entities ao diagrama."""

    members: list[DiagramMemberIn]


class DiagramLayoutIn(BaseModel):
    """Posições a salvar para membros já existentes do diagrama."""

    positions: list[DiagramMemberIn]
