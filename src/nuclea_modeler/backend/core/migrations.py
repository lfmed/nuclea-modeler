"""Schema migrations runner for the Núclea Modeler app state.

Convention:
- All migrations live as `.sql` files in `databricks/sql/` at the repo root.
- File names sort lexicographically (e.g. `001_create_schema.sql`,
  `002_create_tables.sql`). Numeric prefixes drive ordering.
- Each `.sql` file is split into statements on `;` boundaries. Empty statements
  and comment-only blocks are skipped.
- A `schema_migrations` table in the app schema records which files have been
  applied, with their SHA-256 checksums. If a file already applied has a
  different checksum than the stored one, we WARN (not fail) — manual review.

Operating modes:
- Auto-apply on app startup (default) when `NUCLEA_MIGRATIONS_AUTO_APPLY=true`.
- Standalone CLI: `python -m nuclea_modeler.backend.core.migrations`.

The runner is idempotent: it can be invoked any number of times. Already-applied
files are skipped.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from databricks.sdk.service.sql import StatementState

from . import delta
from ._config import logger
from ._nuclea_config import get_settings
from .sql import Sql


# Statement-splitter: naive `;`-split that ignores semicolons inside string
# literals. Sufficient for our DDL/INSERT files which never embed `;` inside
# strings.
_STMT_SPLIT_RE = re.compile(r";\s*\n|;\s*$")
_USE_CATALOG_RE = re.compile(r"^\s*USE\s+CATALOG\s+(\S+)\s*$", re.IGNORECASE)
_USE_SCHEMA_RE = re.compile(r"^\s*USE\s+SCHEMA\s+(\S+)\s*$", re.IGNORECASE)


def _statements(sql_text: str) -> list[str]:
    """Split a SQL file into individual statements, dropping empties and
    pure-comment chunks."""
    out: list[str] = []
    for raw in _STMT_SPLIT_RE.split(sql_text):
        stmt = raw.strip()
        if not stmt:
            continue
        # Strip whole-line comments to detect comment-only blocks
        non_comment_lines = [
            line for line in stmt.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if not non_comment_lines:
            continue
        out.append(stmt)
    return out


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _ensure_migrations_table(sql_dep: Sql) -> None:
    """Create the schema and the schema_migrations table if missing.

    The very first migration (001_create_schema.sql) is what *creates* the
    schema in the first place, so we cannot rely on the schema existing here.
    Instead, this bootstrap creates the schema (idempotent) and then the
    tracking table inside it.
    """
    s = get_settings()
    # Bootstrap: create schema (idempotent — same as 001_create_schema.sql).
    delta.run(
        sql_dep,
        f"CREATE SCHEMA IF NOT EXISTS {s.catalog}.{s.schema_}",
    )
    delta.run(
        sql_dep,
        f"""
        CREATE TABLE IF NOT EXISTS {s.fq_table('schema_migrations')} (
            filename     STRING NOT NULL,
            checksum     STRING NOT NULL,
            applied_at   TIMESTAMP NOT NULL,
            applied_by   STRING,
            duration_ms  BIGINT
        ) USING DELTA
        COMMENT 'Tracking de migrations aplicadas — Núclea Modeler'
        """,
    )


def _already_applied(sql_dep: Sql) -> dict[str, str]:
    """Return a dict {filename → checksum} of migrations already applied."""
    s = get_settings()
    try:
        rows = delta.fetch_all(
            sql_dep,
            f"SELECT filename, checksum FROM {s.fq_table('schema_migrations')}",
        )
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _record_migration(
    sql_dep: Sql,
    filename: str,
    checksum: str,
    duration_ms: int,
    actor: str,
) -> None:
    s = get_settings()
    delta.insert(
        sql_dep,
        s.fq_table("schema_migrations"),
        {
            "filename": filename,
            "checksum": checksum,
            "applied_at": datetime.utcnow(),
            "applied_by": actor,
            "duration_ms": duration_ms,
        },
    )


def discover_migrations(migrations_dir: Path) -> list[tuple[str, Path]]:
    """Return [(filename, path), ...] sorted lexicographically.

    Skips files whose names don't end in `.sql`.
    """
    if not migrations_dir.exists():
        return []
    files = sorted(
        (p for p in migrations_dir.iterdir() if p.is_file() and p.suffix == ".sql"),
        key=lambda p: p.name,
    )
    return [(p.name, p) for p in files]


def apply_migrations(
    sql_dep: Sql,
    migrations_dir: Path,
    *,
    actor: str = "system",
) -> dict[str, int]:
    """Apply all pending migrations. Returns {applied, skipped, drifted, failed}.

    Idempotent: already-applied (matching checksum) files are skipped.
    Files with a different checksum than recorded are logged as `drifted`
    but NOT re-applied — manual intervention required.
    """
    summary = {"applied": 0, "skipped": 0, "drifted": 0, "failed": 0}

    _ensure_migrations_table(sql_dep)
    applied = _already_applied(sql_dep)

    for filename, path in discover_migrations(migrations_dir):
        content = path.read_text(encoding="utf-8")
        checksum = _checksum(content)

        if filename in applied:
            if applied[filename] != checksum:
                logger.warning(
                    f"[migrations] DRIFT detected: {filename} checksum differs "
                    f"(stored={applied[filename][:12]}..., file={checksum[:12]}...). "
                    "Manual review required — NOT re-applying."
                )
                summary["drifted"] += 1
            else:
                summary["skipped"] += 1
            continue

        logger.info(f"[migrations] Applying {filename}...")
        started = datetime.utcnow()
        try:
            # execute_statement é stateless — `USE CATALOG/SCHEMA` no início do
            # arquivo não persiste entre statements. Capturamos esses comandos
            # e passamos `catalog=` / `schema=` explicitamente nos próximos.
            current_catalog: str | None = None
            current_schema: str | None = None
            for stmt in _statements(content):
                m_cat = _USE_CATALOG_RE.match(stmt)
                m_sch = _USE_SCHEMA_RE.match(stmt)
                if m_cat:
                    current_catalog = m_cat.group(1).strip("`")
                    continue
                if m_sch:
                    current_schema = m_sch.group(1).strip("`")
                    continue
                kwargs: dict = {"statement": stmt, "wait_timeout": "50s"}
                if current_catalog:
                    kwargs["catalog"] = current_catalog
                if current_schema:
                    kwargs["schema"] = current_schema
                resp = sql_dep.execute_statement(**kwargs)
                state = resp.status.state if resp.status else None
                if state != StatementState.SUCCEEDED:
                    err = (
                        resp.status.error.message
                        if resp.status and resp.status.error
                        else "unknown error"
                    )
                    raise RuntimeError(f"statement failed (state={state}): {err}")
            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            _record_migration(sql_dep, filename, checksum, duration_ms, actor)
            logger.info(f"[migrations] Applied {filename} in {duration_ms}ms")
            summary["applied"] += 1
        except Exception as exc:
            logger.error(f"[migrations] FAILED {filename}: {exc}")
            summary["failed"] += 1
            # Stop on first failure — don't apply later migrations on a broken state.
            break

    return summary


def find_migrations_dir() -> Path:
    """Locate `databricks/sql/` relative to the package.

    In source repo: ../../../databricks/sql/ from this file.
    In deployed app: same — the Databricks Apps platform preserves the layout
    declared in databricks.yml `sync.include` (which we set to include `src/**`
    and the repo root). Setting NUCLEA_MIGRATIONS_DIR overrides discovery.
    """
    import os
    override = os.getenv("NUCLEA_MIGRATIONS_DIR")
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    # core/migrations.py → core/ → backend/ → nuclea_modeler/ → src/ → repo_root
    candidates = [
        here.parent.parent.parent.parent.parent / "databricks" / "sql",
        # Databricks Apps deploy layout: /app/python/source_code/databricks/sql
        Path("/app/python/source_code/databricks/sql"),
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback: return first candidate so caller can decide what to do
    return candidates[0]


# ─── CLI ────────────────────────────────────────────────────────────────────


def _cli() -> int:
    """Standalone CLI: python -m nuclea_modeler.backend.core.migrations."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from databricks.sdk import WorkspaceClient

    migrations_dir = find_migrations_dir()
    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        return 1

    files = discover_migrations(migrations_dir)
    if not files:
        logger.warning(f"No .sql migrations found in {migrations_dir}")
        return 0

    logger.info(f"Discovered {len(files)} migration(s) in {migrations_dir}")

    settings = get_settings()
    ws = WorkspaceClient()  # picks up DATABRICKS_* env vars
    sql_dep = Sql(
        config=type("_Cfg", (), {"warehouse_id": settings.warehouse_id})(),
        api=ws.statement_execution,
    )

    summary = apply_migrations(sql_dep, migrations_dir, actor="cli")
    logger.info(f"Migrations summary: {summary}")
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(_cli())
