"""Pydantic models for DDL export — Módulo 10."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DDLDialect = Literal["ANSI", "TSQL", "PLSQL", "POSTGRES", "MYSQL", "SPARKSQL"]


class DDLExportRequest(BaseModel):
    system_id: str
    dialect: DDLDialect = "SPARKSQL"
    include_comments: bool = True
    qualify_schema: bool = True
    include_drop_if_exists: bool = False
    one_file_per_object: bool = False
    entity_ids: list[str] | None = None  # None = export all entities of the system


class DDLObjectResult(BaseModel):
    object_name: str  # qualified "schema.table" when applicable
    object_kind: Literal["TABLE", "VIEW"] = "TABLE"
    ddl_text: str
    errors: list[str] = Field(default_factory=list)


class DDLExportResult(BaseModel):
    dialect: DDLDialect
    total_objects: int
    success_count: int
    error_count: int
    files: list[DDLObjectResult] = Field(default_factory=list)
    combined_text: str = ""


class DDLDialectInfo(BaseModel):
    code: DDLDialect
    label: str
    subtitle: str
