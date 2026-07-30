-- ============================================================================
-- Bloco 5 — Flags em Relacionamentos
--
-- Migration aditiva: cria a tabela `relationship_flags` espelhando `attribute_flags`.
-- Permite aplicar flags do catálogo a relacionamentos (1:N, N:N, herança, etc.)
-- sem propagação LGPD (não faz sentido propagar para entidades).
--
-- Padrão: cada flag aplicada a um relacionamento é uma linha em `relationship_flags`.
-- Sem UNIQUE/enforced no Delta (não é suportado em Databricks).
-- Idempotente: usa MERGE com relationship_id + flag_id como chave natural.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- Cria tabela relationship_flags (aditiva, não-destrutiva)
CREATE TABLE IF NOT EXISTS relationship_flags (
    relationship_flag_id STRING NOT NULL,
    relationship_id      STRING NOT NULL,
    flag_id              STRING NOT NULL,
    justification        STRING,
    applied_at           TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    applied_by           STRING NOT NULL,
    applied_in_version   STRING
)
USING DELTA
COMMENT 'Aplicação de flags aos relacionamentos'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);
