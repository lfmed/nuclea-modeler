import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListExtractionsSuspense,
  useListSandboxesSuspense,
  useListSystemsSuspense,
  useRunLakebaseExtraction,
  useRunDDLImport,
  useRunEmbarcaderoImport,
  type ExtractionResult,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  ScanSearch,
  Database,
  FileCode,
  FileBox,
  Plus,
  Minus,
  RefreshCw,
  ArrowRight,
  Inbox,
  CheckCircle2,
  XCircle,
  Upload,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/extractions")({
  component: ExtractionsPage,
});

function ExtractionsPage() {
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
                    Erro ao carregar engenharia reversa
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <ExtractionsContent />
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
        <h1 className="text-3xl font-bold tracking-tight">Engenharia Reversa</h1>
        <Badge variant="outline" className="font-mono">M2</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Extraia metadados dos sistemas de origem (Lakebase sandbox ou DDL importado) e gere
        automaticamente um ticket de reconciliação para revisão humana antes de aplicar ao catálogo.
      </p>
    </div>
  );
}

function ExtractionsContent() {
  const [tab, setTab] = useState<"lakebase" | "ddl" | "erx" | "history">("lakebase");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b">
        <TabButton active={tab === "lakebase"} onClick={() => setTab("lakebase")}>
          <Database className="h-4 w-4 mr-2" />
          Lakebase
        </TabButton>
        <TabButton active={tab === "ddl"} onClick={() => setTab("ddl")}>
          <FileCode className="h-4 w-4 mr-2" />
          Import de DDL
        </TabButton>
        <TabButton active={tab === "erx"} onClick={() => setTab("erx")}>
          <FileBox className="h-4 w-4 mr-2" />
          Embarcadero (.erx)
        </TabButton>
        <TabButton active={tab === "history"} onClick={() => setTab("history")}>
          <Inbox className="h-4 w-4 mr-2" />
          Histórico
        </TabButton>
      </div>

      {tab === "lakebase" && <LakebaseTab />}
      {tab === "ddl" && <DDLTab />}
      {tab === "erx" && <EmbarcaderoTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-nuclea-primary text-nuclea-primary"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function LakebaseTab() {
  const { data: sandboxes } = useListSandboxesSuspense(selector());
  const { data: systems } = useListSystemsSuspense(selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { mutate: runExtraction, isPending, data: result } = useRunLakebaseExtraction({
    mutation: {
      onSuccess: (r) => {
        qc.invalidateQueries({ queryKey: ["listExtractions"] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        if (r.ticket_id) {
          // optionally jump to ticket detail
          setTimeout(() => navigate({ to: "/tickets/$id", params: { id: r.ticket_id! } }), 800);
        }
      },
    },
  });

  const [sandboxId, setSandboxId] = useState(sandboxes[0]?.sandbox_id || "");
  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [schemasInput, setSchemasInput] = useState("");
  const [includeTables, setIncludeTables] = useState(true);
  const [includeViews, setIncludeViews] = useState(true);

  if (sandboxes.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <Database className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            Você ainda não conectou um sandbox Lakebase.{" "}
            <Link to="/lakebase" className="text-nuclea-primary underline">
              Conecte um agora
            </Link>{" "}
            para começar.
          </p>
        </CardContent>
      </Card>
    );
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const schemas = schemasInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const kinds: ("TABLE" | "VIEW")[] = [];
    if (includeTables) kinds.push("TABLE");
    if (includeViews) kinds.push("VIEW");
    runExtraction({
      data: {
        sandbox_id: sandboxId,
        system_id: systemId,
        schemas,
        object_kinds: kinds,
        open_ticket: true,
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Nova extração — Lakebase</CardTitle>
        <CardDescription>
          Conecta no sandbox, lista tabelas/colunas via <code>information_schema</code> e
          gera um ticket com a diff vs. catálogo.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Sandbox Lakebase" required>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={sandboxId}
                onChange={(e) => setSandboxId(e.target.value)}
                required
              >
                {sandboxes.map((sb) => (
                  <option key={sb.sandbox_id} value={sb.sandbox_id}>
                    {sb.name} ({sb.instance_name})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Sistema-alvo do diff" required>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                required
              >
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>{s.system_name}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field
            label="Schemas (CSV, vazio = todos visíveis)"
          >
            <Input
              value={schemasInput}
              onChange={(e) => setSchemasInput(e.target.value)}
              placeholder="public, audit, financial"
            />
          </Field>
          <div className="flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={includeTables} onChange={(e) => setIncludeTables(e.target.checked)} />
              Tabelas
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={includeViews} onChange={(e) => setIncludeViews(e.target.checked)} />
              Views
            </label>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={isPending || !sandboxId || !systemId}>
              {isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Extraindo...
                </>
              ) : (
                <>
                  <ScanSearch className="mr-2 h-4 w-4" />
                  Iniciar extração
                </>
              )}
            </Button>
          </div>
        </form>

        {result && <ResultPanel result={result} />}
      </CardContent>
    </Card>
  );
}

function DDLTab() {
  const { data: systems } = useListSystemsSuspense(selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { mutate: runDDL, isPending, data: result } = useRunDDLImport({
    mutation: {
      onSuccess: (r) => {
        qc.invalidateQueries({ queryKey: ["listExtractions"] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        if (r.ticket_id) {
          setTimeout(() => navigate({ to: "/tickets/$id", params: { id: r.ticket_id! } }), 800);
        }
      },
    },
  });

  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [dialect, setDialect] = useState("ANSI");
  const [ddlText, setDdlText] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ddlText.trim()) return;
    runDDL({
      data: {
        system_id: systemId,
        dialect,
        ddl_text: ddlText,
        open_ticket: true,
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Importar DDL</CardTitle>
        <CardDescription>Cole scripts CREATE TABLE / CREATE VIEW para reconciliação.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Sistema-alvo do diff" required>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                required
              >
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>{s.system_name}</option>
                ))}
              </select>
            </Field>
            <Field label="Dialeto">
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={dialect}
                onChange={(e) => setDialect(e.target.value)}
              >
                <option value="ANSI">ANSI SQL</option>
                <option value="TSQL">T-SQL (SQL Server)</option>
                <option value="PLSQL">PL/SQL (Oracle)</option>
                <option value="POSTGRES">PostgreSQL</option>
                <option value="MYSQL">MySQL / MariaDB</option>
                <option value="SPARKSQL">SparkSQL / Delta</option>
              </select>
            </Field>
          </div>
          <Field label="DDL" required>
            <textarea
              value={ddlText}
              onChange={(e) => setDdlText(e.target.value)}
              rows={12}
              className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono"
              placeholder={"CREATE TABLE public.cliente (\n  id BIGINT PRIMARY KEY,\n  nome VARCHAR(200) NOT NULL,\n  ...\n);"}
              required
            />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={isPending || !ddlText.trim() || !systemId}>
              {isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Parseando...
                </>
              ) : (
                <>
                  <FileCode className="mr-2 h-4 w-4" />
                  Parsear e reconciliar
                </>
              )}
            </Button>
          </div>
        </form>

        {result && <ResultPanel result={result} />}
      </CardContent>
    </Card>
  );
}

function EmbarcaderoTab() {
  const { data: systems } = useListSystemsSuspense(selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB

  const { mutate: runImport, isPending, data: result } = useRunEmbarcaderoImport({
    mutation: {
      onSuccess: (r) => {
        qc.invalidateQueries({ queryKey: ["listExtractions"] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        if (r.ticket_id) {
          setTimeout(() => navigate({ to: "/tickets/$id", params: { id: r.ticket_id! } }), 800);
        }
      },
    },
  });

  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [fileName, setFileName] = useState<string>("");
  const [fileSize, setFileSize] = useState<number>(0);
  const [xmlText, setXmlText] = useState<string>("");
  const [fileError, setFileError] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setFileError(null);
    setXmlText("");
    setFileName("");
    setFileSize(0);
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setFileError(
        `Arquivo muito grande (${(file.size / 1024 / 1024).toFixed(1)} MB). Limite: 10 MB.`,
      );
      return;
    }
    try {
      const text = await file.text();
      setFileName(file.name);
      setFileSize(file.size);
      setXmlText(text);
    } catch (err) {
      setFileError(`Falha ao ler o arquivo: ${String(err)}`);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!xmlText || !systemId) return;
    runImport({
      data: {
        system_id: systemId,
        xml_text: xmlText,
        open_ticket: true,
      },
    });
  };

  if (systems.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <FileBox className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">
            Cadastre um sistema antes de importar um modelo Embarcadero.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Importar modelo Embarcadero (.erx)</CardTitle>
        <CardDescription>
          Faça upload de um arquivo <code>.erx</code> exportado pelo Embarcadero ER/Studio.
          O parser identifica entidades, atributos e tipos, e gera um ticket de reconciliação
          contra o catálogo atual.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Sistema-alvo do diff" required>
            <select
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={systemId}
              onChange={(e) => setSystemId(e.target.value)}
              required
            >
              {systems.map((s) => (
                <option key={s.system_id} value={s.system_id}>{s.system_name}</option>
              ))}
            </select>
          </Field>
          <Field label="Arquivo .erx (máximo 10 MB)" required>
            <Input
              type="file"
              accept=".erx,.xml,application/xml,text/xml"
              onChange={handleFile}
            />
            {fileName && !fileError && (
              <p className="text-xs text-muted-foreground mt-1">
                <strong>{fileName}</strong> · {(fileSize / 1024).toFixed(1)} KB
              </p>
            )}
            {fileError && (
              <p className="text-xs text-destructive mt-1">{fileError}</p>
            )}
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={isPending || !xmlText || !systemId || !!fileError}>
              {isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Importando...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Importar
                </>
              )}
            </Button>
          </div>
        </form>

        {result && <ResultPanel result={result} />}
      </CardContent>
    </Card>
  );
}

function ResultPanel({ result }: { result: ExtractionResult }) {
  const okColor = result.status === "SUCCESS"
    ? "border-emerald-500/50 bg-emerald-500/5"
    : result.status === "PARTIAL"
      ? "border-amber-500/50 bg-amber-500/5"
      : "border-destructive/50 bg-destructive/5";
  return (
    <div className={`mt-6 rounded-lg border p-4 ${okColor}`}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          {result.status === "SUCCESS" ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          ) : result.status === "FAILED" ? (
            <XCircle className="h-5 w-5 text-destructive" />
          ) : (
            <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
          )}
          <strong className="text-sm">{result.summary_md}</strong>
        </div>
        {result.ticket_id && (
          <Button size="sm" asChild>
            <Link to="/tickets/$id" params={{ id: result.ticket_id }}>
              Ver ticket
              <ArrowRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-3 mt-3 text-xs">
        <Counter icon={<Plus className="h-3 w-3" />} label="novos" value={result.objects_new} tone="positive" />
        <Counter icon={<RefreshCw className="h-3 w-3" />} label="alterados" value={result.objects_changed} tone="warning" />
        <Counter icon={<Minus className="h-3 w-3" />} label="removidos" value={result.objects_removed} tone="negative" />
        <Counter icon={<ScanSearch className="h-3 w-3" />} label="encontrados" value={result.objects_found} tone="neutral" />
      </div>
      {result.errors.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs cursor-pointer">Erros ({result.errors.length})</summary>
          <ul className="list-disc pl-5 mt-2 space-y-1 text-xs font-mono">
            {result.errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

function Counter({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "positive" | "negative" | "warning" | "neutral";
}) {
  const color =
    tone === "positive"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "warning"
        ? "text-amber-600 dark:text-amber-400"
        : tone === "negative"
          ? "text-destructive"
          : "text-muted-foreground";
  return (
    <span className={`inline-flex items-center gap-1 ${color}`}>
      {icon}
      <strong>{value}</strong>
      {label}
    </span>
  );
}

function HistoryTab() {
  const { data: extractions } = useListExtractionsSuspense({}, selector());
  if (extractions.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <Inbox className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">Sem extrações executadas ainda.</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 px-3 font-medium">ID</th>
                <th className="py-2 px-3 font-medium">Fonte</th>
                <th className="py-2 px-3 font-medium">Sistema</th>
                <th className="py-2 px-3 font-medium">Status</th>
                <th className="py-2 px-3 font-medium text-right">Encontrados</th>
                <th className="py-2 px-3 font-medium text-right">Novos</th>
                <th className="py-2 px-3 font-medium text-right">Alterados</th>
                <th className="py-2 px-3 font-medium text-right">Removidos</th>
                <th className="py-2 px-3 font-medium">Ticket</th>
                <th className="py-2 px-3 font-medium">Quando</th>
              </tr>
            </thead>
            <tbody>
              {extractions.map((e) => (
                <tr key={e.extraction_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 px-3 font-mono text-xs">{e.extraction_id.slice(0, 12)}…</td>
                  <td className="py-2 px-3">
                    <Badge variant="outline">{e.source_kind}</Badge>
                  </td>
                  <td className="py-2 px-3">{e.system_name || e.system_id}</td>
                  <td className="py-2 px-3"><StatusBadge status={e.status} /></td>
                  <td className="py-2 px-3 text-right tabular-nums">{e.objects_found ?? 0}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">{e.objects_new ?? 0}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-amber-600 dark:text-amber-400">{e.objects_changed ?? 0}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-destructive">{e.objects_removed ?? 0}</td>
                  <td className="py-2 px-3">
                    {e.ticket_id ? (
                      <Link to="/tickets/$id" params={{ id: e.ticket_id }} className="text-nuclea-primary hover:underline text-xs">
                        Ver ticket
                      </Link>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground">
                    {new Date(e.started_at).toLocaleString("pt-BR")}
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

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "SUCCESS"
      ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300"
      : status === "PARTIAL"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : status === "FAILED"
          ? "bg-destructive/10 text-destructive border-destructive/30"
          : "bg-muted text-muted-foreground border-border";
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>
      {status}
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
