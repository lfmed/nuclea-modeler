-- ============================================================================
-- Bloco 4 — Nomear Relacionamentos
--
-- Adiciona coluna `relationship_name` (STRING, nullable) à tabela `relationships`
-- para permitir que o usuário nomeie/descreva o relacionamento semanticamente
-- (ex: "Pedido → Cliente", "Fornecedor → Contato").
--
-- Migration: aditiva, não-destrutiva. Sem constraint ENFORCED.
-- Sem relacionamento lógico com "flags de relacionamento" (018 — nome vs. 019 — flags).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE relationships
ADD COLUMNS (
    relationship_name STRING COMMENT 'Nome/rótulo do relacionamento ex: "Pedido → Cliente"'
);
