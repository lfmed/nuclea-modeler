-- ============================================================================
-- 016_attachments.sql
-- Anexos de documentos a tabelas (entities) e modelos (schema/diagram/system) —
-- pedido do cliente #7. Os BYTES ficam num Volume gerenciado do Unity Catalog;
-- aqui guardamos apenas os METADADOS + o caminho no Volume.
--
-- O Volume gerenciado NÃO é criado aqui de propósito: criar Volume exige um
-- grant específico (CREATE VOLUME) que o SP pode não ter, e uma falha aqui
-- abortaria o boot do app inteiro (o runner faz exit 1). Em vez disso, o Volume
-- é criado sob demanda no primeiro upload de anexo (attachments/service.py:
-- _ensure_volume), degradando graciosamente se faltar permissão — assim a
-- ausência do grant desabilita só os anexos, não o app. Esta migration cria
-- apenas a tabela de metadados (precisa só de privilégio no schema, que o app
-- já tem por criar todas as suas tabelas).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id     STRING NOT NULL COMMENT 'PK (att-<uuid>)',
    owner_kind        STRING NOT NULL COMMENT 'entity | schema | diagram | system',
    owner_id          STRING NOT NULL COMMENT 'id do alvo (entity_id / schema_id / diagram_id / system_id)',
    original_filename STRING NOT NULL COMMENT 'nome original do arquivo enviado',
    mime_type         STRING COMMENT 'content-type declarado no upload',
    file_size_bytes   BIGINT COMMENT 'tamanho em bytes',
    volume_path       STRING NOT NULL COMMENT 'caminho absoluto em /Volumes/...',
    description       STRING COMMENT 'nota opcional sobre o anexo',
    created_at        TIMESTAMP NOT NULL,
    created_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Metadados de documentos anexados; bytes no Volume attachments'
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = true
);
