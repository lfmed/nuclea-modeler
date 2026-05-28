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


class LivenessOut(BaseModel):
    """Process liveness probe — no dependency check."""

    status: str = "alive"
    version: str
    uptime_seconds: float


class ReadinessOut(BaseModel):
    """Readiness probe — verifies the app can serve real traffic.

    `ready=true` only when the SQL warehouse responds within the budget.
    Cached internally with a short TTL so per-pod calls don't hammer the
    warehouse during k8s-style probe loops.
    """

    ready: bool
    version: str
    checked_at: str
    warehouse_reachable: bool
    warehouse_latency_ms: int | None = None
    error: str | None = None
