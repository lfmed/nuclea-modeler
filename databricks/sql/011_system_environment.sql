-- ============================================================================
-- 011_system_environment.sql
-- Adiciona tag de ambiente em systems (DEV / HINT / PRD).
-- Permite que o mesmo modelo lógico exista replicado em 3 sistemas, um por
-- ambiente, com versões potencialmente diferentes em cada um.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE systems ADD COLUMNS (
    environment STRING COMMENT 'DEV | HINT | PRD — nullable para sistemas legacy'
);
