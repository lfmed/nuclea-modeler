"""Apply DB migrations once before uvicorn starts.

Roda como passo separado no `command:` do app.yml para evitar contention
entre os 2 workers do uvicorn (que duplicaria INSERTs/MERGEs e dispararia
DELTA_CONCURRENT_APPEND em seeds).

Uso:
    python -m scripts.run_migrations

Falha (exit != 0) aborta o start do app. Para skip explícito em ambientes
read-only, exporte NUCLEA_MIGRATIONS_AUTO_APPLY=false.
"""
from __future__ import annotations

import os
import sys

from databricks.sdk import WorkspaceClient

from nuclea_modeler.backend.core.migrations import (
    apply_migrations,
    find_migrations_dir,
)
from nuclea_modeler.backend.core.sql import Sql, SqlConfig


def main() -> int:
    flag = os.getenv("NUCLEA_MIGRATIONS_AUTO_APPLY", "true").strip().lower()
    if flag in ("false", "0", "no", "off"):
        print("[migrations] disabled via NUCLEA_MIGRATIONS_AUTO_APPLY")
        return 0

    migrations_dir = find_migrations_dir()
    if not migrations_dir.exists():
        print(f"[migrations] directory not found: {migrations_dir}; skipping")
        return 0

    ws = WorkspaceClient()
    sql = Sql(config=SqlConfig(), api=ws.statement_execution)
    summary = apply_migrations(sql, migrations_dir, actor="startup")
    print(f"[migrations] summary: {summary}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
