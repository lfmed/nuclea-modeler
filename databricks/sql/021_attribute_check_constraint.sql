-- ============================================================================
-- Attribute CHECK constraint (v1.0043, round 6 pt 21)
--
-- Motivação (feedback do cliente, pt 21): permitir preencher/importar/exportar
-- CHECK CONSTRAINTS por coluna (ex.: `CHECK (PRINCIPAL IN (0,1))`). Guardamos a
-- EXPRESSÃO do check (o texto entre parênteses, ex.: "PRINCIPAL IN (0, 1)") por
-- atributo — cobre o caso comum (check de coluna única) e a importação via DDL.
--
-- Migration: aditiva, não-destrutiva. Delta não enforça CHECK como constraint
-- relacional; aqui é METADADO editorial (documentação + emissão no export DDL).
-- Idempotente pelo runner (schema_migrations rastreia por filename+checksum;
-- roda uma vez só).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE attributes ADD COLUMNS (
    check_constraint STRING COMMENT 'Expressão de CHECK CONSTRAINT da coluna (ex.: "situacao IN (0,1)"). Metadado editorial; emitido no export DDL.'
);
