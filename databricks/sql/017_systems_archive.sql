-- ============================================================================
-- 017_systems_archive.sql
-- Soft-delete (arquivamento) de sistemas — pedido do cliente: excluir sistemas
-- retendo histórico E podendo restaurar. Em vez de apagar a linha do systems
-- (perderia nome/metadados e órfãos), marcamos archived_at: o sistema some das
-- listas mas continua recuperável (Restaurar limpa o archived_at).
--
-- Aditiva e não-destrutiva: colunas novas nuláveis; NULL = ativo.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE systems ADD COLUMNS (
    archived_at TIMESTAMP COMMENT 'quando foi arquivado (soft-delete); NULL = ativo',
    archived_by STRING COMMENT 'quem arquivou'
);
