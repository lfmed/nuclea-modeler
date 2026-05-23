import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetConnectionSuspense,
  useTestConnection,
  useDeleteConnection,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft, AlertCircle, RefreshCw, Trash2, CheckCircle2, XCircle, Clock,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/connections/$id")({
  component: ConnectionDetailPage,
});

function ConnectionDetailPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/connections">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Conexões
          </Link>
        </Button>
      </div>

      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar conexão
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <ConnectionDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ConnectionDetail() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: conn } = useGetConnectionSuspense(id, selector());

  const { mutate: test, isPending: testing } = useTestConnection({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getConnection", id] });
        qc.invalidateQueries({ queryKey: ["listConnections"] });
      },
    },
  });
  const { mutate: del, isPending: deleting } = useDeleteConnection({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listConnections"] });
        navigate({ to: "/connections" });
      },
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{conn.alias}</h1>
          <div className="flex items-center gap-2 mt-2">
            <EnvBadge env={conn.environment} />
            <Badge variant="outline">{conn.connection_type}</Badge>
            <span className="text-sm text-muted-foreground">·</span>
            <span className="text-sm text-muted-foreground">
              {conn.system_name || conn.system_id}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => test({ connectionId: id })} disabled={testing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${testing ? "animate-spin" : ""}`} />
            Testar conexão
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              if (confirm(`Excluir conexão "${conn.alias}"?`)) del({ connectionId: id });
            }}
            disabled={deleting}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Excluir
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Último teste</CardTitle>
            <CardDescription>Resultado da última validação de conectividade</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <TestStatusBlock
              status={conn.last_test_status}
              latency={conn.last_test_latency_ms}
              version={conn.last_test_db_version}
              error={conn.last_test_error}
              at={conn.last_test_at}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Configuração</CardTitle>
            <CardDescription>Parâmetros de conexão (sem credenciais)</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="rounded-md bg-muted p-3 text-xs overflow-x-auto">
              {JSON.stringify(conn.config, null, 2)}
            </pre>
            <Separator className="my-4" />
            <div className="space-y-2 text-sm">
              <KV label="Secrets scope" value={conn.secret_scope || "—"} />
              <KV label="Chave usuário" value={conn.secret_key_user || "—"} />
              <KV label="Chave senha" value={conn.secret_key_pass ? "•••••" : "—"} />
              <KV label="Chave token" value={conn.secret_key_token ? "•••••" : "—"} />
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Metadados</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm md:grid-cols-2">
            <KV label="ID" value={conn.connection_id} mono />
            <KV label="Sistema" value={conn.system_name || conn.system_id} />
            <KV label="Criado por" value={conn.created_by} />
            <KV label="Atualizado por" value={conn.updated_by} />
            <KV label="Criado em" value={new Date(conn.created_at).toLocaleString("pt-BR")} />
            <KV label="Atualizado em" value={new Date(conn.updated_at).toLocaleString("pt-BR")} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KV({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-xs" : ""}>{value}</span>
    </div>
  );
}

function EnvBadge({ env }: { env: "HINT" | "HEXT" | "PROD" }) {
  const color =
    env === "PROD"
      ? "bg-destructive/10 text-destructive border-destructive/30"
      : env === "HEXT"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300";
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>
      {env}
    </span>
  );
}

function TestStatusBlock({
  status, latency, version, error, at,
}: {
  status?: string | null;
  latency?: number | null;
  version?: string | null;
  error?: string | null;
  at?: string | null;
}) {
  if (!status || status === "never") {
    return (
      <p className="text-sm text-muted-foreground">
        Esta conexão ainda não foi testada. Clique em <strong>Testar conexão</strong>.
      </p>
    );
  }
  const ok = status === "success";
  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-2 ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>
        {ok ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
        <span className="font-medium">{ok ? "Conexão saudável" : "Falha na conexão"}</span>
      </div>
      {at && (
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {new Date(at).toLocaleString("pt-BR")}
        </p>
      )}
      <div className="space-y-1 text-sm">
        {latency != null && <p>Latência: <span className="font-mono">{latency} ms</span></p>}
        {version && <p>Versão detectada: <span className="font-mono">{version}</span></p>}
        {error && (
          <pre className="mt-2 rounded-md bg-destructive/10 p-3 text-xs whitespace-pre-wrap text-destructive">
            {error}
          </pre>
        )}
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-1/2" />
      <div className="grid gap-6 md:grid-cols-2">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
