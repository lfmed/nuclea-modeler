"""Núclea Modeler runtime config.

Reads catalog/schema/warehouse coordinates and secrets scope from the
environment exposed by `databricks.yml` (NUCLEA_*) or local `.env`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NucleaSettings(BaseSettings):
    """App-specific configuration (Delta/UC + secrets scope)."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="NUCLEA_",
        extra="ignore",
    )

    catalog: str = Field(default="stable_classic_pg4xe1_catalog")
    schema_: str = Field(default="data_catalog_app", alias="schema")
    warehouse_id: str = Field(default="b8e52268d9828bdd")
    secrets_scope: str = Field(default="nuclea-modeler")

    @property
    def schema(self) -> str:  # type: ignore[override]
        return self.schema_

    @property
    def fq_schema(self) -> str:
        """Fully qualified catalog.schema reference."""
        return f"{self.catalog}.{self.schema_}"

    def fq_table(self, table: str) -> str:
        """Fully qualified catalog.schema.table reference."""
        return f"{self.catalog}.{self.schema_}.{table}"


@lru_cache(maxsize=1)
def get_settings() -> NucleaSettings:
    """Singleton settings instance."""
    return NucleaSettings()


# Sanity helpers for debugging
def settings_dict() -> dict[str, str]:
    s = get_settings()
    return {
        "catalog": s.catalog,
        "schema": s.schema_,
        "warehouse_id": s.warehouse_id,
        "secrets_scope": s.secrets_scope,
        "env_NUCLEA_CATALOG": os.getenv("NUCLEA_CATALOG", ""),
    }
