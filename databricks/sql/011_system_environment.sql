-- ============================================================================
-- 011_system_environment.sql
-- Adiciona tag de ambiente em systems (DEV / HINT / PRD).
-- Permite que o mesmo modelo lógico exista replicado em 3 sistemas, um por
-- ambiente, com versões potencialmente diferentes em cada um.
-- ============================================================================

USE CATALOG stable_classic_pg4xe1_catalog;
USE SCHEMA data_catalog_app;

ALTER TABLE systems ADD COLUMNS (
    environment STRING COMMENT 'DEV | HINT | PRD — nullable para sistemas legacy'
);
