/**
 * Lógica pura do Comparador (canvas exploratório).
 *
 * Extrai a lista de campos de um objeto — seja da entidade viva (atributos da
 * API) ou de um snapshot de versão (M8, `model_versions.snapshot_json`) — e
 * calcula similaridade/diferenças entre dois conjuntos de campos.
 *
 * Mantida SEM dependência de React para ser trivialmente testável e reutilizável.
 */
import type { AttributeOut } from "@/lib/api";

/** Campo (coluna) normalizado para comparação. */
export interface CmpField {
  name: string;
  type: string | null;
  pk: boolean;
  nullable: boolean;
}

/**
 * Normaliza um tipo para comparação: maiúsculas, sem espaços e sem os
 * argumentos de precisão. Ex.: "varchar(100)" → "VARCHAR", "decimal(10,2)" →
 * "DECIMAL". Assim VARCHAR(100) e varchar(255) contam como "mesmo tipo base".
 */
export function normalizeType(t: string | null | undefined): string {
  if (!t) return "";
  return String(t).toUpperCase().replace(/\s+/g, "").replace(/\(.*\)/, "");
}

function sortByOrdinal<T extends { ordinal_position?: number | null }>(items: T[]): T[] {
  return [...items].sort(
    (a, b) => (a.ordinal_position ?? 1e9) - (b.ordinal_position ?? 1e9),
  );
}

/** Campos a partir dos atributos da entidade viva (API). */
export function fieldsFromAttributes(attrs: AttributeOut[]): CmpField[] {
  return sortByOrdinal(attrs).map((a) => ({
    name: a.technical_name,
    type: a.native_data_type ?? null,
    pk: !!a.is_primary_key,
    nullable: a.is_nullable !== false,
  }));
}

/**
 * Campos a partir do snapshot de uma versão. `entityKey` = "schema.tabela".
 * Retorna null se a entidade não existe naquela versão. Defensivo: campos
 * ausentes no snapshot (ex.: tipo) viram null, sem quebrar a comparação por nome.
 */
export function fieldsFromVersionSnapshot(
  snapshot: Record<string, unknown> | null | undefined,
  entityKey: string,
): CmpField[] | null {
  if (!snapshot) return null;
  const entities = (snapshot.entities as Array<Record<string, unknown>>) ?? [];
  const ent = entities.find(
    (e) => `${e.schema_name}.${e.technical_name}` === entityKey,
  );
  if (!ent) return null;
  const byEntity =
    (snapshot.attributes_by_entity as Record<string, Array<Record<string, unknown>>>) ??
    {};
  const attrs = byEntity[ent.entity_id as string] ?? [];
  return sortByOrdinal(
    attrs as Array<{ ordinal_position?: number | null }>,
  ).map((a) => {
    const r = a as Record<string, unknown>;
    return {
      name: String(r.technical_name ?? ""),
      type: (r.native_data_type as string | null) ?? null,
      pk: !!r.is_primary_key,
      nullable: r.is_nullable !== false,
    };
  });
}

/** Status de um campo em relação à base (cartão de referência). */
export type FieldStatus = "match" | "type_diff" | "only_here";

/** Índice nome(lowercase) → campo, para comparar contra uma base. */
export function indexByName(fields: CmpField[]): Map<string, CmpField> {
  const m = new Map<string, CmpField>();
  for (const f of fields) m.set(f.name.toLowerCase(), f);
  return m;
}

/** Classifica um campo comparado com a base (match / tipo difere / só aqui). */
export function fieldStatusVsBase(
  field: CmpField,
  baseByName: Map<string, CmpField>,
): FieldStatus {
  const b = baseByName.get(field.name.toLowerCase());
  if (!b) return "only_here";
  return normalizeType(b.type) === normalizeType(field.type) ? "match" : "type_diff";
}

/** Métricas de similaridade entre dois conjuntos de campos. */
export interface Similarity {
  /** Jaccard sobre nomes de coluna (0..1). */
  nameJaccard: number;
  /** Fração da união em que nome existe nos dois E o tipo base coincide (0..1). */
  nameTypeScore: number;
  matched: number;
  onlyBase: number;
  onlyOther: number;
}

export function similarity(base: CmpField[], other: CmpField[]): Similarity {
  const baseNames = new Set(base.map((f) => f.name.toLowerCase()));
  const otherNames = new Set(other.map((f) => f.name.toLowerCase()));
  const union = new Set([...baseNames, ...otherNames]);
  let intersect = 0;
  for (const n of baseNames) if (otherNames.has(n)) intersect += 1;

  const baseByName = indexByName(base);
  let sameNameType = 0;
  for (const f of other) {
    const b = baseByName.get(f.name.toLowerCase());
    if (b && normalizeType(b.type) === normalizeType(f.type)) sameNameType += 1;
  }

  const unionSize = union.size || 1;
  return {
    nameJaccard: intersect / unionSize,
    nameTypeScore: sameNameType / unionSize,
    matched: intersect,
    onlyBase: baseNames.size - intersect,
    onlyOther: otherNames.size - intersect,
  };
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}
