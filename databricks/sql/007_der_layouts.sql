-- ============================================================================
-- Núclea Modeler — DDL para layouts persistidos do DER (M4)
-- ============================================================================

USE CATALOG stable_classic_pg4xe1_catalog;
USE SCHEMA data_catalog_app;

-- ---------------------------------------------------------------------------
-- 23) der_layouts — Layout (posições dos nós) salvo por (system_id, layout_name)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS der_layouts (
    layout_id     STRING NOT NULL,
    system_id     STRING NOT NULL,
    layout_name   STRING NOT NULL COMMENT 'default | per-user (email) | per-version (version_id)',
    layout_json   STRING NOT NULL COMMENT 'JSON dict {entity_id: {x, y, hidden_attrs?}}',
    created_at    TIMESTAMP NOT NULL,
    created_by    STRING NOT NULL,
    updated_at    TIMESTAMP NOT NULL,
    updated_by    STRING NOT NULL
)
USING DELTA
COMMENT 'Posicionamento manual do DER por sistema/contexto'
TBLPROPERTIES (delta.enableChangeDataFeed = true);
