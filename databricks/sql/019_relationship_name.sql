-- ============================================================================
-- Bloco 4 — Nomear Relacionamentos
--
-- Adiciona coluna `relationship_name` (STRING, nullable) à tabela `relationships`
-- para permitir que o usuário nomeie/descreva o relacionamento semanticamente
-- (ex: "Pedido → Cliente", "Fornecedor → Contato").
--
-- Migration: aditiva, não-destrutiva. Sem constraint ENFORCED.
-- Independente da migration 018 (relationship_flags) — esta (019) só adiciona o
-- nome/rótulo do relacionamento.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE relationships
ADD COLUMNS (
    relationship_name STRING COMMENT 'Nome/rótulo do relacionamento ex: "Pedido → Cliente"'
);
