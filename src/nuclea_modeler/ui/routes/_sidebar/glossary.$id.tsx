import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetTermSuspense,
  useListTermMappingsSuspense,
  useCreateMapping,
  useDeleteMapping,
  useDeleteTerm,
  useTransitionTerm,
  useMyRolesSuspense,
  useListEntitiesSuspense,
  useListAttributesSuspense,
  type TermStatus,
  type MappingOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  AlertCircle,
  AlertTriangle,
  Trash2,
  Plus,
  Link as LinkIcon,
  Send,
  CheckCircle2,
  ShieldOff,
  RotateCcw,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/glossary/$id")({
  component: TermDetailPage,
});

function TermDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/glossary">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Dicionário
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
                    Erro ao carregar termo
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <TermDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function TermDetail() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: term } = useGetTermSuspense(id, selector());
  const { data: me } = useMyRolesSuspense(selector());

  const isArchitectOrAdmin = me.is_admin || me.roles.includes("DATA_ARCHITECT");
  const canApprove = me.is_admin
    || me.roles.includes("DATA_ARCHITECT")
    || me.roles.includes("DATA_STEWARD");
  const isCreator = me.user_email === term.created_by;

  const { mutate: transition, isPending: transitioning } = useTransitionTerm({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getTerm", id] });
        qc.invalidateQueries({ queryKey: ["listTerms"] });
      },
    },
  });

  const { mutate: removeTerm, isPending: removing } = useDeleteTerm({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listTerms"] });
        navigate({ to: "/glossary" });
      },
    },
  });

  const canSubmitForReview = term.status === "DRAFT";
  const canApproveNow = term.status === "IN_REVIEW" && canApprove;
  const canDeprecate = term.status === "APPROVED" && isArchitectOrAdmin;
  const canReturnToDraft =
    (term.status === "IN_REVIEW" || term.status === "APPROVED")
    && (isCreator || isArchitectOrAdmin);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <StatusBadge status={term.status} />
            {term.domain && <Badge variant="secondary">{term.domain}</Badge>}
            {term.conceptual_type && (
              <Badge variant="outline">{term.conceptual_type}</Badge>
            )}
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{term.canonical_name}</h1>
          {term.owner_person && (
            <p className="text-sm text-muted-foreground mt-1">
              Owner: <strong>{term.owner_person}</strong>
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {canSubmitForReview && (
            <Button
              variant="outline"
              onClick={() => transition({ termId: id, to: "IN_REVIEW" })}
              disabled={transitioning}
            >
              <Send className="mr-2 h-4 w-4" />
              Enviar para revisão
            </Button>
          )}
          {canApproveNow && (
            <Button
              onClick={() => transition({ termId: id, to: "APPROVED" })}
              disabled={transitioning}
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Aprovar
            </Button>
          )}
          {canDeprecate && (
            <Button
              variant="outline"
              onClick={() => {
                if (confirm(`Depreciar o termo "${term.canonical_name}"?`))
                  transition({ termId: id, to: "DEPRECATED" });
              }}
              disabled={transitioning}
            >
              <ShieldOff className="mr-2 h-4 w-4" />
              Depreciar
            </Button>
          )}
          {canReturnToDraft && (
            <Button
              variant="ghost"
              onClick={() => transition({ termId: id, to: "DRAFT" })}
              disabled={transitioning}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Voltar para rascunho
            </Button>
          )}
          {isArchitectOrAdmin && term.status !== "DEPRECATED" && (
            <Button
              variant="outline"
              onClick={() => {
                if (confirm(`Excluir (depreciar) o termo "${term.canonical_name}"?`))
                  removeTerm({ termId: id });
              }}
              disabled={removing}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Excluir
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Definição de negócio</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans">
              {term.definition || "—"}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Metadados</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <KV label="Sinônimos">
              {term.synonyms.length === 0 ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {term.synonyms.map((syn) => (
                    <Badge key={syn} variant="secondary">{syn}</Badge>
                  ))}
                </div>
              )}
            </KV>
            <KV label="Exemplos válidos">
              {term.valid_examples.length === 0 ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {term.valid_examples.map((ex) => (
                    <Badge key={ex} variant="outline" className="font-mono">{ex}</Badge>
                  ))}
                </div>
              )}
            </KV>
            <Separator />
            <KVLine label="Tipo conceitual" value={term.conceptual_type || "—"} />
            <KVLine label="Domínio" value={term.domain || "—"} />
            <KVLine label="Owner" value={term.owner_person || "—"} />
            <Separator />
            <KVLine label="Criado por" value={term.created_by} />
            <KVLine
              label="Em"
              value={new Date(term.created_at).toLocaleString("pt-BR")}
            />
            {term.approved_at && (
              <>
                <KVLine label="Aprovado por" value={term.approved_by || "—"} />
                <KVLine
                  label="Em"
                  value={new Date(term.approved_at).toLocaleString("pt-BR")}
                />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <MappingsSection termId={id} />
      </Suspense>
    </div>
  );
}

function MappingsSection({ termId }: { termId: string }) {
  const { data: mappings } = useListTermMappingsSuspense(termId, selector());
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { mutate: removeMapping } = useDeleteMapping({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listTermMappings", termId] });
        qc.invalidateQueries({ queryKey: ["getTerm", termId] });
      },
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle>Atributos vinculados ({mappings.length})</CardTitle>
            <CardDescription>
              Colunas em sistemas que implementam este conceito
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus className="mr-2 h-4 w-4" />
            {showForm ? "Cancelar" : "Novo vínculo"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {showForm && (
          <Suspense fallback={<Skeleton className="h-24 w-full mb-4" />}>
            <NewMappingForm termId={termId} onDone={() => setShowForm(false)} />
          </Suspense>
        )}

        {mappings.some((m) => m.type_compat_warning) && (
          <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              Existem vínculos com possível incompatibilidade entre o tipo nativo
              do atributo e o tipo conceitual do termo. Revise os itens marcados.
            </span>
          </div>
        )}

        {mappings.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Nenhum atributo vinculado ainda.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Sistema</th>
                  <th className="py-2 pr-3 font-medium">Schema · Entidade</th>
                  <th className="py-2 pr-3 font-medium">Atributo</th>
                  <th className="py-2 pr-3 font-medium">Tipo nativo</th>
                  <th className="py-2 pr-3 font-medium">Compat?</th>
                  <th className="py-2 pr-3 font-medium w-12"></th>
                </tr>
              </thead>
              <tbody>
                {mappings.map((m) => (
                  <MappingRow
                    key={m.mapping_id}
                    mapping={m}
                    onDelete={(mappingId) => {
                      if (confirm("Remover este vínculo?"))
                        removeMapping({ mappingId });
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MappingRow({
  mapping: m,
  onDelete,
}: {
  mapping: MappingOut;
  onDelete: (id: string) => void;
}) {
  return (
    <tr className="border-b hover:bg-muted/40">
      <td className="py-2 pr-3">{m.system_name || m.system_id || "—"}</td>
      <td className="py-2 pr-3 font-mono text-xs">
        {m.entity_id ? (
          <Link
            to="/entities/$id"
            params={{ id: m.entity_id }}
            className="hover:text-nuclea-primary"
          >
            {m.schema_name || "?"}.{m.entity_technical_name || "?"}
          </Link>
        ) : (
          <span>{m.schema_name}.{m.entity_technical_name}</span>
        )}
      </td>
      <td className="py-2 pr-3 font-mono text-xs">
        {m.attribute_technical_name}
        {m.attribute_logical_name && (
          <span className="ml-1 text-muted-foreground">({m.attribute_logical_name})</span>
        )}
      </td>
      <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">
        {m.native_data_type || "—"}
      </td>
      <td className="py-2 pr-3">
        {m.type_compat_warning ? (
          <Badge variant="outline" className="bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300">
            <AlertTriangle className="mr-1 h-3 w-3" />
            Verificar
          </Badge>
        ) : (
          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300">
            OK
          </Badge>
        )}
      </td>
      <td className="py-2 pr-3">
        <button
          onClick={() => onDelete(m.mapping_id)}
          className="text-muted-foreground hover:text-destructive"
          title="Remover vínculo"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </td>
    </tr>
  );
}

function NewMappingForm({
  termId,
  onDone,
}: {
  termId: string;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const { data: entities } = useListEntitiesSuspense({}, selector());
  const [entityFilter, setEntityFilter] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<string>("");
  const [inheritDesc, setInheritDesc] = useState(true);
  const [lastWarning, setLastWarning] = useState<{
    native: string | null | undefined;
    conceptual: string | null | undefined;
  } | null>(null);

  const filteredEntities = useMemo(() => {
    const q = entityFilter.trim().toLowerCase();
    if (!q) return entities.slice(0, 50);
    return entities
      .filter((e) =>
        e.technical_name.toLowerCase().includes(q)
        || e.logical_name?.toLowerCase().includes(q)
        || e.schema_name.toLowerCase().includes(q)
        || e.system_name?.toLowerCase().includes(q),
      )
      .slice(0, 50);
  }, [entityFilter, entities]);

  const { mutate: createMapping, isPending, error } = useCreateMapping({
    mutation: {
      onSuccess: (m) => {
        qc.invalidateQueries({ queryKey: ["listTermMappings", termId] });
        qc.invalidateQueries({ queryKey: ["getTerm", termId] });
        if (m.type_compat_warning) {
          setLastWarning({
            native: m.native_data_type,
            conceptual: m.term_conceptual_type,
          });
        } else {
          onDone();
        }
      },
    },
  });

  return (
    <div className="mb-6 rounded-lg border bg-muted/30 p-4 space-y-3">
      <div className="grid md:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Filtrar entidade</label>
          <Input
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            placeholder="Buscar por nome / sistema..."
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Entidade</label>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={selectedEntityId}
            onChange={(e) => setSelectedEntityId(e.target.value)}
          >
            <option value="">Selecione...</option>
            {filteredEntities.map((e) => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.system_name || e.system_id} · {e.schema_name}.{e.technical_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {selectedEntityId && (
        <Suspense fallback={<Skeleton className="h-20 w-full" />}>
          <AttributePicker
            entityId={selectedEntityId}
            inheritDesc={inheritDesc}
            setInheritDesc={setInheritDesc}
            isPending={isPending}
            onSubmit={(attributeId, override) =>
              createMapping({
                termId,
                data: {
                  term_id: termId,
                  attribute_id: attributeId,
                  inherit_description: inheritDesc,
                  override_description: override || null,
                },
              })
            }
          />
        </Suspense>
      )}

      {lastWarning && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            Vínculo criado com aviso: tipo nativo{" "}
            <strong>{lastWarning.native || "(desconhecido)"}</strong> pode não ser
            compatível com tipo conceitual{" "}
            <strong>{lastWarning.conceptual || "(não definido)"}</strong>.
          </span>
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">{String(error)}</p>
      )}
    </div>
  );
}

function AttributePicker({
  entityId,
  inheritDesc,
  setInheritDesc,
  isPending,
  onSubmit,
}: {
  entityId: string;
  inheritDesc: boolean;
  setInheritDesc: (v: boolean) => void;
  isPending: boolean;
  onSubmit: (attributeId: string, override: string) => void;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  const [attrId, setAttrId] = useState("");
  const [override, setOverride] = useState("");

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Atributo</label>
        <select
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={attrId}
          onChange={(e) => setAttrId(e.target.value)}
        >
          <option value="">Selecione um atributo...</option>
          {attrs.map((a) => (
            <option key={a.attribute_id} value={a.attribute_id}>
              {a.technical_name}
              {a.native_data_type ? ` — ${a.native_data_type}` : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={inheritDesc}
            onChange={(e) => setInheritDesc(e.target.checked)}
          />
          Herdar descrição do termo
        </label>
      </div>

      {!inheritDesc && (
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Descrição override</label>
          <Input
            value={override}
            onChange={(e) => setOverride(e.target.value)}
            placeholder="Descrição específica para este atributo..."
          />
        </div>
      )}

      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          disabled={!attrId || isPending}
          onClick={() => onSubmit(attrId, override)}
        >
          <LinkIcon className="mr-2 h-4 w-4" />
          {isPending ? "Vinculando..." : "Vincular"}
        </Button>
      </div>
    </div>
  );
}

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-xs uppercase tracking-wide">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

function KVLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: TermStatus }) {
  const map: Record<TermStatus, { label: string; cls: string }> = {
    DRAFT: {
      label: "Rascunho",
      cls: "bg-muted text-muted-foreground border-muted-foreground/20",
    },
    IN_REVIEW: {
      label: "Em revisão",
      cls: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
    },
    APPROVED: {
      label: "Aprovado",
      cls: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
    },
    DEPRECATED: {
      label: "Depreciado",
      cls: "bg-destructive/10 text-destructive border-destructive/30",
    },
  };
  const { label, cls } = map[status];
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
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
