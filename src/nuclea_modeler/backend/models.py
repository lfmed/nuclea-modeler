from pydantic import BaseModel, Field
from .. import __version__


class VersionOut(BaseModel):
    version: str

    @classmethod
    def from_metadata(cls):
        return cls(version=__version__)


class HealthOut(BaseModel):
    """Status do app + conectividade Delta."""

    version: str
    catalog: str
    schema: str = Field(..., alias="schema")
    warehouse_id: str
    delta_reachable: bool
    delta_tables_count: int | None = None
    flags_count: int | None = None
    error: str | None = None

    model_config = {"populate_by_name": True}
