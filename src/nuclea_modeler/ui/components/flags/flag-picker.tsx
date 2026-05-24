/**
 * Reusable flag application UI — used for both entities and attributes.
 *
 * Renders existing flag chips with a `×` to remove, plus a "+ Aplicar flag"
 * button that opens a picker (search input + flags grouped by category +
 * justification textarea required when the flag demands it).
 */
import { useMemo, useState } from "react";
import { Plus } from "lucide-react";

import {
  useListFlagsSuspense,
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
  label = "Aplicar flag",
}: {
  applied: AppliedFlag[];
  onApply: (data: { flag_id: string; justification: string | null }) => void;
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
          onApply={(data) => {
            onApply(data);
            setOpen(false);
          }}
          applying={applying}
        />
      )}
    </div>
  );
}

function FlagPickerModal({
  appliedFlagIds,
  onClose,
  onApply,
  applying,
}: {
  appliedFlagIds: string[];
  onClose: () => void;
  onApply: (data: { flag_id: string; justification: string | null }) => void;
  applying?: boolean;
}) {
  const { data: flags } = useListFlagsSuspense({ isActive: true }, selector());
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<FlagOut | null>(null);
  const [justification, setJustification] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    if (!selected) {
      setError("Selecione uma flag.");
      return;
    }
    if (selected.requires_justification && !justification.trim()) {
      setError("Esta flag exige uma justificativa.");
      return;
    }
    onApply({
      flag_id: selected.flag_id,
      justification: justification.trim() || null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg shadow-lg w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b">
          <h3 className="font-semibold">Aplicar flag</h3>
          <p className="text-xs text-muted-foreground">
            Busque pelo nome ou chave. Flags LGPD exigem justificativa.
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
                  {list.map((f) => (
                    <button
                      key={f.flag_id}
                      type="button"
                      onClick={() => setSelected(f)}
                      className={
                        "flex items-start gap-2 rounded border px-2 py-1.5 text-left text-xs hover:bg-muted/50 transition-colors " +
                        (selected?.flag_id === f.flag_id
                          ? "border-nuclea-primary bg-nuclea-primary/5"
                          : "border-transparent")
                      }
                    >
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
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        {selected && (
          <div className="p-4 border-t space-y-2">
            <div className="flex items-center gap-2">
              <FlagChip flag={selected} />
              <span className="text-xs text-muted-foreground truncate">
                {selected.description}
              </span>
            </div>
            <textarea
              className="w-full text-sm rounded border p-2 focus:outline-none focus:ring-1 focus:ring-nuclea-primary"
              rows={2}
              placeholder={
                selected.requires_justification
                  ? "Justificativa (obrigatória)*"
                  : "Justificativa (opcional)"
              }
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
            />
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}
        <div className="p-4 border-t flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" disabled={!selected || applying} onClick={submit}>
            {applying ? "Aplicando..." : "Aplicar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
