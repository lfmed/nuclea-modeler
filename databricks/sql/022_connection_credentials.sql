-- ============================================================================
-- Conexões de banco nativas: senha cifrada em repouso (v1.0058, rodada 8)
--
-- Motivação (feedback do cliente, rodada 8): o cliente cadastra conexões
-- self-service digitando URL/usuário/SENHA direto no app, e o app conecta no
-- banco por driver Python EMBUTIDO (Postgres/Oracle/MySQL/SQL Server/DB2) —
-- substituindo o ODBC, que NÃO roda no runtime do Databricks Apps (sem
-- unixODBC/driver). Ver connections/testers.py::test_database.
--
-- A senha é dado sensível do cliente e NÃO pode ficar em texto plano na tabela
-- (que, inclusive, é exibida na UI via config_json). Guardamos o CIFRADO (Fernet,
-- lib cryptography) nesta coluna nova; a chave-mestra vem do secret
-- 'nuclea-modeler/conn_enc_key' via env NUCLEA_CONN_ENC_KEY (ver app.yml e
-- connections/crypto.py). O username NÃO é sigiloso e permanece em config_json.
--
-- Migration: aditiva, não-destrutiva, idempotente pelo runner (schema_migrations
-- rastreia por filename+checksum). Linhas antigas (ODBC/REST) ficam com
-- enc_password NULL — sem senha cifrada, comportam-se como "sem senha".
-- ============================================================================

USE CATALOG ${CATALOG};
USE SCHEMA ${SCHEMA};

ALTER TABLE connections ADD COLUMNS (
    enc_password STRING COMMENT 'Senha do banco CIFRADA em repouso (token Fernet). Nunca retornada pela API — só vira o booleano has_password. Ver connections/crypto.py.'
);
