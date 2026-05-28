import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListSandboxesSuspense,
  useListLakebaseInstancesSuspense,
  useCreateSandbox,
  useTestSandbox,
  useDeactivateSandbox,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  Database,
  Plus,
  RefreshCw,
  CheckCircle2,
  XCircle,
  TestTube2,
  Trash2,
  MinusCircle,
} from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";

export const Route = createFileRoute("/_sidebar/lakebase")({
  component: LakebasePage,
});

function LakebasePage() {
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
                    Erro ao carregar sandboxes
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
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <SandboxesList />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function Header() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <h1 className="text-3xl font-bold tracking-tight">Lakebase Sandbox</h1>
        <Badge variant="outline" className="font-mono">M-LB</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Instâncias Lakebase Postgres usadas como sandbox de validação para os modelos catalogados.
        O app não usa Lakebase para guardar seu estado — apenas para validação round-trip:
        aplicar DDL → engenharia reversa → diff.
      </p>
    </div>
  );
}

function SandboxesList() {
  const { data: sandboxes } = useListSandboxesSuspense(selector());
  const [showNew, setShowNew] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Sandboxes ({sandboxes.length})</h2>
        <Button onClick={() => setShowNew(!showNew)}>
          <Plus className="mr-2 h-4 w-4" />
          {showNew ? "Cancelar" : "Conectar sandbox"}
        </Button>
      </div>

      {showNew && (
        <Suspense fallback={<Skeleton className="h-60 w-full" />}>
          <NewSandboxForm onClose={() => setShowNew(false)} />
        </Suspense>
      )}

      {sandboxes.length === 0 && !showNew ? (
        <EmptyState
          icon={<Database className="h-10 w-10" />}
          title="Nenhum sandbox Lakebase conectado"
          description={
            <>
              Sandboxes Lakebase são instâncias Postgres descartáveis usadas para
              <strong> validação round-trip</strong>: o app gera DDL do modelo, executa no sandbox,
              faz reverse-engineering e compara com o catálogo. Subem e descem em minutos.
            </>
          }
          primaryAction={{ label: "Conectar primeiro sandbox", onClick: () => setShowNew(true) }}
          secondaryAction={{ label: "Ver documentação", to: "/help" }}
        />
      ) : (
        <div className="grid gap-3">
          {sandboxes.map((sb) => (
            <SandboxCard key={sb.sandbox_id} sb={sb} />
          ))}
        </div>
      )}
    </div>
  );
}

function NewSandboxForm({ onClose }: { onClose: () => void }) {
  const { data: instances } = useListLakebaseInstancesSuspense(selector());
  const qc = useQueryClient();
  const { mutate: create, isPending, error } = useCreateSandbox({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listSandboxes"] });
        onClose();
      },
    },
  });
  const available = instances.filter((i) => i.state === "AVAILABLE");

  const [name, setName] = useState("");
  const [instanceName, setInstanceName] = useState(available[0]?.instance_name || "");
  const [databaseName, setDatabaseName] = useState("databricks_postgres");
  const [defaultSchema, setDefaultSchema] = useState("public");
  const [description, setDescription] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        name,
        instance_name: instanceName,
        database_name: databaseName,
        default_schema: defaultSchema,
        description: description || null,
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Novo sandbox Lakebase</CardTitle>
        <CardDescription>Conecte uma instância Postgres existente do workspace</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Nome amigável" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="sandbox-validation" required />
          </Field>
          <Field label="Instância Lakebase" required>
            {available.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhuma instância AVAILABLE no workspace. Crie uma em{" "}
                <code>databricks database create-database-instance</code>.
              </p>
            ) : (
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                required
              >
                {available.map((i) => (
                  <option key={i.instance_name} value={i.instance_name}>
                    {i.instance_name} · {i.pg_version} · {i.capacity}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Database">
              <Input value={databaseName} onChange={(e) => setDatabaseName(e.target.value)} />
            </Field>
            <Field label="Schema default">
              <Input value={defaultSchema} onChange={(e) => setDefaultSchema(e.target.value)} />
            </Field>
          </div>
          <Field label="Descrição">
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="opcional" />
          </Field>
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
              {String(error)}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={isPending || !name || !instanceName}>
              {isPending ? "Salvando..." : "Salvar sandbox"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SandboxCard({ sb }: { sb: import("@/lib/api").SandboxListOut }) {
  const qc = useQueryClient();
  const { mutate: test, isPending: testing, data: testResult } = useTestSandbox({
    mutation: {
      onSuccess: () => qc.invalidateQueries({ queryKey: ["listSandboxes"] }),
    },
  });
  const { mutate: deactivate } = useDeactivateSandbox({
    mutation: {
      onSuccess: () => qc.invalidateQueries({ queryKey: ["listSandboxes"] }),
    },
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Database className="h-4 w-4 text-nuclea-primary" />
              <h3 className="font-semibold truncate">{sb.name}</h3>
              <TestBadge status={sb.last_test_status} />
            </div>
            <p className="text-sm text-muted-foreground">
              <code className="text-xs">{sb.instance_name}</code>
              <span className="mx-1">·</span>
              {sb.database_name}
              <span className="mx-1">·</span>
              schema <code className="text-xs">{sb.default_schema}</code>
              {sb.pg_version && (
                <>
                  <span className="mx-1">·</span>
                  pg {sb.pg_version}
                </>
              )}
            </p>
            {sb.last_test_at && (
              <p className="text-xs text-muted-foreground mt-1">
                Último teste: {new Date(sb.last_test_at).toLocaleString("pt-BR")}
              </p>
            )}
            {testResult && testResult.status === "success" && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                ✓ {testResult.schemas_visible} schemas visíveis · latência {testResult.latency_ms} ms
              </p>
            )}
            {testResult && testResult.status === "failure" && (
              <p className="text-xs text-destructive mt-1">✗ {testResult.error}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => test({ sandboxId: sb.sandbox_id })} disabled={testing}>
              <TestTube2 className={`mr-2 h-4 w-4 ${testing ? "animate-spin" : ""}`} />
              Testar
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link to="/extractions">
                Engenharia reversa
              </Link>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (confirm(`Desativar sandbox "${sb.name}"?`))
                  deactivate({ sandboxId: sb.sandbox_id });
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TestBadge({ status }: { status?: string | null }) {
  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs">
        <CheckCircle2 className="h-3 w-3" />
        OK
      </span>
    );
  }
  if (status === "failure") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive text-xs">
        <XCircle className="h-3 w-3" />
        Falha
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground text-xs">
      <MinusCircle className="h-3 w-3" />
      Não testado
    </span>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium flex items-center gap-1">
        {label}
        {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  );
}
