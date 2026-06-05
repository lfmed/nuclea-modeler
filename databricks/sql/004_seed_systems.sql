-- ============================================================================
-- Núclea Modeler — seed de sistemas exemplo (DW Principal + 2 plataformas)
-- Idempotente: MERGE por system_id estável.
-- Remova/ajuste conforme sistemas reais da Núclea.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

MERGE INTO systems AS t
USING (
  SELECT * FROM VALUES
    ('sys-dw-principal',    'DW Principal',         'Data Warehouse corporativo principal',   'Cross-domain', 'Tribo de Dados',  'SQL Server'),
    ('sys-core-banking',    'Core Bancário',        'Sistema core de pagamentos e liquidação','Pagamentos',   'Plataforma Core', 'Oracle'),
    ('sys-crm',             'CRM Comercial',        'Cadastro e relacionamento com clientes', 'Comercial',    'Comercial',       'PostgreSQL')
  AS s(system_id, system_name, description, domain, owner_team, technology)
) AS s
ON t.system_id = s.system_id
WHEN MATCHED THEN UPDATE SET
  system_name = s.system_name,
  description = s.description,
  domain = s.domain,
  owner_team = s.owner_team,
  technology = s.technology,
  updated_at = current_timestamp(),
  updated_by = 'system-seed'
WHEN NOT MATCHED THEN INSERT (
  system_id, system_name, description, domain, owner_team, technology, is_active,
  created_at, created_by, updated_at, updated_by
) VALUES (
  s.system_id, s.system_name, s.description, s.domain, s.owner_team, s.technology, true,
  current_timestamp(), 'system-seed', current_timestamp(), 'system-seed'
);
