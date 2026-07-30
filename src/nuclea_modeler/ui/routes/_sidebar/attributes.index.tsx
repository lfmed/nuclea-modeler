/**
 * Visão GLOBAL de atributos (ponto 5.2 do plano feedback-cliente-jul2026).
 *
 * Até a v1.0014 atributos só eram visíveis navegando entidade por entidade.
 * Esta rota (`/attributes`) lista atributos de todo o catálogo, com contexto
 * da entity-host, paginação, busca, filtros (sistema, PK, flag), ordenação
 * por coluna, coluna de flags e export CSV.
 *
 * Consome `GET /attributes/page` via useListAttributesPaginatedSuspense.
 */
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListAttributesPaginatedSuspense,
  useListSystemsSuspense,
  useListFlagsSuspense,
  type AttributesPageParams,
  type AttributeListOut,
  type FlagOut,
  type SystemListOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, KeyRound, RefreshCw } from "lucide-react";
import {
  SearchInput,
  FilterSelect,
  PaginationBar,
  FlagBadges,
  SortableTh,
  ExportCsvButton,
  downloadCsv,
} from "@/components/listings/listing-controls";

export const Route = createFileRoute("/_sidebar/attributes/")({
  component: AttributesPage,
});

const PAGE_SIZE = 50;

const PK_OPTIONS = [
  { value: "true", label: "Somente PKs" },
  { value: "false", label: "Sem PKs" },
];

function AttributesPage() {
  const [q, setQ] = useState("");
  const [systemId, setSystemId] = useState("");
  const [pk, setPk] = useState("");
  const [flagId, setFlagId] = useState("");
  const [sortBy, setSortBy] = useState("technical_name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

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

  const params: AttributesPageParams = useMemo(
    () => ({
      q: q.trim() || undefined,
      systemId: systemId || undefined,
      isPrimaryKey: pk === "" ? undefined : pk === "true",
      flagId: flagId || undefined,
      sortBy,
      sortDir,
      page,
      pageSize: PAGE_SIZE,
    }),
    [q, systemId, pk, flagId, sortBy, sortDir, page],
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Atributos</h1>
          <Badge variant="outline" className="font-mono">M3</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Visão global das colunas catalogadas em todos os sistemas. Filtre por
          sistema, chave primária ou flag; ordene clicando no cabeçalho.
        </p>
      </div>
      <Card>
        <CardHeader className="gap-3">
          <CardTitle>Atributos catalogados</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={q} onChange={withReset(setQ)} placeholder="Buscar atributo…" />
            <Suspense fallback={<Skeleton className="h-9 w-40" />}>
              <SystemFilter value={systemId} onChange={withReset(setSystemId)} />
            </Suspense>
            <FilterSelect
              value={pk}
              onChange={withReset(setPk)}
              options={PK_OPTIONS}
              placeholder="PK e não-PK"
              ariaLabel="Filtrar por chave primária"
            />
            <Suspense fallback={<Skeleton className="h-9 w-40" />}>
              <FlagFilter value={flagId} onChange={withReset(setFlagId)} />
            </Suspense>
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
                      Erro ao carregar atributos
                    </p>
                    <Button onClick={resetErrorBoundary}>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Tentar novamente
                    </Button>
                  </div>
                )}
              >
                <Suspense fallback={<TableSkeleton />}>
                  <AttributesTable
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

function FlagFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data: flags } = useListFlagsSuspense({ isActive: true }, selector());
  const options = (flags as FlagOut[]).map((f) => ({ value: f.flag_id, label: f.display_name }));
  return (
    <FilterSelect value={value} onChange={onChange} options={options} placeholder="Todas as flags" ariaLabel="Filtrar por flag" />
  );
}

function AttributesTable({
  params,
  setPage,
  sortBy,
  sortDir,
  onSort,
}: {
  params: AttributesPageParams;
  setPage: (fn: (p: number) => number) => void;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const { data } = useListAttributesPaginatedSuspense(params, selector());
  const navigate = useNavigate();
  const rows = data.items;

  const exportCsv = () => {
    const headers = ["Atributo", "Nome lógico", "Entidade", "Schema", "Sistema", "Tipo", "PK", "Nulo", "Flags"];
    const csv = rows.map((a) => [
      a.technical_name,
      a.logical_name || "",
      a.entity_technical_name || a.entity_id,
      a.schema_name || "",
      a.system_name || a.system_id || "",
      a.native_data_type || "",
      a.is_primary_key ? "sim" : "",
      a.is_nullable === false ? "NOT NULL" : "",
      (a.flags || []).map((f) => f.display_name).join(" | "),
    ]);
    downloadCsv("atributos.csv", headers, csv);
  };

  if (!rows || rows.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        Nenhum atributo encontrado com os filtros atuais.
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
              <SortableTh label="Atributo" col="technical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Nome lógico" col="logical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Entidade" col="entity_technical_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Schema" col="schema_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Sistema" col="system_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Tipo" col="native_data_type" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <th className="py-2 pr-3 font-medium">PK</th>
              <th className="py-2 pr-3 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a: AttributeListOut) => (
              <tr
                key={a.attribute_id}
                className="border-b hover:bg-muted/40 cursor-pointer transition-colors"
                onClick={() => navigate({ to: "/entities/$id", params: { id: a.entity_id } })}
              >
                <td className="py-2 pr-3 font-mono text-xs">{a.technical_name}</td>
                <td className="py-2 pr-3">{a.logical_name || "—"}</td>
                <td className="py-2 pr-3 font-mono text-xs">{a.entity_technical_name || a.entity_id}</td>
                <td className="py-2 pr-3 text-muted-foreground">{a.schema_name || "—"}</td>
                <td className="py-2 pr-3 text-muted-foreground">
                  <Link
                    to="/diagram"
                    search={{ system: a.system_id ?? undefined }}
                    className="hover:text-nuclea-primary hover:underline"
                    onClick={(ev) => ev.stopPropagation()}
                  >
                    {a.system_name || a.system_id || "—"}
                  </Link>
                </td>
                <td className="py-2 pr-3 font-mono text-xs">{a.native_data_type || "—"}</td>
                <td className="py-2 pr-3">
                  {a.is_primary_key ? (
                    <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                      <KeyRound className="h-3.5 w-3.5" /> PK
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <FlagBadges flags={a.flags} />
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
