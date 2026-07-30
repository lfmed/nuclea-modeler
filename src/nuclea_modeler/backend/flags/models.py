"""Pydantic models for the Flagging module (Módulo 5)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FlagCategory = Literal["LGPD", "USE", "QUALITY", "CUSTOM"]


# -------------------- Flag catalog --------------------

class FlagOut(BaseModel):
    flag_id: str
    flag_key: str
    category: FlagCategory
    display_name: str
    description: str | None = None
    color_hex: str | None = None
    requires_justification: bool = False
    is_system: bool = False
    is_active: bool = True
    uc_tag_key: str | None = None


class FlagIn(BaseModel):
    """Payload for creating a CUSTOM flag (system flags are seeded via SQL)."""

    flag_key: str = Field(min_length=1, max_length=120)
    category: FlagCategory = "CUSTOM"
    display_name: str = Field(min_length=1)
    description: str | None = None
    color_hex: str | None = Field(default="#6C757D")
    requires_justification: bool = False


class FlagPatch(BaseModel):
    """Patch payload — used to toggle is_active or update color/description."""

    is_active: bool | None = None
    display_name: str | None = None
    description: str | None = None
    color_hex: str | None = None
    requires_justification: bool | None = None


# -------------------- Entity flags --------------------

class EntityFlagApplyIn(BaseModel):
    flag_id: str
    justification: str | None = None


class EntityFlagOut(BaseModel):
    entity_flag_id: str
    entity_id: str
    flag_id: str
    flag: FlagOut
    justification: str | None = None
    applied_at: datetime
    applied_by: str
    applied_in_version: str | None = None
    is_propagated: bool = False


# -------------------- Attribute flags --------------------

class AttributeFlagApplyIn(BaseModel):
    flag_id: str
    justification: str | None = None


class AttributeFlagOut(BaseModel):
    attribute_flag_id: str
    attribute_id: str
    flag_id: str
    flag: FlagOut
    justification: str | None = None
    applied_at: datetime
    applied_by: str
    applied_in_version: str | None = None


# -------------------- Relationship flags (Bloco 5) --------------------

class RelationshipFlagApplyIn(BaseModel):
    flag_id: str
    justification: str | None = None


class RelationshipFlagOut(BaseModel):
    relationship_flag_id: str
    relationship_id: str
    flag_id: str
    flag: FlagOut
    justification: str | None = None
    applied_at: datetime
    applied_by: str
    applied_in_version: str | None = None


# -------------------- Batch flag operations (Blocos 3 + 6) --------------------
#
# Motivação: o fluxo single-id (uma flag por alvo por request) exige ~250 cliques
# para o cenário real do cliente (50 atributos × 5 flags). Estes payloads permitem
# aplicar/remover VÁRIAS flags em VÁRIOS alvos numa única chamada, com erro parcial
# por item (padrão BatchTicketResult: total/succeeded/failed/results[]).

class BatchFlagSpec(BaseModel):
    """Uma flag a aplicar em lote, com justificativa opcional.

    A justificativa vale para todos os alvos do lote (a UI coleta uma justificativa
    por flag quando `requires_justification`). Quando exigida e vazia, cada par
    (alvo, flag) falha individualmente — o lote não aborta.
    """

    flag_id: str
    justification: str | None = None


class BatchFlagApplyIn(BaseModel):
    """Aplica N flags a N alvos (entidades ou atributos) numa única chamada.

    O resultado é o produto cartesiano `target_ids × flags`: cada par vira um item
    em `results`. Idempotente — reaplicar uma flag já existente conta como sucesso.
    """

    target_ids: list[str] = Field(min_length=1)
    flags: list[BatchFlagSpec] = Field(min_length=1)


class BatchFlagRemoveIn(BaseModel):
    """Remove N flags de N alvos numa única chamada.

    A remoção é por `flag_id` (não pelo id da linha aplicada), porque o lote opera
    sobre muitos alvos distintos. Idempotente — remover uma flag ausente conta como
    sucesso (nada a fazer).
    """

    target_ids: list[str] = Field(min_length=1)
    flag_ids: list[str] = Field(min_length=1)


class BatchFlagItemResult(BaseModel):
    """Resultado de um par (alvo, flag). `applied_flag_id` traz o id da linha
    (entity_flag_id / attribute_flag_id) quando a operação foi de aplicação."""

    target_id: str
    flag_id: str
    ok: bool
    applied_flag_id: str | None = None
    error: str | None = None


class BatchFlagResult(BaseModel):
    action: Literal["apply", "remove"]
    total: int
    succeeded: int
    failed: int
    results: list[BatchFlagItemResult] = Field(default_factory=list)
