from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import APIRouter, FastAPI

from ..._metadata import api_prefix, app_name, dist_dir
from ._base import LifespanDependency
from ._config import logger

# --- Lifespan ---


@asynccontextmanager
async def _chain_dep_lifespans(
    deps: list[LifespanDependency],
    app: FastAPI,
) -> AsyncIterator[None]:
    """Chain multiple dependency lifespans into a single nested context manager."""
    if not deps:
        yield
        return

    head, *tail = deps

    async with head.lifespan(app):
        async with _chain_dep_lifespans(tail, app):
            yield


# --- Factory ---


def create_app(
    *,
    routers: list[APIRouter] | None = None,
) -> FastAPI:
    """Create and configure a FastAPI application.

    Dependencies are discovered automatically from the Dependency registry.
    All concrete Dependency subclasses that have been imported are instantiated
    and their lifespans are chained in import order.

    Args:
        routers: List of APIRouter instances to include in the app.

    Returns:
        Configured FastAPI application instance.
    """
    all_deps: list[LifespanDependency] = []
    for dep in LifespanDependency._registry:
        try:
            all_deps.append(dep())
        except Exception as e:
            logger.error(f"Failed to instantiate dependency {dep.__name__}: {e}")
            raise e

    @asynccontextmanager
    async def _composed_lifespan(app: FastAPI):
        async with _chain_dep_lifespans(all_deps, app):
            _maybe_run_startup_migrations(app)
            yield

    app = FastAPI(
        title=app_name,
        version=__import__("nuclea_modeler").__version__,
        description=(
            "Núclea Modeler — catálogo e modelagem de dados corporativa "
            "Databricks-native. Cobre 10 módulos da spec + extras (tickets de "
            "reconciliação, Lakebase sandbox, code objects, audit log, busca "
            "global, importer Embarcadero)."
        ),
        contact={"name": "Tribo de Dados Núclea", "url": "https://github.com/lfmed/nuclea-modeler"},
        license_info={"name": "Privado · Núclea S.A."},
        openapi_tags=[
            {"name": "systems", "description": "Sistemas de origem catalogados (M1 contexto)"},
            {"name": "connections", "description": "Conexões ODBC/REST/DDL (M1)"},
            {"name": "extractions", "description": "Engenharia reversa (M2): Lakebase, DDL, .DM1"},
            {"name": "entities", "description": "Entidades + atributos (M3)"},
            {"name": "diagram", "description": "Diagrama Entidade-Relacionamento (M4)"},
            {"name": "flags", "description": "Flagueamento + propagação LGPD (M5)"},
            {"name": "glossary", "description": "Dicionário corporativo (M6)"},
            {"name": "lineage", "description": "Linhagem upstream/downstream (M7)"},
            {"name": "versions", "description": "Versionamento de modelos (M8)"},
            {"name": "sync", "description": "Sincronização Unity Catalog (M9)"},
            {"name": "ddl", "description": "Exportação DDL multi-dialect (M10)"},
            {"name": "lakebase", "description": "Lakebase Sandbox (validação round-trip)"},
            {"name": "tickets", "description": "Tickets de Reconciliação"},
            {"name": "rbac", "description": "Roles e permissões"},
            {"name": "audit", "description": "Audit log (admin)"},
        ],
        lifespan=_composed_lifespan,
    )

    api_router: APIRouter = create_router()
    for dep in all_deps:
        for r in dep.get_routers():
            api_router.include_router(r)
    app.include_router(api_router)

    for router in routers or []:
        if router is not api_router:
            app.include_router(router)

    if dist_dir.exists():
        from ._static import CachedStaticFiles, add_not_found_handler

        app.mount("/", CachedStaticFiles(directory=dist_dir, html=True))
        add_not_found_handler(app)

    return app


# singleton APIRouter with the application's API prefix
@lru_cache(maxsize=1)
def create_router() -> APIRouter:
    """Return the singleton APIRouter with the application's API prefix."""
    return APIRouter(prefix=api_prefix)


def _maybe_run_startup_migrations(app: FastAPI) -> None:
    """Apply pending schema migrations during startup, when enabled.

    Controlled by NUCLEA_MIGRATIONS_AUTO_APPLY (default: "true"). Set to "false"
    in environments where DDL is managed by another process. Failures are logged
    but NEVER abort the app boot — operators can investigate and re-run via the
    CLI: `python -m nuclea_modeler.backend.core.migrations`.
    """
    flag = os.getenv("NUCLEA_MIGRATIONS_AUTO_APPLY", "true").lower()
    if flag not in ("true", "1", "yes"):
        logger.info("[migrations] Auto-apply disabled (NUCLEA_MIGRATIONS_AUTO_APPLY != true)")
        return

    try:
        from databricks.sdk import WorkspaceClient
        from .migrations import apply_migrations, find_migrations_dir
        from ._nuclea_config import get_settings
        from .sql import Sql

        migrations_dir = find_migrations_dir()
        if not migrations_dir.exists():
            logger.warning(f"[migrations] Directory not found, skipping: {migrations_dir}")
            return

        settings = get_settings()
        ws = WorkspaceClient()
        sql_dep = Sql(
            config=type("_Cfg", (), {"warehouse_id": settings.warehouse_id})(),
            api=ws.statement_execution,
        )
        summary = apply_migrations(sql_dep, migrations_dir, actor="startup")
        logger.info(f"[migrations] Startup summary: {summary}")
    except Exception as exc:  # never abort boot
        logger.error(f"[migrations] Startup runner failed (app continues): {exc}")
