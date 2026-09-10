-- ============================================================================
-- Seed das flags OFP — Operações Fora do Padrão (v1.0060, rodada 8 item 7)
--
-- Motivação (feedback do cliente): sinalizar dados/tabelas ligados a operações
-- fora do padrão (cargas manuais, fora de janela, sem aprovação, reprocessamento,
-- correções emergenciais). Nova categoria 'OFP' no catálogo de flags.
--
-- ATENÇÃO: este é um conjunto-RASCUNHO — os nomes/significados devem ser
-- validados com o cliente e podem ser ajustados (renomear = nova migration com
-- o MERGE; as antigas ficam is_active=false se descontinuadas). São flags de
-- SISTEMA (is_system=true), aplicáveis a entidades/atributos como as demais.
--
-- Idempotente: MERGE por flag_key (mesmo padrão do 003_seed_flags.sql). Cores em
-- tons de laranja/vermelho (sinal de atenção); sem justificativa obrigatória
-- (a exigência de justificativa não bloqueia aplicação desde v1.0035).
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

MERGE INTO flags AS t
USING (
  SELECT * FROM VALUES
    ('flag-ofp-operacao-manual',    'operacao-manual',    'OFP', 'Operação Manual',       'Dado gerado/alterado por operação manual, fora do fluxo automatizado.',   '#EA580C', false, true, 'ofp.operacao_manual'),
    ('flag-ofp-fora-de-janela',     'fora-de-janela',     'OFP', 'Fora de Janela',         'Processamento/carga executado fora da janela padrão.',                     '#D97706', false, true, 'ofp.fora_de_janela'),
    ('flag-ofp-sem-aprovacao',      'sem-aprovacao',      'OFP', 'Sem Aprovação',          'Alteração aplicada sem aprovação formal do processo.',                     '#DC2626', false, true, 'ofp.sem_aprovacao'),
    ('flag-ofp-reprocessamento',    'reprocessamento',    'OFP', 'Reprocessamento',        'Dado sujeito a reprocessamento (recarga/reexecução).',                     '#CA8A04', false, true, 'ofp.reprocessamento'),
    ('flag-ofp-carga-emergencial',  'carga-emergencial',  'OFP', 'Carga Emergencial',      'Carga ou correção emergencial fora do rito normal.',                       '#DC2626', false, true, 'ofp.carga_emergencial')
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
