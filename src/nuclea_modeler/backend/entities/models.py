"""Pydantic models for Entities, Attributes, Relationships — Módulo 3."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Criticality = Literal["HIGH", "MEDIUM", "LOW"]
EntityType = Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"]
RelType = Literal["1:1", "1:N", "N:M", "INHERIT"]
Cardinality = Literal["OPTIONAL", "MANDATORY"]
PendingOp = Literal["add", "change", "remove"]


# -------------------- Entities --------------------

class EntityIn(BaseModel):
    system_id: str
    schema_name: str = Field(min_length=1)
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    description_md: str | None = None
    domain: str | None = None
    business_owner: str | None = None
    technical_owner: str | None = None
    criticality: Criticality | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    entity_type: EntityType = "TABLE"
    native_comment: str | None = None
    row_count_approx: int | None = None
    is_shared: bool = False  # entity compartilhada: pode ser target cross-system


class EntityOut(BaseModel):
    entity_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    description_md: str | None = None
    domain: str | None = None
    business_owner: str | None = None
    technical_owner: str | None = None
    criticality: Criticality | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    entity_type: EntityType
    native_comment: str | None = None
    row_count_approx: int | None = None
    last_extracted_at: datetime | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    attributes_count: int | None = None
    is_shared: bool = False
    # Editorial overlay — só preenchido em endpoints que aplicam overlay
    # de sessão; reads "frias" deixam None.
    pending_op: PendingOp | None = None
    pending_ticket_id: str | None = None


class FlagBadge(BaseModel):
    """Resumo compacto de uma flag aplicada — usado nas listagens para
    exibir uma coluna de flags sem carregar todo o payload de EntityFlagOut.

    Só os campos que a UI precisa para renderizar a chip (cor + rótulo) e
    filtrar por flag. Mantido separado de FlagOut (flags/models.py) para não
    acoplar o módulo de listagens ao catálogo de flags e evitar import circular.
    """

    flag_id: str
    flag_key: str
    display_name: str
    color_hex: str | None = None
    category: str | None = None


class EntityListOut(BaseModel):
    entity_id: str
    system_id: str
    system_name: str | None = None
    schema_name: str
    technical_name: str
    logical_name: str | None = None
    entity_type: EntityType
    domain: str | None = None
    criticality: Criticality | None = None
    attributes_count: int | None = None
    updated_at: datetime
    is_shared: bool = False
    # Coluna de flags nas listagens (ponto 5.3 do plano). Preenchida só nos
    # endpoints paginados que fazem o join agregado; listas "frias" deixam [].
    flags: list[FlagBadge] = Field(default_factory=list)
    pending_op: PendingOp | None = None
    pending_ticket_id: str | None = None


class PaginatedEntities(BaseModel):
    """Paginated entity listing — preferred for systems with many tables."""

    items: list[EntityListOut]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    has_more: bool


# -------------------- Attributes --------------------

class AttributeIn(BaseModel):
    entity_id: str
    technical_name: str = Field(min_length=1)
    logical_name: str | None = None
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool = False
    description_md: str | None = None
    business_rule: str | None = None
    sample_value: str | None = None
    glossary_term_id: str | None = None
    native_comment: str | None = None


class AttributeOut(BaseModel):
    attribute_id: str
    entity_id: str
    technical_name: str
    logical_name: str | None = None
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool
    description_md: str | None = None
    business_rule: str | None = None
    sample_value: str | None = None
    glossary_term_id: str | None = None
    native_comment: str | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    pending_op: PendingOp | None = None


# -------------------- Indexes & Partitioning --------------------

IndexType = Literal[
    "BTREE", "HASH", "UNIQUE", "GIN", "BRIN", "GIST",
    "BITMAP", "CLUSTERED", "NONCLUSTERED",
    "Z-ORDER", "LIQUID",
]
ColumnDirection = Literal["ASC", "DESC"]
PartitionStrategy = Literal["RANGE", "LIST", "HASH", "LIQUID", "NONE"]


class IndexColumn(BaseModel):
    """Coluna de um índice — ordem na lista importa."""

    name: str = Field(min_length=1)
    direction: ColumnDirection = "ASC"


class EntityIndexIn(BaseModel):
    entity_id: str
    index_name: str = Field(min_length=1, max_length=128)
    index_type: IndexType = "BTREE"
    columns: list[IndexColumn] = Field(min_length=1)
    include_columns: list[str] = Field(default_factory=list)
    partial_where: str | None = None
    is_unique: bool = False
    description_md: str | None = None
    native_comment: str | None = None


class EntityIndexOut(BaseModel):
    index_id: str
    entity_id: str
    index_name: str
    index_type: IndexType
    columns: list[IndexColumn]
    include_columns: list[str] = Field(default_factory=list)
    partial_where: str | None = None
    is_unique: bool = False
    description_md: str | None = None
    native_comment: str | None = None
    origin: Literal["EXTRACTED", "MANUAL"] | None = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    pending_op: PendingOp | None = None


class EntityPartitioningIn(BaseModel):
    entity_id: str
    strategy: PartitionStrategy = "NONE"
    columns: list[str] = Field(default_factory=list)
    num_partitions: int | None = None
    bounds: dict[str, list] | None = None  # {part_name: [bound_low, bound_high]} ou {part_name: [valor1, valor2]}
    description_md: str | None = None


class EntityPartitioningOut(BaseModel):
    entity_id: str
    strategy: PartitionStrategy
    columns: list[str] = Field(default_factory=list)
    num_partitions: int | None = None
    bounds: dict[str, list] | None = None
    description_md: str | None = None
    origin: Literal["EXTRACTED", "MANUAL"] | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
    pending_op: PendingOp | None = None


# -------------------- Global listings (visão de sistema) --------------------
# Visões globais de atributos e índices (ponto 5.2 do plano). Diferente das
# listagens por-entity, estas cruzam TODAS as entidades de um sistema/catálogo
# e trazem o contexto da entity-host (nome técnico, schema, sistema) para que a
# tabela seja legível sem navegar até cada entidade. Definidas aqui no fim do
# arquivo porque dependem de IndexType/IndexColumn declarados acima.


class AttributeListOut(BaseModel):
    """Linha da visão global de atributos — atributo + contexto da entity."""

    attribute_id: str
    entity_id: str
    entity_technical_name: str | None = None
    entity_logical_name: str | None = None
    schema_name: str | None = None
    system_id: str | None = None
    system_name: str | None = None
    technical_name: str
    logical_name: str | None = None
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    is_primary_key: bool = False
    updated_at: datetime | None = None
    flags: list[FlagBadge] = Field(default_factory=list)


class PaginatedAttributes(BaseModel):
    items: list[AttributeListOut]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    has_more: bool


class IndexListOut(BaseModel):
    """Linha da visão global de índices — índice + contexto da entity."""

    index_id: str
    entity_id: str
    entity_technical_name: str | None = None
    schema_name: str | None = None
    system_id: str | None = None
    system_name: str | None = None
    index_name: str
    index_type: IndexType
    columns: list[IndexColumn] = Field(default_factory=list)
    is_unique: bool = False
    origin: Literal["EXTRACTED", "MANUAL"] | None = None
    updated_at: datetime | None = None


class PaginatedIndexes(BaseModel):
    items: list[IndexListOut]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    has_more: bool
