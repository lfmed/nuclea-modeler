-- ============================================================================
-- App Settings (v1.0035) — configurações de app persistidas (key/value)
--
-- Motivação (feedback do cliente): o catálogo de destino do sync com o Unity
-- Catalog era HARDCODED (NUCLEA_CATALOG / DEFAULT_TARGET_CATALOG). O cliente quer
-- uma tela de Admin para ESCOLHER, entre os catálogos disponíveis, qual será
-- usado no sync. Precisamos persistir essa escolha — daí uma tabela genérica de
-- settings (key/value), que também serve para futuras configurações de app.
--
-- Migration: aditiva, não-destrutiva. Sem constraint ENFORCED (Delta não enforça).
-- Chave conhecida hoje: 'sync_target_catalog'.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key    STRING   NOT NULL COMMENT 'Chave da configuração (ex: sync_target_catalog)',
    setting_value  STRING            COMMENT 'Valor (texto). Interpretação por chave.',
    updated_at     TIMESTAMP         COMMENT 'Quando foi definido pela última vez',
    updated_by     STRING            COMMENT 'E-mail do admin que definiu'
) USING DELTA
COMMENT 'Configurações de app (key/value). Uma linha por chave.';
