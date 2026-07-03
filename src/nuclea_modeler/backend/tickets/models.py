"""Pydantic models for Reconciliation Tickets."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TicketStatus = Literal["OPEN", "APPROVED", "APPLIED", "REJECTED"]
TicketSource = Literal[
    "REVERSE_ENG", "DDL_IMPORT", "LAKEBASE_ROUNDTRIP", "MANUAL", "SYSTEM_DELETE"
]


class DiffEntity(BaseModel):
    """One entity change inside the diff."""

    op: Literal["add", "remove", "change"]
    schema_name: str
    technical_name: str
    entity_type: str = "TABLE"
    # When op=add: full payload to materialize
    payload: dict[str, Any] | None = None
    # When op=change: list of field-level changes
    field_changes: list[dict[str, Any]] | None = None
    # When op=add: list of attributes (columns) to create with the entity
    attributes: list[dict[str, Any]] | None = None
    # When op=add: list of indexes to create with the entity (from reverse eng)
    indexes: list[dict[str, Any]] | None = None


class TicketDiff(BaseModel):
    """Structured diff payload — what the ticket asks to change."""

    entities: list[DiffEntity] = Field(default_factory=list)
    # Counters (denormalized on the ticket row for quick listings)
    additions: int = 0
    removals: int = 0
    changes: int = 0


class TicketIn(BaseModel):
    """Payload to open a ticket manually (eng. reversa abre internamente)."""

    title: str
    system_id: str
    source_type: TicketSource = "MANUAL"
    extraction_id: str | None = None
    summary_md: str | None = None
    diff: TicketDiff


class TicketListOut(BaseModel):
    ticket_id: str
    title: str
    system_id: str
    system_name: str | None = None
    source_type: TicketSource
    status: TicketStatus
    additions_count: int
    removals_count: int
    changes_count: int
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    applied_at: datetime | None = None


class TicketOut(BaseModel):
    ticket_id: str
    title: str
    system_id: str
    system_name: str | None = None
    extraction_id: str | None = None
    source_type: TicketSource
    status: TicketStatus
    summary_md: str | None = None
    diff: TicketDiff
    additions_count: int
    removals_count: int
    changes_count: int
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    applied_at: datetime | None = None
    applied_by: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    target_version_id: str | None = None


class TicketApprove(BaseModel):
    note: str | None = None


class TicketReject(BaseModel):
    reason: str = Field(min_length=1)


class TicketApplyResult(BaseModel):
    ticket_id: str
    status: TicketStatus
    applied_entities: int
    applied_attributes: int
    reversed_items: int = 0  # quantas decisões "reverse" foram executadas com sucesso
    ignored_items: int = 0   # quantas decisões "ignore" foram pulares
    errors: list[str] = Field(default_factory=list)


# Decisão por field dentro de um op=change. `field` é o mesmo string do
# field_change ("attribute_remove:Teste", "logical_name", etc.).
class FieldDecision(BaseModel):
    field: str
    action: Literal["apply", "ignore", "reverse"] = "apply"


# Decisão por entity. Para op=add/remove a action aplica ao item inteiro.
# Para op=change, action é fallback e field_decisions detalha por field.
class EntityDecision(BaseModel):
    schema_name: str
    technical_name: str
    op: Literal["add", "remove", "change"]
    action: Literal["apply", "ignore", "reverse"] = "apply"
    field_decisions: list[FieldDecision] = Field(default_factory=list)


class TicketApplyIn(BaseModel):
    # Se None ou vazio, comporta-se como antes (apply tudo seguindo a fonte).
    decisions: list[EntityDecision] | None = None
    # Necessário quando alguma decisão tem action="reverse" — sandbox onde
    # rodar os DDLs propagados (em geral o mesmo da extração que gerou o ticket).
    reverse_sandbox_id: str | None = None


BatchAction = Literal["approve", "reject", "apply", "approve_and_apply"]


class BatchTicketIn(BaseModel):
    """Ação em lote sobre vários tickets de uma vez.

    `approve_and_apply` resolve o atrito do fluxo manual: aprova e materializa
    numa tacada só (exige papel de applier). `approve`/`apply`/`reject` espelham
    as ações unitárias mas aplicadas a N tickets.
    """

    ticket_ids: list[str] = Field(min_length=1)
    action: BatchAction
    note: str | None = None  # usado em approve / approve_and_apply
    reason: str | None = None  # usado em reject (obrigatório p/ reject)


class BatchTicketItemResult(BaseModel):
    ticket_id: str
    ok: bool
    status: TicketStatus | None = None
    applied_entities: int = 0
    applied_attributes: int = 0
    error: str | None = None


class BatchTicketResult(BaseModel):
    action: BatchAction
    total: int
    succeeded: int
    failed: int
    results: list[BatchTicketItemResult] = Field(default_factory=list)


class SessionStateOut(BaseModel):
    """Estado da sessão editorial OPEN do user atual para um sistema.

    Retornado por GET /sessions/current. Permite frontend mostrar barra de
    "rascunho com N mudanças pendentes" e botão revisar/aprovar.
    """

    ticket_id: str
    system_id: str
    additions: int = 0
    changes: int = 0
    removals: int = 0
    entities_added: list[dict[str, Any]] = Field(default_factory=list)
    entities_changed: list[dict[str, Any]] = Field(default_factory=list)
    entities_removed: list[dict[str, Any]] = Field(default_factory=list)
