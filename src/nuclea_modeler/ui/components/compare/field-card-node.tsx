/**
 * Node do Comparador: um "cartão de objeto" (tabela) read-only no canvas xyflow,
 * listando as colunas (nome · tipo · PK · nullable).
 *
 * Auto-contido: cada cartão busca seus PRÓPRIOS campos (entidade viva via API ou
 * uma versão via snapshot M8). Quando o modo comparar está ligado, também busca
 * os campos do cartão-base (React Query deduplica o fetch entre cartões) e colore
 * cada linha: verde = igual, âmbar = mesmo nome/tipo diferente, cinza = só aqui.
 */
import { createContext, memo, useContext, useMemo } from "react";
import { X, KeyRound } from "lucide-react";

import { useEntityAttributes, useVersion } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  type CmpField,
  fieldsFromAttributes,
  fieldsFromVersionSnapshot,
  fieldStatusVsBase,
  indexByName,
  similarity,
  pct,
} from "@/components/compare/compare-utils";

/** Descritor de um cartão no board (serializável → localStorage). */
export interface CompareCard {
  id: string;
  source: "live" | "version";
  /** entity_id — presente quando source === "live". */
  entityId?: string;
  /** version_id — presente quando source === "version". */
  versionId?: string;
  /** "schema.tabela" — rótulo e chave de lookup no snapshot da versão. */
  entityKey: string;
  /** Texto exibido no cabeçalho do cartão. */
  label: string;
}

/** Dados serializáveis do node (o que vai para o xyflow / localStorage). */
export interface FieldCardData {
  card: CompareCard;
}

/**
 * Flags de comparação e callbacks compartilhados por todos os cartões.
 * Passados por contexto (não por node.data) para que ligar/desligar o modo
 * comparar ou trocar a base NÃO precise recriar os nodes do xyflow — preserva
 * seleção/drag e evita churn.
 */
export const CompareContext = createContext<{
  compareOn: boolean;
  baseCard: CompareCard | null;
  onRemove: (id: string) => void;
}>({ compareOn: false, baseCard: null, onRemove: () => {} });

/** Resolve os campos de um cartão (ou vazio quando `card` é null). Hooks sempre
 *  chamados (fetch condicional via `enabled`), respeitando as regras de hooks. */
function useCardFields(card: CompareCard | null): { fields: CmpField[]; loading: boolean } {
  const isLive = card?.source === "live";
  const isVer = card?.source === "version";
  const attrsQ = useEntityAttributes(isLive ? card?.entityId : null);
  const verQ = useVersion(isVer ? card?.versionId : null);
  const fields = useMemo<CmpField[]>(() => {
    if (!card) return [];
    if (isLive) return fieldsFromAttributes(attrsQ.data ?? []);
    return fieldsFromVersionSnapshot(verQ.data?.snapshot_json, card.entityKey) ?? [];
  }, [card, isLive, attrsQ.data, verQ.data]);
  const loading = (isLive && attrsQ.isLoading) || (isVer && verQ.isLoading);
  return { fields, loading };
}

const STATUS_ROW: Record<string, string> = {
  match: "bg-emerald-500/10",
  type_diff: "bg-amber-500/10",
  only_here: "bg-muted/40",
};

export const FieldCardNode = memo(function FieldCardNode({
  data,
}: {
  data: FieldCardData;
}) {
  const { card } = data;
  const { compareOn, baseCard, onRemove } = useContext(CompareContext);
  const self = useCardFields(card);

  const isBase = compareOn && baseCard?.id === card.id;
  const comparing = compareOn && !!baseCard && baseCard.id !== card.id;
  // Busca os campos da base só quando comparando (senão null → hook desabilitado).
  const base = useCardFields(comparing ? baseCard : null);
  const baseByName = useMemo(() => indexByName(base.fields), [base.fields]);
  const sim = useMemo(
    () => (comparing ? similarity(base.fields, self.fields) : null),
    [comparing, base.fields, self.fields],
  );

  return (
    <div
      className={`w-72 rounded-md border bg-background shadow-sm ${
        isBase ? "ring-2 ring-nuclea-primary" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <p className="truncate font-mono text-sm font-medium" title={card.label}>
            {card.label}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-1">
            <Badge variant="outline" className="text-[10px]">
              {card.source === "version" ? "versão" : "atual"}
            </Badge>
            {isBase && (
              <Badge variant="secondary" className="text-[10px]">base</Badge>
            )}
            {sim && (
              <span
                className="text-[10px] text-muted-foreground"
                title="Similaridade vs. base: nomes de coluna / nome+tipo"
              >
                {pct(sim.nameJaccard)} nomes · {pct(sim.nameTypeScore)} nome+tipo
              </span>
            )}
          </div>
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 shrink-0"
          title="Remover do canvas"
          onClick={() => onRemove(card.id)}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="max-h-[420px] overflow-auto">
        {self.loading ? (
          <p className="px-3 py-3 text-xs text-muted-foreground">Carregando campos…</p>
        ) : self.fields.length === 0 ? (
          <p className="px-3 py-3 text-xs text-muted-foreground italic">Sem campos.</p>
        ) : (
          <ul className="text-xs">
            {self.fields.map((f) => {
              const status = comparing ? fieldStatusVsBase(f, baseByName) : null;
              return (
                <li
                  key={f.name}
                  className={`flex items-center justify-between gap-2 px-3 py-1 ${
                    status ? STATUS_ROW[status] : ""
                  }`}
                >
                  <span className="flex min-w-0 items-center gap-1">
                    {f.pk && <KeyRound className="h-3 w-3 shrink-0 text-amber-500" />}
                    <span className="truncate font-mono">{f.name}</span>
                    {!f.nullable && <span className="text-[9px] text-muted-foreground">NN</span>}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    {f.type ?? "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
});
FieldCardNode.displayName = "FieldCardNode";
