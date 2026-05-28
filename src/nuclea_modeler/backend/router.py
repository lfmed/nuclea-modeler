import time
from datetime import datetime, timezone

from databricks.sdk.service.iam import User as UserOut
from databricks.sdk.service.sql import StatementState

from .core import Dependencies, create_router
from .core.sql import SqlDependency
from .core._nuclea_config import get_settings
from .models import HealthOut, LivenessOut, ReadinessOut, VersionOut

router = create_router()

# /health TTL cache. Per-worker (uvicorn --workers 2 = 2 processes), so the
# warehouse sees at most 2 hits per TTL window. Counts are nice-to-have, not
# load-bearing — a 30s staleness is acceptable.
_HEALTH_TTL_SECONDS = 30.0
_health_cache: dict[str, tuple[float, HealthOut]] = {}

# /readyz also has its own TTL cache — k8s/Apps may poll every few seconds.
_READYZ_TTL_SECONDS = 5.0
_readyz_cache: tuple[float, ReadinessOut] | None = None

# Process boot timestamp for liveness uptime.
_BOOT_TIME = time.monotonic()


@router.get("/version", response_model=VersionOut, operation_id="version")
async def version():
    return VersionOut.from_metadata()


@router.get("/livez", response_model=LivenessOut, operation_id="livez")
async def livez() -> LivenessOut:
    """Liveness probe — process is running. No dependency check.

    k8s/Databricks Apps polls this to decide whether to restart the pod.
    Must return immediately and have no failure mode that depends on
    downstream services.
    """
    return LivenessOut(
        version=__import__("nuclea_modeler").__version__,
        uptime_seconds=time.monotonic() - _BOOT_TIME,
    )


@router.get("/readyz", response_model=ReadinessOut, operation_id="readyz")
def readyz(sql: SqlDependency) -> ReadinessOut:
    """Readiness probe — verifies warehouse connectivity.

    Returns `ready=true` only if the SQL warehouse responds within budget.
    Cached for 5s to avoid hammering the warehouse during probe loops.
    Counts and table inventory live in /health (richer, slower).
    """
    global _readyz_cache
    now = time.monotonic()
    if _readyz_cache and (now - _readyz_cache[0]) < _READYZ_TTL_SECONDS:
        return _readyz_cache[1]

    version_str = __import__("nuclea_modeler").__version__
    checked_at = datetime.now(timezone.utc).isoformat()
    probe_started = time.monotonic()
    try:
        resp = sql.execute_statement(statement="SELECT 1", wait_timeout="10s")
        state = resp.status.state if resp.status else None
        elapsed_ms = int((time.monotonic() - probe_started) * 1000)
        if state == StatementState.SUCCEEDED:
            out = ReadinessOut(
                ready=True,
                version=version_str,
                checked_at=checked_at,
                warehouse_reachable=True,
                warehouse_latency_ms=elapsed_ms,
            )
        else:
            err = resp.status.error.message if resp.status and resp.status.error else f"state={state}"
            out = ReadinessOut(
                ready=False,
                version=version_str,
                checked_at=checked_at,
                warehouse_reachable=False,
                warehouse_latency_ms=elapsed_ms,
                error=err[:300],
            )
    except Exception as exc:
        out = ReadinessOut(
            ready=False,
            version=version_str,
            checked_at=checked_at,
            warehouse_reachable=False,
            error=str(exc)[:300],
        )

    _readyz_cache = (now, out)
    return out


@router.get("/current-user", response_model=UserOut, operation_id="currentUser")
def me(user_ws: Dependencies.UserClient):
    return user_ws.current_user.me()


@router.get("/health", response_model=HealthOut, operation_id="health")
def health(sql: SqlDependency) -> HealthOut:
    """Reporta status do app + conectividade com o schema Delta no UC.

    Estratégia: probe barato (`SELECT 1`) sempre + contagens cacheadas (TTL 30s).
    Evita martelar `information_schema` a cada poll do frontend.
    """
    s = get_settings()
    base = {
        "version": __import__("nuclea_modeler").__version__,
        "catalog": s.catalog,
        "schema": s.schema_,
        "warehouse_id": s.warehouse_id,
    }

    cache_key = f"{s.catalog}.{s.schema_}"
    cached = _health_cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _HEALTH_TTL_SECONDS:
        return cached[1]

    try:
        # Cheap reachability probe — fails fast if warehouse/auth is broken.
        probe = sql.execute_statement(statement="SELECT 1", wait_timeout="10s")
        if not (probe.status and probe.status.state == StatementState.SUCCEEDED):
            return HealthOut(
                **base,
                delta_reachable=False,
                error=f"statement state: {probe.status.state if probe.status else 'unknown'}",
            )

        # Counts are best-effort. If either fails we still report reachable=True
        # so the UI shows "healthy" while flagging the count as unknown.
        tables_count: int | None = None
        flags_count: int | None = None
        try:
            stmt = sql.execute_statement(
                statement=(
                    f"SELECT COUNT(*) FROM {s.catalog}.information_schema.tables "
                    f"WHERE table_schema = '{s.schema_}'"
                ),
                wait_timeout="20s",
            )
            if (
                stmt.status and stmt.status.state == StatementState.SUCCEEDED
                and stmt.result and stmt.result.data_array
            ):
                tables_count = int(stmt.result.data_array[0][0])
        except Exception:
            pass

        try:
            stmt2 = sql.execute_statement(
                statement=f"SELECT COUNT(*) FROM {s.fq_table('flags')} WHERE is_system = true",
                wait_timeout="20s",
            )
            if (
                stmt2.status and stmt2.status.state == StatementState.SUCCEEDED
                and stmt2.result and stmt2.result.data_array
            ):
                flags_count = int(stmt2.result.data_array[0][0])
        except Exception:
            pass

        out = HealthOut(
            **base,
            delta_reachable=True,
            delta_tables_count=tables_count,
            flags_count=flags_count,
        )
        _health_cache[cache_key] = (time.monotonic(), out)
        return out
    except Exception as exc:  # surface error to UI, do NOT cache failures
        return HealthOut(**base, delta_reachable=False, error=str(exc)[:300])
