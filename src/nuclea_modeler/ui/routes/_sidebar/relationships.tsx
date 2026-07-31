import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useEffect, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { saveLastSystemId } from "@/lib/persist-search";

import {
  useCreateRelationship,
  useDeleteRelationship,
  useListAttributesSuspense,
  useListEntitiesSuspense,
  useListRelationshipsSuspense,
  useListSystemsSuspense,
  useListRelationshipFlagsSuspense,
  useBatchApplyRelationshipFlags,
  useRemoveRelationshipFlag,
  type Cardinality,
  type EntityListOut,
  type FKRule,
  type RelType,
  type RelationshipListOut,
} from "@/lib/api";
import { toast } from "sonner";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Link2, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";
import { FlagPicker } from "@/components/flags/flag-picker";

export const Route = createFileRoute("/_sidebar/relationships")({
  component: RelationshipsPage,
  validateSearch: (search: Record<string, unknown>) => ({
    system: (search.system as string) || undefined,
  }),
});

function RelationshipsPage() {
  return (
    <div className="space-y-6">
      <Header />
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar relacionamentos
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Tentar novamente
                  </Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<TableSkeleton />}>
              <RelationshipsBody />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function Header() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <h1 className="text-3xl font-bold tracking-tight">Relacionamentos</h1>
        <Badge variant="outline" className="font-mono">
          M3+
        </Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Defina relacionamentos entre entidades — manuais ou descobertos via
        engenharia reversa. Suporta cardinalidades, tipo (1:1, 1:N, N:M, INHERIT)
        e regras de FK.
      </p>
    </div>
  );
}

function RelationshipsBody() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { system: systemFromUrl } = Route.useSearch();
  const navigate = useNavigate();

  // Inicializa systemId: URL → último salvo → primeiro da lista
  const initialSystem = systemFromUrl || "";
  const [systemId, setSystemId] = useState<string>(initialSystem);
  const [openDialog, setOpenDialog] = useState(false);

  // Sincroniza estado na URL e sessionStorage
  useEffect(() => {
    if (systemId) saveLastSystemId(systemId);
    navigate({
      search: {
        system: systemId || undefined,
      },
    });
  }, [systemId, navigate]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[240px]">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Sistema
              </label>
              <select
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">Todos os sistemas</option>
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.system_name}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={() => setOpenDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Novo relacionamento
            </Button>
          </div>
        </CardContent>
      </Card>

      <Suspense fallback={<TableSkeleton />}>
        <RelationshipsTable systemId={systemId} />
      </Suspense>

      {openDialog && (
        <NewRelationshipDialog
          initialSystemId={systemId}
          onClose={() => setOpenDialog(false)}
        />
      )}
    </div>
  );
}

function RelationshipsTable({ systemId }: { systemId: string }) {
  const { data: rels } = useListRelationshipsSuspense(
    { systemId: systemId || undefined },
    selector(),
  );
  const qc = useQueryClient();
  const { mutate: del, isPending: deleting } = useDeleteRelationship({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRelationships"] });
        if (systemId) {
          qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        }
      },
    },
  });

  if (!rels || rels.length === 0) {
    return (
      <EmptyState
        icon={<Link2 className="h-10 w-10" />}
        title="Sem relacionamentos cadastrados"
        description={
          <>
            Relacionamentos (FKs lógicas) ligam entidades no DER e geram linhagem.
            Você pode criar pelo formulário acima ou arrastando uma aresta entre
            duas tabelas no <strong>Diagrama</strong>.
          </>
        }
        primaryAction={{ label: "Abrir Diagrama", to: "/diagram" }}
      />
    );
  }

  const handleDelete = (rel: RelationshipListOut) => {
    if (
      confirm(
        `Excluir relacionamento ${rel.source_entity_label || rel.source_entity_id} → ${rel.target_entity_label || rel.target_entity_id}?`,
      )
    ) {
      del({ relationshipId: rel.relationship_id });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Relacionamentos ({rels.length})</CardTitle>
        <CardDescription>Ordenado por última atualização</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Origem → Destino</th>
                <th className="py-2 pr-3 font-medium">Tipo</th>
                <th className="py-2 pr-3 font-medium">Cardinalidades</th>
                <th className="py-2 pr-3 font-medium">Origem</th>
                <th className="py-2 pr-3 font-medium">Descrição</th>
                <th className="py-2 pr-3 font-medium">Flags</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {rels.map((r) => (
                <tr key={r.relationship_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <span className="text-nuclea-primary">
                      {r.source_entity_label || r.source_entity_id}
                    </span>
                    <span className="mx-2 text-muted-foreground">→</span>
                    <span className="text-nuclea-accent">
                      {r.target_entity_label || r.target_entity_id}
                    </span>
                  </td>
                  <td className="py-2 pr-3">
                    <RelTypeBadge value={r.rel_type} />
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {r.source_cardinality || "—"}{" "}
                    <span className="opacity-60">↔</span>{" "}
                    {r.target_cardinality || "—"}
                  </td>
                  <td className="py-2 pr-3">
                    <OriginBadge value={r.origin} />
                  </td>
                  <td className="py-2 pr-3 max-w-xs truncate">
                    {r.description || (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <Suspense fallback={<span className="text-[10px] text-muted-foreground">…</span>}>
                      <RelationshipFlagsCell relationshipId={r.relationship_id} />
                    </Suspense>
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    <Link
                      to="/diagram"
                      search={{ system: r.system_id }}
                      className="hover:text-nuclea-primary hover:underline"
                    >
                      {r.system_name || r.system_id}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(r)}
                      disabled={deleting}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function RelTypeBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const color =
    value === "INHERIT"
      ? "bg-purple-500/10 text-purple-700 border-purple-500/30 dark:text-purple-300"
      : value === "N:M"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-sky-500/10 text-sky-700 border-sky-500/30 dark:text-sky-300";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium font-mono ${color}`}
    >
      {value}
    </span>
  );
}

function OriginBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const isManual = value === "MANUAL";
  const cls = isManual
    ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300"
    : "bg-slate-500/10 text-slate-700 border-slate-500/30 dark:text-slate-300";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {value}
    </span>
  );
}

// ─── New Relationship Dialog ────────────────────────────────────────────────

function NewRelationshipDialog({
  initialSystemId,
  onClose,
}: {
  initialSystemId: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg border shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Novo relacionamento</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <Suspense
          fallback={
            <div className="p-6">
              <Skeleton className="h-40 w-full" />
            </div>
          }
        >
          <RelationshipForm
            initialSystemId={initialSystemId}
            onClose={onClose}
          />
        </Suspense>
      </div>
    </div>
  );
}

function RelationshipForm({
  initialSystemId,
  onClose,
}: {
  initialSystemId: string;
  onClose: () => void;
}) {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: allEntities } = useListEntitiesSuspense({}, selector());

  const [systemId, setSystemId] = useState(
    initialSystemId || systems[0]?.system_id || "",
  );
  const [sourceEntityId, setSourceEntityId] = useState("");
  const [targetEntityId, setTargetEntityId] = useState("");
  const [sourceAttrIds, setSourceAttrIds] = useState<string[]>([]);
  const [targetAttrIds, setTargetAttrIds] = useState<string[]>([]);
  const [relType, setRelType] = useState<RelType>("1:N");
  const [sourceCard, setSourceCard] = useState<Cardinality>("OPTIONAL");
  const [targetCard, setTargetCard] = useState<Cardinality>("MANDATORY");
  const [description, setDescription] = useState("");
  const [fkUpdate, setFkUpdate] = useState<FKRule | "">("");
  const [fkDelete, setFkDelete] = useState<FKRule | "">("");

  const qc = useQueryClient();
  const { mutate: create, isPending, error } = useCreateRelationship({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRelationships"] });
        qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        onClose();
      },
    },
  });

  const entitiesInSystem = useMemo<EntityListOut[]>(
    () => allEntities.filter((e) => e.system_id === systemId),
    [allEntities, systemId],
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        system_id: systemId,
        source_entity_id: sourceEntityId,
        target_entity_id: targetEntityId,
        source_attr_ids: sourceAttrIds,
        target_attr_ids: targetAttrIds,
        rel_type: relType,
        source_cardinality: sourceCard,
        target_cardinality: targetCard,
        description: description || null,
        fk_update_rule: (fkUpdate || null) as FKRule | null,
        fk_delete_rule: (fkDelete || null) as FKRule | null,
      },
    });
  };

  return (
    <form onSubmit={submit} className="p-4 space-y-4">
      <Field label="Sistema" required>
        <select
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={systemId}
          onChange={(e) => {
            setSystemId(e.target.value);
            setSourceEntityId("");
            setTargetEntityId("");
            setSourceAttrIds([]);
            setTargetAttrIds([]);
          }}
          required
        >
          <option value="">Selecione...</option>
          {systems.map((s) => (
            <option key={s.system_id} value={s.system_id}>
              {s.system_name}
            </option>
          ))}
        </select>
      </Field>

      <div className="grid md:grid-cols-2 gap-4">
        <Field label="Entidade origem" required>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={sourceEntityId}
            onChange={(e) => {
              setSourceEntityId(e.target.value);
              setSourceAttrIds([]);
            }}
            disabled={!systemId}
            required
          >
            <option value="">Selecione...</option>
            {entitiesInSystem.map((ent) => (
              <option key={ent.entity_id} value={ent.entity_id}>
                {ent.schema_name}.{ent.technical_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Entidade destino" required>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={targetEntityId}
            onChange={(e) => {
              setTargetEntityId(e.target.value);
              setTargetAttrIds([]);
            }}
            disabled={!systemId}
            required
          >
            <option value="">Selecione...</option>
            {entitiesInSystem.map((ent) => (
              <option key={ent.entity_id} value={ent.entity_id}>
                {ent.schema_name}.{ent.technical_name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Field label="Colunas origem">
          {sourceEntityId ? (
            <Suspense fallback={<Skeleton className="h-20 w-full" />}>
              <AttributesMultiSelect
                entityId={sourceEntityId}
                selected={sourceAttrIds}
                onChange={setSourceAttrIds}
              />
            </Suspense>
          ) : (
            <p className="text-xs text-muted-foreground">
              Selecione uma entidade origem primeiro.
            </p>
          )}
        </Field>
        <Field label="Colunas destino">
          {targetEntityId ? (
            <Suspense fallback={<Skeleton className="h-20 w-full" />}>
              <AttributesMultiSelect
                entityId={targetEntityId}
                selected={targetAttrIds}
                onChange={setTargetAttrIds}
              />
            </Suspense>
          ) : (
            <p className="text-xs text-muted-foreground">
              Selecione uma entidade destino primeiro.
            </p>
          )}
        </Field>
      </div>

      <Field label="Tipo de relacionamento" required>
        <div className="flex flex-wrap gap-2">
          {(["1:1", "1:N", "N:M", "INHERIT"] as RelType[]).map((rt) => (
            <label
              key={rt}
              className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs font-mono ${
                relType === rt
                  ? "bg-nuclea-primary text-primary-foreground border-nuclea-primary"
                  : "hover:bg-muted"
              }`}
            >
              <input
                type="radio"
                name="rel_type"
                value={rt}
                checked={relType === rt}
                onChange={() => setRelType(rt)}
                className="sr-only"
              />
              {rt}
            </label>
          ))}
        </div>
      </Field>

      <div className="grid md:grid-cols-2 gap-4">
        <Field label="Cardinalidade origem" required>
          <CardinalityRadio value={sourceCard} onChange={setSourceCard} name="src_card" />
        </Field>
        <Field label="Cardinalidade destino" required>
          <CardinalityRadio value={targetCard} onChange={setTargetCard} name="tgt_card" />
        </Field>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Field label="Regra FK — UPDATE">
          <FkRuleSelect value={fkUpdate} onChange={setFkUpdate} />
        </Field>
        <Field label="Regra FK — DELETE">
          <FkRuleSelect value={fkDelete} onChange={setFkDelete} />
        </Field>
      </div>

      <Field label="Descrição">
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          placeholder="Ex.: cliente_id em pedido referencia cliente.id"
        />
      </Field>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-xs text-destructive">
          <pre className="whitespace-pre-wrap">{String(error)}</pre>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          type="submit"
          disabled={
            isPending ||
            !systemId ||
            !sourceEntityId ||
            !targetEntityId ||
            sourceEntityId === targetEntityId
          }
        >
          {isPending ? "Salvando..." : "Criar relacionamento"}
        </Button>
      </div>
    </form>
  );
}

function AttributesMultiSelect({
  entityId,
  selected,
  onChange,
}: {
  entityId: string;
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  const toggle = (id: string) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id));
    else onChange([...selected, id]);
  };
  if (attrs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">Sem atributos cadastrados.</p>
    );
  }
  return (
    <div className="max-h-32 overflow-y-auto border rounded-md p-2 space-y-1">
      {attrs.map((a) => (
        <label
          key={a.attribute_id}
          className="flex items-center gap-2 text-xs cursor-pointer hover:bg-muted/40 rounded px-1 py-0.5"
        >
          <input
            type="checkbox"
            checked={selected.includes(a.attribute_id)}
            onChange={() => toggle(a.attribute_id)}
          />
          <span className="font-mono">{a.technical_name}</span>
          {a.is_primary_key && (
            <span className="text-[9px] uppercase text-nuclea-primary">PK</span>
          )}
          {a.native_data_type && (
            <span className="text-[10px] text-muted-foreground ml-auto">
              {a.native_data_type}
            </span>
          )}
        </label>
      ))}
    </div>
  );
}

function CardinalityRadio({
  value,
  onChange,
  name,
}: {
  value: Cardinality;
  onChange: (v: Cardinality) => void;
  name: string;
}) {
  return (
    <div className="flex gap-2">
      {(["OPTIONAL", "MANDATORY"] as Cardinality[]).map((c) => (
        <label
          key={c}
          className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs ${
            value === c
              ? "bg-nuclea-primary text-primary-foreground border-nuclea-primary"
              : "hover:bg-muted"
          }`}
        >
          <input
            type="radio"
            name={name}
            value={c}
            checked={value === c}
            onChange={() => onChange(c)}
            className="sr-only"
          />
          {c === "OPTIONAL" ? "Opcional" : "Obrigatória"}
        </label>
      ))}
    </div>
  );
}

function FkRuleSelect({
  value,
  onChange,
}: {
  value: FKRule | "";
  onChange: (v: FKRule | "") => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as FKRule | "")}
      className="w-full rounded-md border bg-background px-3 py-2 text-sm"
    >
      <option value="">—</option>
      <option value="NO ACTION">NO ACTION</option>
      <option value="CASCADE">CASCADE</option>
      <option value="SET NULL">SET NULL</option>
      <option value="SET DEFAULT">SET DEFAULT</option>
      <option value="RESTRICT">RESTRICT</option>
    </select>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium flex items-center gap-1">
        {label}
        {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  );
}

/**
 * RelationshipFlagsCell — Componente para aplicar flags a relacionamentos.
 * Reusa FlagPicker com suspense para carregar flags do relacionamento.
 * Integrado à tabela de relacionamentos.
 */
function RelationshipFlagsCell({ relationshipId }: { relationshipId: string }) {
  const qc = useQueryClient();
  const { data: appliedFlags } = useListRelationshipFlagsSuspense(
    relationshipId,
    selector(),
  );

  const { mutate: applyBatch, isPending: applying } = useBatchApplyRelationshipFlags({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRelationshipFlags", relationshipId] });
      },
      onError: (e) => {
        toast.error("Erro ao aplicar flags: " + String(e));
      },
    },
  });

  const { mutate: remove } = useRemoveRelationshipFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRelationshipFlags", relationshipId] });
      },
    },
  });

  const applied = appliedFlags.map((rf) => ({
    applied_flag_id: rf.relationship_flag_id,
    flag: rf.flag,
    justification: rf.justification,
  }));

  return (
    <FlagPicker
      applied={applied}
      applying={applying}
      onApply={(specs) =>
        applyBatch({ data: { target_ids: [relationshipId], flags: specs } })
      }
      onRemove={(rfid) =>
        remove({ relationshipId, relationshipFlagId: rfid })
      }
      size="small"
      label="+ Flag"
    />
  );
}

function TableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
      </CardHeader>
      <CardContent className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
