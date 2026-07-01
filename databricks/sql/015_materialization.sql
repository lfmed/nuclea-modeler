-- ============================================================================
-- 015_materialization.sql
-- Rastreia a materialização do modelo em tabelas Delta reais (pedido do cliente #9).
-- O sync engine (M9) passa a poder CRIAR a tabela no catálogo destino
-- (modo materialize), não só espelhar COMMENT/TAGS em tabelas existentes.
-- Aqui guardamos se / onde / quando cada entidade foi materializada.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- Databricks SQL não suporta IF NOT EXISTS em ALTER ADD COLUMN; o tracking de
-- migrations (schema_migrations.checksum) garante que esta roda exatamente uma
-- vez. Em caso de reaplicação manual, drop as colunas primeiro.
ALTER TABLE entities ADD COLUMNS (
    is_materialized      BOOLEAN COMMENT 'true quando há tabela Delta materializada no catálogo destino',
    materialized_at      TIMESTAMP COMMENT 'quando a entidade foi materializada/sincronizada em Delta pela última vez',
    materialized_catalog STRING COMMENT 'catálogo Unity Catalog onde a tabela foi materializada'
);
