import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useListEntitiesSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, FileText, Plus, RefreshCw } from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";

export const Route = createFileRoute("/_sidebar/entities/")({
  component: EntitiesPage,
});

function EntitiesPage() {
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
                    Erro ao carregar entidades
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
              <EntitiesTable />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
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

function EntitiesTable() {
  const { data: entities } = useListEntitiesSuspense({}, selector());
  const navigate = useNavigate();

  if (!entities || entities.length === 0) {
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
    <Card>
      <CardHeader>
        <CardTitle>Entidades catalogadas ({entities.length})</CardTitle>
        <CardDescription>Ordenado por última atualização</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Nome técnico</th>
                <th className="py-2 pr-3 font-medium">Nome lógico</th>
                <th className="py-2 pr-3 font-medium">Sistema · Schema</th>
                <th className="py-2 pr-3 font-medium">Tipo</th>
                <th className="py-2 pr-3 font-medium">Domínio</th>
                <th className="py-2 pr-3 font-medium">Criticidade</th>
                <th className="py-2 pr-3 font-medium text-right"># Attrs</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr
                  key={e.entity_id}
                  className="border-b hover:bg-muted/40 cursor-pointer transition-colors"
                  onClick={() => navigate({ to: "/entities/$id", params: { id: e.entity_id } })}
                >
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
                  <td className="py-2 pr-3 text-right tabular-nums">{e.attributes_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
      </CardHeader>
      <CardContent className="space-y-2">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
