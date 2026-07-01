import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetEntitySuspense,
  useListAttributesSuspense,
  useCreateAttribute,
  useDeleteAttribute,
  useDeleteEntity,
  useListEntityFlagsSuspense,
  useApplyEntityFlag,
  useRemoveEntityFlag,
  useListAttributeFlagsSuspense,
  useApplyAttributeFlag,
  useRemoveAttributeFlag,
  useListSystemsSuspense,
} from "@/lib/api";
import selector from "@/lib/selector";
import { TypePicker } from "@/components/diagram/type-picker";
import { IndexesSection } from "@/components/diagram/indexes-section";
import { PartitioningSection } from "@/components/diagram/partitioning-section";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { FlagPicker } from "@/components/flags/flag-picker";
import {
  ArrowLeft, AlertCircle, Trash2, Plus, Key, FileText, ShieldCheck,
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

      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <AttributesSection entityId={id} technology={systemTechnology} />
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
  const { mutate: apply, isPending: applying } = useApplyEntityFlag({
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
          onApply={({ flag_id, justification }) =>
            apply({ entityId, data: { flag_id, justification } })
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
  const { mutate: apply, isPending: applying } = useApplyAttributeFlag({
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
      label="Flag"
      onApply={({ flag_id, justification }) =>
        apply({ attributeId, data: { flag_id, justification } })
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

function AttributesSection({
  entityId,
  technology,
}: {
  entityId: string;
  technology: string | null;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { mutate: createAttr, isPending } = useCreateAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        qc.invalidateQueries({ queryKey: ["getEntity", entityId] });
        setShowForm(false);
      },
    },
  });
  const { mutate: delAttr } = useDeleteAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        qc.invalidateQueries({ queryKey: ["getEntity", entityId] });
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
        is_nullable: nullable,
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle>Atributos ({attrs.length})</CardTitle>
            <CardDescription>Colunas catalogadas desta entidade</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus className="mr-2 h-4 w-4" />
            {showForm ? "Cancelar" : "Adicionar atributo"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {showForm && (
          <form onSubmit={submit} className="mb-6 rounded-lg border bg-muted/30 p-4 space-y-3">
            <div className="grid md:grid-cols-3 gap-3">
              <Input placeholder="Nome técnico*" value={techName} onChange={(e) => setTechName(e.target.value)} required />
              <Input placeholder="Nome lógico" value={logName} onChange={(e) => setLogName(e.target.value)} />
              <TypePicker value={dataType} onChange={setDataType} technology={technology} />
            </div>
            <div className="flex items-center gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={isPk} onChange={(e) => setIsPk(e.target.checked)} />
                Chave primária
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={nullable} onChange={(e) => setNullable(e.target.checked)} />
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

        {attrs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Sem atributos cadastrados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium w-8"></th>
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
                {attrs.map((a) => (
                  <tr key={a.attribute_id} className="border-b hover:bg-muted/40 align-top">
                    <td className="py-2 pr-3">
                      {a.is_primary_key && <Key className="h-3.5 w-3.5 text-nuclea-primary" />}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{a.technical_name}</td>
                    <td className="py-2 pr-3">{a.logical_name || "—"}</td>
                    <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{a.native_data_type || "—"}</td>
                    <td className="py-2 pr-3 text-xs">{a.is_nullable === false ? "NOT NULL" : "NULL"}</td>
                    <td className="py-2 pr-3">
                      <Suspense
                        fallback={<Skeleton className="h-5 w-20" />}
                      >
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
                ))}
              </tbody>
            </table>
          </div>
        )}
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
