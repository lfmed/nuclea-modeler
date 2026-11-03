/**
 * Dialeto do sistema — vocabulário ÚNICO entre "tecnologia" e "dialeto de DDL"
 * (rodada 9, item 7).
 *
 * O cliente não entendia "onde se define o dialeto": havia DOIS conceitos soltos —
 * `systems.technology` (texto livre, ex. "PostgreSQL", usado por tipos/índices/
 * particionamento) e o select "Dialeto" de cada tela de DDL (chaves canônicas do
 * backend, ex. "POSTGRES"). Decisão: a TECNOLOGIA do sistema é o dialeto dele.
 * Ela é definida no wizard de criação ou no Navegador e vira o dialeto PADRÃO do
 * import de DDL (o export continua livre porque o destino costuma ser outro banco,
 * ex. Databricks).
 *
 * Os rótulos guardados em `technology` continuam os de sempre ("PostgreSQL",
 * "SQL Server"…) — `types-by-tech.ts`/`index-types-by-tech.ts` reconhecem por
 * substring, então nada precisa ser migrado. As chaves de dialeto DEVEM ser as
 * canônicas do backend (`extractions/service.py::_resolve_sqlglot_dialect`) — ver o
 * gotcha do v1.0037 no CLAUDE.md.
 */

export type CanonicalDialect =
  | "ANSI"
  | "POSTGRES"
  | "TSQL"
  | "PLSQL"
  | "MYSQL"
  | "SPARKSQL"
  | "DB2";

export interface TechnologyOption {
  /** Valor gravado em `systems.technology`. */
  label: string;
  /**
   * Dialeto canônico de DDL SQL, ou `null` para bancos NÃO relacionais (DynamoDB),
   * que não têm DDL SQL: o modelo entra/sai por JSON (Engenharia Reversa →
   * DynamoDB; Exportar DDL → "DynamoDB (JSON)").
   */
  dialect: CanonicalDialect | null;
}

/** Opções oferecidas no Navegador/wizard. A ordem é a de exibição. */
export const TECHNOLOGY_OPTIONS: TechnologyOption[] = [
  { label: "PostgreSQL", dialect: "POSTGRES" },
  { label: "Oracle", dialect: "PLSQL" },
  { label: "SQL Server", dialect: "TSQL" },
  { label: "MySQL", dialect: "MYSQL" },
  { label: "DB2", dialect: "DB2" },
  { label: "Databricks", dialect: "SPARKSQL" },
  { label: "ANSI (genérico)", dialect: "ANSI" },
  // Rodada 9 consolidada, item 17 — não relacional (sem DDL SQL).
  { label: "DynamoDB", dialect: null },
];

/**
 * Tecnologia (texto livre, possivelmente legado) → dialeto canônico, ou `null` se
 * não reconhecer. Mesmas regras de substring do `techKey` de index-types-by-tech
 * para que tipos e DDL nunca discordem sobre o banco de um sistema.
 */
export function technologyToDialect(tech: string | null | undefined): CanonicalDialect | null {
  const t = (tech || "").toLowerCase().trim();
  if (!t) return null;
  if (t.includes("dynamo")) return null; // não relacional: sem dialeto SQL
  if (t.includes("postgres") || t.includes("lakebase") || t.includes("pg")) return "POSTGRES";
  if (t.includes("oracle") || t.includes("plsql")) return "PLSQL";
  if (t.includes("sqlserver") || t.includes("mssql") || t.includes("sql server") || t.includes("tsql"))
    return "TSQL";
  if (t.includes("mysql") || t.includes("mariadb")) return "MYSQL";
  if (t.includes("databricks") || t.includes("delta") || t.includes("spark")) return "SPARKSQL";
  if (t.includes("db2") || t.includes("ibm")) return "DB2";
  if (t.includes("ansi")) return "ANSI";
  return null;
}

/** Rótulo canônico da opção que corresponde à tecnologia (para pré-selecionar o select). */
export function technologyOptionLabel(tech: string | null | undefined): string | null {
  if ((tech || "").toLowerCase().includes("dynamo")) return "DynamoDB";
  const d = technologyToDialect(tech);
  return d ? TECHNOLOGY_OPTIONS.find((o) => o.dialect === d)?.label ?? null : null;
}
