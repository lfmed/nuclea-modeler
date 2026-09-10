-- ============================================================================
-- Calendário de avaliação de conformidade (v1.0062, rodada 8 item 3)
--
-- Motivação (feedback do cliente): incorporar o calendário de avaliação de
-- conformidade na aplicação. O sistema guarda, POR SISTEMA, a periodicidade e a
-- próxima data de avaliação; quando a data chega/vence, um pop-up avisa e permite
-- REGISTRAR a execução (o sistema calcula a próxima data). A execução em si roda
-- FORA do Núclea Modeler (métodos variam por sistema); o checklist pode ser
-- ANEXADO ao sistema (módulo de anexos já existente, owner_kind='system').
--
-- Modelo: um agendamento por sistema (system_id é a chave natural do import;
-- calendar_id é a PK técnica). `next_due_date` é STRING ISO 'YYYY-MM-DD' (evita
-- casting de DATE na Statement Execution API, que devolve tudo como string).
--
-- Migration: aditiva, idempotente pelo runner (schema_migrations).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

CREATE TABLE IF NOT EXISTS compliance_calendar (
    calendar_id       STRING NOT NULL COMMENT 'PK técnica (UUID v7)',
    system_id         STRING NOT NULL COMMENT 'FK -> systems.system_id (1 agendamento por sistema)',
    recurrence        STRING NOT NULL COMMENT 'MONTHLY | QUARTERLY | SEMIANNUAL | ANNUAL',
    next_due_date     STRING NOT NULL COMMENT 'Próxima avaliação (ISO YYYY-MM-DD). O app calcula a próxima ao registrar execução.',
    last_executed_at  TIMESTAMP COMMENT 'Quando a última avaliação foi registrada como executada',
    last_executed_by  STRING,
    notes             STRING COMMENT 'Observações livres (ex.: responsável, método)',
    created_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    created_by        STRING NOT NULL,
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    updated_by        STRING NOT NULL
)
USING DELTA
COMMENT 'Calendário de avaliação de conformidade por sistema (rodada 8, item 3)'
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.enableChangeDataFeed' = true
);
