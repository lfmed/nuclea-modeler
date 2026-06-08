-- ============================================================================
-- 012_indexes_and_partitioning.sql
-- Catalogação de índices e particionamento por entity.
--
-- entity_indexes: 0..N índices por entity (BTREE/HASH/UNIQUE/GIN/BRIN/
--   Z-ORDER/LIQUID/CLUSTERED). Colunas armazenadas como ARRAY<STRUCT> pra
--   preservar ordem + direção (ASC/DESC).
-- entity_partitioning: 0..1 estratégia por entity (RANGE/LIST/HASH/LIQUID).
--   Tabela separada (não coluna em entities) pra manter migrations limpas
--   e permitir auditoria via change data feed.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- ---------------------------------------------------------------------------
-- entity_indexes — Índices por entity
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_indexes (
    index_id          STRING NOT NULL COMMENT 'PK (UUID v7)',
    entity_id         STRING NOT NULL COMMENT 'FK -> entities',
    index_name        STRING NOT NULL COMMENT 'ex: ix_pedido_cliente',
    index_type        STRING NOT NULL COMMENT 'BTREE | HASH | UNIQUE | GIN | BRIN | GIST | BITMAP | CLUSTERED | NONCLUSTERED | Z-ORDER | LIQUID',
    columns_json      STRING NOT NULL COMMENT 'JSON: [{"name":"col_a","direction":"ASC"},{"name":"col_b","direction":"DESC"}]',
    include_columns   ARRAY<STRING> COMMENT 'Columns na cláusula INCLUDE (SQL Server / PG covering)',
    partial_where     STRING COMMENT 'Cláusula WHERE pra partial index (PG/MSSQL)',
    is_unique         BOOLEAN NOT NULL DEFAULT false COMMENT 'redundante com index_type=UNIQUE mas facilita queries',
    native_comment    STRING,
    description_md    STRING,
    origin            STRING COMMENT 'EXTRACTED | MANUAL',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Índices de tabela catalogados — visíveis no DER e gerados no DDL'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- entity_partitioning — Estratégia de particionamento (0..1 por entity)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_partitioning (
    entity_id         STRING NOT NULL COMMENT 'PK + FK -> entities (1:1)',
    strategy          STRING NOT NULL COMMENT 'RANGE | LIST | HASH | LIQUID | NONE',
    columns_json      STRING NOT NULL COMMENT 'JSON: ["col_a","col_b"] — ordem importa',
    num_partitions    INT COMMENT 'Pra HASH: número de buckets',
    bounds_json       STRING COMMENT 'Pra RANGE/LIST: definição de bounds — JSON: {"part_2024":[2024,2025]}',
    description_md    STRING,
    origin            STRING COMMENT 'EXTRACTED | MANUAL',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Particionamento físico/lógico da entity — usado em DDL generation'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);
