/**
 * BatchBar de flags — barra flutuante reutilizada pelas listagens de entidades e
 * de atributos (Blocos 3 + 6).
 *
 * Espelha o padrão da BatchBar de tickets (tickets.index.tsx): aparece quando há
 * itens selecionados e oferece ações em lote. Aqui as ações são "Aplicar flags"
 * (abre o `FlagPickerModal` multi-select) e "Remover flags" (abre um seletor
 * simples das flags a remover). Delega a chamada de API ao componente-pai via
 * callbacks, para manter este componente agnóstico de entidade vs. atributo.
 *
 * TODO [P1 — plano §6.3]: "Templates de flags" (ex.: "pacote LGPD mínimo")
 * aplicáveis à seleção. Backend não tem catálogo de templates ainda; quando
 * existir, adicionar um botão "Aplicar template" ao lado de "Aplicar flags" que
 * expande para um conjunto pré-definido de BatchFlagSpec e chama o mesmo onApply.
 */
import { Suspense, useState } from "react";
import { toast } from "sonner";

import {
  useListFlagsSuspense,
  type BatchFlagResult,
  type BatchFlagSpec,
  type FlagCategory,
  type FlagOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Tag, Trash2 } from "lucide-react";
import { FlagPickerModal } from "@/components/flags/flag-picker";

const CATEGORY_ORDER: FlagCategory[] = ["LGPD", "USE", "QUALITY", "CUSTOM"];

/**
 * Toast padronizado para o resultado de um lote de flags: "X ok · Y falha",
 * mostrando o primeiro erro quando há falhas. Reutilizado por entidades e
 * atributos (mesma UX que a BatchBar de tickets).
 */
export function toastBatchFlagResult(result: BatchFlagResult) {
  const desc = `${result.succeeded} ok · ${result.failed} com falha`;
  if (result.failed > 0) {
    const firstErr = result.results.find((r) => !r.ok && r.error)?.error;
    toast.warning(`Flags em lote: ${desc}`, { description: firstErr ?? undefined });
  } else {
    toast.success(`Flags em lote: ${desc}`);
  }
}

export function FlagBatchBar({
  count,
  busy,
  onClear,
  onApply,
  onRemove,
  noun = "item",
}: {
  count: number;
  busy: boolean;
  onClear: () => void;
  /** Aplica as flags escolhidas (multi) aos alvos selecionados. */
  onApply: (specs: BatchFlagSpec[]) => void;
  /** Remove as flags escolhidas (por flag_id) dos alvos selecionados. */
  onRemove: (flagIds: string[]) => void;
  /** Palavra usada no texto ("entidade", "atributo"). */
  noun?: string;
}) {
  const [mode, setMode] = useState<"apply" | "remove" | null>(null);

  return (
    <div className="sticky top-2 z-30 flex flex-wrap items-center gap-2 rounded-md border bg-muted/60 backdrop-blur p-3 shadow-sm">
      <span className="text-sm font-medium">
        {count} {noun}
        {count === 1 ? "" : "s"} selecionado{count === 1 ? "" : "s"}
      </span>
      <div className="flex-1" />
      <Button size="sm" disabled={busy} onClick={() => setMode("apply")}>
        <Tag className="mr-2 h-4 w-4" />
        Aplicar flags
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => setMode("remove")}
      >
        <Trash2 className="mr-2 h-4 w-4" />
        Remover flags
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={onClear}>
        Limpar
      </Button>

      {mode === "apply" && (
        <Suspense fallback={null}>
          <FlagPickerModal
            title={`Aplicar flags a ${count} ${noun}${count === 1 ? "" : "s"}`}
            subtitle="As flags marcadas serão aplicadas a todos os selecionados. Flags LGPD exigem justificativa."
            onClose={() => setMode(null)}
            applying={busy}
            onApply={(specs) => {
              onApply(specs);
              setMode(null);
            }}
          />
        </Suspense>
      )}
      {mode === "remove" && (
        <Suspense fallback={null}>
          <FlagRemoveModal
            noun={noun}
            count={count}
            busy={busy}
            onClose={() => setMode(null)}
            onRemove={(flagIds) => {
              onRemove(flagIds);
              setMode(null);
            }}
          />
        </Suspense>
      )}
    </div>
  );
}

/**
 * Modal simples para escolher quais flags remover em lote. Não precisa de
 * justificativa; só marca as flags que devem sair dos alvos selecionados.
 */
function FlagRemoveModal({
  count,
  noun,
  busy,
  onClose,
  onRemove,
}: {
  count: number;
  noun: string;
  busy?: boolean;
  onClose: () => void;
  onRemove: (flagIds: string[]) => void;
}) {
  const { data: flags } = useListFlagsSuspense({}, selector());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const grouped: Record<FlagCategory, FlagOut[]> = {
    LGPD: [],
    USE: [],
    QUALITY: [],
    CUSTOM: [],
  };
  for (const f of flags) grouped[f.category]?.push(f);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg shadow-lg w-full max-w-lg max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b">
          <h3 className="font-semibold">
            Remover flags de {count} {noun}
            {count === 1 ? "" : "s"}
          </h3>
          <p className="text-xs text-muted-foreground">
            Marque as flags a remover. Se um alvo não tiver a flag, é ignorado (sem
            erro).
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {CATEGORY_ORDER.map((cat) => {
            const list = grouped[cat];
            if (!list || list.length === 0) return null;
            return (
              <div key={cat}>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">
                  {cat}
                </p>
                <div className="space-y-1">
                  {list.map((f) => (
                    <label
                      key={f.flag_id}
                      className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(f.flag_id)}
                        onChange={() => toggle(f.flag_id)}
                        className="h-4 w-4 accent-nuclea-primary"
                      />
                      <span
                        className="h-3 w-3 rounded-full border border-black/10"
                        style={{ backgroundColor: f.color_hex || "#6C757D" }}
                      />
                      <span>{f.display_name}</span>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div className="p-4 border-t flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            disabled={selected.size === 0 || busy}
            onClick={() => onRemove(Array.from(selected))}
          >
            {busy ? "Removendo..." : `Remover (${selected.size})`}
          </Button>
        </div>
      </div>
    </div>
  );
}
