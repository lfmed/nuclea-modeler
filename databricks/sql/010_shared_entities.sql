-- ============================================================================
-- 010_shared_entities.sql
-- Adiciona flag is_shared em entities pra permitir relacionamentos cross-system.
-- Uma entity compartilhada vira "biblioteca" — outros sistemas podem referenciá-la
-- como target de relationship (FK lógica).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- Databricks SQL não suporta IF NOT EXISTS em ALTER ADD COLUMN; o tracking
-- de migrations (schema_migrations.checksum) garante que esta roda exatamente
-- uma vez. Em caso de reaplicação manual, drop a coluna primeiro.
ALTER TABLE entities ADD COLUMNS (
    is_shared BOOLEAN COMMENT 'Quando true, esta entidade aparece como referenciável em DERs de outros sistemas'
);
