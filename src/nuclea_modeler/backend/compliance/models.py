"""Models do calendário de conformidade (rodada 8, item 3).

Um agendamento por sistema: periodicidade + próxima data. O app calcula a próxima
data ao registrar a execução. `next_due_date` é STRING ISO 'YYYY-MM-DD'.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Periodicidades suportadas (o cliente escolhe Mensal/Trimestral/Semestral/Anual).
Recurrence = Literal["MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"]


class ComplianceScheduleIn(BaseModel):
    """Payload de criar/editar um agendamento (manual)."""

    system_id: str = Field(min_length=1)
    recurrence: Recurrence
    next_due_date: str = Field(description="Próxima avaliação, ISO YYYY-MM-DD")
    notes: str | None = None


class ComplianceScheduleOut(BaseModel):
    calendar_id: str
    system_id: str
    system_name: str | None = None
    recurrence: Recurrence
    next_due_date: str
    last_executed_at: datetime | None = None
    last_executed_by: str | None = None
    notes: str | None = None
    # Derivados (calculados no router a partir de next_due_date vs. hoje):
    is_due: bool = False           # vence hoje ou já venceu
    days_until: int | None = None  # dias até vencer (negativo = vencida)
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class ComplianceImportRow(BaseModel):
    """Resultado por linha do import de planilha (1ª carga do calendário)."""

    ok: bool
    system: str
    recurrence: str | None = None
    next_due_date: str | None = None
    error: str | None = None


class ComplianceImportResult(BaseModel):
    total: int
    imported: int
    updated: int
    failed: int
    rows: list[ComplianceImportRow] = Field(default_factory=list)
