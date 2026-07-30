import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { toast } from "sonner";

import {
  useGetEntitySuspense,
  useListAttributesSuspense,
  useCreateAttribute,
  useUpdateAttribute,
  useDeleteAttribute,
  useDeleteEntity,
  useListEntityFlagsSuspense,
  useBatchApplyEntityFlags,
  useRemoveEntityFlag,
  useListAttributeFlagsSuspense,
  useBatchApplyAttributeFlags,
  useBatchRemoveAttributeFlags,
  useRemoveAttributeFlag,
  useListSystemsSuspense,
  useGetDiagramSuspense,
  useGetSessionStatusSuspense,
  useGetSessionStateSuspense,
  type BatchFlagSpec,
  type AttributeOut,
  type SessionStateOut,
} from "@/lib/api";
import selector from "@/lib/selector";
import { TypePicker } from "@/components/diagram/type-picker";
import { IndexesSection } from "@/components/diagram/indexes-section";
import { PartitioningSection } from "@/components/diagram/partitioning-section";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { FlagBatchBar, toastBatchFlagResult } from "@/components/flags/flag-batch-bar";
import {
  PkToggle,
  computePkOrdinals,
  getPkWarnings,
  usePkDragReorder,
} from "@/components/attributes/pk-controls";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { FlagPicker } from "@/components/flags/flag-picker";
import {
  ArrowLeft, AlertCircle, Trash2, Plus, Key, FileText, ShieldCheck,
  ClipboardList, GripVertical,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/entities/$id")({
  component: EntityDetailPage,
});

function EntityDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/entities">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Entidades
        </Link>
      </Button>

      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar entidade
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <EntityDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function EntityDetail() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: entity } = useGetEntitySuspense(id, selector());
  const { data: systems } = useListSystemsSuspense(selector());
  const systemTechnology =
    systems.find((s) => s.system_id === entity.system_id)?.technology || null;

  const { mutate: del, isPending: deleting } = useDeleteEntity({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        navigate({ to: "/entities" });
      },
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="outline">{entity.entity_type}</Badge>
            {entity.domain && <Badge variant="secondary">{entity.domain}</Badge>}
            {entity.criticality && <CriticalityBadge value={entity.criticality} />}
          </div>
          <h1 className="text-3xl font-bold tracking-tight font-mono">
            {entity.schema_name}.{entity.technical_name}
          </h1>
          {entity.logical_name && (
            <p className="text-lg text-muted-foreground mt-1">{entity.logical_name}</p>
          )}
          <p className="text-sm text-muted-foreground mt-1">
            Sistema: <strong>{entity.system_name || entity.system_id}</strong>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (confirm(`Excluir entidade "${entity.technical_name}" e seus atributos?`))
                del({ entityId: id });
            }}
            disabled={deleting}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Excluir
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Descrição de negócio
            </CardTitle>
          </CardHeader>
          <CardContent>
            {entity.description_md ? (
              <pre className="whitespace-pre-wrap text-sm leading-relaxed">{entity.description_md}</pre>
            ) : (
              <p className="text-sm text-muted-foreground italic">
                Sem descrição. Edite a entidade para adicionar contexto de negócio.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Responsáveis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <KV label="Business owner" value={entity.business_owner || "—"} />
            <KV label="Technical owner" value={entity.technical_owner || "—"} />
            <Separator />
            <KV label="Tags" value={entity.tags?.length ? entity.tags.join(", ") : "—"} />
            <KV label="# Atributos" value={String(entity.attributes_count ?? 0)} />
            <Separator />
            <KV label="Criado por" value={entity.created_by} />
            <KV label="Em" value={new Date(entity.created_at).toLocaleString("pt-BR")} />
            <KV label="Atualizado por" value={entity.updated_by} />
            <KV label="Em" value={new Date(entity.updated_at).toLocaleString("pt-BR")} />
          </CardContent>
        </Card>
      </div>

      <Suspense fallback={<Skeleton className="h-24 w-full" />}>
        <EntityFlagsSection entityId={id} />
      </Suspense>

      <Suspense fallback={<Skeleton className="h-32 w-full" />}>
        <PendingChangesSection
          entityId={id}
          entityTechName={entity.technical_name}
          systemId={entity.system_id}
        />
      </Suspense>

      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <AttributesSection
          entityId={id}
          systemId={entity.system_id}
          technology={systemTechnology}
        />
      </Suspense>

      <IndexesSection entityId={id} technology={systemTechnology} />
      <PartitioningSection entityId={id} technology={systemTechnology} />

      <AttachmentsPanel ownerKind="entity" ownerId={id} label="Anexos da tabela" />
    </div>
  );
}

function EntityFlagsSection({ entityId }: { entityId: string }) {
  const qc = useQueryClient();
  const { data: appliedFlags } = useListEntityFlagsSuspense(entityId, selector());
  // Multi-select: uma única chamada batch aplica todas as flags escolhidas.
  const { mutate: applyBatch, isPending: applying } = useBatchApplyEntityFlags({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
      onError: (e) => {
        alert(extractErrorMessage(e));
      },
    },
  });
  const { mutate: remove } = useRemoveEntityFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
    },
  });

  const applied = appliedFlags.map((ef) => ({
    applied_flag_id: ef.entity_flag_id,
    flag: ef.flag,
    justification: ef.justification,
    is_propagated: ef.is_propagated,
  }));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-nuclea-primary" />
              Flags da entidade ({appliedFlags.length})
            </CardTitle>
            <CardDescription>
              LGPD, uso e qualidade aplicados a esta tabela. Flags LGPD em colunas
              propagam automaticamente para a entidade.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <FlagPicker
          applied={applied}
          applying={applying}
          onApply={(specs) =>
            applyBatch({ data: { target_ids: [entityId], flags: specs } })
          }
          onRemove={(efid) =>
            remove({ entityId, entityFlagId: efid })
          }
        />
      </CardContent>
    </Card>
  );
}

function AttributeFlagsCell({ attributeId }: { attributeId: string }) {
  const qc = useQueryClient();
  const { data: appliedFlags } = useListAttributeFlagsSuspense(
    attributeId,
    selector(),
  );
  const params = Route.useParams();
  const entityId = params.id;
  const { mutate: applyBatch, isPending: applying } = useBatchApplyAttributeFlags({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributeFlags", attributeId] });
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
      onError: (e) => {
        alert(extractErrorMessage(e));
      },
    },
  });
  const { mutate: remove } = useRemoveAttributeFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributeFlags", attributeId] });
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
    },
  });

  const applied = appliedFlags.map((af) => ({
    applied_flag_id: af.attribute_flag_id,
    flag: af.flag,
    justification: af.justification,
  }));

  return (
    <FlagPicker
      applied={applied}
      applying={applying}
      size="small"
      label="Flags"
      onApply={(specs) =>
        applyBatch({ data: { target_ids: [attributeId], flags: specs } })
      }
      onRemove={(afid) =>
        remove({ attributeId, attributeFlagId: afid })
      }
    />
  );
}

function extractErrorMessage(e: unknown): string {
  // Axios errors carry the server response payload under e.response.data.detail.
  // Fall back to the plain Error message for everything else.
  const anyE = e as { response?: { data?: { detail?: string } }; message?: string };
  return anyE?.response?.data?.detail || anyE?.message || "Erro ao aplicar flag";
}

/**
 * Banner reutilizável de "mudanças pendentes" (mesma linguagem visual do
 * SessionBanner do diagrama, v1.0014). Mostrado no topo da seção de atributos
 * quando a edição de PK/coluna virou ticket OPEN — assim o usuário sabe que a
 * mudança está STAGED (não gravada direto no catálogo) e precisa de aprovação.
 */
function PendingChangesBanner({ systemId }: { systemId: string }) {
  const { data: session } = useGetSessionStatusSuspense(systemId, selector());
  const total = session
    ? session.additions + session.changes + session.removals
    : 0;
  if (!session || total === 0) return null;
  return (
    <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2 text-sm">
        <ClipboardList className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
        <span>
          <strong>{total}</strong> mudança{total !== 1 ? "s" : ""} pendente
          {total !== 1 ? "s" : ""} de aprovação nesta sessão (inclui edições de PK).
        </span>
      </div>
      <Button asChild size="sm" variant="outline">
        <Link to="/tickets/$id" params={{ id: session.ticket_id }}>
          Revisar e aprovar
        </Link>
      </Button>
    </div>
  );
}

function AttributesSection({
  entityId,
  systemId,
  technology,
}: {
  entityId: string;
  systemId: string;
  technology: string | null;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  // Diagrama do sistema → detecta quais colunas desta entity são FK, para avisar
  // (não bloquear) quando marcadas como PK. `source_attrs`/`target_attrs` do
  // relacionamento carregam IDs de atributos. Usamos o diagram view porque a
  // rota resumida de relationships não expõe as colunas.
  const { data: diagram } = useGetDiagramSuspense(systemId, "default", selector());
  const fkAttrIds = new Set<string>();
  for (const rel of diagram.relationships) {
    if (rel.source_entity_id === entityId) {
      for (const id of rel.source_attrs) fkAttrIds.add(id);
    }
    if (rel.target_entity_id === entityId) {
      for (const id of rel.target_attrs) fkAttrIds.add(id);
    }
  }
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  // Seleção múltipla de atributos p/ flags em lote (mata os ~250 cliques).
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const clearSelection = () => setSelected(new Set());
  const allSelected = attrs.length > 0 && selected.size === attrs.length;
  const toggleAll = () =>
    setSelected((prev) =>
      prev.size === attrs.length
        ? new Set()
        : new Set(attrs.map((a) => a.attribute_id)),
    );

  const invalidateAttrFlags = () => {
    qc.invalidateQueries({ queryKey: ["listAttributeFlags"] });
    qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
  };
  // Invalida as queries afetadas pela edição de atributo/PK (inclui o status da
  // sessão, para o banner de "mudanças pendentes" refletir o novo ticket).
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
    qc.invalidateQueries({ queryKey: ["getEntity", entityId] });
    qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
  };
  const { mutate: applyFlags, isPending: applyingFlags } =
    useBatchApplyAttributeFlags({
      mutation: {
        onSuccess: (r) => {
          invalidateAttrFlags();
          clearSelection();
          toastBatchFlagResult(r);
        },
        onError: (e) =>
          toast.error("Falha ao aplicar flags", {
            description: extractErrorMessage(e),
          }),
      },
    });
  const { mutate: removeFlags, isPending: removingFlags } =
    useBatchRemoveAttributeFlags({
      mutation: {
        onSuccess: (r) => {
          invalidateAttrFlags();
          clearSelection();
          toastBatchFlagResult(r);
        },
        onError: (e) =>
          toast.error("Falha ao remover flags", {
            description: extractErrorMessage(e),
          }),
      },
    });
  const selectedIds = Array.from(selected);
  const onApplyFlags = (specs: BatchFlagSpec[]) =>
    applyFlags({ data: { target_ids: selectedIds, flags: specs } });
  const onRemoveFlags = (flagIds: string[]) =>
    removeFlags({ data: { target_ids: selectedIds, flag_ids: flagIds } });

  const { mutate: createAttr, isPending } = useCreateAttribute({
    mutation: {
      onSuccess: () => {
        invalidate();
        setShowForm(false);
        toast.success("Atributo adicionado (pendente de aprovação)");
      },
    },
  });
  const { mutate: updateAttr } = useUpdateAttribute({
    mutation: {
      onSuccess: () => invalidate(),
      onError: (e) => toast.error(extractErrorMessage(e)),
    },
  });
  const { mutate: delAttr } = useDeleteAttribute({
    mutation: {
      onSuccess: () => {
        invalidate();
        toast.success("Remoção de atributo staged (pendente)");
      },
    },
  });

  const [techName, setTechName] = useState("");
  const [logName, setLogName] = useState("");
  const [dataType, setDataType] = useState("");
  const [nullable, setNullable] = useState(true);
  const [isPk, setIsPk] = useState(false);
  const [desc, setDesc] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    createAttr({
      entityId,
      data: {
        entity_id: entityId,
        technical_name: techName,
        logical_name: logName || null,
        native_data_type: dataType || null,
        // PK não deveria ser nullable — ao marcar PK na criação, força NOT NULL.
        is_nullable: isPk ? false : nullable,
        is_primary_key: isPk,
        description_md: desc || null,
      },
    });
    setTechName("");
    setLogName("");
    setDataType("");
    setDesc("");
    setIsPk(false);
    setNullable(true);
  };

  // Numeração PK1, PK2… na ordem de definição (ordinal_position).
  const pkOrdinals = computePkOrdinals(attrs);

  /**
   * Alterna PK de uma coluna. STAGE via PUT /entities/{id}/attributes/{attrId}
   * (fluxo editorial → ticket, não grava direto). Ao MARCAR como PK, também
   * força NOT NULL (uma PK não pode ser nullable). Feedback via toast.
   */
  const togglePk = (a: AttributeOut, checked: boolean) => {
    updateAttr({
      entityId,
      attributeId: a.attribute_id,
      data: {
        entity_id: entityId,
        technical_name: a.technical_name,
        logical_name: a.logical_name ?? null,
        native_data_type: a.native_data_type ?? null,
        ordinal_position: a.ordinal_position ?? null,
        is_nullable: checked ? false : a.is_nullable,
        default_value: a.default_value ?? null,
        is_primary_key: checked,
        description_md: a.description_md ?? null,
      },
    });
    toast.success(
      checked
        ? `"${a.technical_name}" marcada como PK (pendente)`
        : `"${a.technical_name}" deixou de ser PK (pendente)`,
    );
  };

  // Reordenação de PK composta via drag (P2): stage novo ordinal_position.
  const { rowProps, dragId } = usePkDragReorder({
    attrs,
    onApply: (updates) => {
      if (updates.length === 0) return;
      const byId = new Map(attrs.map((a) => [a.attribute_id, a]));
      for (const u of updates) {
        const a = byId.get(u.attribute_id);
        if (!a) continue;
        updateAttr({
          entityId,
          attributeId: a.attribute_id,
          data: {
            entity_id: entityId,
            technical_name: a.technical_name,
            logical_name: a.logical_name ?? null,
            native_data_type: a.native_data_type ?? null,
            ordinal_position: u.ordinal_position,
            is_nullable: a.is_nullable,
            default_value: a.default_value ?? null,
            is_primary_key: a.is_primary_key,
            description_md: a.description_md ?? null,
          },
        });
      }
      toast.success("Ordem da PK composta atualizada (pendente)");
    },
  });
  const pkCount = attrs.filter((a) => a.is_primary_key).length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle>Atributos ({attrs.length})</CardTitle>
            <CardDescription>
              Colunas catalogadas desta entidade. Marque a{" "}
              <span className="inline-flex items-center gap-0.5 text-nuclea-primary">
                <Key className="h-3 w-3" />PK
              </span>{" "}
              direto na tabela — a mudança vira um ticket para aprovação.
              {pkCount > 1 && " PK composta é numerada PK1, PK2… na ordem."}
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus className="mr-2 h-4 w-4" />
            {showForm ? "Cancelar" : "Adicionar atributo"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Suspense fallback={null}>
          <PendingChangesBanner systemId={systemId} />
        </Suspense>

        {showForm && (
          <form onSubmit={submit} className="mb-6 rounded-lg border bg-muted/30 p-4 space-y-3">
            <div className="grid md:grid-cols-3 gap-3">
              <Input placeholder="Nome técnico*" value={techName} onChange={(e) => setTechName(e.target.value)} required />
              <Input placeholder="Nome lógico" value={logName} onChange={(e) => setLogName(e.target.value)} />
              <TypePicker value={dataType} onChange={setDataType} technology={technology} />
            </div>
            <div className="flex items-center gap-4 text-sm">
              <PkToggle
                checked={isPk}
                warnings={getPkWarnings({ isNullable: isPk ? false : nullable })}
                onCheckedChange={(v) => {
                  setIsPk(v);
                  if (v) setNullable(false); // PK ⇒ NOT NULL
                }}
              />
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={nullable}
                  disabled={isPk}
                  onChange={(e) => setNullable(e.target.checked)}
                />
                Nullable
              </label>
            </div>
            <Input placeholder="Descrição (opcional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
            <div className="flex justify-end">
              <Button type="submit" size="sm" disabled={isPending || !techName}>
                {isPending ? "Salvando..." : "Adicionar"}
              </Button>
            </div>
          </form>
        )}

        {selected.size > 0 && (
          <div className="mb-3">
            <FlagBatchBar
              count={selected.size}
              busy={applyingFlags || removingFlags}
              noun="atributo"
              onClear={clearSelection}
              onApply={onApplyFlags}
              onRemove={onRemoveFlags}
            />
          </div>
        )}

        {attrs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Sem atributos cadastrados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium w-8">
                    <input
                      type="checkbox"
                      className="h-4 w-4 cursor-pointer accent-nuclea-primary"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="Selecionar todos os atributos"
                    />
                  </th>
                  <th className="py-2 pr-3 font-medium w-32">PK</th>
                  <th className="py-2 pr-3 font-medium">Nome técnico</th>
                  <th className="py-2 pr-3 font-medium">Nome lógico</th>
                  <th className="py-2 pr-3 font-medium">Tipo</th>
                  <th className="py-2 pr-3 font-medium">Nullable</th>
                  <th className="py-2 pr-3 font-medium">Flags</th>
                  <th className="py-2 pr-3 font-medium">Descrição</th>
                  <th className="py-2 pr-3 font-medium w-12"></th>
                </tr>
              </thead>
              <tbody>
                {attrs.map((a) => {
                  const isFk = fkAttrIds.has(a.attribute_id);
                  const warnings = getPkWarnings({
                    isNullable: a.is_nullable,
                    isForeignKey: isFk,
                  });
                  const pending = a.pending_op;
                  return (
                    <tr
                      key={a.attribute_id}
                      className={`border-b hover:bg-muted/40 align-top ${
                        dragId === a.attribute_id ? "opacity-50" : ""
                      } ${selected.has(a.attribute_id) ? "bg-nuclea-primary/5" : ""}`}
                      {...rowProps(a)}
                    >
                      <td className="py-2 pr-3">
                        <input
                          type="checkbox"
                          className="h-4 w-4 cursor-pointer accent-nuclea-primary"
                          checked={selected.has(a.attribute_id)}
                          onChange={() => toggle(a.attribute_id)}
                          aria-label={`Selecionar ${a.technical_name}`}
                        />
                      </td>
                      <td className="py-2 pr-3">
                        <div className="flex items-center gap-1">
                          {a.is_primary_key && pkCount > 1 && (
                            <GripVertical
                              className="h-3.5 w-3.5 text-muted-foreground/40 cursor-grab shrink-0"
                              aria-label="Arraste para reordenar a PK composta"
                            />
                          )}
                          <PkToggle
                            checked={a.is_primary_key}
                            ordinal={pkOrdinals.get(a.attribute_id)}
                            warnings={warnings}
                            onCheckedChange={(v) => togglePk(a, v)}
                          />
                        </div>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {a.technical_name}
                        {pending && (
                          <span className="ml-1.5 text-[9px] rounded px-1 py-0.5 border border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300">
                            pendente
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">{a.logical_name || "—"}</td>
                      <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{a.native_data_type || "—"}</td>
                      <td className="py-2 pr-3 text-xs">{a.is_nullable === false ? "NOT NULL" : "NULL"}</td>
                      <td className="py-2 pr-3">
                        <Suspense fallback={<Skeleton className="h-5 w-20" />}>
                          <AttributeFlagsCell attributeId={a.attribute_id} />
                        </Suspense>
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">
                        {a.description_md ? (a.description_md.length > 80 ? a.description_md.slice(0, 80) + "…" : a.description_md) : "—"}
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          onClick={() => {
                            if (confirm(`Remover atributo "${a.technical_name}"?`))
                              delAttr({ entityId, attributeId: a.attribute_id });
                          }}
                          className="text-muted-foreground hover:text-destructive"
                          title="Remover"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Seção "Campos em aprovação": mostra edições pendentes (staged) dessa entidade
 * no ticket OPEN da sessão. Extrai do diff as mudanças (op=change) que afetam
 * esta entidade e lista os field_changes.
 */
function PendingChangesSection({
  entityId,
  entityTechName,
  systemId,
}: {
  entityId: string;
  entityTechName: string;
  systemId: string;
}) {
  const { data: session } = useGetSessionStateSuspense(systemId, selector());

  if (!session || !session.entities_changed) {
    return null;
  }

  // Encontra mudanças para esta entidade (batemos pelo target_entity_id no payload)
  const relevantChanges = session.entities_changed.filter((e: Record<string, unknown>) => {
    const payload = e.payload as Record<string, unknown> | undefined;
    return payload?.target_entity_id === entityId;
  });

  if (relevantChanges.length === 0) {
    return null;
  }

  // Extrai os field_changes de todas as mudanças relevantes
  const allFieldChanges: Array<{ field: string; before: unknown; after: unknown }> = [];
  for (const change of relevantChanges) {
    const fc = (change.field_changes as Array<{ field: string; before: unknown; after: unknown }> | undefined) || [];
    allFieldChanges.push(...fc);
  }

  if (allFieldChanges.length === 0) {
    return null;
  }

  return (
    <Card className="border-blue-200 dark:border-blue-900/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
          <ClipboardList className="h-5 w-5" />
          Campos em aprovação ({allFieldChanges.length})
        </CardTitle>
        <CardDescription>
          Edições staged (pendentes) desta tabela no ticket da sessão
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {allFieldChanges.map((fc, idx) => {
            const fieldName = fc.field || "?";
            // Decodifica nomes de campos especiais (attribute_add:name, attribute:name.update)
            let displayName = fieldName;
            if (fieldName.startsWith("attribute_add:")) {
              displayName = `Nova coluna: ${fieldName.slice("attribute_add:".length)}`;
            } else if (fieldName.startsWith("attribute:") && fieldName.endsWith(".update")) {
              const attrName = fieldName.slice("attribute:".length, -".update".length);
              displayName = `Editar coluna: ${attrName}`;
            }
            return (
              <div key={idx} className="text-sm border-l-2 border-blue-300 pl-3">
                <div className="font-medium text-foreground">{displayName}</div>
                {fc.before !== undefined && fc.before !== null && (
                  <div className="text-xs text-muted-foreground">
                    antes: <span className="font-mono">{String(fc.before).slice(0, 50)}</span>
                  </div>
                )}
                {fc.after !== undefined && fc.after !== null && (
                  <div className="text-xs text-muted-foreground">
                    depois: <span className="font-mono">{String(fc.after).slice(0, 50)}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-950/30 rounded-md text-sm text-blue-700 dark:text-blue-300">
          <p>Essas mudanças estão aguardando aprovação. Após aprovação, serão aplicadas ao catálogo.</p>
        </div>
      </CardContent>
    </Card>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function CriticalityBadge({ value }: { value: string }) {
  const color =
    value === "HIGH"
      ? "bg-destructive/10 text-destructive border-destructive/30"
      : value === "MEDIUM"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300";
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>{value}</span>;
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-2/3" />
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="lg:col-span-2 h-48" />
        <Skeleton className="h-48" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
