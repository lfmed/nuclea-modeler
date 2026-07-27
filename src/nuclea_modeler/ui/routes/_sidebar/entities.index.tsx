/**
 * Listagem de entidades — agora paginada, filtrável e ordenável.
 *
 * Contexto (ponto 5 do plano feedback-cliente-jul2026): a versão anterior
 * carregava TODAS as entidades de uma vez (useListEntitiesSuspense, sem
 * paginação nem filtros, ordenação fixa). Passou a consumir o endpoint
 * paginado (`GET /entities/page` via useListEntitiesPaginatedSuspense) com:
 *   - busca textual (nome técnico/lógico);
 *   - filtros: sistema, tipo, criticidade e flag;
 *   - ordenação por coluna (clicando no cabeçalho);
 *   - coluna de flags;
 *   - export CSV da página atual.
 *
 * Os controles de filtro ficam FORA do Suspense boundary (renderizam na hora);
 * só a tabela suspende — assim mudar um filtro não pisca a página inteira.
 */
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListEntitiesPaginatedSuspense,
  useListSystemsSuspense,
  useListFlagsSuspense,
  useBatchApplyEntityFlags,
  useBatchRemoveEntityFlags,
  type EntitiesPageParams,
  type EntityListOut,
  type FlagOut,
  type SystemListOut,
  type BatchFlagSpec,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, FileText, Plus, RefreshCw } from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";
import {
  SearchInput,
  FilterSelect,
  PaginationBar,
  FlagBadges,
  SortableTh,
  ExportCsvButton,
  downloadCsv,
} from "@/components/listings/listing-controls";
import { FlagBatchBar, toastBatchFlagResult } from "@/components/flags/flag-batch-bar";

export const Route = createFileRoute("/_sidebar/entities/")({
  component: EntitiesPage,
});

const PAGE_SIZE = 50;

const ENTITY_TYPES: { value: string; label: string }[] = [
  { value: "TABLE", label: "Tabela" },
  { value: "VIEW", label: "View" },
  { value: "MATERIALIZED_VIEW", label: "View materializada" },
  { value: "EXTERNAL", label: "Externa" },
];

const CRITICALITIES: { value: string; label: string }[] = [
  { value: "HIGH", label: "Alta" },
  { value: "MEDIUM", label: "Média" },
  { value: "LOW", label: "Baixa" },
];

function EntitiesPage() {
  // Estado dos filtros vive no topo (fora do Suspense) para não resetar quando
  // a tabela suspende. Ao mudar qualquer filtro, voltamos para a página 1.
  const [q, setQ] = useState("");
  const [systemId, setSystemId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [criticality, setCriticality] = useState("");
  const [flagId, setFlagId] = useState("");
  const [sortBy, setSortBy] = useState("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const onSort = (col: string) => {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir("asc");
    }
    setPage(1);
  };

  // Helper para resetar a paginação sempre que um filtro muda.
  const withReset = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  const params: EntitiesPageParams = useMemo(
    () => ({
      q: q.trim() || undefined,
      systemId: systemId || undefined,
      entityType: (entityType || undefined) as EntitiesPageParams["entityType"],
      criticality: (criticality || undefined) as EntitiesPageParams["criticality"],
      flagId: flagId || undefined,
      sortBy,
      sortDir,
      page,
      pageSize: PAGE_SIZE,
    }),
    [q, systemId, entityType, criticality, flagId, sortBy, sortDir, page],
  );

  return (
    <div className="space-y-6">
      <Header />
      <Card>
        <CardHeader className="gap-3">
          <CardTitle>Entidades catalogadas</CardTitle>
          <Filters
            q={q}
            setQ={withReset(setQ)}
            systemId={systemId}
            setSystemId={withReset(setSystemId)}
            entityType={entityType}
            setEntityType={withReset(setEntityType)}
            criticality={criticality}
            setCriticality={withReset(setCriticality)}
            flagId={flagId}
            setFlagId={withReset(setFlagId)}
          />
        </CardHeader>
        <CardContent>
          <QueryErrorResetBoundary>
            {({ reset }) => (
              <ErrorBoundary
                onReset={reset}
                fallbackRender={({ resetErrorBoundary }) => (
                  <div className="flex flex-col items-start gap-3 py-6">
                    <p className="flex items-center gap-2 text-destructive">
                      <AlertCircle className="h-5 w-5" />
                      Erro ao carregar entidades
                    </p>
                    <Button onClick={resetErrorBoundary}>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Tentar novamente
                    </Button>
                  </div>
                )}
              >
                <Suspense fallback={<TableSkeleton />}>
                  <EntitiesTable
                    params={params}
                    page={page}
                    setPage={setPage}
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
          </QueryErrorResetBoundary>
        </CardContent>
      </Card>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Entidades</h1>
          <Badge variant="outline" className="font-mono">M3</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Tabelas, views e demais objetos catalogados. Documente nome lógico, descrição,
          domínio, owners e criticidade.
        </p>
      </div>
      <Button asChild>
        <Link to="/entities/new">
          <Plus className="mr-2 h-4 w-4" />
          Nova entidade
        </Link>
      </Button>
    </div>
  );
}

function Filters(props: {
  q: string;
  setQ: (v: string) => void;
  systemId: string;
  setSystemId: (v: string) => void;
  entityType: string;
  setEntityType: (v: string) => void;
  criticality: string;
  setCriticality: (v: string) => void;
  flagId: string;
  setFlagId: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchInput value={props.q} onChange={props.setQ} placeholder="Buscar entidade…" />
      <Suspense fallback={<Skeleton className="h-9 w-40" />}>
        <SystemFilter value={props.systemId} onChange={props.setSystemId} />
      </Suspense>
      <FilterSelect
        value={props.entityType}
        onChange={props.setEntityType}
        options={ENTITY_TYPES}
        placeholder="Todos os tipos"
        ariaLabel="Filtrar por tipo"
      />
      <FilterSelect
        value={props.criticality}
        onChange={props.setCriticality}
        options={CRITICALITIES}
        placeholder="Toda criticidade"
        ariaLabel="Filtrar por criticidade"
      />
      <Suspense fallback={<Skeleton className="h-9 w-40" />}>
        <FlagFilter value={props.flagId} onChange={props.setFlagId} />
      </Suspense>
    </div>
  );
}

function SystemFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: systems } = useListSystemsSuspense(selector());
  const options = (systems as SystemListOut[]).map((s) => ({
    value: s.system_id,
    label: s.system_name,
  }));
  return (
    <FilterSelect
      value={value}
      onChange={onChange}
      options={options}
      placeholder="Todos os sistemas"
      ariaLabel="Filtrar por sistema"
    />
  );
}

function FlagFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: flags } = useListFlagsSuspense({ isActive: true }, selector());
  const options = (flags as FlagOut[]).map((f) => ({
    value: f.flag_id,
    label: f.display_name,
  }));
  return (
    <FilterSelect
      value={value}
      onChange={onChange}
      options={options}
      placeholder="Todas as flags"
      ariaLabel="Filtrar por flag"
    />
  );
}

function EntitiesTable({
  params,
  page,
  setPage,
  sortBy,
  sortDir,
  onSort,
}: {
  params: EntitiesPageParams;
  page: number;
  setPage: (fn: (p: number) => number) => void;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const { data } = useListEntitiesPaginatedSuspense(params, selector());
  const navigate = useNavigate();
  const entities = data.items;
  const qc = useQueryClient();

  const exportCsv = () => {
    const headers = [
      "Nome técnico", "Nome lógico", "Sistema", "Schema", "Tipo",
      "Domínio", "Criticidade", "# Attrs", "Flags",
    ];
    const rows = entities.map((e) => [
      e.technical_name,
      e.logical_name || "",
      e.system_name || e.system_id,
      e.schema_name,
      e.entity_type,
      e.domain || "",
      e.criticality || "",
      e.attributes_count ?? 0,
      (e.flags || []).map((f) => f.display_name).join(" | "),
    ]);
    downloadCsv("entidades.csv", headers, rows);
  };

  // Seleção múltipla p/ operações em lote de flags (Blocos 3 + 6).
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const clearSelection = () => setSelected(new Set());

  const invalidateFlags = () => {
    // As flags de cada entidade são carregadas na página de detalhe e agora
    // também na coluna de flags desta lista paginada; invalidamos ambas para
    // refletir mudanças imediatamente.
    qc.invalidateQueries({ queryKey: ["listEntityFlags"] });
    qc.invalidateQueries({ queryKey: ["listEntitiesPaginated"] });
  };

  const { mutate: applyFlags, isPending: applying } = useBatchApplyEntityFlags({
    mutation: {
      onSuccess: (r) => {
        invalidateFlags();
        clearSelection();
        toastBatchFlagResult(r);
      },
      onError: (e) =>
        toast.error("Falha ao aplicar flags", {
          description: e instanceof Error ? e.message : "Erro desconhecido",
        }),
    },
  });
  const { mutate: removeFlags, isPending: removing } = useBatchRemoveEntityFlags({
    mutation: {
      onSuccess: (r) => {
        invalidateFlags();
        clearSelection();
        toastBatchFlagResult(r);
      },
      onError: (e) =>
        toast.error("Falha ao remover flags", {
          description: e instanceof Error ? e.message : "Erro desconhecido",
        }),
    },
  });

  const ids = Array.from(selected);
  const onApply = (specs: BatchFlagSpec[]) =>
    applyFlags({ data: { target_ids: ids, flags: specs } });
  const onRemove = (flagIds: string[]) =>
    removeFlags({ data: { target_ids: ids, flag_ids: flagIds } });
  const allSelected = entities.length > 0 && selected.size === entities.length;
  const toggleAll = () =>
    setSelected((prev) =>
      prev.size === entities.length
        ? new Set()
        : new Set(entities.map((e) => e.entity_id)),
    );

  if (!entities || entities.length === 0) {
    // Página vazia: se estamos filtrando/paginando, mostra mensagem simples;
    // se o catálogo está realmente vazio (sem filtros, página 1), mostra o
    // EmptyState rico com CTAs.
    const hasFilters =
      !!params.q || !!params.systemId || !!params.entityType ||
      !!params.criticality || !!params.flagId;
    if (page > 1 || hasFilters) {
      return (
        <div className="py-10 text-center text-sm text-muted-foreground">
          Nenhuma entidade encontrada com os filtros atuais.
        </div>
      );
    }
    return (
      <EmptyState
        icon={<FileText className="h-10 w-10" />}
        title="Nenhuma entidade catalogada"
        description={
          <>
            Entidades são as tabelas e views que vivem nos sistemas. Você pode criar uma
            manualmente, importar de um arquivo <code className="text-xs font-mono bg-muted/60 px-1 py-0.5 rounded">.DM1</code> do
            ER/Studio, ou rodar uma engenharia reversa contra HINT/HEXT/PROD.
          </>
        }
        primaryAction={{ label: "Nova entidade", to: "/entities/new" }}
        secondaryAction={{ label: "Engenharia reversa", to: "/extractions" }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {selected.size > 0 && (
        <FlagBatchBar
          count={selected.size}
          busy={applying || removing}
          noun="entidade"
          onClear={clearSelection}
          onApply={onApply}
          onRemove={onRemove}
        />
      )}
      <div className="flex justify-end pb-2">
        <ExportCsvButton onClick={exportCsv} />
      </div>
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
                  aria-label="Selecionar todas as entidades"
                />
              </th>
              <SortableTh label="Nome técnico" col="technical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Nome lógico" col="logical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Sistema · Schema" col="system_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Tipo" col="entity_type" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Domínio" col="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Criticidade" col="criticality" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <th className="py-2 pr-3 font-medium">Flags</th>
              <SortableTh label="# Attrs" col="attributes_count" sortBy={sortBy} sortDir={sortDir} onSort={onSort} className="text-right" />
            </tr>
          </thead>
          <tbody>
            {entities.map((e: EntityListOut) => (
              <tr
                key={e.entity_id}
                className={
                  "border-b hover:bg-muted/40 cursor-pointer transition-colors " +
                  (selected.has(e.entity_id) ? "bg-nuclea-primary/5" : "")
                }
                onClick={() => navigate({ to: "/entities/$id", params: { id: e.entity_id } })}
              >
                <td className="py-2 pr-3" onClick={(ev) => ev.stopPropagation()}>
                  <input
                    type="checkbox"
                    className="h-4 w-4 cursor-pointer accent-nuclea-primary"
                    checked={selected.has(e.entity_id)}
                    onChange={() => toggle(e.entity_id)}
                    aria-label={`Selecionar ${e.technical_name}`}
                  />
                </td>
                <td className="py-2 pr-3 font-mono text-xs">
                  <Link
                    to="/entities/$id"
                    params={{ id: e.entity_id }}
                    className="hover:text-nuclea-primary"
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    {e.technical_name}
                  </Link>
                </td>
                <td className="py-2 pr-3">{e.logical_name || "—"}</td>
                <td className="py-2 pr-3 text-muted-foreground">
                  {e.system_name || e.system_id} <span className="opacity-60">·</span> {e.schema_name}
                </td>
                <td className="py-2 pr-3">
                  <Badge variant="outline">{e.entity_type}</Badge>
                </td>
                <td className="py-2 pr-3">{e.domain || "—"}</td>
                <td className="py-2 pr-3">
                  <CriticalityBadge value={e.criticality} />
                </td>
                <td className="py-2 pr-3">
                  <FlagBadges flags={e.flags} />
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{e.attributes_count ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationBar
        page={data.page}
        pageSize={data.page_size}
        total={data.total}
        count={entities.length}
        hasMore={data.has_more}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => p + 1)}
      />
    </div>
  );
}

function CriticalityBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const color =
    value === "HIGH"
      ? "bg-destructive/10 text-destructive border-destructive/30"
      : value === "MEDIUM"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300";
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>{value}</span>;
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
