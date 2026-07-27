"""Pydantic models for Reverse Engineering (M2) — extractions and snapshots."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["LAKEBASE", "DDL_FILE", "EMBARCADERO", "ODBC", "REST", "UC"]
ExtractionStatus = Literal["RUNNING", "SUCCESS", "PARTIAL", "FAILED"]


class LakebaseExtractionIn(BaseModel):
    """Trigger an extraction from a Lakebase sandbox."""

    sandbox_id: str
    system_id: str
    schemas: list[str] = Field(default_factory=list, description="empty list = all visible schemas")
    object_kinds: list[Literal["TABLE", "VIEW"]] = Field(default_factory=lambda: ["TABLE", "VIEW"])
    open_ticket: bool = True


class UCExtractionIn(BaseModel):
    """Trigger an extraction from a Unity Catalog catalog.schema.

    Se `table_names` é vazio, descobre todas as tabelas do schema. Caso
    contrário, restringe ao subset informado (útil para schemas grandes
    onde só algumas tabelas interessam ao sistema modelado).
    """

    system_id: str
    catalog: str = Field(min_length=1, max_length=255)
    schema: str = Field(min_length=1, max_length=255)
    table_names: list[str] | None = None
    open_ticket: bool = True


class DDLImportIn(BaseModel):
    """Trigger an extraction from raw DDL text.

    Size cap: 5 MB. Mais do que isso indica dump-de-banco-inteiro que deveria
    vir via Lakebase round-trip, não import manual. Cap protege contra
    parser DoS (sqlglot é pure-Python — payloads patológicos podem causar
    loops longos).
    """

    system_id: str
    dialect: str = "ANSI"
    ddl_text: str = Field(min_length=1, max_length=5_000_000)
    open_ticket: bool = True


class EmbarcaderoImportIn(BaseModel):
    """Trigger an extraction from an Embarcadero ER/Studio .DM1 file.

    Size cap: 50 MB. Arquivos .DM1 são ASCII multi-seção (CSV interno) e
    podem ser maiores que .erx XML — cap conservador protege o parser
    contra DoS.
    """

    system_id: str
    dm1_text: str = Field(min_length=1, max_length=50_000_000)
    open_ticket: bool = True


class ExtractedAttribute(BaseModel):
    technical_name: str
    ordinal_position: int | None = None
    native_data_type: str | None = None
    is_nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool = False
    native_comment: str | None = None


class ExtractedIndexColumn(BaseModel):
    name: str
    direction: Literal["ASC", "DESC"] = "ASC"


class ExtractedIndex(BaseModel):
    index_name: str
    index_type: str = "BTREE"
    is_unique: bool = False
    columns: list[ExtractedIndexColumn] = Field(default_factory=list)
    native_comment: str | None = None
    # `include_columns` / `partial_where` só são preenchidos por fontes que
    # expõem esses metadados (ex.: DDL Postgres com `INCLUDE (...)` / `WHERE`).
    # Default vazio/None mantém o shape do DM1/UC (que não os informam). O apply
    # (`entities.indexes.apply_index_add`) já lê essas chaves do payload, então
    # basta o model_dump() carregá-las até a tabela `entity_indexes`.
    include_columns: list[str] = Field(default_factory=list)
    partial_where: str | None = None


class ExtractedEntity(BaseModel):
    schema_name: str
    technical_name: str
    entity_type: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "EXTERNAL"] = "TABLE"
    native_comment: str | None = None
    row_count_approx: int | None = None
    attributes: list[ExtractedAttribute] = Field(default_factory=list)
    indexes: list[ExtractedIndex] = Field(default_factory=list)


class ExtractedRelationship(BaseModel):
    """Um relacionamento (FK) extraído de uma fonte.

    Convenção de direção (alinhada com a tabela ``relationships``):
    - ``parent`` = tabela referenciada (lado PK / "um") → vira ``source_entity``.
    - ``child``  = tabela que segura a FK (lado "muitos")  → vira ``target_entity``.

    As colunas são guardadas por NOME (técnico). A resolução para
    ``entity_id``/``attribute_id`` acontece no apply do ticket, depois que as
    entities já foram materializadas.
    """

    parent_schema: str
    parent_entity: str
    parent_columns: list[str] = Field(default_factory=list)  # colunas referenciadas (PK)
    child_schema: str
    child_entity: str
    child_columns: list[str] = Field(default_factory=list)  # colunas FK locais
    rel_type: str = "1:N"
    constraint_name: str | None = None
    fk_update_rule: str | None = None
    fk_delete_rule: str | None = None


class ExtractionSnapshot(BaseModel):
    source_kind: SourceKind
    sandbox_id: str | None = None
    connection_id: str | None = None
    system_id: str
    captured_at: datetime
    schemas: list[str] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class ExtractionListOut(BaseModel):
    extraction_id: str
    source_kind: SourceKind
    system_id: str
    system_name: str | None = None
    status: ExtractionStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    objects_found: int | None = None
    objects_new: int | None = None
    objects_changed: int | None = None
    objects_removed: int | None = None
    ticket_id: str | None = None
    created_by: str


class ExtractionOut(ExtractionListOut):
    connection_id: str | None = None
    lakebase_sandbox_id: str | None = None
    requested_schemas: str | None = None
    requested_kinds: str | None = None
    error_summary: str | None = None
    snapshot: ExtractionSnapshot | None = None
    diff_summary: dict | None = None


class ExtractionResult(BaseModel):
    extraction_id: str
    status: ExtractionStatus
    objects_found: int
    objects_new: int
    objects_changed: int
    objects_removed: int
    duration_ms: int
    ticket_id: str | None = None
    summary_md: str
    errors: list[str] = Field(default_factory=list)
