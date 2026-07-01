-- ============================================================================
-- 016_attachments.sql
-- Anexos de documentos a tabelas (entities) e modelos (schema/diagram/system) —
-- pedido do cliente #7. Os BYTES ficam num Volume gerenciado do Unity Catalog;
-- aqui guardamos apenas os METADADOS + o caminho no Volume.
--
-- Requer que o SP do app tenha permissão de escrita no Volume. O Volume é
-- gerenciado (sem LOCATION) — vive dentro do próprio schema do app.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- Volume gerenciado onde os arquivos são gravados (/Volumes/<cat>/<schema>/attachments/...)
CREATE VOLUME IF NOT EXISTS attachments
    COMMENT 'Documentos anexados a entidades e modelos (Núclea Modeler)';

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
