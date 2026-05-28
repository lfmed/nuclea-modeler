-- ============================================================================
-- 010_shared_entities.sql
-- Adiciona flag is_shared em entities pra permitir relacionamentos cross-system.
-- Uma entity compartilhada vira "biblioteca" — outros sistemas podem referenciá-la
-- como target de relationship (FK lógica).
-- ============================================================================

USE CATALOG stable_classic_pg4xe1_catalog;
USE SCHEMA data_catalog_app;

ALTER TABLE entities
ADD COLUMN IF NOT EXISTS is_shared BOOLEAN DEFAULT false
COMMENT 'Quando true, esta entidade aparece como referenciável em DERs de outros sistemas';
