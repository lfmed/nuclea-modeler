"""SQL Warehouse connection, query execution addon, and routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import partial
from typing import Annotated, AsyncGenerator, TypeAlias

from databricks.sdk.service.sql import (
    StatementExecutionAPI,
)
from fastapi import FastAPI, Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._base import LifespanDependency
from ._defaults import ClientDependency, UserWorkspaceClientDependency  # noqa: F401


class SqlConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABRICKS_SQL_")
    warehouse_id: str = Field(description="SQL Warehouse ID")


# --- Addon dependency ---


class Sql:
    """SQL Warehouse connection and query API."""

    def __init__(self, config: SqlConfig, api: StatementExecutionAPI):
        self.config: SqlConfig = config
        self.api: StatementExecutionAPI = api

    @property
    def execute_statement(self):
        """Partially apply the warehouse ID to the execute_statement method."""
        return partial(
            self.api.execute_statement, warehouse_id=self.config.warehouse_id
        )


class _SqlDependency(LifespanDependency):
    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.sql_config = SqlConfig()  # ty: ignore[missing-argument]
        yield

    @staticmethod
    def __call__(request: Request, ws: ClientDependency) -> Sql:
        """Use the APP service principal's WorkspaceClient (M2M auth) — its
        OAuth token has the `sql` scope granted via the warehouse resource
        declared in app.yml. The user OBO token typically does NOT include
        `sql` scope without explicit user re-authorization."""
        return Sql(config=request.app.state.sql_config, api=ws.statement_execution)


SqlDependency: TypeAlias = Annotated[Sql, _SqlDependency.depends()]
