/**
 * Visão GLOBAL de índices (ponto 5.2 do plano feedback-cliente-jul2026).
 *
 * Até a v1.0014 índices só apareciam em cards dentro de cada entidade
 * (indexes-section.tsx). Esta rota (`/indexes`) lista índices de todo o
 * catálogo com contexto da entity-host, paginação, busca, filtros (sistema,
 * tipo de índice, UNIQUE), ordenação por coluna e export CSV.
 *
 * Consome `GET /indexes/page` via useListIndexesPaginatedSuspense.
 */
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Suspense, useEffect, useMemo, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { saveLastSystemId, getLastSystemId, coerceNumber } from "@/lib/persist-search";

import {
  useListIndexesPaginatedSuspense,
  useListSystemsSuspense,
  type IndexesPageParams,
  type IndexListOut,
  type IndexType,
  type SystemListOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RefreshCw } from "lucide-react";
import {
  SearchInput,
  FilterSelect,
  PaginationBar,
  SortableTh,
  ExportCsvButton,
  downloadCsv,
} from "@/components/listings/listing-controls";

export const Route = createFileRoute("/_sidebar/indexes/")({
  component: IndexesPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): {
    q?: string;
    system?: string;
    indexType?: string;
    unique?: string;
    sortBy?: string;
    sortDir?: "asc" | "desc";
    page?: number;
  } => ({
    q: (search.q as string) || undefined,
    system: (search.system as string) || undefined,
    indexType: (search.indexType as string) || undefined,
    unique: (search.unique as string) || undefined,
    sortBy: (search.sortBy as string) || undefined,
    sortDir: (search.sortDir as string as "asc" | "desc") || undefined,
    page: coerceNumber(search.page as string) || undefined,
  }),
});

const PAGE_SIZE = 50;

const INDEX_TYPES: { value: string; label: string }[] = [
  "BTREE", "HASH", "UNIQUE", "GIN", "BRIN", "GIST",
  "BITMAP", "CLUSTERED", "NONCLUSTERED", "Z-ORDER", "LIQUID",
].map((t) => ({ value: t, label: t }));

const UNIQUE_OPTIONS = [
  { value: "true", label: "Somente UNIQUE" },
  { value: "false", label: "Não UNIQUE" },
];

function IndexesPage() {
  // Lê os search params da URL (fonte primária de estado para persistência)
  const search = Route.useSearch();
  const navigate = useNavigate();

  // Inicializa estado a partir da URL (search params)
  const [q, setQ] = useState(search.q || "");
  // "Sistema atual" compartilhado entre as telas de modelagem (ver entities.index).
  const [systemId, setSystemId] = useState(search.system || getLastSystemId() || "");
  const [indexType, setIndexType] = useState(search.indexType || "");
  const [unique, setUnique] = useState(search.unique || "");
  const [sortBy, setSortBy] = useState(search.sortBy || "index_name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(search.sortDir || "asc");
  const [page, setPage] = useState(search.page || 1);

  // Sincroniza estado no URL e sessionStorage sempre que muda (to: "." fixa a rota).
  useEffect(() => {
    if (systemId) saveLastSystemId(systemId);
    navigate({
      to: ".",
      search: {
        q: q || undefined,
        system: systemId || undefined,
        indexType: indexType || undefined,
        unique: unique || undefined,
        sortBy: sortBy !== "index_name" ? sortBy : undefined,
        sortDir: sortDir !== "asc" ? sortDir : undefined,
        page: page !== 1 ? page : undefined,
      },
    });
  }, [q, systemId, indexType, unique, sortBy, sortDir, page, navigate]);

  const onSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortBy(col);
      setSortDir("asc");
    }
    setPage(1);
  };
  const withReset = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  const params: IndexesPageParams = useMemo(
    () => ({
      q: q.trim() || undefined,
      systemId: systemId || undefined,
      indexType: (indexType || undefined) as IndexType | undefined,
      isUnique: unique === "" ? undefined : unique === "true",
      sortBy,
      sortDir,
      page,
      pageSize: PAGE_SIZE,
    }),
    [q, systemId, indexType, unique, sortBy, sortDir, page],
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Índices</h1>
          <Badge variant="outline" className="font-mono">M3</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Visão global dos índices catalogados em todos os sistemas. Filtre por
          sistema, tipo de índice ou UNIQUE; ordene clicando no cabeçalho.
        </p>
      </div>
      <Card>
        <CardHeader className="gap-3">
          <CardTitle>Índices catalogados</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={q} onChange={withReset(setQ)} placeholder="Buscar índice…" />
            <Suspense fallback={<Skeleton className="h-9 w-40" />}>
              <SystemFilter value={systemId} onChange={withReset(setSystemId)} />
            </Suspense>
            <FilterSelect
              value={indexType}
              onChange={withReset(setIndexType)}
              options={INDEX_TYPES}
              placeholder="Todos os tipos"
              ariaLabel="Filtrar por tipo de índice"
            />
            <FilterSelect
              value={unique}
              onChange={withReset(setUnique)}
              options={UNIQUE_OPTIONS}
              placeholder="UNIQUE e não-UNIQUE"
              ariaLabel="Filtrar por UNIQUE"
            />
          </div>
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
                      Erro ao carregar índices
                    </p>
                    <Button onClick={resetErrorBoundary}>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Tentar novamente
                    </Button>
                  </div>
                )}
              >
                <Suspense fallback={<TableSkeleton />}>
                  <IndexesTable
                    params={params}
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

function SystemFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: systems } = useListSystemsSuspense(selector());
  const options = (systems as SystemListOut[]).map((s) => ({
    value: s.system_id,
    label: s.system_name,
  }));
  return (
    <FilterSelect value={value} onChange={onChange} options={options} placeholder="Todos os sistemas" ariaLabel="Filtrar por sistema" />
  );
}

function IndexesTable({
  params,
  setPage,
  sortBy,
  sortDir,
  onSort,
}: {
  params: IndexesPageParams;
  setPage: (fn: (p: number) => number) => void;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const { data } = useListIndexesPaginatedSuspense(params, selector());
  const navigate = useNavigate();
  const rows = data.items;

  const exportCsv = () => {
    // Descrição incluída no export (v1.0030).
    const headers = ["Índice", "Tipo", "UNIQUE", "Colunas", "Entidade", "Schema", "Sistema", "Origem", "Descrição"];
    const csv = rows.map((ix) => [
      ix.index_name,
      ix.index_type,
      ix.is_unique ? "sim" : "",
      ix.columns.map((c) => `${c.name} ${c.direction}`).join(", "),
      ix.entity_technical_name || ix.entity_id,
      ix.schema_name || "",
      ix.system_name || ix.system_id || "",
      ix.origin || "",
      ix.description_md || "",
    ]);
    downloadCsv("indices.csv", headers, csv);
  };

  if (!rows || rows.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        Nenhum índice encontrado com os filtros atuais.
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-end pb-2">
        <ExportCsvButton onClick={exportCsv} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <SortableTh label="Índice" col="index_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Tipo" col="index_type" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="UNIQUE" col="is_unique" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <th className="py-2 pr-3 font-medium">Colunas</th>
              <SortableTh label="Entidade" col="entity_technical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Schema" col="schema_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Sistema" col="system_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {rows.map((ix: IndexListOut) => (
              <tr
                key={ix.index_id}
                className="border-b hover:bg-muted/40 cursor-pointer transition-colors"
                onClick={() => navigate({ to: "/entities/$id", params: { id: ix.entity_id } })}
              >
                <td className="py-2 pr-3 font-mono text-xs">{ix.index_name}</td>
                <td className="py-2 pr-3">
                  <Badge variant="outline">{ix.index_type}</Badge>
                </td>
                <td className="py-2 pr-3">
                  {ix.is_unique ? (
                    <Badge variant="secondary" className="text-[10px]">UNIQUE</Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="py-2 pr-3 font-mono text-xs">
                  {ix.columns.map((c) => `${c.name} ${c.direction}`).join(", ") || "—"}
                </td>
                <td className="py-2 pr-3 font-mono text-xs">{ix.entity_technical_name || ix.entity_id}</td>
                <td className="py-2 pr-3 text-muted-foreground">{ix.schema_name || "—"}</td>
                <td className="py-2 pr-3 text-muted-foreground">
                  <Link
                    to="/diagram"
                    search={{ system: ix.system_id ?? undefined }}
                    className="hover:text-nuclea-primary hover:underline"
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    {ix.system_name || ix.system_id || "—"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationBar
        page={data.page}
        pageSize={data.page_size}
        total={data.total}
        count={rows.length}
        hasMore={data.has_more}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => p + 1)}
      />
    </div>
  );
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
