-- ============================================================================
-- Núclea Modeler — 18 tabelas Delta (conforme seção 6 da spec funcional)
-- Catálogo: ${CATALOG}.${SCHEMA}
--
-- Convenções:
--   - PKs como STRING (UUID v7 gerado pela app)
--   - Auditoria: created_at, created_by, updated_at, updated_by em todas as tabelas
--   - FKs lógicas (UC ainda não tem constraints FK obrigatórias) — validadas no app
--   - Delta features: change data feed habilitado nas tabelas mutáveis
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- ---------------------------------------------------------------------------
-- 1) connections — Conexões de ambiente (HINT/HEXT/PROD)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connections (
    connection_id     STRING NOT NULL COMMENT 'PK (UUID v7)',
    alias             STRING NOT NULL COMMENT 'Nome amigável da conexão',
    environment       STRING NOT NULL COMMENT 'HINT | HEXT | PROD',
    system_id         STRING NOT NULL COMMENT 'FK -> systems.system_id',
    connection_type   STRING NOT NULL COMMENT 'ODBC | REST | DDL_IMPORT',
    config_json       STRING COMMENT 'JSON com config sem credenciais (host, porta, base, etc)',
    secret_scope      STRING COMMENT 'Databricks Secrets scope para credenciais',
    secret_key_user   STRING,
    secret_key_pass   STRING,
    secret_key_token  STRING,
    last_test_status  STRING COMMENT 'success | failure | never',
    last_test_at      TIMESTAMP,
    last_test_latency_ms BIGINT,
    last_test_db_version STRING,
    last_test_error   STRING,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Conexões ODBC/REST/DDL para os ambientes HINT, HEXT, PROD'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 2) systems — Sistemas de origem catalogados
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS systems (
    system_id         STRING NOT NULL,
    system_name       STRING NOT NULL COMMENT 'ex: SAP_ERP, CRM_SALESFORCE, DW_PRINCIPAL',
    description       STRING,
    domain            STRING COMMENT 'Financeiro | RH | Logística | ...',
    owner_team        STRING,
    technology        STRING COMMENT 'SQL Server | Oracle | PostgreSQL | MySQL | etc',
    is_active         BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Sistemas de origem catalogados pela app'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 3) model_versions — Versões publicadas dos modelos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_versions (
    version_id        STRING NOT NULL,
    system_id         STRING NOT NULL COMMENT 'FK -> systems',
    version_number    STRING NOT NULL COMMENT 'v1.0, v1.1, v2.0 ...',
    title             STRING,
    changelog         STRING COMMENT 'Markdown',
    status            STRING NOT NULL COMMENT 'DRAFT | PUBLISHED | ACTIVE | DEPRECATED',
    published_at      TIMESTAMP,
    published_by      STRING,
    snapshot_json     STRING COMMENT 'JSON imutável do modelo congelado',
    based_on_version  STRING COMMENT 'version_id da versão restaurada (quando aplicável)',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Versões/snapshots imutáveis dos modelos de dados'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 4) entities — Tabelas/entidades catalogadas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
    entity_id         STRING NOT NULL,
    system_id         STRING NOT NULL,
    schema_name       STRING NOT NULL COMMENT 'Schema/owner no banco de origem',
    technical_name    STRING NOT NULL,
    logical_name      STRING COMMENT 'Nome de negócio',
    description_md    STRING COMMENT 'Markdown',
    domain            STRING,
    business_owner    STRING,
    technical_owner   STRING,
    criticality       STRING COMMENT 'HIGH | MEDIUM | LOW',
    tags              ARRAY<STRING>,
    notes             STRING,
    entity_type       STRING COMMENT 'TABLE | VIEW | MATERIALIZED_VIEW | EXTERNAL',
    native_comment    STRING COMMENT 'COMMENT original do banco',
    row_count_approx  BIGINT,
    last_extracted_at TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Entidades (tabelas, views) catalogadas — fonte única de verdade do modelo'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 5) attributes — Colunas/atributos catalogados
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attributes (
    attribute_id      STRING NOT NULL,
    entity_id         STRING NOT NULL,
    technical_name    STRING NOT NULL,
    logical_name      STRING,
    ordinal_position  INT,
    native_data_type  STRING COMMENT 'tipo no SGBD de origem',
    is_nullable       BOOLEAN,
    default_value     STRING,
    is_primary_key    BOOLEAN NOT NULL DEFAULT false,
    description_md    STRING,
    business_rule     STRING,
    sample_value      STRING,
    glossary_term_id  STRING COMMENT 'FK -> glossary_terms',
    native_comment    STRING,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Atributos (colunas) catalogados'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 6) relationships — Relacionamentos entre entidades
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS relationships (
    relationship_id   STRING NOT NULL,
    system_id         STRING NOT NULL,
    source_entity_id  STRING NOT NULL,
    target_entity_id  STRING NOT NULL,
    source_attr_ids   ARRAY<STRING>,
    target_attr_ids   ARRAY<STRING>,
    rel_type          STRING COMMENT '1:1 | 1:N | N:M | INHERIT',
    source_cardinality STRING COMMENT 'OPTIONAL | MANDATORY',
    target_cardinality STRING COMMENT 'OPTIONAL | MANDATORY',
    description       STRING,
    origin            STRING COMMENT 'EXTRACTED | MANUAL',
    fk_update_rule    STRING,
    fk_delete_rule    STRING,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Relacionamentos entre entidades'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 7) views_catalog — Metadados de views
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS views_catalog (
    view_entity_id    STRING NOT NULL COMMENT 'FK -> entities.entity_id',
    purpose           STRING,
    definition_sql    STRING,
    base_entity_ids   ARRAY<STRING>,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Documentação extra para entidades do tipo VIEW'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 8) procedures_catalog — Stored procedures
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS procedures_catalog (
    procedure_id      STRING NOT NULL,
    system_id         STRING NOT NULL,
    schema_name       STRING NOT NULL,
    technical_name    STRING NOT NULL,
    logical_name      STRING,
    behavior_desc     STRING,
    parameters_json   STRING COMMENT 'JSON array de {name, type, direction, description}',
    source_code       STRING,
    dependent_systems ARRAY<STRING>,
    change_risk_level STRING COMMENT 'CRITICAL | MODERATE | LOW',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Stored procedures catalogadas'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 9) triggers_catalog — Triggers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS triggers_catalog (
    trigger_id        STRING NOT NULL,
    system_id         STRING NOT NULL,
    schema_name       STRING NOT NULL,
    technical_name    STRING NOT NULL,
    associated_entity_id STRING,
    event_type        STRING COMMENT 'INSERT | UPDATE | DELETE',
    timing            STRING COMMENT 'BEFORE | AFTER | INSTEAD_OF',
    body              STRING,
    behavior_desc     STRING,
    change_risk_level STRING,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Triggers catalogados'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 10) flags — Definição de flags disponíveis (LGPD/uso/qualidade/custom)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flags (
    flag_id           STRING NOT NULL,
    flag_key          STRING NOT NULL COMMENT 'ex: dados-pessoais, dado-master',
    category          STRING NOT NULL COMMENT 'LGPD | USE | QUALITY | CUSTOM',
    display_name      STRING NOT NULL,
    description       STRING,
    color_hex         STRING COMMENT 'cor da chip na UI',
    requires_justification BOOLEAN NOT NULL DEFAULT false,
    is_system         BOOLEAN NOT NULL DEFAULT false COMMENT 'flags pré-definidas não-editáveis',
    is_active         BOOLEAN NOT NULL DEFAULT true,
    uc_tag_key        STRING COMMENT 'chave da tag no Unity Catalog ao sincronizar',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Definição catalogada das flags disponíveis no sistema'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 11) entity_flags — Aplicação de flags a entidades
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_flags (
    entity_flag_id    STRING NOT NULL,
    entity_id         STRING NOT NULL,
    flag_id           STRING NOT NULL,
    justification     STRING,
    applied_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    applied_by        STRING NOT NULL,
    applied_in_version STRING COMMENT 'version_id ativa no momento da aplicação',
    is_propagated     BOOLEAN NOT NULL DEFAULT false COMMENT 'true se herdada de uma coluna'
)
USING DELTA
COMMENT 'Aplicação de flags às entidades (tabelas)'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 12) attribute_flags — Aplicação de flags a atributos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attribute_flags (
    attribute_flag_id STRING NOT NULL,
    attribute_id      STRING NOT NULL,
    flag_id           STRING NOT NULL,
    justification     STRING,
    applied_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    applied_by        STRING NOT NULL,
    applied_in_version STRING
)
USING DELTA
COMMENT 'Aplicação de flags aos atributos (colunas)'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 13) glossary_terms — Dicionário corporativo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS glossary_terms (
    term_id           STRING NOT NULL,
    canonical_name    STRING NOT NULL,
    definition        STRING NOT NULL,
    synonyms          ARRAY<STRING>,
    domain            STRING,
    conceptual_type   STRING COMMENT 'Identifier | Monetary | Date | Boolean | Text | ...',
    valid_examples    ARRAY<STRING>,
    owner_person      STRING,
    status            STRING NOT NULL COMMENT 'DRAFT | IN_REVIEW | APPROVED | DEPRECATED',
    approved_by       STRING,
    approved_at       TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Glossário corporativo de termos de dados'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 14) glossary_mappings — Vínculos termo ↔ atributo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS glossary_mappings (
    mapping_id        STRING NOT NULL,
    term_id           STRING NOT NULL,
    attribute_id      STRING NOT NULL,
    inherit_description BOOLEAN NOT NULL DEFAULT true,
    override_description STRING,
    type_compat_warning BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Vínculos N:N entre termos do dicionário e atributos'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 15) lineage_upstream — Linhagem de origem
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lineage_upstream (
    lineage_id        STRING NOT NULL,
    entity_id         STRING NOT NULL,
    source_system     STRING NOT NULL,
    source_entity     STRING,
    integration_type  STRING COMMENT 'CDC | BATCH | API_PULL | API_PUSH | FILE',
    periodicity       STRING COMMENT 'REAL_TIME | DAILY | WEEKLY | ON_DEMAND',
    transformations   STRING,
    pipeline_link     STRING COMMENT 'URL para job/notebook/pipeline DLT',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Linhagem upstream (origem) das entidades'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 16) lineage_downstream — Linhagem de consumo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lineage_downstream (
    consumer_id       STRING NOT NULL,
    entity_id         STRING NOT NULL,
    consumer_system   STRING NOT NULL,
    consumption_type  STRING COMMENT 'DIRECT_READ | API | REPORT | ML_MODEL',
    responsible_team  STRING,
    sla_dependency    STRING COMMENT 'CRITICAL | HIGH | MEDIUM | LOW',
    detected_via      STRING COMMENT 'MANUAL | UC_LINEAGE',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Linhagem downstream (consumidores) das entidades'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 17) sync_log — Log de sincronizações com Unity Catalog
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_log (
    sync_id           STRING NOT NULL,
    version_id        STRING NOT NULL,
    system_id         STRING NOT NULL,
    started_at        TIMESTAMP NOT NULL,
    ended_at          TIMESTAMP,
    status            STRING NOT NULL COMMENT 'RUNNING | SUCCESS | PARTIAL | FAILED',
    objects_total     INT,
    objects_synced    INT,
    objects_failed    INT,
    duration_ms       BIGINT,
    target_catalog    STRING,
    triggered_by      STRING,
    error_summary     STRING,
    details_json      STRING
)
USING DELTA
COMMENT 'Histórico de execuções de sincronização com Unity Catalog'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);

-- ---------------------------------------------------------------------------
-- 18) audit_log — Auditoria imutável geral
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id          STRING NOT NULL,
    occurred_at       TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    actor_email       STRING NOT NULL,
    actor_role        STRING,
    action            STRING NOT NULL COMMENT 'CREATE | UPDATE | DELETE | APPROVE | PUBLISH | SYNC | ...',
    object_type       STRING NOT NULL COMMENT 'connection | entity | attribute | flag | term | ...',
    object_id         STRING,
    before_json       STRING,
    after_json        STRING,
    request_id        STRING,
    client_ip         STRING,
    user_agent        STRING
)
USING DELTA
COMMENT 'Log imutável de auditoria de todas as operações relevantes'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = false,
    'delta.appendOnly' = true
);
