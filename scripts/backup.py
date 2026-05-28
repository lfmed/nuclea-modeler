"""Backup CLI — exporta todas as tabelas Delta do app para Parquet em Volume UC.

Delta Time Travel já cobre restore granular (linha-a-linha em até 30 dias por
default). Este script é um snapshot EXTERNO complementar:

- Cross-region: copia para um Volume UC que pode estar em outra region.
- Pré-mudança de schema: dump antes de aplicar migration arriscada.
- Compliance: snapshots periódicos arquivados para audit trimestral.

Por design NÃO é automatizado — operador roda manualmente quando precisar.
Para snapshots regulares, configurar um Databricks Job que chama este script.

Uso:
    # Backup completo para /Volumes/<catalog>/<schema>/<volume>/backups/<timestamp>/
    python -m scripts.backup --volume /Volumes/main/default/nuclea_backups

    # Apenas algumas tabelas
    python -m scripts.backup --volume /Volumes/... --tables entities attributes

    # Dry-run (lista o que seria feito sem executar)
    python -m scripts.backup --volume /Volumes/... --dry-run

Auth: usa DATABRICKS_HOST + DATABRICKS_TOKEN (ou DEFAULT auth via SDK).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the package importable when running from the repo root.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from nuclea_modeler.backend.core._nuclea_config import get_settings
from nuclea_modeler.backend.core.sql import Sql


logger = logging.getLogger("nuclea.backup")


# Order matters for restore: parents before children. A backup written in this
# order can be restored top-down without FK-like reference errors (we use
# logical FKs, but ordered restore still helps incremental scenarios).
TABLES_IN_ORDER = (
    "schema_migrations",
    "systems",
    "connections",
    "entities",
    "attributes",
    "relationships",
    "views_catalog",
    "procedures_catalog",
    "triggers_catalog",
    "sequences_catalog",
    "der_layouts",
    "model_versions",
    "flags",
    "entity_flags",
    "attribute_flags",
    "glossary_terms",
    "glossary_mappings",
    "lineage_upstream",
    "lineage_downstream",
    "sync_log",
    "extractions",
    "reconciliation_tickets",
    "lakebase_sandboxes",
    "user_roles",
    "audit_log",
)


def _run_statement(sql: Sql, statement: str, *, wait: str = "60s") -> None:
    """Execute a statement, raising on non-success states."""
    resp = sql.execute_statement(statement=statement, wait_timeout=wait)
    state = resp.status.state if resp.status else None
    if state != StatementState.SUCCEEDED:
        err = resp.status.error.message if resp.status and resp.status.error else "unknown"
        raise RuntimeError(f"failed: {err}")


def _table_exists(sql: Sql, catalog: str, schema: str, table: str) -> bool:
    """Check via information_schema."""
    resp = sql.execute_statement(
        statement=(
            f"SELECT 1 FROM {catalog}.information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
        ),
        wait_timeout="20s",
    )
    return bool(
        resp.status
        and resp.status.state == StatementState.SUCCEEDED
        and resp.result
        and resp.result.data_array
    )


def backup_table(
    sql: Sql,
    *,
    catalog: str,
    schema: str,
    table: str,
    target_path: str,
    dry_run: bool,
) -> tuple[bool, str]:
    """Copy a single table to {target_path}/{table}/ as Parquet.

    Returns (success, message). On dry-run, success=True and message describes
    what would happen.
    """
    src = f"{catalog}.{schema}.{table}"
    dst = f"{target_path}/{table}"

    if not _table_exists(sql, catalog, schema, table):
        return (False, f"table {src} does not exist — skipped")

    if dry_run:
        return (True, f"[dry-run] would copy {src} → {dst} (Parquet)")

    stmt = (
        f"COPY INTO '{dst}' "
        f"FROM (SELECT * FROM {src}) "
        f"FILEFORMAT = PARQUET "
        f"COPY_OPTIONS ('mergeSchema' = 'false')"
    )
    try:
        _run_statement(sql, stmt, wait="120s")
        return (True, f"{src} → {dst}")
    except Exception as exc:
        # Fallback for table types that don't support COPY INTO (views,
        # streaming tables). Use CREATE TABLE AS SELECT into a managed
        # snapshot table within a backup schema. We don't go that route
        # automatically — surface the error and let the operator decide.
        return (False, f"{src}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backup do schema do Núclea Modeler para Volume UC (Parquet).",
    )
    parser.add_argument(
        "--volume",
        required=True,
        help="Base path do Volume UC (ex: /Volumes/main/default/nuclea_backups)",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Subconjunto de tabelas (default: todas). Nomes sem prefixo de schema.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria feito sem executar.",
    )
    parser.add_argument(
        "--label",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        help="Label do snapshot (default: timestamp UTC). Vira o nome da pasta.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    catalog = settings.catalog
    schema = settings.schema_

    ws = WorkspaceClient()
    sql = Sql(
        config=type("_Cfg", (), {"warehouse_id": settings.warehouse_id})(),
        api=ws.statement_execution,
    )

    target_root = args.volume.rstrip("/") + f"/{args.label}"
    logger.info("Backup label: %s", args.label)
    logger.info("Target: %s", target_root)
    logger.info("Source: %s.%s", catalog, schema)
    if args.dry_run:
        logger.info("DRY-RUN — no data will be written")

    tables = tuple(args.tables) if args.tables else TABLES_IN_ORDER
    logger.info("Tables to back up: %d", len(tables))

    ok, failed, skipped = 0, 0, 0
    for table in tables:
        success, message = backup_table(
            sql,
            catalog=catalog,
            schema=schema,
            table=table,
            target_path=target_root,
            dry_run=args.dry_run,
        )
        if success:
            logger.info("✓ %s", message)
            ok += 1
        elif "does not exist" in message or "skipped" in message:
            logger.warning("∘ %s", message)
            skipped += 1
        else:
            logger.error("✗ %s", message)
            failed += 1

    logger.info(
        "Summary: %d ok, %d failed, %d skipped (of %d total)",
        ok, failed, skipped, len(tables),
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
