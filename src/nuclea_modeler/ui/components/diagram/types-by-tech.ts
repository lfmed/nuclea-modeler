// Catálogo de tipos de coluna por tecnologia.
// Cada família declara se aceita parâmetro (length / precision_scale) — o
// TypePicker mostra inputs adicionais conforme aplicável.

export type TypeParam = "none" | "length" | "precision_scale";

export interface TypeFamily {
  /** Nome canônico do tipo (sem parâmetros). Ex: "VARCHAR", "NUMERIC". */
  name: string;
  /** Tipo de parâmetro aceito. */
  param: TypeParam;
  /** Defaults quando o user escolhe a família. */
  defaultLength?: number;
  defaultPrecision?: number;
  defaultScale?: number;
  /** Limite máximo do length (ajuda a UI a validar). */
  maxLength?: number;
}

// ─── Catálogos por tecnologia ───────────────────────────────────────────────

const POSTGRES: TypeFamily[] = [
  { name: "TEXT", param: "none" },
  { name: "VARCHAR", param: "length", defaultLength: 50, maxLength: 10485760 },
  { name: "CHAR", param: "length", defaultLength: 1 },
  { name: "INTEGER", param: "none" },
  { name: "BIGINT", param: "none" },
  { name: "SMALLINT", param: "none" },
  { name: "NUMERIC", param: "precision_scale", defaultPrecision: 18, defaultScale: 2 },
  { name: "REAL", param: "none" },
  { name: "DOUBLE PRECISION", param: "none" },
  { name: "BOOLEAN", param: "none" },
  { name: "DATE", param: "none" },
  { name: "TIMESTAMP", param: "none" },
  { name: "TIMESTAMPTZ", param: "none" },
  { name: "UUID", param: "none" },
  { name: "JSONB", param: "none" },
  { name: "BYTEA", param: "none" },
];

const ORACLE: TypeFamily[] = [
  { name: "VARCHAR2", param: "length", defaultLength: 50, maxLength: 4000 },
  { name: "CHAR", param: "length", defaultLength: 1 },
  { name: "NUMBER", param: "precision_scale", defaultPrecision: 10, defaultScale: 0 },
  { name: "FLOAT", param: "none" },
  { name: "DATE", param: "none" },
  { name: "TIMESTAMP", param: "none" },
  { name: "TIMESTAMP WITH TIME ZONE", param: "none" },
  { name: "CLOB", param: "none" },
  { name: "BLOB", param: "none" },
  { name: "RAW", param: "length", defaultLength: 16 },
];

const SQLSERVER: TypeFamily[] = [
  { name: "NVARCHAR", param: "length", defaultLength: 50, maxLength: 4000 },
  { name: "VARCHAR", param: "length", defaultLength: 50, maxLength: 8000 },
  { name: "CHAR", param: "length", defaultLength: 1 },
  { name: "INT", param: "none" },
  { name: "BIGINT", param: "none" },
  { name: "SMALLINT", param: "none" },
  { name: "DECIMAL", param: "precision_scale", defaultPrecision: 18, defaultScale: 2 },
  { name: "FLOAT", param: "none" },
  { name: "BIT", param: "none" },
  { name: "DATE", param: "none" },
  { name: "DATETIME2", param: "none" },
  { name: "DATETIMEOFFSET", param: "none" },
  { name: "UNIQUEIDENTIFIER", param: "none" },
  { name: "VARBINARY", param: "length", defaultLength: 50 },
];

const MYSQL: TypeFamily[] = [
  { name: "VARCHAR", param: "length", defaultLength: 50, maxLength: 65535 },
  { name: "CHAR", param: "length", defaultLength: 1 },
  { name: "TEXT", param: "none" },
  { name: "INT", param: "none" },
  { name: "BIGINT", param: "none" },
  { name: "SMALLINT", param: "none" },
  { name: "DECIMAL", param: "precision_scale", defaultPrecision: 18, defaultScale: 2 },
  { name: "FLOAT", param: "none" },
  { name: "DOUBLE", param: "none" },
  { name: "BOOLEAN", param: "none" },
  { name: "DATE", param: "none" },
  { name: "DATETIME", param: "none" },
  { name: "TIMESTAMP", param: "none" },
  { name: "JSON", param: "none" },
  { name: "BLOB", param: "none" },
];

const DATABRICKS: TypeFamily[] = [
  { name: "STRING", param: "none" },
  { name: "INT", param: "none" },
  { name: "BIGINT", param: "none" },
  { name: "FLOAT", param: "none" },
  { name: "DOUBLE", param: "none" },
  { name: "DECIMAL", param: "precision_scale", defaultPrecision: 18, defaultScale: 2 },
  { name: "BOOLEAN", param: "none" },
  { name: "DATE", param: "none" },
  { name: "TIMESTAMP", param: "none" },
  { name: "BINARY", param: "none" },
];

const GENERIC: TypeFamily[] = [
  { name: "STRING", param: "none" },
  { name: "VARCHAR", param: "length", defaultLength: 255 },
  { name: "TEXT", param: "none" },
  { name: "INTEGER", param: "none" },
  { name: "BIGINT", param: "none" },
  { name: "DECIMAL", param: "precision_scale", defaultPrecision: 18, defaultScale: 2 },
  { name: "BOOLEAN", param: "none" },
  { name: "DATE", param: "none" },
  { name: "TIMESTAMP", param: "none" },
];

// ─── API pública ───────────────────────────────────────────────────────────

export function getTypeFamiliesForTechnology(tech: string | null | undefined): TypeFamily[] {
  const t = (tech || "").toLowerCase().trim();
  if (!t) return GENERIC;
  if (t.includes("postgres") || t.includes("lakebase") || t.includes("pg")) return POSTGRES;
  if (t.includes("oracle")) return ORACLE;
  if (t.includes("sqlserver") || t.includes("mssql") || t.includes("sql server")) return SQLSERVER;
  if (t.includes("mysql") || t.includes("mariadb")) return MYSQL;
  if (t.includes("databricks") || t.includes("delta") || t.includes("spark")) return DATABRICKS;
  return GENERIC;
}

/** Legacy: lista flat de strings com defaults aplicados. Mantida por compat. */
export function getTypesForTechnology(tech: string | null | undefined): string[] {
  return getTypeFamiliesForTechnology(tech).map((f) => composeType(f));
}

/** Compõe o native_data_type final a partir de família + params. */
export function composeType(
  family: TypeFamily,
  length?: number | null,
  precision?: number | null,
  scale?: number | null,
): string {
  if (family.param === "none") return family.name;
  if (family.param === "length") {
    const len = length ?? family.defaultLength ?? 50;
    return `${family.name}(${len})`;
  }
  if (family.param === "precision_scale") {
    const p = precision ?? family.defaultPrecision ?? 18;
    const s = scale ?? family.defaultScale ?? 2;
    return `${family.name}(${p},${s})`;
  }
  return family.name;
}

/** Inverso: tenta extrair família + params de uma string nativa.
 * Útil pra inicializar o picker com um valor existente. */
export function parseType(
  raw: string | null | undefined,
  families: TypeFamily[],
): { family: TypeFamily | null; length: number | null; precision: number | null; scale: number | null } {
  if (!raw) return { family: null, length: null, precision: null, scale: null };
  const trimmed = raw.trim();
  const m = trimmed.match(/^([A-Z][A-Z0-9_ ]*)\s*(?:\(([^)]+)\))?\s*$/i);
  if (!m) return { family: null, length: null, precision: null, scale: null };
  const name = m[1].trim().toUpperCase();
  const args = (m[2] || "").trim();
  const family = families.find((f) => f.name.toUpperCase() === name) || null;
  if (!family) return { family: null, length: null, precision: null, scale: null };
  if (!args) {
    return { family, length: null, precision: null, scale: null };
  }
  if (args.includes(",")) {
    const [p, s] = args.split(",").map((x) => parseInt(x.trim(), 10));
    return {
      family,
      length: null,
      precision: Number.isFinite(p) ? p : null,
      scale: Number.isFinite(s) ? s : null,
    };
  }
  const n = parseInt(args, 10);
  return { family, length: Number.isFinite(n) ? n : null, precision: null, scale: null };
}
