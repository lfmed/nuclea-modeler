import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetSyncRunSuspense,
  type SyncObjectResult,
  type SyncStatus,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  RefreshCw,
  SkipForward,
  XCircle,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/sync/$id")({
  component: SyncDetailPage,
});

function SyncDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/sync">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Sincronizações
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
                    Erro ao carregar execução
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <SyncDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function SyncDetail() {
  const { id } = Route.useParams();
  const { data: run } = useGetSyncRunSuspense(id, selector());

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <RunStatusBadge status={run.status} />
          <span className="text-sm text-muted-foreground">
            Sistema: <strong>{run.system_id}</strong>
          </span>
          {run.target_catalog && (
            <span className="text-sm text-muted-foreground">
              · Catálogo destino: <strong>{run.target_catalog}</strong>
            </span>
          )}
        </div>
        <h1 className="text-3xl font-bold tracking-tight font-mono">
          {run.sync_id}
        </h1>
        <p className="text-sm text-muted-foreground mt-1 flex items-center gap-3 flex-wrap">
          <span>
            <Clock className="inline h-3.5 w-3.5 mr-1" />
            Início: {new Date(run.started_at).toLocaleString("pt-BR")}
          </span>
          {run.ended_at && (
            <span>· Fim: {new Date(run.ended_at).toLocaleString("pt-BR")}</span>
          )}
          {run.duration_ms != null && <span>· {run.duration_ms}ms</span>}
          {run.triggered_by && <span>· por {run.triggered_by}</span>}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total" value={run.objects_total ?? 0} />
        <StatCard label="Sincronizados" value={run.objects_synced ?? 0} tone="positive" />
        <StatCard label="Falharam" value={run.objects_failed ?? 0} tone="negative" />
      </div>

      {run.error_summary && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="pt-4 text-sm">
            <p className="font-medium mb-1 flex items-center gap-1">
              <AlertCircle className="h-4 w-4 text-amber-600" />
              Resumo de erros
            </p>
            <pre className="text-xs whitespace-pre-wrap font-mono">{run.error_summary}</pre>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Objetos processados</CardTitle>
        </CardHeader>
        <CardContent>
          <ObjectsTable objects={run.objects} />
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "positive" | "negative";
}) {
  const color =
    tone === "positive"
      ? "text-emerald-700 dark:text-emerald-300"
      : tone === "negative"
        ? "text-destructive"
        : "";
  return (
    <Card>
      <CardContent className="pt-4">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className={`text-3xl font-bold tabular-nums ${color}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function ObjectsTable({ objects }: { objects: SyncObjectResult[] }) {
  if (objects.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        Sem objetos registrados nesta execução.
      </p>
    );
  }
  return (
    <div className="rounded-md border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Status</th>
            <th className="text-left px-3 py-2 font-medium">Entidade</th>
            <th className="text-left px-3 py-2 font-medium">Tabela destino</th>
            <th className="text-left px-3 py-2 font-medium">Mensagem</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {objects.map((o, i) => (
            <tr key={i}>
              <td className="px-3 py-2">
                <ObjectStatusBadge status={o.status} />
              </td>
              <td className="px-3 py-2 font-mono">
                {o.schema_name}.{o.technical_name}
              </td>
              <td className="px-3 py-2 font-mono text-muted-foreground">
                {o.target_table}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {o.message ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunStatusBadge({ status }: { status: SyncStatus }) {
  const cfg = {
    RUNNING: {
      icon: <RefreshCw className="h-3.5 w-3.5 animate-spin" />,
      color: "bg-muted text-muted-foreground border-muted-foreground/30",
    },
    SUCCESS: {
      icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      color: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
    },
    PARTIAL: {
      icon: <AlertCircle className="h-3.5 w-3.5" />,
      color: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
    },
    FAILED: {
      icon: <XCircle className="h-3.5 w-3.5" />,
      color: "bg-destructive/10 text-destructive border-destructive/30",
    },
  }[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${cfg.color}`}
    >
      {cfg.icon}
      {status}
    </span>
  );
}

function ObjectStatusBadge({ status }: { status: SyncObjectResult["status"] }) {
  const cfg = {
    OK: {
      icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      color: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
    },
    SKIPPED: {
      icon: <SkipForward className="h-3.5 w-3.5" />,
      color: "bg-muted text-muted-foreground border-muted-foreground/30",
    },
    ERROR: {
      icon: <XCircle className="h-3.5 w-3.5" />,
      color: "bg-destructive/10 text-destructive border-destructive/30",
    },
  }[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${cfg.color}`}
    >
      {cfg.icon}
      {status}
    </span>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-12 w-2/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
