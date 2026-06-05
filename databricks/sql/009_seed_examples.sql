-- ============================================================================
-- Núclea Modeler — seeds de exemplo (Lakebase sandbox + conexão exemplo)
-- Idempotente: usa MERGE por sandbox_id / connection_id.
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

-- Lakebase sandbox apontando para a instância JDBCTESTLAKEBASE que já existe
MERGE INTO lakebase_sandboxes AS t
USING (SELECT
    'sb-example-jdbctest' AS sandbox_id,
    'JDBC Test Sandbox' AS name,
    'JDBCTESTLAKEBASE' AS instance_name,
    '131aec02-8ea1-41b3-8b92-b6f96079449b' AS instance_uid,
    'databricks_postgres' AS database_name,
    'public' AS default_schema,
    'Sandbox Lakebase de exemplo — use para validar modelos via round-trip DDL ↔ catálogo' AS description,
    'instance-131aec02-8ea1-41b3-8b92-b6f96079449b.database.cloud.databricks.com' AS read_write_dns,
    'PG_VERSION_16' AS pg_version) AS s
ON t.sandbox_id = s.sandbox_id
WHEN MATCHED THEN UPDATE SET
    name = s.name,
    instance_name = s.instance_name,
    description = s.description,
    read_write_dns = s.read_write_dns,
    pg_version = s.pg_version,
    updated_at = current_timestamp(),
    updated_by = 'system-seed'
WHEN NOT MATCHED THEN INSERT (
    sandbox_id, name, instance_name, instance_uid, database_name,
    default_schema, description, read_write_dns, pg_version,
    is_active, created_at, created_by, updated_at, updated_by
) VALUES (
    s.sandbox_id, s.name, s.instance_name, s.instance_uid, s.database_name,
    s.default_schema, s.description, s.read_write_dns, s.pg_version,
    true, current_timestamp(), 'system-seed', current_timestamp(), 'system-seed'
);

-- Conexão exemplo: ODBC apontando para o mesmo Lakebase (PostgreSQL driver)
-- Útil para testar fluxos M1/M2 sem precisar de banco externo
MERGE INTO connections AS t
USING (SELECT
    'conn-example-lakebase' AS connection_id,
    'Lakebase — Sandbox Exemplo' AS alias,
    'HINT' AS environment,
    'sys-dw-principal' AS system_id,
    'ODBC' AS connection_type,
    '{"driver":"PostgreSQL Unicode","host":"instance-131aec02-8ea1-41b3-8b92-b6f96079449b.database.cloud.databricks.com","port":5432,"database":"databricks_postgres"}' AS config_json,
    'nuclea-modeler' AS secret_scope) AS s
ON t.connection_id = s.connection_id
WHEN MATCHED THEN UPDATE SET
    alias = s.alias,
    environment = s.environment,
    config_json = s.config_json,
    updated_at = current_timestamp(),
    updated_by = 'system-seed'
WHEN NOT MATCHED THEN INSERT (
    connection_id, alias, environment, system_id, connection_type,
    config_json, secret_scope, last_test_status,
    created_at, created_by, updated_at, updated_by
) VALUES (
    s.connection_id, s.alias, s.environment, s.system_id, s.connection_type,
    s.config_json, s.secret_scope, 'never',
    current_timestamp(), 'system-seed', current_timestamp(), 'system-seed'
);
