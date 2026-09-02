"""Diagram (M4 DER) — view models combining entities, attributes, relationships, layout."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PendingOp = Literal["add", "change", "remove"]


class DiagramAttribute(BaseModel):
    attribute_id: str
    technical_name: str
    logical_name: str | None = None
    native_data_type: str | None = None
    is_primary_key: bool = False
    is_nullable: bool | None = None
    ordinal_position: int | None = None
    has_lgpd_flag: bool = False
    # F9: true se a coluna aparece em pelo menos um índice (não-PK)
    is_indexed: bool = False
    # Descrição: campo markdown/texto da coluna (p/ exibir no tooltip do DER)
    description_md: str | None = None
    # Comentário nativo: extraído do DDL (COMMENT ON COLUMN no Postgres, etc.)
    native_comment: str | None = None
    # Regra de negócio: validações/constraints não-DDL aplicadas à coluna
    business_rule: str | None = None
    # Editorial overlay — set quando o atributo tem mudança pendente na
    # sessão atual do usuário. NÃO é estado committed.
    pending_op: PendingOp | None = None


class DiagramIndexSummary(BaseModel):
    """Resumo compacto do índice pra mostrar inline no node do DER."""

    index_name: str
    index_type: str
    is_unique: bool = False
    columns: list[str] = Field(default_factory=list)


class DiagramEntity(BaseModel):
    entity_id: str
    system_id: str
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    entity_type: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"] = "TABLE"
    domain: str | None = None
    criticality: str | None = None
    attributes: list[DiagramAttribute] = Field(default_factory=list)
    has_lgpd_flag: bool = False  # propagated from columns or applied at entity level
    # Descrição: campo markdown/texto da tabela (p/ exibir no tooltip do DER)
    description_md: str | None = None
    # Comentário nativo: extraído do DDL (COMMENT ON TABLE no Postgres, etc.)
    native_comment: str | None = None
    # Storage badges no DER — agregados a partir de entity_indexes /
    # entity_partitioning. Mantemos compactos (só contagem + estratégia)
    # pra não inflar o payload do diagrama.
    indexes_count: int = 0
    partition_strategy: Literal["RANGE", "LIST", "HASH", "LIQUID", "NONE"] | None = None
    # F9: índices resumidos pra renderizar inline (max 5 por node — se tiver
    # mais, mostra "(+N)" e dirige pro detail da entity).
    indexes: list[DiagramIndexSummary] = Field(default_factory=list)
    partition_columns: list[str] = Field(default_factory=list)
    # Editorial overlay — preenchido quando há ticket OPEN do user com
    # mudança pendente. Frontend renderiza com badge/opacidade.
    pending_op: PendingOp | None = None
    pending_ticket_id: str | None = None


class DiagramRelationship(BaseModel):
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    rel_type: str | None = None
    source_cardinality: str | None = None
    target_cardinality: str | None = None
    source_attrs: list[str] = Field(default_factory=list)
    target_attrs: list[str] = Field(default_factory=list)
    description: str | None = None
    origin: str | None = None


class NodePosition(BaseModel):
    x: float
    y: float


class DiagramView(BaseModel):
    system_id: str
    system_name: str | None = None
    entities: list[DiagramEntity]
    relationships: list[DiagramRelationship]
    layout: dict[str, NodePosition] = Field(default_factory=dict)
    layout_name: str = "default"


class LayoutSaveIn(BaseModel):
    layout_name: str = "default"
    positions: dict[str, NodePosition]


class LayoutOut(BaseModel):
    layout_id: str
    system_id: str
    layout_name: str
    positions: dict[str, NodePosition]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


# ─── Source validation ──────────────────────────────────────────────────────

class SourceCheckResult(BaseModel):
    entity_id: str
    schema_name: str
    technical_name: str
    exists_in_source: bool
    source_kind: Literal["UC_DELTA", "LAKEBASE", "UNKNOWN"] = "UNKNOWN"
    source_catalog: str | None = None
    columns_in_source: int | None = None
    columns_in_catalog: int = 0
    missing_in_source: list[str] = Field(default_factory=list)
    extra_in_source: list[str] = Field(default_factory=list)
    error: str | None = None


class SourceValidationOut(BaseModel):
    system_id: str
    system_name: str | None = None
    source_kind: str
    target_catalog: str | None = None
    results: list[SourceCheckResult]
    total_entities: int
    found_count: int
    missing_count: int


class QuickEntityIn(BaseModel):
    """Atalho para criar uma entidade diretamente do canvas DER."""

    system_id: str
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    entity_type: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"] = "TABLE"
    domain: str | None = None
    # round 6 pt 16: descrição + flags já no ato da criação manual. As flags vão
    # no ticket e são aplicadas na aprovação (modelo editorial). Cada dict de
    # `initial_attributes` também aceita "description_md" e "flag_keys": [ ].
    description_md: str | None = None
    flag_keys: list[str] = Field(default_factory=list)
    initial_attributes: list[dict] = Field(default_factory=list)
