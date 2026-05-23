-- ============================================================================
-- Núclea Modeler — schema bootstrap
-- Cria o schema do app dentro do catalog gerenciado existente.
-- Idempotente: pode rodar múltiplas vezes sem efeito colateral.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS stable_classic_pg4xe1_catalog.data_catalog_app
COMMENT 'Núclea Modeler — app state (catálogo de dados corporativo Núclea). Tudo em Delta.';
