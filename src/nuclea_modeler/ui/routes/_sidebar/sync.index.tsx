import { createFileRoute, Link } from "@tanstack/react-router";
import { Fragment, Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListSystemsSuspense,
  useListSyncRunsSuspense,
  useMyRolesSuspense,
  usePreviewSync,
  useRunSync,
  useUCCatalogs,
  useUCSchemas,
  type SyncMode,
  type SyncObjectResult,
  type SyncRunResult,
  type SyncStatus,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  CheckCircle2,
  PlayCircle,
  RefreshCw,
  ShieldOff,
  SkipForward,
  XCircle,
  Eye,
  Database,
  History,
  Clock,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/sync/")({
  component: SyncPage,
});

const DEFAULT_TARGET_CATALOG = "stable_classic_pg4xe1_catalog";
// Lembra o último catálogo/schema usados no sync (pré-preenche na próxima vez).
const SYNC_PREFS_KEY = "nuclea.sync.lastTarget";
function loadSyncPrefs(): { catalog?: string; schema?: string } {
  try {
    return JSON.parse(localStorage.getItem(SYNC_PREFS_KEY) || "{}");
  } catch {
    return {};
  }
}

function SyncPage() {
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
                    Erro ao carregar sincronização
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
            <Suspense fallback={<PageSkeleton />}>
              <SyncContent />
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
        <h1 className="text-3xl font-bold tracking-tight">Sincronização Unity Catalog</h1>
        <Badge variant="outline" className="font-mono">M9</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Espelhamento do modelo curado para o Unity Catalog. Descrições viram
        <strong> COMMENTs</strong> e atributos como domínio, criticidade e business owner
        viram <strong>TAGs</strong>. Tipos nativos do UC nunca são sobrescritos. Com
        <strong> Materializar em Delta</strong>, tabelas que ainda não existem são
        criadas no catálogo destino. Faça um <em>dry-run</em> antes de aplicar.
      </p>
    </div>
  );
}

function SyncContent() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: me } = useMyRolesSuspense(selector());
  const qc = useQueryClient();

  const prefs = loadSyncPrefs();
  const { data: catalogs } = useUCCatalogs();
  const [systemId, setSystemId] = useState<string>(systems[0]?.system_id ?? "");
  const [targetCatalog, setTargetCatalog] = useState<string>(
    prefs.catalog || DEFAULT_TARGET_CATALOG,
  );
  const [targetSchema, setTargetSchema] = useState<string>(prefs.schema || "");
  const [mode, setMode] = useState<SyncMode>("INCREMENTAL");
  const [materialize, setMaterialize] = useState<boolean>(false);
  const [lastResult, setLastResult] = useState<SyncRunResult | null>(null);
  const [lastKind, setLastKind] = useState<"preview" | "run" | null>(null);

  // Schemas do catálogo destino selecionado (dropdown).
  const { data: schemas } = useUCSchemas(targetCatalog);

  // Guarda catálogo/schema escolhidos para pré-preencher no próximo sync.
  const savePrefs = (catalog: string, schema: string) => {
    try {
      localStorage.setItem(SYNC_PREFS_KEY, JSON.stringify({ catalog, schema }));
    } catch {
      /* best-effort */
    }
  };

  const preview = usePreviewSync({
    mutation: {
      onSuccess: (data) => {
        setLastResult(data);
        setLastKind("preview");
        savePrefs(targetCatalog.trim(), targetSchema.trim());
      },
    },
  });
  const run = useRunSync({
    mutation: {
      onSuccess: (data) => {
        setLastResult(data);
        setLastKind("run");
        savePrefs(targetCatalog.trim(), targetSchema.trim());
        qc.invalidateQueries({ queryKey: ["listSyncRuns"] });
      },
    },
  });

  const canApply = me.can_apply_tickets;
  const formReady = !!systemId && !!targetCatalog.trim();
  const isBusy = preview.isPending || run.isPending;

  const payload = {
    system_id: systemId,
    target_catalog: targetCatalog.trim(),
    target_schema: targetSchema.trim() || null,
    mode,
    dry_run: false,
    materialize,
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-nuclea-primary" />
            Nova sincronização
          </CardTitle>
          <CardDescription>
            Escolha o sistema, o catálogo destino e o modo. Preview executa em modo dry-run.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium mb-1 block">Sistema</label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                disabled={isBusy}
              >
                {systems.length === 0 && (
                  <option value="">— sem sistemas cadastrados —</option>
                )}
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.system_name} {s.domain ? `· ${s.domain}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Catálogo destino</label>
              {catalogs && catalogs.length > 0 ? (
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                  value={targetCatalog}
                  onChange={(e) => {
                    setTargetCatalog(e.target.value);
                    setTargetSchema(""); // schema depende do catálogo
                  }}
                  disabled={isBusy}
                >
                  {targetCatalog &&
                    !catalogs.some((c) => c.name === targetCatalog) && (
                      <option value={targetCatalog}>{targetCatalog}</option>
                    )}
                  {catalogs.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              ) : (
                // Fallback: SP não conseguiu listar catálogos → texto livre.
                <Input
                  value={targetCatalog}
                  onChange={(e) => setTargetCatalog(e.target.value)}
                  placeholder={DEFAULT_TARGET_CATALOG}
                  disabled={isBusy}
                />
              )}
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Schema destino</label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm disabled:opacity-50"
                value={targetSchema}
                onChange={(e) => setTargetSchema(e.target.value)}
                disabled={isBusy || !targetCatalog}
                title="Schema do Databricks onde o modelo será replicado"
              >
                <option value="">— manter schema de origem —</option>
                {targetSchema &&
                  !(schemas ?? []).some((s) => s.name === targetSchema) && (
                    <option value={targetSchema}>{targetSchema}</option>
                  )}
                {(schemas ?? []).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground mt-1">
                Vazio = cada tabela vai para o schema de mesmo nome da origem.
              </p>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium mb-2 block">Modo</label>
            <div className="flex flex-wrap gap-3">
              {(["INCREMENTAL", "FULL"] as SyncMode[]).map((m) => (
                <label
                  key={m}
                  className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm cursor-pointer ${
                    mode === m
                      ? "border-nuclea-primary bg-nuclea-primary/10 text-nuclea-primary"
                      : "border-input hover:bg-muted/40"
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={m}
                    checked={mode === m}
                    onChange={() => setMode(m)}
                    className="sr-only"
                    disabled={isBusy}
                  />
                  {m === "INCREMENTAL" ? "Incremental" : "Full"}
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              No momento, ambos os modos percorrem todas as entidades do sistema.
              Incremental será otimizado em fases futuras.
            </p>
          </div>

          <div>
            <label
              className={`flex items-start gap-3 rounded-md border p-3 cursor-pointer ${
                materialize
                  ? "border-nuclea-primary bg-nuclea-primary/5"
                  : "border-input hover:bg-muted/40"
              }`}
            >
              <input
                type="checkbox"
                checked={materialize}
                onChange={(e) => setMaterialize(e.target.checked)}
                disabled={isBusy}
                className="mt-0.5"
              />
              <span className="text-sm">
                <span className="font-medium">Materializar em Delta</span>
                <span className="block text-xs text-muted-foreground">
                  Cria a tabela Delta no catálogo destino quando ela ainda não
                  existe (tipos mapeados p/ Spark, com COMMENTs) e marca a
                  entidade como materializada. Sem isso, tabelas inexistentes
                  ficam apenas como <em>SKIPPED</em>.
                </span>
              </span>
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button
              variant="outline"
              disabled={!formReady || isBusy}
              onClick={() => preview.mutate({ data: { ...payload, dry_run: true } })}
            >
              <Eye className="mr-2 h-4 w-4" />
              {preview.isPending ? "Calculando..." : "Preview (dry-run)"}
            </Button>
            <div className="relative inline-flex">
              <Button
                disabled={!formReady || isBusy || !canApply}
                onClick={() => run.mutate({ data: payload })}
                title={
                  !canApply
                    ? "Apenas Data Architects ou Admins podem aplicar sincronizações"
                    : undefined
                }
              >
                <PlayCircle className="mr-2 h-4 w-4" />
                {run.isPending ? "Executando..." : "Executar"}
              </Button>
            </div>
            {!canApply && (
              <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
                <ShieldOff className="h-3.5 w-3.5" />
                Sem permissão para aplicar
              </span>
            )}
          </div>

          {(preview.error || run.error) && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertCircle className="inline h-4 w-4 mr-1" />
              {(preview.error || run.error)?.message}
            </div>
          )}

          {lastResult && <ResultPanel result={lastResult} kind={lastKind} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5 text-nuclea-primary" />
            Histórico de execuções
          </CardTitle>
          <CardDescription>Últimas 50 sincronizações aplicadas.</CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<Skeleton className="h-40 w-full" />}>
            <HistoryList />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  );
}

function HistoryList() {
  const { data: runs } = useListSyncRunsSuspense(selector());
  if (runs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        Nenhuma sincronização executada ainda.
      </p>
    );
  }
  return (
    <div className="divide-y -mx-2">
      {runs.map((r) => (
        <Link
          key={r.sync_id}
          to="/sync/$id"
          params={{ id: r.sync_id }}
          className="block px-2 py-3 hover:bg-muted/40 transition-colors"
        >
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="font-mono text-xs text-muted-foreground">
              {r.sync_id.slice(-8)}
            </span>
            <RunStatusBadge status={r.status} />
          </div>
          <p className="text-sm truncate">
            <strong>{r.system_id}</strong>
            {r.target_catalog && (
              <span className="text-muted-foreground"> → {r.target_catalog}</span>
            )}
          </p>
          <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
            <span>
              <Clock className="inline h-3 w-3 mr-1" />
              {new Date(r.started_at).toLocaleString("pt-BR")}
            </span>
            <span>
              {r.objects_synced ?? 0}/{r.objects_total ?? 0} objetos
              {r.duration_ms != null && <> · {r.duration_ms}ms</>}
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}

function ResultPanel({
  result,
  kind,
}: {
  result: SyncRunResult;
  kind: "preview" | "run" | null;
}) {
  const tone =
    result.status === "SUCCESS"
      ? "border-emerald-500/40 bg-emerald-500/5"
      : result.status === "PARTIAL"
        ? "border-amber-500/40 bg-amber-500/5"
        : "border-destructive/40 bg-destructive/5";
  return (
    <div className={`rounded-md border p-4 space-y-3 ${tone}`}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <RunStatusBadge status={result.status} />
          {kind === "preview" && (
            <Badge variant="outline">
              <Eye className="mr-1 h-3 w-3" />
              dry-run
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {result.objects_synced}/{result.objects_total} objetos
          {result.materialize && result.objects_created > 0 && (
            <> · {result.objects_created} materializada(s)</>
          )}
          {" · "}
          {result.duration_ms}ms
        </div>
      </div>

      {result.errors.length > 0 && (
        <div className="text-xs">
          <p className="font-medium mb-1">Avisos / erros:</p>
          <ul className="list-disc pl-5 space-y-0.5 font-mono text-[11px] max-h-32 overflow-auto">
            {result.errors.slice(0, 20).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
            {result.errors.length > 20 && (
              <li className="italic">… +{result.errors.length - 20} avisos</li>
            )}
          </ul>
        </div>
      )}

      <ObjectsTable objects={result.objects} />
    </div>
  );
}

function ObjectsTable({ objects }: { objects: SyncObjectResult[] }) {
  if (objects.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        Nenhuma entidade encontrada para esse sistema.
      </p>
    );
  }
  return (
    <div className="rounded-md border bg-background overflow-hidden">
      <table className="w-full text-xs">
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
            <Fragment key={i}>
              <tr>
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
              {o.ddl && (
                <tr>
                  <td colSpan={4} className="px-3 pb-2">
                    <details className="rounded-md border bg-muted/20">
                      <summary className="cursor-pointer px-2 py-1 text-[11px] font-medium">
                        DDL de criação
                      </summary>
                      <pre className="max-h-60 overflow-auto border-t px-2 py-2 font-mono text-[11px] leading-relaxed whitespace-pre">
                        {o.ddl};
                      </pre>
                    </details>
                  </td>
                </tr>
              )}
            </Fragment>
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
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${cfg.color}`}
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
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${cfg.color}`}
    >
      {cfg.icon}
      {status}
    </span>
  );
}

function PageSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Skeleton className="lg:col-span-2 h-80" />
      <Skeleton className="h-80" />
    </div>
  );
}
