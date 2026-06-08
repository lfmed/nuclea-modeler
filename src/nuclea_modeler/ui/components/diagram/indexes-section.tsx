import { Suspense, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  type AttributeOut,
  type EntityIndexOut,
  type IndexColumn,
  type IndexType,
  useCreateEntityIndex,
  useDeleteEntityIndex,
  useListAttributesSuspense,
  useListEntityIndexesSuspense,
  useUpdateEntityIndex,
  useValidateEntityIndexesSuspense,
} from "@/lib/api";
import selector from "@/lib/selector";
import { getIndexTypesForTechnology } from "@/components/diagram/index-types-by-tech";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, ChevronDown, ChevronRight, Info, Plus, Trash2, X } from "lucide-react";

interface IndexesSectionProps {
  entityId: string;
  technology: string | null;
}

/**
 * Card colapsável de índices na página da entity. Lista índices catalogados
 * + permite criar/editar/remover. Toda mutação vai pro ticket OPEN do user.
 */
export function IndexesSection(props: IndexesSectionProps) {
  const [open, setOpen] = useState(true);
  return (
    <section className="rounded-lg border bg-card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-muted/40 transition"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <span className="font-semibold">Índices</span>
        <span className="text-xs text-muted-foreground ml-2">
          (estrutura física da tabela)
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <Suspense fallback={<Skeleton className="h-24 w-full" />}>
            <IndexesContent {...props} />
          </Suspense>
        </div>
      )}
    </section>
  );
}

function IndexesContent({ entityId, technology }: IndexesSectionProps) {
  const { data: indexes } = useListEntityIndexesSuspense(entityId, selector());
  const { data: attributes } = useListAttributesSuspense(entityId, selector());
  const { data: warnings } = useValidateEntityIndexesSuspense(entityId, selector());
  const qc = useQueryClient();
  const [editing, setEditing] = useState<EntityIndexOut | null>(null);
  const [creating, setCreating] = useState(false);

  const { mutate: del, isPending: deleting } = useDeleteEntityIndex({
    mutation: {
      onSuccess: (r) => {
        qc.invalidateQueries({ queryKey: ["listEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["validateEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success(`Índice removido (pendente no ticket ${r.ticket_id?.slice(-6)})`);
      },
      onError: (e) =>
        toast.error("Falha ao remover índice", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {indexes.length} índice(s)
        </span>
        {!creating && !editing && (
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Novo índice
          </Button>
        )}
      </div>

      {creating && (
        <IndexForm
          entityId={entityId}
          technology={technology}
          attributes={attributes}
          existing={null}
          onClose={() => setCreating(false)}
        />
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1.5">
          {warnings.map((w, i) => (
            <li
              key={i}
              className={`flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
                w.severity === "warning"
                  ? "border-amber-500/40 bg-amber-500/5"
                  : "border-sky-500/40 bg-sky-500/5"
              }`}
            >
              {w.severity === "warning" ? (
                <AlertTriangle className="h-3.5 w-3.5 text-amber-600 mt-0.5 shrink-0" />
              ) : (
                <Info className="h-3.5 w-3.5 text-sky-600 mt-0.5 shrink-0" />
              )}
              <span>{w.message}</span>
            </li>
          ))}
        </ul>
      )}

      {indexes.length === 0 && !creating && (
        <p className="text-xs text-muted-foreground italic py-2">
          Nenhum índice catalogado nesta tabela.
        </p>
      )}

      <div className="space-y-2">
        {indexes.map((idx) => {
          if (editing?.index_id === idx.index_id) {
            return (
              <IndexForm
                key={idx.index_id}
                entityId={entityId}
                technology={technology}
                attributes={attributes}
                existing={idx}
                onClose={() => setEditing(null)}
              />
            );
          }
          return (
            <IndexRow
              key={idx.index_id}
              idx={idx}
              onEdit={() => setEditing(idx)}
              onDelete={() => {
                if (window.confirm(`Remover índice "${idx.index_name}"?`)) {
                  del({ entityId, indexId: idx.index_id });
                }
              }}
              deleting={deleting}
            />
          );
        })}
      </div>
    </div>
  );
}

function IndexRow({
  idx, onEdit, onDelete, deleting,
}: {
  idx: EntityIndexOut;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div className="rounded-md border bg-background p-3 text-sm space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-sm">
          <span className="font-medium">{idx.index_name}</span>
          <Badge variant="outline" className="text-[10px] font-mono">
            {idx.index_type}
          </Badge>
          {idx.is_unique && idx.index_type !== "UNIQUE" && (
            <Badge variant="outline" className="text-[10px]">UNIQUE</Badge>
          )}
          {idx.partial_where && (
            <Badge variant="outline" className="text-[10px]">PARTIAL</Badge>
          )}
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={onEdit}>editar</Button>
          <Button size="sm" variant="ghost" onClick={onDelete} disabled={deleting}>
            <Trash2 className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      </div>
      <div className="font-mono text-xs text-muted-foreground">
        {idx.columns.map((c, i) => (
          <span key={i}>
            {i > 0 && ", "}
            {c.name}
            {c.direction === "DESC" && <span className="text-amber-600"> DESC</span>}
          </span>
        ))}
      </div>
      {idx.include_columns.length > 0 && (
        <div className="text-[11px] text-muted-foreground">
          INCLUDE: <span className="font-mono">{idx.include_columns.join(", ")}</span>
        </div>
      )}
      {idx.partial_where && (
        <div className="text-[11px] text-muted-foreground">
          WHERE <span className="font-mono">{idx.partial_where}</span>
        </div>
      )}
    </div>
  );
}

function IndexForm({
  entityId, technology, attributes, existing, onClose,
}: {
  entityId: string;
  technology: string | null;
  attributes: AttributeOut[];
  existing: EntityIndexOut | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const indexTypes = getIndexTypesForTechnology(technology);
  const [name, setName] = useState(existing?.index_name || "");
  const [indexType, setIndexType] = useState<IndexType>(
    existing?.index_type || (indexTypes[0]?.value ?? "BTREE"),
  );
  const [cols, setCols] = useState<IndexColumn[]>(
    existing?.columns.length
      ? existing.columns
      : [{ name: attributes[0]?.technical_name || "", direction: "ASC" }],
  );
  const [includeCols, setIncludeCols] = useState<string[]>(
    existing?.include_columns || [],
  );
  const [partialWhere, setPartialWhere] = useState(existing?.partial_where || "");
  const [isUnique, setIsUnique] = useState(existing?.is_unique || false);

  const opt = indexTypes.find((t) => t.value === indexType);
  const supportsInclude = opt?.supportsInclude ?? false;
  const supportsPartial = opt?.supportsPartial ?? false;

  const { mutate: create, isPending: creating } = useCreateEntityIndex({
    mutation: {
      onSuccess: (r) => {
        qc.invalidateQueries({ queryKey: ["listEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["validateEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success(`Índice criado (pendente no ticket ${r.pending_op})`);
        onClose();
      },
      onError: (e) =>
        toast.error("Falha ao criar índice", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });
  const { mutate: update, isPending: updating } = useUpdateEntityIndex({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["validateEntityIndexes", entityId] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success("Índice atualizado");
        onClose();
      },
      onError: (e) =>
        toast.error("Falha ao atualizar índice", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const cleanCols = cols.filter((c) => c.name);
    if (!name.trim() || cleanCols.length === 0) {
      toast.error("Nome e ao menos 1 coluna são obrigatórios");
      return;
    }
    const data = {
      entity_id: entityId,
      index_name: name.trim(),
      index_type: indexType,
      columns: cleanCols,
      include_columns: supportsInclude ? includeCols.filter(Boolean) : [],
      partial_where: supportsPartial && partialWhere.trim() ? partialWhere.trim() : null,
      is_unique: isUnique,
    };
    if (existing) {
      update({ entityId, indexId: existing.index_id, data });
    } else {
      create({ entityId, data });
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-md border bg-muted/30 p-3 space-y-3"
    >
      <div className="grid md:grid-cols-2 gap-3">
        <Input
          placeholder="Nome do índice (ex: ix_pedido_cliente)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          value={indexType}
          onChange={(e) => setIndexType(e.target.value as IndexType)}
          className="h-9 rounded border bg-background px-2 text-sm"
        >
          {indexTypes.map((t) => (
            <option key={t.value} value={t.value} title={t.hint}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {opt?.hint && (
        <p className="text-[11px] text-muted-foreground italic">{opt.hint}</p>
      )}

      <div className="space-y-2">
        <label className="text-xs font-medium">Colunas (ordem importa)</label>
        {cols.map((c, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <select
              value={c.name}
              onChange={(e) => {
                const next = [...cols];
                next[idx] = { ...c, name: e.target.value };
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
            <select
              value={c.direction}
              onChange={(e) => {
                const next = [...cols];
                next[idx] = { ...c, direction: e.target.value as "ASC" | "DESC" };
                setCols(next);
              }}
              className="h-8 rounded border bg-background px-2 text-xs w-20"
            >
              <option value="ASC">ASC</option>
              <option value="DESC">DESC</option>
            </select>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setCols(cols.filter((_, i) => i !== idx))}
              disabled={cols.length === 1}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            setCols([...cols, { name: attributes[0]?.technical_name || "", direction: "ASC" }])
          }
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar coluna
        </Button>
      </div>

      {supportsInclude && (
        <div>
          <label className="text-xs font-medium block mb-1">
            Colunas INCLUDE (covering)
          </label>
          <Input
            placeholder="col_a, col_b — separadas por vírgula"
            value={includeCols.join(", ")}
            onChange={(e) =>
              setIncludeCols(
                e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              )
            }
          />
        </div>
      )}

      {supportsPartial && (
        <div>
          <label className="text-xs font-medium block mb-1">
            Partial WHERE (opcional)
          </label>
          <Input
            placeholder="ex: status = 'ATIVO'"
            value={partialWhere}
            onChange={(e) => setPartialWhere(e.target.value)}
          />
        </div>
      )}

      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={isUnique}
          onChange={(e) => setIsUnique(e.target.checked)}
        />
        Forçar UNIQUE
      </label>

      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" disabled={creating || updating}>
          {existing ? "Atualizar" : "Criar"}
        </Button>
      </div>
    </form>
  );
}
