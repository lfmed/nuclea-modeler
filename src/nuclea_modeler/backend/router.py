from databricks.sdk.service.iam import User as UserOut
from databricks.sdk.service.sql import StatementState

from .core import Dependencies, create_router
from .core.sql import SqlDependency
from .core._nuclea_config import get_settings
from .models import HealthOut, VersionOut

router = create_router()


@router.get("/version", response_model=VersionOut, operation_id="version")
async def version():
    return VersionOut.from_metadata()


@router.get("/current-user", response_model=UserOut, operation_id="currentUser")
def me(user_ws: Dependencies.UserClient):
    return user_ws.current_user.me()


@router.get("/health", response_model=HealthOut, operation_id="health")
def health(sql: SqlDependency) -> HealthOut:
    """Reporta status do app + conectividade com o schema Delta no UC."""
    s = get_settings()
    base = {
        "version": __import__("nuclea_modeler").__version__,
        "catalog": s.catalog,
        "schema": s.schema_,
        "warehouse_id": s.warehouse_id,
    }
    try:
        # Count tables in the app schema
        stmt = sql.execute_statement(
            statement=(
                "SELECT COUNT(*) AS n FROM "
                f"{s.catalog}.information_schema.tables "
                f"WHERE table_schema = '{s.schema_}'"
            ),
            wait_timeout="20s",
        )
        if stmt.status and stmt.status.state == StatementState.SUCCEEDED:
            tables_count = int(stmt.result.data_array[0][0]) if stmt.result and stmt.result.data_array else 0
        else:
            return HealthOut(
                **base,
                delta_reachable=False,
                error=f"statement state: {stmt.status.state if stmt.status else 'unknown'}",
            )

        # Count system flags (sanity)
        stmt2 = sql.execute_statement(
            statement=f"SELECT COUNT(*) FROM {s.fq_table('flags')} WHERE is_system = true",
            wait_timeout="20s",
        )
        flags_count = (
            int(stmt2.result.data_array[0][0])
            if stmt2.status and stmt2.status.state == StatementState.SUCCEEDED
               and stmt2.result and stmt2.result.data_array
            else None
        )
        return HealthOut(
            **base,
            delta_reachable=True,
            delta_tables_count=tables_count,
            flags_count=flags_count,
        )
    except Exception as exc:  # surface error to UI
        return HealthOut(**base, delta_reachable=False, error=str(exc)[:300])
