/**
 * Controles compartilhados de Chave Primária (PK).
 *
 * PORQUÊ: a manipulação de PK estava fragmentada e inconsistente entre a página
 * de detalhe da entidade (`entities.$id.tsx`, read-only), o editor do diagrama
 * (`diagram.tsx`, checkbox "nu") e o node do DER (`entity-node.tsx`, só ícone).
 * Este módulo centraliza:
 *   - a NUMERAÇÃO de PK composta (PK1, PK2… na ordem de `ordinal_position`);
 *   - o TOGGLE rotulado (ícone chave + texto "PK") usado nas duas telas de edição;
 *   - a VALIDAÇÃO não bloqueante (PK nullable, PK que também é FK);
 *   - o BADGE read-only para o DER;
 *   - o helper de REORDENAÇÃO de PK composta (drag) preservando as colunas não-PK.
 *
 * Assim o mesmo controle e a mesma regra valem em todos os lugares — o usuário
 * marca/desmarca PK sempre do mesmo jeito, com a mesma affordance.
 */
import { useState } from "react";
import { Key, AlertTriangle } from "lucide-react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";

/** Forma mínima de um atributo para calcular ordem/validação de PK. */
export interface PkAttrLike {
  attribute_id: string;
  technical_name: string;
  is_primary_key: boolean;
  is_nullable?: boolean | null;
  ordinal_position?: number | null;
}

/**
 * Calcula a posição ordinal de cada PK (1-based) para exibir PK1, PK2…
 *
 * Ordena as colunas PK por `ordinal_position` (ordem de definição da tabela) e,
 * como desempate estável, pelo nome técnico. Retorna um mapa
 * `attribute_id -> número da PK`. Colunas não-PK não entram no mapa.
 */
export function computePkOrdinals(attrs: PkAttrLike[]): Map<string, number> {
  const MAX = Number.MAX_SAFE_INTEGER;
  const pks = attrs
    .filter((a) => a.is_primary_key)
    .sort((a, b) => {
      const pa = a.ordinal_position ?? MAX;
      const pb = b.ordinal_position ?? MAX;
      if (pa !== pb) return pa - pb;
      return a.technical_name.localeCompare(b.technical_name);
    });
  const map = new Map<string, number>();
  pks.forEach((a, i) => map.set(a.attribute_id, i + 1));
  return map;
}

/**
 * Avisos não bloqueantes ao marcar uma coluna como PK.
 * - PK nullable: uma PK nunca deveria aceitar NULL.
 * - PK que também é FK: é permitido (chave herdada), mas normalmente merece
 *   confirmação do usuário — sinalizamos sem impedir.
 */
export function getPkWarnings(opts: {
  isNullable?: boolean | null;
  isForeignKey?: boolean;
}): string[] {
  const warnings: string[] = [];
  if (opts.isNullable) {
    warnings.push("Uma PK não deveria ser nullable (a coluna permite NULL).");
  }
  if (opts.isForeignKey) {
    warnings.push("Esta coluna também é FK — confirme se ela deve ser PK.");
  }
  return warnings;
}

/**
 * Toggle rotulado de PK (ícone chave + "PK"/"PKn"). Usado nas duas telas de
 * edição (detalhe da entidade e editor do diagrama) para manter consistência.
 *
 * Quando `checked` e há `warnings`, mostra um ícone de alerta âmbar com o
 * detalhe no tooltip — aviso, não bloqueio.
 */
export function PkToggle({
  checked,
  ordinal,
  warnings = [],
  disabled = false,
  onCheckedChange,
}: {
  checked: boolean;
  ordinal?: number;
  warnings?: string[];
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const showWarning = checked && warnings.length > 0;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <label
          className={`inline-flex items-center gap-1 select-none rounded px-1 py-0.5 ${
            disabled ? "opacity-50" : "cursor-pointer hover:bg-muted/50"
          }`}
        >
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled}
            onChange={(e) => onCheckedChange(e.target.checked)}
            aria-label="Chave primária"
          />
          <Key
            className={`h-3.5 w-3.5 shrink-0 ${
              checked ? "text-nuclea-primary" : "text-muted-foreground/50"
            }`}
          />
          <span
            className={`text-xs font-medium ${
              checked ? "text-nuclea-primary" : "text-muted-foreground"
            }`}
          >
            {checked && ordinal ? `PK${ordinal}` : "PK"}
          </span>
          {showWarning && (
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
          )}
        </label>
      </TooltipTrigger>
      <TooltipContent className="max-w-[260px]">
        {showWarning
          ? warnings.join(" ")
          : "Marca/desmarca esta coluna como chave primária (PK). Várias colunas = PK composta (numerada PK1, PK2…)."}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Badge read-only de PK para o DER / listas somente-leitura. Mostra o ícone de
 * chave + "PKn" (ou "PK" se `ordinal` ausente). Numeração torna a PK composta
 * legível de relance.
 */
export function PkBadge({
  ordinal,
  className = "",
}: {
  ordinal?: number;
  className?: string;
}) {
  const label = ordinal ? `Chave primária ${ordinal}` : "Chave primária";
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-nuclea-primary shrink-0 ${className}`}
      title={label}
      aria-label={label}
    >
      <Key className="h-3 w-3" />
      <span className="text-[9px] font-semibold leading-none">
        PK{ordinal ?? ""}
      </span>
    </span>
  );
}

/**
 * Calcula as atualizações de `ordinal_position` para reordenar a PK composta
 * via drag, SEM mexer nas colunas não-PK.
 *
 * Estratégia: pega o conjunto de posições ordinais atualmente ocupadas pelas
 * colunas PK e as reatribui na NOVA ordem (movendo `draggedId` para antes de
 * `targetId`). Assim as colunas não-PK ficam intactas e só a ordem relativa das
 * PKs muda. Retorna apenas os atributos cujo `ordinal_position` mudou.
 */
export function reorderedPkOrdinalUpdates(
  attrs: PkAttrLike[],
  draggedId: string,
  targetId: string,
): { attribute_id: string; ordinal_position: number }[] {
  const MAX = Number.MAX_SAFE_INTEGER;
  const pks = attrs
    .filter((a) => a.is_primary_key)
    .sort((a, b) => {
      const pa = a.ordinal_position ?? MAX;
      const pb = b.ordinal_position ?? MAX;
      if (pa !== pb) return pa - pb;
      return a.technical_name.localeCompare(b.technical_name);
    });
  const fromIdx = pks.findIndex((a) => a.attribute_id === draggedId);
  const toIdx = pks.findIndex((a) => a.attribute_id === targetId);
  if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return [];

  // Slots = posições ordinais originais das PKs (fallback para índice sequencial
  // quando ordinal_position estiver ausente). Preservamos os valores; só mudamos
  // a QUEM cada valor pertence.
  const slots = pks.map((a, i) => a.ordinal_position ?? i + 1);

  const reordered = [...pks];
  const [moved] = reordered.splice(fromIdx, 1);
  reordered.splice(toIdx, 0, moved);

  const updates: { attribute_id: string; ordinal_position: number }[] = [];
  reordered.forEach((a, i) => {
    const newPos = slots[i];
    if ((a.ordinal_position ?? null) !== newPos) {
      updates.push({ attribute_id: a.attribute_id, ordinal_position: newPos });
    }
  });
  return updates;
}

/**
 * Hook de drag-and-drop para reordenar PK composta. Só torna arrastáveis as
 * linhas de colunas PK; ao soltar sobre outra PK, chama `onApply` com as
 * atualizações de `ordinal_position`.
 */
export function usePkDragReorder({
  attrs,
  onApply,
  enabled = true,
}: {
  attrs: PkAttrLike[];
  onApply: (
    updates: { attribute_id: string; ordinal_position: number }[],
  ) => void;
  enabled?: boolean;
}) {
  const [dragId, setDragId] = useState<string | null>(null);

  const rowProps = (attr: PkAttrLike) => {
    if (!enabled || !attr.is_primary_key) return {};
    return {
      draggable: true,
      onDragStart: () => setDragId(attr.attribute_id),
      onDragOver: (e: React.DragEvent) => {
        if (dragId && dragId !== attr.attribute_id) e.preventDefault();
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        if (dragId && dragId !== attr.attribute_id) {
          onApply(reorderedPkOrdinalUpdates(attrs, dragId, attr.attribute_id));
        }
        setDragId(null);
      },
      onDragEnd: () => setDragId(null),
    };
  };

  return { rowProps, dragId };
}
