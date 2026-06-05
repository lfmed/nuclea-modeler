-- ============================================================================
-- Núclea Modeler — seed das flags do sistema (LGPD/uso/qualidade)
-- Idempotente: usa MERGE com flag_key como chave natural.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

MERGE INTO flags AS t
USING (
  SELECT * FROM VALUES
    -- LGPD / Privacidade (requires_justification = true)
    ('flag-lgpd-dados-pessoais',      'dados-pessoais',            'LGPD', 'Dados Pessoais',                'Dados que identificam direta ou indiretamente uma pessoa natural.',     '#7B2D8E', true,  true, 'lgpd.dados_pessoais'),
    ('flag-lgpd-dados-sensiveis',     'dados-sensiveis',           'LGPD', 'Dados Pessoais Sensíveis',      'Dados sobre origem racial/étnica, religião, saúde, vida sexual, etc.',  '#D11A2A', true,  true, 'lgpd.dados_sensiveis'),
    ('flag-lgpd-titular-identificado','titular-identificado',      'LGPD', 'Titular Identificado',          'Coluna que isoladamente identifica o titular.',                          '#7B2D8E', true,  true, 'lgpd.titular_identificado'),
    ('flag-lgpd-anonimizado',         'anonimizado',               'LGPD', 'Anonimizado',                   'Dado submetido a anonimização irreversível.',                             '#0A8754', false, true, 'lgpd.anonimizado'),
    ('flag-lgpd-pseudonimizado',      'pseudonimizado',            'LGPD', 'Pseudonimizado',                'Dado pseudonimizado (reversível com chave segregada).',                   '#5E8B7E', false, true, 'lgpd.pseudonimizado'),
    ('flag-lgpd-base-consentimento',  'base-legal-consentimento',  'LGPD', 'Base Legal — Consentimento',    'Tratamento sob a base legal de consentimento (Art. 7º, I).',              '#FFC72C', true,  true, 'lgpd.base_legal_consentimento'),
    ('flag-lgpd-base-contrato',       'base-legal-contrato',       'LGPD', 'Base Legal — Contrato',         'Tratamento sob execução de contrato (Art. 7º, V).',                       '#FFC72C', true,  true, 'lgpd.base_legal_contrato'),
    ('flag-lgpd-base-obrigacao',      'base-legal-obrigacao-legal','LGPD', 'Base Legal — Obrigação Legal',  'Tratamento para cumprimento de obrigação legal (Art. 7º, II).',           '#FFC72C', true,  true, 'lgpd.base_legal_obrigacao'),
    ('flag-lgpd-retencao-definida',   'retencao-definida',         'LGPD', 'Retenção Definida',             'Dado com política de retenção e descarte documentada.',                   '#0A8754', false, true, 'lgpd.retencao_definida'),

    -- Uso do dado
    ('flag-use-master',               'dado-master',               'USE',  'Dado Master',                   'Master data — referencial corporativo.',                                  '#244B8C', false, true, 'use.dado_master'),
    ('flag-use-transacional',         'dado-transacional',         'USE',  'Dado Transacional',             'Dado operacional/transacional.',                                          '#5C7AEA', false, true, 'use.dado_transacional'),
    ('flag-use-historico',            'dado-historico',            'USE',  'Dado Histórico',                'Dado mantido para fins históricos/analíticos.',                           '#7A8A9B', false, true, 'use.dado_historico'),
    ('flag-use-calculado',            'dado-calculado',            'USE',  'Dado Calculado',                'Resultado de transformação/cálculo a partir de outros dados.',            '#6C757D', false, true, 'use.dado_calculado'),
    ('flag-use-depreciado',           'depreciado',                'USE',  'Depreciado',                    'Marcado para descontinuação.',                                            '#8B5E3C', false, true, 'use.depreciado'),
    ('flag-use-em-migracao',          'em-migracao',               'USE',  'Em Migração',                   'Em processo de migração para nova plataforma/modelo.',                    '#B8860B', false, true, 'use.em_migracao'),
    ('flag-use-restrito',             'uso-restrito',              'USE',  'Uso Restrito',                  'Acesso restrito a perfis específicos.',                                   '#D11A2A', true,  true, 'use.uso_restrito'),
    ('flag-use-publico-interno',      'uso-publico-interno',       'USE',  'Uso Público Interno',           'Disponível para qualquer colaborador interno.',                           '#0A8754', false, true, 'use.uso_publico_interno'),

    -- Qualidade
    ('flag-qual-critico',             'dado-critico',              'QUALITY','Dado Crítico',                 'Crítico para operação ou compliance — alta governança.',                  '#D11A2A', false, true, 'quality.dado_critico'),
    ('flag-qual-sem-validacao',       'sem-validacao',             'QUALITY','Sem Validação',                'Sem validação automática implementada.',                                  '#B8860B', false, true, 'quality.sem_validacao'),
    ('flag-qual-validado-negocio',    'validado-negocio',          'QUALITY','Validado por Negócio',         'Validação de regras de negócio aplicada.',                                '#0A8754', false, true, 'quality.validado_negocio'),
    ('flag-qual-inconsistencia',      'inconsistencia-conhecida',  'QUALITY','Inconsistência Conhecida',     'Inconsistência mapeada — ver notas técnicas.',                            '#D11A2A', true,  true, 'quality.inconsistencia_conhecida')
  AS s(flag_id, flag_key, category, display_name, description, color_hex, requires_justification, is_system, uc_tag_key)
) AS s
ON t.flag_key = s.flag_key
WHEN MATCHED THEN UPDATE SET
  display_name = s.display_name,
  description = s.description,
  color_hex = s.color_hex,
  requires_justification = s.requires_justification,
  uc_tag_key = s.uc_tag_key,
  updated_at = current_timestamp(),
  updated_by = 'system-seed'
WHEN NOT MATCHED THEN INSERT (
  flag_id, flag_key, category, display_name, description, color_hex,
  requires_justification, is_system, is_active, uc_tag_key,
  created_at, created_by, updated_at, updated_by
) VALUES (
  s.flag_id, s.flag_key, s.category, s.display_name, s.description, s.color_hex,
  s.requires_justification, s.is_system, true, s.uc_tag_key,
  current_timestamp(), 'system-seed', current_timestamp(), 'system-seed'
);
