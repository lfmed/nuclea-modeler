-- ============================================================================
-- Núclea Modeler — seed de admin(s) bootstrap (RBAC)
-- Idempotente: MERGE por user_role_id estável.
-- Concede ADMIN ao(s) e-mail(s) abaixo. Adicione novas linhas conforme
-- necessário; o ADMIN pode então gerenciar os demais papéis pela UI.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

MERGE INTO user_roles AS t
USING (
  SELECT * FROM VALUES
    ('role-admin-rodrigol-silva', 'rodrigol.silva@nuclea.com.br', 'ADMIN')
  AS s(user_role_id, user_email, role_name)
) AS s
ON t.user_role_id = s.user_role_id
WHEN MATCHED THEN UPDATE SET
  user_email = s.user_email,
  role_name  = s.role_name,
  is_active  = true
WHEN NOT MATCHED THEN INSERT (
  user_role_id, user_email, role_name, granted_at, granted_by, is_active
) VALUES (
  s.user_role_id, s.user_email, s.role_name, current_timestamp(), 'system-seed', true
);
