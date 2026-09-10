-- ============================================================================
-- Escopo de flag por SISTEMA (v1.0061, rodada 8 item 4)
--
-- Motivação (feedback do cliente): poder criar flags CUSTOM válidas para UM
-- sistema só (ex.: "Duplicatas — uso de dados para os Lakes"), sem poluir o
-- catálogo global. Adiciona `system_id` à tabela `flags`:
--   NULL      = flag GLOBAL (vale para todos os sistemas) — comportamento atual;
--   <id>      = flag específica daquele sistema (FK lógica -> systems.system_id).
-- Só flags CUSTOM usam escopo; as de sistema (LGPD/USE/QUALITY/OFP) ficam globais.
--
-- Os pickers passam a listar "globais + do sistema atual" (WHERE system_id IS NULL
-- OR system_id = :sys). A aba Flags mostra o selo do sistema nas flags escopadas.
--
-- Migration: aditiva, não-destrutiva, idempotente pelo runner. Linhas existentes
-- ficam com system_id NULL (globais) — nada muda para elas.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE flags ADD COLUMNS (
    system_id STRING COMMENT 'Escopo da flag: NULL = global; preenchido = válida só para este sistema (FK lógica -> systems.system_id). Só flags CUSTOM usam.'
);
