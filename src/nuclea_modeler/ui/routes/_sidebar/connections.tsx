import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useListConnectionsSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Database, Plus, RefreshCw, CheckCircle2, XCircle, MinusCircle } from "lucide-react";

export const Route = createFileRoute("/_sidebar/connections")({
  component: ConnectionsPage,
});

function ConnectionsPage() {
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
                    Erro ao carregar conexões
                  </CardTitle>
                  <CardDescription>
                    O backend está disponível? Tente novamente.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button variant="outline" onClick={resetErrorBoundary}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Tentar novamente
                  </Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<TableSkeleton />}>
              <ConnectionsTable />
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
          <h1 className="text-3xl font-bold tracking-tight">Conexões de Ambiente</h1>
          <Badge variant="outline" className="font-mono">M1</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Cadastre conexões ODBC, REST ou import de DDL para os ambientes HINT, HEXT e PROD.
          Credenciais são armazenadas em Databricks Secrets, nunca em texto puro.
        </p>
      </div>
      <Button asChild>
        <Link to="/connections/new">
          <Plus className="mr-2 h-4 w-4" />
          Nova conexão
        </Link>
      </Button>
    </div>
  );
}

function ConnectionsTable() {
  const { data: connections } = useListConnectionsSuspense(selector());

  if (!connections || connections.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <Database className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            Nenhuma conexão cadastrada. Comece criando uma conexão para HINT, HEXT ou PROD.
          </p>
          <Button asChild>
            <Link to="/connections/new">
              <Plus className="mr-2 h-4 w-4" />
              Cadastrar primeira conexão
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Conexões cadastradas ({connections.length})</CardTitle>
        <CardDescription>Ordenado por última atualização</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Alias</th>
                <th className="py-2 pr-3 font-medium">Ambiente</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium">Tipo</th>
                <th className="py-2 pr-3 font-medium">Último teste</th>
                <th className="py-2 pr-3 font-medium text-right">Latência</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((c) => (
                <tr key={c.connection_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3">
                    <Link to="/connections/$id" params={{ id: c.connection_id }} className="font-medium hover:text-nuclea-primary">
                      {c.alias}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <EnvBadge env={c.environment} />
                  </td>
                  <td className="py-2 pr-3">{c.system_name || c.system_id}</td>
                  <td className="py-2 pr-3">
                    <Badge variant="outline">{c.connection_type}</Badge>
                  </td>
                  <td className="py-2 pr-3">
                    <TestStatusBadge status={c.last_test_status} />
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {c.last_test_latency_ms != null ? `${c.last_test_latency_ms} ms` : "—"}
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

function EnvBadge({ env }: { env: "HINT" | "HEXT" | "PROD" }) {
  const color =
    env === "PROD"
      ? "bg-destructive/10 text-destructive border-destructive/30"
      : env === "HEXT"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300";
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>{env}</span>;
}

function TestStatusBadge({ status }: { status?: string | null }) {
  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3.5 w-3.5" />
        OK
      </span>
    );
  }
  if (status === "failure") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        <XCircle className="h-3.5 w-3.5" />
        Falha
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <MinusCircle className="h-3.5 w-3.5" />
      Nunca testado
    </span>
  );
}

function TableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-32" />
      </CardHeader>
      <CardContent className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
