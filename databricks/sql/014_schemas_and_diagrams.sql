-- ============================================================================
-- Núclea Modeler — Segregação por schema + múltiplos diagramas (M6, fatia 1)
-- ============================================================================
-- Reifica o conceito de "schema" (hoje só uma string em entities) como entidade
-- de 1ª classe, e introduz múltiplos diagramas por schema.
--
-- NÃO ALTERA a tabela `entities` — a relação entity↔schema é derivada por JOIN
-- na chave natural (system_id, schema_name). Isso garante ZERO risco aos dados
-- já existentes do cliente (nenhum DROP/DELETE/UPDATE/ALTER em tabela existente)
-- e migration 100% idempotente (CREATE IF NOT EXISTS + INSERT ... WHERE NOT
-- EXISTS), segura para re-execução.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- ---------------------------------------------------------------------------
-- schemas — schema/owner de um sistema, com metadados próprios
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schemas (
    schema_id      STRING NOT NULL,
    system_id      STRING NOT NULL,
    schema_name    STRING NOT NULL COMMENT 'nome técnico do schema/owner no banco',
    logical_name   STRING COMMENT 'nome de negócio',
    domain         STRING,
    owner_team     STRING,
    description_md STRING,
    is_active      BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by     STRING NOT NULL,
    updated_at     TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by     STRING NOT NULL
)
USING DELTA
COMMENT 'Schemas (1ª classe) — agrupam entities dentro de um sistema'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- diagrams — vários diagramas (recortes) por schema
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagrams (
    diagram_id   STRING NOT NULL,
    system_id    STRING NOT NULL,
    schema_id    STRING NOT NULL,
    diagram_name STRING NOT NULL,
    description  STRING,
    is_default   BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by   STRING NOT NULL,
    updated_at   TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by   STRING NOT NULL
)
USING DELTA
COMMENT 'Diagramas DER por schema (vários recortes possíveis)'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- diagram_entities — membership (quais entities estão no diagrama) + posição
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagram_entities (
    diagram_id STRING NOT NULL,
    entity_id  STRING NOT NULL,
    pos_x      DOUBLE,
    pos_y      DOUBLE
)
USING DELTA
COMMENT 'Entidades visíveis em cada diagrama + posição (NULL = auto-layout)'
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- ---------------------------------------------------------------------------
-- Backfill 1: um schemas por (system_id, schema_name) distinto das entities
-- (somente INSERT em tabela nova — entities não é tocada)
-- ---------------------------------------------------------------------------
INSERT INTO schemas (schema_id, system_id, schema_name, logical_name, domain, owner_team, description_md, is_active, created_at, created_by, updated_at, updated_by)
SELECT concat('sch-', replace(uuid(), '-', '')),
       e.system_id, e.schema_name,
       NULL, NULL, NULL, NULL, true,
       current_timestamp(), 'migration-014', current_timestamp(), 'migration-014'
FROM (SELECT DISTINCT system_id, schema_name FROM entities WHERE schema_name IS NOT NULL) e
WHERE NOT EXISTS (
    SELECT 1 FROM schemas s
    WHERE s.system_id = e.system_id AND s.schema_name = e.schema_name
);

-- ---------------------------------------------------------------------------
-- Backfill 2: um diagrama "Default" por schema
-- ---------------------------------------------------------------------------
INSERT INTO diagrams (diagram_id, system_id, schema_id, diagram_name, description, is_default, created_at, created_by, updated_at, updated_by)
SELECT concat('dia-', replace(uuid(), '-', '')),
       s.system_id, s.schema_id, 'Default',
       'Diagrama padrão (gerado na migração 014)', true,
       current_timestamp(), 'migration-014', current_timestamp(), 'migration-014'
FROM schemas s
WHERE NOT EXISTS (
    SELECT 1 FROM diagrams d WHERE d.schema_id = s.schema_id AND d.is_default = true
);

-- ---------------------------------------------------------------------------
-- Backfill 3: membership do diagrama Default = todas as entities do schema,
-- resolvidas por JOIN na chave natural (system_id, schema_name).
-- Posição NULL → o canvas aplica auto-layout.
-- ---------------------------------------------------------------------------
INSERT INTO diagram_entities (diagram_id, entity_id, pos_x, pos_y)
SELECT d.diagram_id, e.entity_id, CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE)
FROM diagrams d
JOIN schemas s ON s.schema_id = d.schema_id
JOIN entities e ON e.system_id = s.system_id AND e.schema_name = s.schema_name
WHERE d.is_default = true
AND NOT EXISTS (
    SELECT 1 FROM diagram_entities de
    WHERE de.diagram_id = d.diagram_id AND de.entity_id = e.entity_id
);
