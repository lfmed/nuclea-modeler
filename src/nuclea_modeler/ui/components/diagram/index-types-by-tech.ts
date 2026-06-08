// Catálogo de tipos de índice + estratégias de particionamento por
// tecnologia. Espelha o pattern de types-by-tech.ts.

import type { IndexType, PartitionStrategy } from "@/lib/api";

export interface IndexTypeOption {
  value: IndexType;
  label: string;
  /** Aceita cláusula INCLUDE (SQL Server / Postgres covering indexes)? */
  supportsInclude?: boolean;
  /** Aceita partial WHERE? */
  supportsPartial?: boolean;
  /** Hint pra UX. */
  hint?: string;
}

export interface PartitionOption {
  value: PartitionStrategy;
  label: string;
  /** Pede num_partitions? */
  needsNumPartitions?: boolean;
  /** Pede bounds (ranges/lists)? */
  needsBounds?: boolean;
  /** Hint pra UX. */
  hint?: string;
}

const POSTGRES_IDX: IndexTypeOption[] = [
  { value: "BTREE", label: "BTREE", supportsPartial: true, supportsInclude: true, hint: "default — bom pra equality e range" },
  { value: "HASH", label: "HASH", supportsPartial: true, hint: "só equality" },
  { value: "UNIQUE", label: "UNIQUE (BTREE)", supportsPartial: true, supportsInclude: true, hint: "garante unicidade" },
  { value: "GIN", label: "GIN", supportsPartial: true, hint: "JSONB, arrays, full-text" },
  { value: "BRIN", label: "BRIN", supportsPartial: true, hint: "tabelas grandes ordenadas (logs, IoT)" },
  { value: "GIST", label: "GIST", supportsPartial: true, hint: "geometria, full-text, ranges" },
];

const ORACLE_IDX: IndexTypeOption[] = [
  { value: "BTREE", label: "BTREE", hint: "default" },
  { value: "UNIQUE", label: "UNIQUE", hint: "garante unicidade" },
  { value: "BITMAP", label: "BITMAP", hint: "baixa cardinalidade" },
];

const SQLSERVER_IDX: IndexTypeOption[] = [
  { value: "CLUSTERED", label: "CLUSTERED", supportsInclude: true, hint: "1 por tabela — define ordenação física" },
  { value: "NONCLUSTERED", label: "NONCLUSTERED", supportsInclude: true, supportsPartial: true, hint: "default" },
  { value: "UNIQUE", label: "UNIQUE (NONCLUSTERED)", supportsInclude: true, supportsPartial: true },
];

const MYSQL_IDX: IndexTypeOption[] = [
  { value: "BTREE", label: "BTREE", hint: "default" },
  { value: "HASH", label: "HASH", hint: "MEMORY engine" },
  { value: "UNIQUE", label: "UNIQUE", hint: "garante unicidade" },
];

const DATABRICKS_IDX: IndexTypeOption[] = [
  { value: "LIQUID", label: "LIQUID CLUSTERING", hint: "recomendado — adapta automaticamente" },
  { value: "Z-ORDER", label: "Z-ORDER (legacy)", hint: "preferir LIQUID em tabelas novas" },
];

const GENERIC_IDX: IndexTypeOption[] = [
  { value: "BTREE", label: "BTREE" },
  { value: "UNIQUE", label: "UNIQUE" },
  { value: "HASH", label: "HASH" },
];

// ─── Particionamento ──────────────────────────────────────────────────────

const POSTGRES_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento" },
  { value: "RANGE", label: "RANGE", needsBounds: true, hint: "por intervalo (data, número)" },
  { value: "LIST", label: "LIST", needsBounds: true, hint: "valores discretos (UF, status)" },
  { value: "HASH", label: "HASH", needsNumPartitions: true, hint: "distribuição uniforme" },
];

const DATABRICKS_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento (recomendado)", hint: "use LIQUID CLUSTERING via índice" },
  { value: "LIQUID", label: "LIQUID CLUSTERING", hint: "adaptativo, sem bounds" },
  { value: "HASH", label: "PARTITIONED BY (legacy)", hint: "evitar em tabelas novas — use LIQUID" },
];

const ORACLE_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento" },
  { value: "RANGE", label: "RANGE", needsBounds: true },
  { value: "LIST", label: "LIST", needsBounds: true },
  { value: "HASH", label: "HASH", needsNumPartitions: true },
];

const SQLSERVER_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento" },
  { value: "RANGE", label: "Partition function (RANGE)", needsBounds: true },
];

const MYSQL_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento" },
  { value: "RANGE", label: "RANGE", needsBounds: true },
  { value: "LIST", label: "LIST", needsBounds: true },
  { value: "HASH", label: "HASH", needsNumPartitions: true },
];

const GENERIC_PART: PartitionOption[] = [
  { value: "NONE", label: "Sem particionamento" },
  { value: "RANGE", label: "RANGE", needsBounds: true },
  { value: "LIST", label: "LIST", needsBounds: true },
  { value: "HASH", label: "HASH", needsNumPartitions: true },
];

// ─── API pública ───────────────────────────────────────────────────────────

function techKey(tech: string | null | undefined): string {
  const t = (tech || "").toLowerCase().trim();
  if (!t) return "generic";
  if (t.includes("postgres") || t.includes("lakebase") || t.includes("pg")) return "pg";
  if (t.includes("oracle")) return "oracle";
  if (t.includes("sqlserver") || t.includes("mssql") || t.includes("sql server")) return "mssql";
  if (t.includes("mysql") || t.includes("mariadb")) return "mysql";
  if (t.includes("databricks") || t.includes("delta") || t.includes("spark")) return "databricks";
  return "generic";
}

export function getIndexTypesForTechnology(tech: string | null | undefined): IndexTypeOption[] {
  switch (techKey(tech)) {
    case "pg": return POSTGRES_IDX;
    case "oracle": return ORACLE_IDX;
    case "mssql": return SQLSERVER_IDX;
    case "mysql": return MYSQL_IDX;
    case "databricks": return DATABRICKS_IDX;
    default: return GENERIC_IDX;
  }
}

export function getPartitionStrategiesForTechnology(tech: string | null | undefined): PartitionOption[] {
  switch (techKey(tech)) {
    case "pg": return POSTGRES_PART;
    case "oracle": return ORACLE_PART;
    case "mssql": return SQLSERVER_PART;
    case "mysql": return MYSQL_PART;
    case "databricks": return DATABRICKS_PART;
    default: return GENERIC_PART;
  }
}
