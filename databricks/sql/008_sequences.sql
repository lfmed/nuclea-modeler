-- ============================================================================
-- Núclea Modeler — DDL para Sequences (M3 complementar)
-- Sequences são suportadas em PostgreSQL, Oracle, SQL Server (2012+), Snowflake.
-- Em SparkSQL/Delta usamos identity columns, mas a sequence ainda é catalogada
-- como objeto-conceito para preservação de modelos vindos de outros SGBDs.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

CREATE TABLE IF NOT EXISTS sequences_catalog (
    sequence_id     STRING NOT NULL,
    system_id       STRING NOT NULL,
    schema_name     STRING NOT NULL,
    technical_name  STRING NOT NULL,
    logical_name    STRING,
    description_md  STRING,
    start_value     BIGINT,
    increment_by    BIGINT,
    min_value       BIGINT,
    max_value       BIGINT,
    cache_size      INT,
    is_cycle        BOOLEAN,
    current_value   BIGINT,
    used_by_entity_ids ARRAY<STRING> COMMENT 'Entidades que consomem esta sequence',
    native_comment  STRING,
    created_at      TIMESTAMP NOT NULL,
    created_by      STRING NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    updated_by      STRING NOT NULL
)
USING DELTA
COMMENT 'Sequences catalogadas (PG/Oracle/SQL Server/Snowflake)'
TBLPROPERTIES (delta.enableChangeDataFeed = true);
