import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import { useCreateConnection, useListSystemsSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle, Database, Globe, FileCode } from "lucide-react";

type ConnType = "DATABASE" | "REST" | "DDL_IMPORT";
type Env = "HINT" | "HEXT" | "PROD";
type Engine = "POSTGRES" | "ORACLE" | "MYSQL" | "SQLSERVER" | "DB2";

// Metadados por motor: rótulo, porta padrão e como chamar o campo "banco"
// (Oracle usa service name). Só apresentação — o backend valida de fato.
const ENGINE_META: Record<Engine, { label: string; port: string; dbLabel: string; dbPlaceholder: string }> = {
  POSTGRES: { label: "PostgreSQL", port: "5432", dbLabel: "Banco", dbPlaceholder: "programa_social" },
  ORACLE: { label: "Oracle", port: "1521", dbLabel: "Service name", dbPlaceholder: "ORCLPDB1" },
  MYSQL: { label: "MySQL", port: "3306", dbLabel: "Banco", dbPlaceholder: "app" },
  SQLSERVER: { label: "SQL Server", port: "1433", dbLabel: "Banco", dbPlaceholder: "dw_principal" },
  DB2: { label: "IBM DB2", port: "50000", dbLabel: "Banco", dbPlaceholder: "BLUDB" },
};

export const Route = createFileRoute("/_sidebar/connections/new")({
  component: NewConnectionPage,
});

function NewConnectionPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/connections">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Conexões
          </Link>
        </Button>
      </div>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Nova conexão</h1>
        <p className="text-muted-foreground">
          Cadastre uma conexão para extração de metadados.
        </p>
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
                    Erro
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<FormSkeleton />}>
              <ConnectionForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ConnectionForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { mutate: create, isPending, error } = useCreateConnection({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["listConnections"] });
        toast.success("Conexão criada com sucesso!");
        navigate({ to: "/connections/$id", params: { id: data.connection_id } });
      },
      onError: (err) => {
        toast.error("Erro ao criar conexão", {
          description: err instanceof Error ? err.message : "Falha desconhecida",
        });
      },
    },
  });

  const [alias, setAlias] = useState("");
  const [environment, setEnvironment] = useState<Env>("HINT");
  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [connType, setConnType] = useState<ConnType>("DATABASE");
  // DATABASE (motor nativo): o cliente informa URL/usuário/senha direto — nada
  // a anexar. A senha é cifrada em repouso no backend (não é secret key).
  const [engine, setEngine] = useState<Engine>("POSTGRES");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // REST
  const [baseUrl, setBaseUrl] = useState("");
  const [authType, setAuthType] = useState("BEARER");
  const [secretKeyToken, setSecretKeyToken] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    let config: Record<string, unknown>;
    let pwd: string | null = null;
    if (connType === "DATABASE") {
      config = {
        engine,
        host,
        port: port ? parseInt(port) : null,
        database: database || null,
        username: username || null,
      };
      pwd = password || null;
    } else if (connType === "REST") {
      config = { base_url: baseUrl, auth_type: authType, headers: {} };
    } else {
      config = { notes: null };
    }
    create({
      data: {
        alias,
        environment,
        system_id: systemId,
        connection_type: connType,
        config,
        password: pwd,
        secret_key_token: connType === "REST" ? secretKeyToken || null : null,
      },
    });
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Identificação</CardTitle>
          <CardDescription>Como esta conexão será apresentada na app</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <FormField label="Alias" required>
            <Input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="DW Principal · PROD" required />
          </FormField>
          <div className="grid md:grid-cols-2 gap-4">
            <FormField label="Ambiente" required>
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={environment} onChange={(e) => setEnvironment(e.target.value as Env)} required>
                <option value="HINT">HINT — Homologação Interna</option>
                <option value="HEXT">HEXT — Homologação Externa</option>
                <option value="PROD">PROD — Produção</option>
              </select>
            </FormField>
            <FormField label="Sistema de origem" required>
              {systems.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nenhum sistema cadastrado.{" "}
                  <Link to="/connections" className="text-nuclea-primary underline">
                    Cadastre um sistema primeiro
                  </Link>
                  .
                </p>
              ) : (
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={systemId} onChange={(e) => setSystemId(e.target.value)} required>
                  {systems.map((s) => (
                    <option key={s.system_id} value={s.system_id}>
                      {s.system_name}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tipo de conexão</CardTitle>
          <CardDescription>Como conectar ao sistema de origem</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <TypeButton icon={<Database className="h-5 w-5" />} label="Banco de dados" active={connType === "DATABASE"} onClick={() => setConnType("DATABASE")} />
            <TypeButton icon={<Globe className="h-5 w-5" />} label="REST" active={connType === "REST"} onClick={() => setConnType("REST")} />
            <TypeButton icon={<FileCode className="h-5 w-5" />} label="Import DDL" active={connType === "DDL_IMPORT"} onClick={() => setConnType("DDL_IMPORT")} />
          </div>

          {connType === "DATABASE" && (
            <div className="space-y-4 pt-2">
              <FormField label="Motor de banco" required>
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={engine}
                  onChange={(e) => setEngine(e.target.value as Engine)}
                  required
                >
                  {(Object.keys(ENGINE_META) as Engine[]).map((k) => (
                    <option key={k} value={k}>
                      {ENGINE_META[k].label}
                    </option>
                  ))}
                </select>
              </FormField>
              <div className="grid md:grid-cols-2 gap-4">
                <FormField label="Host" required>
                  <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="db.interno.nuclea.com.br" required />
                </FormField>
                <FormField label="Porta">
                  <Input type="number" value={port} onChange={(e) => setPort(e.target.value)} placeholder={ENGINE_META[engine].port} />
                </FormField>
                <FormField label={ENGINE_META[engine].dbLabel} required>
                  <Input value={database} onChange={(e) => setDatabase(e.target.value)} placeholder={ENGINE_META[engine].dbPlaceholder} required />
                </FormField>
                <FormField label="Usuário">
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="app_user" autoComplete="off" />
                </FormField>
                <FormField label="Senha">
                  <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password" />
                </FormField>
              </div>
              <p className="text-xs text-muted-foreground">
                A senha é <strong>cifrada em repouso</strong> e nunca é exibida de volta. O driver do banco já vem embutido no app — não é preciso anexar nada.
              </p>
            </div>
          )}

          {connType === "REST" && (
            <div className="grid md:grid-cols-2 gap-4 pt-2">
              <FormField label="Base URL" required>
                <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.sistema.nuclea.com.br" required />
              </FormField>
              <FormField label="Autenticação">
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={authType} onChange={(e) => setAuthType(e.target.value)}>
                  <option value="NONE">Sem autenticação</option>
                  <option value="BASIC">Basic Auth</option>
                  <option value="BEARER">Bearer Token</option>
                  <option value="OAUTH2">OAuth 2.0</option>
                </select>
              </FormField>
            </div>
          )}

          {connType === "DDL_IMPORT" && (
            <p className="text-sm text-muted-foreground pt-2">
              Após salvar, faça upload dos arquivos <code>.sql</code> ou <code>.ddl</code> na página da conexão.
            </p>
          )}
        </CardContent>
      </Card>

      {connType === "REST" && (
        <Card>
          <CardHeader>
            <CardTitle>Credenciais (Databricks Secrets)</CardTitle>
            <CardDescription>
              Informe a <strong>chave</strong> do secret do token (a app lê o valor de Databricks Secrets em tempo de uso).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField label="Chave do token">
              <Input value={secretKeyToken} onChange={(e) => setSecretKeyToken(e.target.value)} placeholder="api_token_prod" />
            </FormField>
          </CardContent>
        </Card>
      )}

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="pt-4 text-sm text-destructive">
            <p className="font-medium">Falha ao salvar:</p>
            <pre className="mt-1 text-xs whitespace-pre-wrap">{String(error)}</pre>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" asChild>
          <Link to="/connections">Cancelar</Link>
        </Button>
        <Button type="submit" disabled={isPending || !alias || !systemId}>
          {isPending ? "Salvando..." : "Salvar conexão"}
        </Button>
      </div>
    </form>
  );
}

function FormField({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
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

function TypeButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors ${
        active
          ? "border-nuclea-primary bg-nuclea-primary/5 text-nuclea-primary"
          : "border-border hover:bg-muted/50"
      }`}
    >
      {icon}
      <span className="text-sm font-medium">{label}</span>
    </button>
  );
}

function FormSkeleton() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-32" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
