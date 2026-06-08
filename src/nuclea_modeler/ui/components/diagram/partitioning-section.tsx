import { Suspense, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  type PartitionStrategy,
  useGetEntityPartitioningSuspense,
  useListAttributesSuspense,
  useSetEntityPartitioning,
} from "@/lib/api";
import selector from "@/lib/selector";
import { getPartitionStrategiesForTechnology } from "@/components/diagram/index-types-by-tech";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";

interface PartitioningSectionProps {
  entityId: string;
  technology: string | null;
}

export function PartitioningSection(props: PartitioningSectionProps) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-lg border bg-card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-muted/40 transition"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <span className="font-semibold">Particionamento</span>
        <span className="text-xs text-muted-foreground ml-2">
          (estratégia física de divisão)
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <Suspense fallback={<Skeleton className="h-24 w-full" />}>
            <PartitioningContent {...props} />
          </Suspense>
        </div>
      )}
    </section>
  );
}

function PartitioningContent({
  entityId, technology,
}: PartitioningSectionProps) {
  const { data: part } = useGetEntityPartitioningSuspense(entityId, selector());
  const { data: attributes } = useListAttributesSuspense(entityId, selector());
  const qc = useQueryClient();
  const strategies = getPartitionStrategiesForTechnology(technology);
  const [strategy, setStrategy] = useState<PartitionStrategy>(part.strategy);
  const [cols, setCols] = useState<string[]>(part.columns || []);
  const [numPart, setNumPart] = useState<string>(
    part.num_partitions != null ? String(part.num_partitions) : "",
  );
  const [boundsRaw, setBoundsRaw] = useState<string>(
    part.bounds ? JSON.stringify(part.bounds, null, 2) : "",
  );

  // Sincroniza quando troca de entity (Suspense reset)
  useEffect(() => {
    setStrategy(part.strategy);
    setCols(part.columns || []);
    setNumPart(part.num_partitions != null ? String(part.num_partitions) : "");
    setBoundsRaw(part.bounds ? JSON.stringify(part.bounds, null, 2) : "");
  }, [part.entity_id, part.strategy, part.columns, part.num_partitions, part.bounds]);

  const opt = strategies.find((s) => s.value === strategy);

  const { mutate: save, isPending } = useSetEntityPartitioning({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getEntityPartitioning", entityId] });
        qc.invalidateQueries({ queryKey: ["validateEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success("Particionamento atualizado (pendente no ticket)");
      },
      onError: (e) =>
        toast.error("Falha ao salvar particionamento", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });

  function submit() {
    let parsedBounds: Record<string, unknown[]> | null = null;
    if (opt?.needsBounds && boundsRaw.trim()) {
      try {
        parsedBounds = JSON.parse(boundsRaw);
      } catch {
        toast.error("Bounds inválido — deve ser JSON");
        return;
      }
    }
    save({
      entityId,
      data: {
        entity_id: entityId,
        strategy,
        columns: cols.filter(Boolean),
        num_partitions: opt?.needsNumPartitions && numPart ? parseInt(numPart, 10) : null,
        bounds: parsedBounds,
      },
    });
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs font-medium block mb-1">Estratégia</label>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value as PartitionStrategy)}
          className="h-9 rounded border bg-background px-2 text-sm w-full md:w-72"
        >
          {strategies.map((s) => (
            <option key={s.value} value={s.value} title={s.hint}>
              {s.label}
            </option>
          ))}
        </select>
        {opt?.hint && (
          <p className="text-[11px] text-muted-foreground italic mt-1">{opt.hint}</p>
        )}
      </div>

      {strategy !== "NONE" && (
        <div className="space-y-2">
          <label className="text-xs font-medium">Coluna(s)</label>
          {cols.map((c, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <select
                value={c}
                onChange={(e) => {
                  const next = [...cols];
                  next[idx] = e.target.value;
                  setCols(next);
                }}
                className="h-8 rounded border bg-background px-2 text-xs flex-1"
              >
                <option value="">(escolha)</option>
                {attributes.map((a) => (
                  <option key={a.attribute_id} value={a.technical_name}>
                    {a.technical_name}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setCols(cols.filter((_, i) => i !== idx))}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setCols([...cols, ""])}
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar coluna
          </Button>
        </div>
      )}

      {opt?.needsNumPartitions && (
        <div>
          <label className="text-xs font-medium block mb-1">Nº de partições</label>
          <Input
            type="number"
            min={1}
            value={numPart}
            onChange={(e) => setNumPart(e.target.value)}
            className="w-32"
          />
        </div>
      )}

      {opt?.needsBounds && (
        <div>
          <label className="text-xs font-medium block mb-1">
            Bounds (JSON: {`{"part_name": [valor1, valor2]}`})
          </label>
          <textarea
            value={boundsRaw}
            onChange={(e) => setBoundsRaw(e.target.value)}
            className="w-full h-24 rounded border bg-background p-2 text-xs font-mono"
            placeholder='{"part_2024": [2024, 2025], "part_2025": [2025, 2026]}'
          />
        </div>
      )}

      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={isPending}>
          Salvar particionamento
        </Button>
      </div>
    </div>
  );
}
