// Catálogo de tipos de coluna disponíveis por tecnologia.
// Usado no QuickAddEntityDialog para popular o dropdown de tipo dependendo
// da tecnologia declarada no sistema. Lista intencionalmente conservadora —
// cobre o que aparece em ~95% das tabelas reais sem virar dump exaustivo.

const POSTGRES = [
  "TEXT",
  "VARCHAR(50)",
  "VARCHAR(100)",
  "VARCHAR(255)",
  "CHAR(1)",
  "INTEGER",
  "BIGINT",
  "SMALLINT",
  "NUMERIC(18,2)",
  "REAL",
  "DOUBLE PRECISION",
  "BOOLEAN",
  "DATE",
  "TIMESTAMP",
  "TIMESTAMPTZ",
  "UUID",
  "JSONB",
  "BYTEA",
];

const ORACLE = [
  "VARCHAR2(50)",
  "VARCHAR2(100)",
  "VARCHAR2(255)",
  "VARCHAR2(4000)",
  "CHAR(1)",
  "NUMBER",
  "NUMBER(10)",
  "NUMBER(18,2)",
  "FLOAT",
  "DATE",
  "TIMESTAMP",
  "TIMESTAMP WITH TIME ZONE",
  "CLOB",
  "BLOB",
  "RAW(16)",
];

const SQLSERVER = [
  "NVARCHAR(50)",
  "NVARCHAR(100)",
  "NVARCHAR(255)",
  "NVARCHAR(MAX)",
  "VARCHAR(50)",
  "VARCHAR(100)",
  "INT",
  "BIGINT",
  "SMALLINT",
  "DECIMAL(18,2)",
  "FLOAT",
  "BIT",
  "DATE",
  "DATETIME2",
  "DATETIMEOFFSET",
  "UNIQUEIDENTIFIER",
  "NVARCHAR(MAX)",
  "VARBINARY(MAX)",
];

const MYSQL = [
  "VARCHAR(50)",
  "VARCHAR(100)",
  "VARCHAR(255)",
  "TEXT",
  "INT",
  "BIGINT",
  "SMALLINT",
  "DECIMAL(18,2)",
  "FLOAT",
  "DOUBLE",
  "BOOLEAN",
  "DATE",
  "DATETIME",
  "TIMESTAMP",
  "JSON",
  "BLOB",
];

const DATABRICKS = [
  "STRING",
  "INT",
  "BIGINT",
  "FLOAT",
  "DOUBLE",
  "DECIMAL(18,2)",
  "BOOLEAN",
  "DATE",
  "TIMESTAMP",
  "BINARY",
  "ARRAY<STRING>",
  "MAP<STRING,STRING>",
  "STRUCT<>",
];

// Fallback: lista mínima neutra (ANSI-ish).
const GENERIC = [
  "STRING",
  "VARCHAR(255)",
  "TEXT",
  "INTEGER",
  "BIGINT",
  "DECIMAL(18,2)",
  "BOOLEAN",
  "DATE",
  "TIMESTAMP",
];

export function getTypesForTechnology(tech: string | null | undefined): string[] {
  const t = (tech || "").toLowerCase().trim();
  if (!t) return GENERIC;
  if (t.includes("postgres") || t.includes("lakebase") || t.includes("pg")) return POSTGRES;
  if (t.includes("oracle")) return ORACLE;
  if (t.includes("sqlserver") || t.includes("mssql") || t.includes("sql server")) return SQLSERVER;
  if (t.includes("mysql") || t.includes("mariadb")) return MYSQL;
  if (t.includes("databricks") || t.includes("delta") || t.includes("spark")) return DATABRICKS;
  return GENERIC;
}
