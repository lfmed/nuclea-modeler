-- ============================================================================
-- Núclea Modeler — DDL para Lakebase Sandboxes + Extractions (M2 + M-LB)
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- ---------------------------------------------------------------------------
-- 21) lakebase_sandboxes — Inst‪âncias Lakebase configuradas como sandboxes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lakebase_sandboxes (
    sandbox_id        STRING NOT NULL,
    name              STRING NOT NULL COMMENT 'Nome amigável (ex: sandbox-validation)',
    instance_name     STRING NOT NULL COMMENT 'Nome da instância Lakebase (ex: JDBCTESTLAKEBASE)',
    instance_uid      STRING COMMENT 'UID da instância Lakebase',
    database_name     STRING NOT NULL DEFAULT 'databricks_postgres',
    default_schema    STRING NOT NULL DEFAULT 'public',
    description       STRING,
    read_write_dns    STRING,
    pg_version        STRING,
    last_test_status  STRING,
    last_test_at      TIMESTAMP,
    last_test_error   STRING,
    is_active         BOOLEAN NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Sandboxes Lakebase Postgres usados para validação de modelos (round-trip)'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- ---------------------------------------------------------------------------
-- 22) extractions — Histórico de execuções de engenharia reversa
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extractions (
    extraction_id     STRING NOT NULL,
    source_kind       STRING NOT NULL COMMENT 'LAKEBASE | DDL_FILE | ODBC | REST',
    connection_id     STRING COMMENT 'FK -> connections.connection_id quando source=ODBC/REST',
    lakebase_sandbox_id STRING COMMENT 'FK -> lakebase_sandboxes quando source=LAKEBASE',
    system_id         STRING NOT NULL COMMENT 'Sistema-alvo do diff',
    requested_schemas STRING COMMENT 'CSV de schemas requisitados',
    requested_kinds   STRING COMMENT 'CSV de object kinds (TABLE,VIEW,...)',
    status            STRING NOT NULL COMMENT 'RUNNING | SUCCESS | PARTIAL | FAILED',
    started_at        TIMESTAMP NOT NULL,
    ended_at          TIMESTAMP,
    duration_ms       BIGINT,
    objects_found     INT,
    objects_new       INT,
    objects_changed   INT,
    objects_removed   INT,
    error_summary     STRING,
    snapshot_json     STRING COMMENT 'JSON com schemas/tables/columns extraídos',
    diff_summary_json STRING COMMENT 'Resumo do diff calculado',
    ticket_id         STRING COMMENT 'FK -> reconciliation_tickets quando há mudanças',
    created_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Histórico de execuções de engenharia reversa (M2)'
TBLPROPERTIES (delta.enableChangeDataFeed = true);
