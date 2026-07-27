/**
 * Reusable flag application UI — used for both entities and attributes.
 *
 * Renders existing flag chips with a `×` to remove, plus a "+ Aplicar flags"
 * button that opens a picker. O picker é MULTI-SELECT (Blocos 3 + 6): dá para
 * marcar várias flags de uma vez e aplicar todas num clique. Flags que exigem
 * justificativa pedem uma justificativa POR flag antes de habilitar o "Aplicar".
 *
 * O modal (`FlagPickerModal`) é exportado e reutilizado pela BatchBar das
 * listagens de entidades/atributos, para não duplicar a UI de seleção.
 */
import { useMemo, useState } from "react";
import { Plus } from "lucide-react";

import {
  useListFlagsSuspense,
  type BatchFlagSpec,
  type FlagCategory,
  type FlagOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { FlagChip } from "@/routes/_sidebar/flags";

export interface AppliedFlag {
  applied_flag_id: string;
  flag: FlagOut;
  justification?: string | null;
  is_propagated?: boolean;
}

const CATEGORY_ORDER: FlagCategory[] = ["LGPD", "USE", "QUALITY", "CUSTOM"];
const CATEGORY_LABEL: Record<FlagCategory, string> = {
  LGPD: "LGPD / Privacidade",
  USE: "Uso do dado",
  QUALITY: "Qualidade",
  CUSTOM: "Personalizadas",
};

export function FlagPicker({
  applied,
  onApply,
  onRemove,
  applying,
  size = "default",
  label = "Aplicar flags",
}: {
  applied: AppliedFlag[];
  /** Recebe TODAS as flags escolhidas de uma vez (multi-select). */
  onApply: (specs: BatchFlagSpec[]) => void;
  onRemove: (appliedFlagId: string) => void;
  applying?: boolean;
  size?: "default" | "small";
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {applied.length === 0 && (
        <span className="text-xs text-muted-foreground italic">
          Sem flags aplicadas.
        </span>
      )}
      {applied.map((af) => (
        <span key={af.applied_flag_id} className="inline-flex items-center gap-1">
          <FlagChip
            flag={af.flag}
            small={size === "small"}
            onRemove={() => onRemove(af.applied_flag_id)}
          />
          {af.is_propagated && (
            <Badge variant="outline" className="text-[10px]">
              propagada
            </Badge>
          )}
        </span>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={size === "small" ? "h-6 px-2 text-xs" : ""}
        onClick={() => setOpen(true)}
      >
        <Plus className={size === "small" ? "mr-1 h-3 w-3" : "mr-1 h-3.5 w-3.5"} />
        {label}
      </Button>
      {open && (
        <FlagPickerModal
          appliedFlagIds={applied.map((af) => af.flag.flag_id)}
          onClose={() => setOpen(false)}
          onApply={(specs) => {
            onApply(specs);
            setOpen(false);
          }}
          applying={applying}
        />
      )}
    </div>
  );
}

/**
 * Modal de seleção MULTI de flags. Mantém um mapa `flag_id → justificativa` para
 * as flags marcadas. Só habilita "Aplicar" quando todas as flags que exigem
 * justificativa têm texto preenchido.
 *
 * Exportado para a BatchBar das listagens reaproveitar exatamente a mesma UI.
 */
export function FlagPickerModal({
  appliedFlagIds = [],
  onClose,
  onApply,
  applying,
  title = "Aplicar flags",
  subtitle,
}: {
  /** Flags já aplicadas ao alvo — omitidas da lista (evita ruído). Em lote,
   *  deixe vazio: os alvos têm conjuntos de flags diferentes. */
  appliedFlagIds?: string[];
  onClose: () => void;
  onApply: (specs: BatchFlagSpec[]) => void;
  applying?: boolean;
  title?: string;
  subtitle?: string;
}) {
  const { data: flags } = useListFlagsSuspense({ isActive: true }, selector());
  const [search, setSearch] = useState("");
  // Map de flag_id → { flag, justificativa }. Ordem de inserção preservada.
  const [selected, setSelected] = useState<
    Map<string, { flag: FlagOut; justification: string }>
  >(new Map());
  const [error, setError] = useState<string | null>(null);

  const toggle = (f: FlagOut) =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(f.flag_id)) next.delete(f.flag_id);
      else next.set(f.flag_id, { flag: f, justification: "" });
      return next;
    });

  const setJustification = (flagId: string, value: string) =>
    setSelected((prev) => {
      const next = new Map(prev);
      const cur = next.get(flagId);
      if (cur) next.set(flagId, { ...cur, justification: value });
      return next;
    });

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = flags.filter((f) => {
      if (appliedFlagIds.includes(f.flag_id)) return false;
      if (!q) return true;
      return (
        f.display_name.toLowerCase().includes(q) ||
        f.flag_key.toLowerCase().includes(q) ||
        (f.description || "").toLowerCase().includes(q)
      );
    });
    const g: Record<FlagCategory, FlagOut[]> = {
      LGPD: [],
      USE: [],
      QUALITY: [],
      CUSTOM: [],
    };
    for (const f of filtered) g[f.category]?.push(f);
    return g;
  }, [flags, search, appliedFlagIds]);

  const submit = () => {
    if (selected.size === 0) {
      setError("Selecione ao menos uma flag.");
      return;
    }
    // Valida justificativa por flag antes de aplicar (o backend também valida,
    // mas checar aqui evita idas e voltas ao servidor).
    const missing = Array.from(selected.values()).filter(
      (s) => s.flag.requires_justification && !s.justification.trim(),
    );
    if (missing.length > 0) {
      setError(
        `Justificativa obrigatória em: ${missing
          .map((s) => s.flag.display_name)
          .join(", ")}.`,
      );
      return;
    }
    const specs: BatchFlagSpec[] = Array.from(selected.values()).map((s) => ({
      flag_id: s.flag.flag_id,
      justification: s.justification.trim() || null,
    }));
    onApply(specs);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg shadow-lg w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b">
          <h3 className="font-semibold">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {subtitle ??
              "Marque uma ou mais flags. Flags LGPD exigem justificativa."}
          </p>
        </div>
        <div className="p-4 border-b">
          <Input
            placeholder="Buscar flag..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {CATEGORY_ORDER.map((cat) => {
            const list = groups[cat];
            if (!list || list.length === 0) return null;
            return (
              <div key={cat}>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">
                  {CATEGORY_LABEL[cat]}
                </p>
                <div className="grid sm:grid-cols-2 gap-1.5">
                  {list.map((f) => {
                    const isSel = selected.has(f.flag_id);
                    return (
                      <button
                        key={f.flag_id}
                        type="button"
                        onClick={() => toggle(f)}
                        className={
                          "flex items-start gap-2 rounded border px-2 py-1.5 text-left text-xs hover:bg-muted/50 transition-colors " +
                          (isSel
                            ? "border-nuclea-primary bg-nuclea-primary/5"
                            : "border-transparent")
                        }
                      >
                        <input
                          type="checkbox"
                          checked={isSel}
                          readOnly
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-nuclea-primary pointer-events-none"
                        />
                        <span
                          className="mt-0.5 h-3 w-3 rounded-full border border-black/10 flex-shrink-0"
                          style={{ backgroundColor: f.color_hex || "#6C757D" }}
                        />
                        <span className="flex-1 min-w-0">
                          <span className="font-medium block">{f.display_name}</span>
                          <span className="font-mono text-[10px] text-muted-foreground block">
                            {f.flag_key}
                          </span>
                        </span>
                        {f.requires_justification && (
                          <span className="text-[10px] text-amber-700 flex-shrink-0">
                            just.
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        {selected.size > 0 && (
          <div className="p-4 border-t space-y-3 max-h-[30vh] overflow-y-auto">
            {Array.from(selected.values()).map(({ flag, justification }) => (
              <div key={flag.flag_id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <FlagChip flag={flag} small />
                  <span className="text-xs text-muted-foreground truncate">
                    {flag.description}
                  </span>
                </div>
                <textarea
                  className="w-full text-sm rounded border p-2 focus:outline-none focus:ring-1 focus:ring-nuclea-primary"
                  rows={2}
                  placeholder={
                    flag.requires_justification
                      ? "Justificativa (obrigatória)*"
                      : "Justificativa (opcional)"
                  }
                  value={justification}
                  onChange={(e) => setJustification(flag.flag_id, e.target.value)}
                />
              </div>
            ))}
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}
        <div className="p-4 border-t flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {selected.size} flag(s) selecionada(s)
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={selected.size === 0 || applying}
              onClick={submit}
            >
              {applying ? "Aplicando..." : "Aplicar"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
