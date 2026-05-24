-- ============================================================================
-- Núclea Modeler — DDL para RBAC roles + Tickets de Reconciliação
-- ============================================================================

USE CATALOG stable_classic_pg4xe1_catalog;
USE SCHEMA data_catalog_app;

-- ---------------------------------------------------------------------------
-- 19) user_roles — RBAC por email
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_role_id     STRING NOT NULL,
    user_email       STRING NOT NULL,
    role_name        STRING NOT NULL COMMENT 'DATA_ARCHITECT | DATA_STEWARD | DATA_ENGINEER | CDE | ADMIN',
    granted_at       TIMESTAMP NOT NULL,
    granted_by       STRING NOT NULL,
    is_active        BOOLEAN NOT NULL
)
USING DELTA
COMMENT 'Atribuição de papéis (RBAC) por email do usuário'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- ---------------------------------------------------------------------------
-- 20) reconciliation_tickets — Tickets de aprovação para diffs de eng. reversa
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciliation_tickets (
    ticket_id          STRING NOT NULL,
    title              STRING NOT NULL,
    system_id          STRING NOT NULL,
    extraction_id      STRING COMMENT 'FK -> extractions.extraction_id quando vem de eng. reversa',
    source_type        STRING NOT NULL COMMENT 'REVERSE_ENG | DDL_IMPORT | LAKEBASE_ROUNDTRIP | MANUAL',
    status             STRING NOT NULL COMMENT 'OPEN | APPROVED | APPLIED | REJECTED',
    summary_md         STRING COMMENT 'Resumo em Markdown para humanos',
    diff_json          STRING NOT NULL COMMENT 'JSON com {additions, removals, changes} de entidades/atributos/rel',
    additions_count    INT,
    removals_count     INT,
    changes_count      INT,
    created_at         TIMESTAMP NOT NULL,
    created_by         STRING NOT NULL,
    approved_at        TIMESTAMP,
    approved_by        STRING,
    applied_at         TIMESTAMP,
    applied_by         STRING,
    rejected_at        TIMESTAMP,
    rejected_by        STRING,
    rejection_reason   STRING,
    target_version_id  STRING COMMENT 'version_id gerado após APPLIED'
)
USING DELTA
COMMENT 'Tickets de reconciliação — diffs aguardando aprovação humana'
TBLPROPERTIES (delta.enableChangeDataFeed = true);
