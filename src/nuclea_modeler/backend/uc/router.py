"""Unity Catalog discovery HTTP endpoints.

Listagem read-only de catalogs / schemas / tables (+ colunas) usadas pelo
wizard de novo sistema para o user "navegar" no UC antes de disparar a
extração propriamente dita via /extractions/uc/run.

Por que usamos `Dependencies.Client` (SP do app) e não `UserClient` (OBO):
- O SP do app tem permissões consistentes via `app.yml` (resource UC). O
  fluxo OBO depende de o user ter recebido scope `catalog.metastore` no
  consent, o que nem sempre vale para usuários funcionais da Núclea.
- Lakebase já usa o mesmo padrão (ver `run_lakebase_extraction`).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..._metadata import api_prefix
from ..core import Dependencies

log = logging.getLogger(__name__)

router = APIRouter(prefix=f"{api_prefix}/uc", tags=["uc"])


# ---------------------------------------------------------------------------
# Pydantic models (apenas o subset que a UI consome — TableInfo é enorme).
# ---------------------------------------------------------------------------


class UCCatalogOut(BaseModel):
    """Catalog visível para o SP do app."""

    name: str
    comment: str | None = None
    catalog_type: str | None = Field(
        default=None,
        description="MANAGED_CATALOG, FOREIGN_CATALOG, SYSTEM_CATALOG, etc.",
    )
    owner: str | None = None


class UCSchemaOut(BaseModel):
    """Schema dentro de um catalog."""

    name: str
    full_name: str
    comment: str | None = None
    owner: str | None = None


class UCColumnOut(BaseModel):
    """Coluna de uma tabela UC. Subset do `ColumnInfo` do SDK."""

    name: str
    type_text: str | None = None
    type_name: str | None = None
    nullable: bool | None = None
    position: int | None = None
    comment: str | None = None
    partition_index: int | None = None


class UCTableOut(BaseModel):
    """Tabela UC com colunas opcionais.

    `entity_type` é nossa normalização (TABLE / VIEW / MATERIALIZED_VIEW /
    EXTERNAL) pra alinhar com `ExtractedEntity.entity_type` no resto do app.
    """

    name: str
    full_name: str
    schema_name: str
    catalog_name: str
    table_type: str | None = None
    entity_type: str = "TABLE"
    comment: str | None = None
    owner: str | None = None
    columns: list[UCColumnOut] = Field(default_factory=list)


def _map_table_type(table_type: str | None) -> str:
    """Mapeia `TableType` do SDK -> nosso `entity_type` (TABLE/VIEW/...)."""
    if not table_type:
        return "TABLE"
    t = table_type.upper()
    if t == "VIEW":
        return "VIEW"
    if t == "MATERIALIZED_VIEW":
        return "MATERIALIZED_VIEW"
    if t in ("EXTERNAL", "EXTERNAL_SHALLOW_CLONE", "FOREIGN"):
        return "EXTERNAL"
    # MANAGED, MANAGED_SHALLOW_CLONE, STREAMING_TABLE, METRIC_VIEW, etc.
    return "TABLE"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/catalogs",
    response_model=list[UCCatalogOut],
    operation_id="listUCCatalogs",
)
def list_catalogs(app_ws: Dependencies.Client) -> list[UCCatalogOut]:
    """Lista catalogs visíveis para o SP do app."""
    try:
        out: list[UCCatalogOut] = []
        for c in app_ws.catalogs.list():
            out.append(
                UCCatalogOut(
                    name=c.name or "",
                    comment=c.comment,
                    catalog_type=str(c.catalog_type.value) if c.catalog_type else None,
                    owner=c.owner,
                )
            )
        # Ordena alfabeticamente para UX consistente no wizard.
        out.sort(key=lambda x: x.name.lower())
        return out
    except Exception as exc:
        log.exception("uc.list_catalogs failed")
        raise HTTPException(500, f"Falha ao listar catalogs do UC: {exc}") from exc


@router.get(
    "/catalogs/{catalog}/schemas",
    response_model=list[UCSchemaOut],
    operation_id="listUCSchemas",
)
def list_schemas(catalog: str, app_ws: Dependencies.Client) -> list[UCSchemaOut]:
    """Lista schemas de um catalog."""
    if not catalog:
        raise HTTPException(400, "catalog é obrigatório")
    try:
        out: list[UCSchemaOut] = []
        for s in app_ws.schemas.list(catalog_name=catalog):
            out.append(
                UCSchemaOut(
                    name=s.name or "",
                    full_name=s.full_name or f"{catalog}.{s.name or ''}",
                    comment=s.comment,
                    owner=s.owner,
                )
            )
        out.sort(key=lambda x: x.name.lower())
        return out
    except Exception as exc:
        log.exception("uc.list_schemas failed catalog=%s", catalog)
        raise HTTPException(
            500, f"Falha ao listar schemas do catalog '{catalog}': {exc}"
        ) from exc


@router.get(
    "/catalogs/{catalog}/schemas/{schema}/tables",
    response_model=list[UCTableOut],
    operation_id="listUCTables",
)
def list_tables(
    catalog: str, schema: str, app_ws: Dependencies.Client
) -> list[UCTableOut]:
    """Lista tabelas + colunas de um schema.

    NOTE: `tables.list` no SDK usa `omit_columns` (default False -> traz
    colunas). Para ficar explícito passamos `omit_columns=False`.
    """
    if not catalog or not schema:
        raise HTTPException(400, "catalog e schema são obrigatórios")
    try:
        out: list[UCTableOut] = []
        for t in app_ws.tables.list(
            catalog_name=catalog,
            schema_name=schema,
            omit_columns=False,
        ):
            table_type_str = str(t.table_type.value) if t.table_type else None
            columns: list[UCColumnOut] = []
            for c in t.columns or []:
                columns.append(
                    UCColumnOut(
                        name=c.name or "",
                        type_text=c.type_text,
                        type_name=str(c.type_name.value) if c.type_name else None,
                        nullable=c.nullable,
                        position=c.position,
                        comment=c.comment,
                        partition_index=c.partition_index,
                    )
                )
            # Ordena colunas por position para reproduzir ordem física da tabela.
            columns.sort(key=lambda x: (x.position is None, x.position or 0))
            out.append(
                UCTableOut(
                    name=t.name or "",
                    full_name=t.full_name or f"{catalog}.{schema}.{t.name or ''}",
                    schema_name=t.schema_name or schema,
                    catalog_name=t.catalog_name or catalog,
                    table_type=table_type_str,
                    entity_type=_map_table_type(table_type_str),
                    comment=t.comment,
                    owner=t.owner,
                    columns=columns,
                )
            )
        out.sort(key=lambda x: x.name.lower())
        return out
    except Exception as exc:
        log.exception(
            "uc.list_tables failed catalog=%s schema=%s", catalog, schema
        )
        raise HTTPException(
            500,
            f"Falha ao listar tabelas de '{catalog}.{schema}': {exc}",
        ) from exc
