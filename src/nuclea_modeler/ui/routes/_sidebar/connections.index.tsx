import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListConnectionsSuspense,
  useGetConnection,
  useTestConnection,
  useDeleteConnection,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/apx/empty-state";
import {
  AlertCircle,
  Database,
  Plus,
  RefreshCw,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Trash2,
  Clock,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/connections/")({
  component: ConnectionsPage,
});

function ConnectionsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
              <ConnectionsTable onSelect={setSelectedId} />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>

      <ConnectionDetailSheet
        connectionId={selectedId}
        onClose={() => setSelectedId(null)}
      />
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

function ConnectionsTable({ onSelect }: { onSelect: (id: string) => void }) {
  const { data: connections } = useListConnectionsSuspense(selector());

  if (!connections || connections.length === 0) {
    return (
      <EmptyState
        icon={<Database className="h-10 w-10" />}
        title="Nenhuma conexão cadastrada"
        description={
          <>
            Conexões representam ambientes (<strong>HINT</strong>, <strong>HEXT</strong>, <strong>PROD</strong>)
            catalogados pelo app. As credenciais ficam em Databricks Secrets — nunca em texto puro.
          </>
        }
        primaryAction={{ label: "Cadastrar primeira conexão", to: "/connections/new" }}
        secondaryAction={{ label: "Saiba mais", to: "/help" }}
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Conexões cadastradas ({connections.length})</CardTitle>
        <CardDescription>
          Clique em uma linha para ver os detalhes
        </CardDescription>
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
                <tr
                  key={c.connection_id}
                  className="border-b hover:bg-muted/40 cursor-pointer transition-colors"
                  onClick={() => onSelect(c.connection_id)}
                >
                  <td className="py-2 pr-3 font-medium">{c.alias}</td>
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

function ConnectionDetailSheet({
  connectionId,
  onClose,
}: {
  connectionId: string | null;
  onClose: () => void;
}) {
  const open = connectionId !== null;
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: conn, isLoading, isError, error, refetch } = useGetConnection(
    connectionId ?? undefined,
  );

  const { mutate: test, isPending: testing } = useTestConnection({
    mutation: {
      onSuccess: () => {
        if (connectionId) {
          qc.invalidateQueries({ queryKey: ["getConnection", connectionId] });
        }
        qc.invalidateQueries({ queryKey: ["listConnections"] });
        toast.success("Conexão testada");
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  const { mutate: del, isPending: deleting } = useDeleteConnection({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listConnections"] });
        toast.success("Conexão excluída");
        onClose();
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="sm:max-w-2xl w-full overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{conn?.alias ?? (isLoading ? "Carregando…" : "Conexão")}</SheetTitle>
          <SheetDescription>
            Detalhes da conexão · {conn?.connection_type ?? "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="px-4 pb-6 space-y-6">
          {isLoading && (
            <div className="space-y-3">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}

          {isError && (
            <Card className="border-destructive/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  Erro ao carregar conexão
                </CardTitle>
                <CardDescription>
                  {error instanceof Error ? error.message : "Erro desconhecido."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button onClick={() => refetch()}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Tentar novamente
                </Button>
              </CardContent>
            </Card>
          )}

          {!isLoading && !isError && conn && connectionId && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <EnvBadge env={conn.environment} />
                <Badge variant="outline">{conn.connection_type}</Badge>
                <span className="text-sm text-muted-foreground">·</span>
                <span className="text-sm text-muted-foreground">
                  {conn.system_name || conn.system_id}
                </span>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button onClick={() => test({ connectionId })} disabled={testing}>
                  <RefreshCw className={`mr-2 h-4 w-4 ${testing ? "animate-spin" : ""}`} />
                  Testar conexão
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    if (confirm(`Excluir conexão "${conn.alias}"?`)) {
                      del({ connectionId });
                    }
                  }}
                  disabled={deleting}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Excluir
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    navigate({
                      to: "/connections/$id",
                      params: { id: connectionId },
                    });
                  }}
                >
                  Abrir em página
                </Button>
              </div>

              <Separator />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Último teste</CardTitle>
                </CardHeader>
                <CardContent>
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
                  <CardTitle className="text-base">Configuração</CardTitle>
                  <CardDescription>Parâmetros (sem credenciais)</CardDescription>
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

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Metadados</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 text-sm">
                  <KV label="ID" value={conn.connection_id} mono />
                  <KV label="Sistema" value={conn.system_name || conn.system_id} />
                  <KV label="Criado por" value={conn.created_by} />
                  <KV label="Atualizado por" value={conn.updated_by} />
                  <KV
                    label="Criado em"
                    value={new Date(conn.created_at).toLocaleString("pt-BR")}
                  />
                  <KV
                    label="Atualizado em"
                    value={new Date(conn.updated_at).toLocaleString("pt-BR")}
                  />
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function KV({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
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
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}
    >
      {env}
    </span>
  );
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

function TestStatusBlock({
  status,
  latency,
  version,
  error,
  at,
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
        Esta conexão ainda não foi testada. Clique em{" "}
        <strong>Testar conexão</strong>.
      </p>
    );
  }
  const ok = status === "success";
  return (
    <div className="space-y-2">
      <div
        className={`flex items-center gap-2 ${
          ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
        }`}
      >
        {ok ? (
          <CheckCircle2 className="h-5 w-5" />
        ) : (
          <XCircle className="h-5 w-5" />
        )}
        <span className="font-medium">
          {ok ? "Conexão saudável" : "Falha na conexão"}
        </span>
      </div>
      {at && (
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {new Date(at).toLocaleString("pt-BR")}
        </p>
      )}
      <div className="space-y-1 text-sm">
        {latency != null && (
          <p>
            Latência: <span className="font-mono">{latency} ms</span>
          </p>
        )}
        {version && (
          <p>
            Versão detectada: <span className="font-mono">{version}</span>
          </p>
        )}
        {error && (
          <pre className="mt-2 rounded-md bg-destructive/10 p-3 text-xs whitespace-pre-wrap text-destructive">
            {error}
          </pre>
        )}
      </div>
    </div>
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
