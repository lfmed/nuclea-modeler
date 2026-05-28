import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Database,
  FileBox,
  Loader2,
  Network,
  Plus,
  Sparkles,
  TableProperties,
  X,
} from "lucide-react";

import {
  useCreateSystem,
  useListSandboxesSuspense,
  useListSandboxSchemasSuspense,
  useListUCCatalogsSuspense,
  useListUCSchemasSuspense,
  useListUCTablesSuspense,
  useRunLakebaseExtraction,
  useRunUCExtraction,
  type SystemListOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Wizard multi-step para criar um Novo Sistema com discovery opcional.
 *
 * Fluxo:
 *  1. Identificação (nome, domínio, tecnologia)
 *  2. Escolha da fonte (vazio / Lakebase / Unity Catalog)
 *  3. Discovery (depende do passo 2 — pula se "vazio")
 *  4. Resumo + submit
 *
 * O submit final faz POST /systems e, conforme a fonte escolhida,
 * dispara POST /extractions/lakebase/run ou POST /extractions/uc/run
 * com o system_id recém-criado. Em caso de falha no discovery, o
 * sistema permanece criado (sem rollback) — o user pode rerodar
 * a extração depois pela página /extractions.
 */

type SourceKind = "NONE" | "LAKEBASE" | "UC";

const TECH_OPTIONS = [
  "PostgreSQL",
  "Oracle",
  "SQL Server",
  "MySQL",
  "Databricks",
  "Outro",
];

const MAX_SCHEMAS = 50;

export function NewSystemWizard({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  /** Chamado depois que o sistema é criado com sucesso. Recebe o sistema novo. */
  onCreated?: (system: SystemListOut) => void;
}) {
  if (!open) return null;
  return <WizardInner onClose={onClose} onCreated={onCreated} />;
}

function WizardInner({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (system: SystemListOut) => void;
}) {
  // ─── Step state ─────────────────────────────────────────────────────────────
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [technology, setTechnology] = useState("");

  // Step 2
  const [source, setSource] = useState<SourceKind>("NONE");

  // Step 3 — Lakebase
  const [sandboxId, setSandboxId] = useState("");
  const [lakebaseSchemas, setLakebaseSchemas] = useState<string[]>([]);

  // Step 3 — UC
  const [ucCatalog, setUcCatalog] = useState("");
  const [ucSchema, setUcSchema] = useState("");
  const [ucTables, setUcTables] = useState<string[]>([]);

  const qc = useQueryClient();
  const [submitting, setSubmitting] = useState(false);

  const createSystem = useCreateSystem();
  const runLakebase = useRunLakebaseExtraction();
  const runUC = useRunUCExtraction();

  // ─── Navegação ──────────────────────────────────────────────────────────────
  const canNextStep1 = name.trim().length > 0;
  const canNextStep2 = !!source;
  const canNextStep3 =
    source === "NONE" ||
    (source === "LAKEBASE" && !!sandboxId && lakebaseSchemas.length > 0) ||
    (source === "UC" && !!ucCatalog && !!ucSchema && ucTables.length > 0);

  function goNext() {
    if (step === 1 && !canNextStep1) return;
    if (step === 2 && !canNextStep2) return;
    if (step === 2 && source === "NONE") {
      // Pula o step de discovery
      setStep(4);
      return;
    }
    if (step === 3 && !canNextStep3) return;
    setStep((s) => (Math.min(4, (s + 1)) as 1 | 2 | 3 | 4));
  }

  function goBack() {
    if (step === 4 && source === "NONE") {
      setStep(2);
      return;
    }
    setStep((s) => (Math.max(1, (s - 1)) as 1 | 2 | 3 | 4));
  }

  // ─── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit() {
    setSubmitting(true);
    try {
      const created = await createSystem.mutateAsync({
        data: {
          system_name: name.trim(),
          domain: domain.trim() || null,
          technology: technology || null,
        },
      });

      if (source === "LAKEBASE") {
        try {
          await runLakebase.mutateAsync({
            data: {
              system_id: created.system_id,
              sandbox_id: sandboxId,
              schemas: lakebaseSchemas,
              object_kinds: ["TABLE", "VIEW"],
              open_ticket: true,
            },
          });
        } catch (e) {
          toast.error("Sistema criado, mas discovery Lakebase falhou", {
            description: e instanceof Error ? e.message : String(e),
          });
        }
      } else if (source === "UC") {
        try {
          await runUC.mutateAsync({
            data: {
              system_id: created.system_id,
              catalog: ucCatalog,
              schema: ucSchema,
              table_names: ucTables,
              open_ticket: true,
            },
          });
        } catch (e) {
          toast.error("Sistema criado, mas discovery UC falhou", {
            description: e instanceof Error ? e.message : String(e),
          });
        }
      }

      // Invalida queries afetadas
      qc.invalidateQueries({ queryKey: ["listSystems"] });
      qc.invalidateQueries({ queryKey: ["listEntities"] });
      qc.invalidateQueries({ queryKey: ["getDiagram"] });
      qc.invalidateQueries({ queryKey: ["listExtractions"] });
      qc.invalidateQueries({ queryKey: ["listTickets"] });

      if (source === "NONE") {
        toast.success(`Sistema "${created.system_name}" criado`);
      } else {
        toast.success(
          "Sistema criado e descoberta iniciada — abra o ticket de reconciliação pra aprovar",
        );
      }

      onCreated?.(created);
      onClose();
    } catch (e) {
      toast.error("Falha ao criar sistema", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSubmitting(false);
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────
  const steps: { n: 1 | 2 | 3 | 4; label: string }[] = [
    { n: 1, label: "Identificação" },
    { n: 2, label: "Fonte" },
    { n: 3, label: "Discovery" },
    { n: 4, label: "Resumo" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-stretch justify-center p-4 sm:p-8"
      onClick={() => !submitting && onClose()}
    >
      <Card
        className="w-full max-w-4xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header + stepper */}
        <div className="border-b px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-nuclea-primary" />
            <h2 className="text-lg font-semibold">Novo sistema</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b px-6 py-3 bg-muted/30">
          <ol className="flex flex-wrap items-center gap-2 text-xs">
            {steps.map((s, i) => {
              const active = step === s.n;
              const done = step > s.n;
              const skipped = s.n === 3 && source === "NONE";
              return (
                <li key={s.n} className="flex items-center gap-2">
                  <span
                    className={
                      "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold " +
                      (active
                        ? "bg-nuclea-primary text-white border-nuclea-primary"
                        : done
                          ? "bg-emerald-500 text-white border-emerald-500"
                          : skipped
                            ? "bg-muted text-muted-foreground border-muted-foreground/30"
                            : "bg-background text-muted-foreground")
                    }
                  >
                    {done ? <CheckCircle2 className="h-3 w-3" /> : s.n}
                  </span>
                  <span
                    className={
                      active
                        ? "font-medium"
                        : skipped
                          ? "line-through text-muted-foreground"
                          : "text-muted-foreground"
                    }
                  >
                    {s.label}
                  </span>
                  {i < steps.length - 1 && (
                    <ChevronRight className="h-3 w-3 text-muted-foreground" />
                  )}
                </li>
              );
            })}
          </ol>
        </div>

        {/* Body */}
        <CardContent className="flex-1 overflow-auto px-6 py-6 min-h-[380px]">
          {step === 1 && (
            <Step1Identification
              name={name}
              setName={setName}
              domain={domain}
              setDomain={setDomain}
              technology={technology}
              setTechnology={setTechnology}
            />
          )}
          {step === 2 && <Step2Source source={source} setSource={setSource} />}
          {step === 3 && source === "LAKEBASE" && (
            <QueryErrorResetBoundary>
              {({ reset }) => (
                <ErrorBoundary
                  onReset={reset}
                  fallbackRender={({ error, resetErrorBoundary }) => (
                    <BrowseError
                      title="Não foi possível listar sandboxes"
                      error={error}
                      onRetry={resetErrorBoundary}
                    />
                  )}
                >
                  <Suspense fallback={<Skeleton className="h-40 w-full" />}>
                    <Step3Lakebase
                      sandboxId={sandboxId}
                      setSandboxId={(v) => {
                        setSandboxId(v);
                        setLakebaseSchemas([]);
                      }}
                      selected={lakebaseSchemas}
                      setSelected={setLakebaseSchemas}
                    />
                  </Suspense>
                </ErrorBoundary>
              )}
            </QueryErrorResetBoundary>
          )}
          {step === 3 && source === "UC" && (
            <QueryErrorResetBoundary>
              {({ reset }) => (
                <ErrorBoundary
                  onReset={reset}
                  fallbackRender={({ error, resetErrorBoundary }) => (
                    <BrowseError
                      title="Não foi possível navegar no Unity Catalog"
                      hint="Verifique se o app tem permissão USE_CATALOG/USE_SCHEMA no Unity Catalog e se a rede permite acesso ao workspace."
                      error={error}
                      onRetry={resetErrorBoundary}
                    />
                  )}
                >
                  <Suspense fallback={<Skeleton className="h-40 w-full" />}>
                    <Step3UC
                      catalog={ucCatalog}
                      setCatalog={(v) => {
                        setUcCatalog(v);
                        setUcSchema("");
                        setUcTables([]);
                      }}
                      schema={ucSchema}
                      setSchema={(v) => {
                        setUcSchema(v);
                        setUcTables([]);
                      }}
                      tables={ucTables}
                      setTables={setUcTables}
                    />
                  </Suspense>
                </ErrorBoundary>
              )}
            </QueryErrorResetBoundary>
          )}
          {step === 4 && (
            <Step4Summary
              name={name}
              domain={domain}
              technology={technology}
              source={source}
              sandboxId={sandboxId}
              lakebaseSchemas={lakebaseSchemas}
              ucCatalog={ucCatalog}
              ucSchema={ucSchema}
              ucTables={ucTables}
            />
          )}
        </CardContent>

        {/* Footer */}
        <div className="border-t px-6 py-3 flex items-center justify-between bg-muted/20">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={goBack}
            disabled={step === 1 || submitting}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Voltar
          </Button>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={submitting}
            >
              Cancelar
            </Button>
            {step < 4 ? (
              <Button
                type="button"
                size="sm"
                onClick={goNext}
                disabled={
                  (step === 1 && !canNextStep1) ||
                  (step === 2 && !canNextStep2) ||
                  (step === 3 && !canNextStep3)
                }
              >
                Próximo
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={handleSubmit}
                disabled={submitting || !canNextStep1}
              >
                {submitting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                {source === "NONE" ? "Criar sistema" : "Criar e descobrir"}
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ─── Steps ────────────────────────────────────────────────────────────────────

function Step1Identification({
  name,
  setName,
  domain,
  setDomain,
  technology,
  setTechnology,
}: {
  name: string;
  setName: (v: string) => void;
  domain: string;
  setDomain: (v: string) => void;
  technology: string;
  setTechnology: (v: string) => void;
}) {
  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h3 className="text-base font-semibold">Identifique o sistema</h3>
        <p className="text-sm text-muted-foreground">
          Um sistema agrupa entidades e relacionamentos de um modelo de dados.
        </p>
      </div>
      <div>
        <label className="text-xs font-medium block mb-1">
          Nome <span className="text-destructive">*</span>
        </label>
        <Input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Cadastro de Clientes"
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium block mb-1">Domínio</label>
          <Input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="Cadastro, Risco, Cobrança..."
          />
        </div>
        <div>
          <label className="text-xs font-medium block mb-1">Tecnologia</label>
          <select
            value={technology}
            onChange={(e) => setTechnology(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9"
          >
            <option value="">— selecione —</option>
            {TECH_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

function Step2Source({
  source,
  setSource,
}: {
  source: SourceKind;
  setSource: (s: SourceKind) => void;
}) {
  const options: {
    value: SourceKind;
    title: string;
    description: string;
    icon: React.ReactNode;
  }[] = [
    {
      value: "NONE",
      title: "Sem fonte (vazio)",
      description:
        "Crie um sistema vazio. Você pode adicionar entidades manualmente ou conectar uma fonte depois.",
      icon: <FileBox className="h-5 w-5" />,
    },
    {
      value: "LAKEBASE",
      title: "Lakebase sandbox",
      description:
        "Discovery automático a partir de uma sandbox Lakebase Postgres já cadastrada. Seleciona schemas para extração.",
      icon: <Database className="h-5 w-5" />,
    },
    {
      value: "UC",
      title: "Unity Catalog",
      description:
        "Discovery a partir de tabelas no Unity Catalog. Selecione catalog → schema → tables.",
      icon: <Network className="h-5 w-5" />,
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">De onde vem o modelo?</h3>
        <p className="text-sm text-muted-foreground">
          Você pode pular o discovery e criar o sistema vazio.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {options.map((opt) => {
          const selected = source === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => setSource(opt.value)}
              className={
                "text-left rounded-lg border p-4 transition-colors hover:bg-muted/40 " +
                (selected
                  ? "border-nuclea-primary ring-2 ring-nuclea-primary/40 bg-nuclea-primary/5"
                  : "border-border")
              }
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={
                    selected ? "text-nuclea-primary" : "text-muted-foreground"
                  }
                >
                  {opt.icon}
                </span>
                <span className="font-medium text-sm">{opt.title}</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {opt.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Step3Lakebase({
  sandboxId,
  setSandboxId,
  selected,
  setSelected,
}: {
  sandboxId: string;
  setSandboxId: (v: string) => void;
  selected: string[];
  setSelected: (v: string[]) => void;
}) {
  const { data: sandboxes } = useListSandboxesSuspense(selector());
  const active = useMemo(() => sandboxes.filter((s) => s.is_active), [sandboxes]);

  if (active.length === 0) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
        <p className="font-medium mb-1">Nenhuma sandbox Lakebase ativa</p>
        <p className="text-muted-foreground text-xs">
          Cadastre uma sandbox em <strong>Lakebase</strong> antes de rodar
          discovery. Você pode voltar e escolher "Sem fonte".
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">Discovery — Lakebase</h3>
        <p className="text-sm text-muted-foreground">
          Escolha a sandbox e quais schemas extrair.
        </p>
      </div>
      <div>
        <label className="text-xs font-medium block mb-1">Sandbox</label>
        <select
          value={sandboxId}
          onChange={(e) => setSandboxId(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9"
        >
          <option value="">— selecione —</option>
          {active.map((sb) => (
            <option key={sb.sandbox_id} value={sb.sandbox_id}>
              {sb.name} ({sb.database_name})
            </option>
          ))}
        </select>
      </div>
      {sandboxId && (
        <QueryErrorResetBoundary>
          {({ reset }) => (
            <ErrorBoundary
              onReset={reset}
              fallbackRender={({ error, resetErrorBoundary }) => (
                <BrowseError
                  title="Não foi possível listar schemas"
                  error={error}
                  onRetry={resetErrorBoundary}
                />
              )}
            >
              <Suspense fallback={<Skeleton className="h-32 w-full" />}>
                <LakebaseSchemasList
                  sandboxId={sandboxId}
                  selected={selected}
                  setSelected={setSelected}
                />
              </Suspense>
            </ErrorBoundary>
          )}
        </QueryErrorResetBoundary>
      )}
    </div>
  );
}

function LakebaseSchemasList({
  sandboxId,
  selected,
  setSelected,
}: {
  sandboxId: string;
  selected: string[];
  setSelected: (v: string[]) => void;
}) {
  const { data: schemas } = useListSandboxSchemasSuspense(sandboxId, selector());
  const capped = useMemo(() => schemas.slice(0, MAX_SCHEMAS), [schemas]);
  const truncated = schemas.length > MAX_SCHEMAS;

  function toggle(s: string) {
    setSelected(
      selected.includes(s) ? selected.filter((x) => x !== s) : [...selected, s],
    );
  }

  function selectAll() {
    setSelected(capped);
  }

  function clearAll() {
    setSelected([]);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-medium">
          Schemas{" "}
          <span className="text-muted-foreground">
            ({selected.length}/{capped.length})
          </span>
        </label>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={selectAll}>
            Selecionar todos
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={clearAll}>
            Limpar
          </Button>
        </div>
      </div>
      {truncated && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
          Exibindo os primeiros {MAX_SCHEMAS} schemas para preservar a UI.
          Use a página de Extractions para conjuntos maiores.
        </p>
      )}
      <div className="rounded-md border max-h-64 overflow-auto">
        {capped.length === 0 ? (
          <p className="text-sm text-muted-foreground p-3">
            Nenhum schema visível para o app nessa sandbox.
          </p>
        ) : (
          <ul className="divide-y">
            {capped.map((s) => (
              <li key={s} className="flex items-center gap-2 px-3 py-2">
                <input
                  type="checkbox"
                  checked={selected.includes(s)}
                  onChange={() => toggle(s)}
                />
                <span className="text-sm font-mono">{s}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Step3UC({
  catalog,
  setCatalog,
  schema,
  setSchema,
  tables,
  setTables,
}: {
  catalog: string;
  setCatalog: (v: string) => void;
  schema: string;
  setSchema: (v: string) => void;
  tables: string[];
  setTables: (v: string[]) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">Discovery — Unity Catalog</h3>
        <p className="text-sm text-muted-foreground">
          Navegue catalog → schema → tables. O app precisa de USE_CATALOG/USE_SCHEMA.
        </p>
      </div>

      <Suspense fallback={<Skeleton className="h-9 w-full" />}>
        <UCCatalogPicker catalog={catalog} setCatalog={setCatalog} />
      </Suspense>

      {catalog && (
        <QueryErrorResetBoundary>
          {({ reset }) => (
            <ErrorBoundary
              onReset={reset}
              fallbackRender={({ error, resetErrorBoundary }) => (
                <BrowseError
                  title="Não foi possível listar schemas do catalog"
                  error={error}
                  onRetry={resetErrorBoundary}
                />
              )}
            >
              <Suspense fallback={<Skeleton className="h-9 w-full" />}>
                <UCSchemaPicker
                  catalog={catalog}
                  schema={schema}
                  setSchema={setSchema}
                />
              </Suspense>
            </ErrorBoundary>
          )}
        </QueryErrorResetBoundary>
      )}

      {catalog && schema && (
        <QueryErrorResetBoundary>
          {({ reset }) => (
            <ErrorBoundary
              onReset={reset}
              fallbackRender={({ error, resetErrorBoundary }) => (
                <BrowseError
                  title="Não foi possível listar tables do schema"
                  error={error}
                  onRetry={resetErrorBoundary}
                />
              )}
            >
              <Suspense fallback={<Skeleton className="h-32 w-full" />}>
                <UCTablesList
                  catalog={catalog}
                  schema={schema}
                  selected={tables}
                  setSelected={setTables}
                />
              </Suspense>
            </ErrorBoundary>
          )}
        </QueryErrorResetBoundary>
      )}
    </div>
  );
}

function UCCatalogPicker({
  catalog,
  setCatalog,
}: {
  catalog: string;
  setCatalog: (v: string) => void;
}) {
  const { data: catalogs } = useListUCCatalogsSuspense(selector());
  return (
    <div>
      <label className="text-xs font-medium block mb-1">Catalog</label>
      <select
        value={catalog}
        onChange={(e) => setCatalog(e.target.value)}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9"
      >
        <option value="">— selecione —</option>
        {catalogs.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function UCSchemaPicker({
  catalog,
  schema,
  setSchema,
}: {
  catalog: string;
  schema: string;
  setSchema: (v: string) => void;
}) {
  const { data: schemas } = useListUCSchemasSuspense(catalog, selector());
  return (
    <div>
      <label className="text-xs font-medium block mb-1">Schema</label>
      <select
        value={schema}
        onChange={(e) => setSchema(e.target.value)}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9"
      >
        <option value="">— selecione —</option>
        {schemas.map((s) => (
          <option key={s.name} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function UCTablesList({
  catalog,
  schema,
  selected,
  setSelected,
}: {
  catalog: string;
  schema: string;
  selected: string[];
  setSelected: (v: string[]) => void;
}) {
  const { data: tables } = useListUCTablesSuspense(catalog, schema, selector());

  function toggle(name: string) {
    setSelected(
      selected.includes(name)
        ? selected.filter((x) => x !== name)
        : [...selected, name],
    );
  }

  function selectAll() {
    setSelected(tables.map((t) => t.name));
  }

  function clearAll() {
    setSelected([]);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-medium">
          Tables{" "}
          <span className="text-muted-foreground">
            ({selected.length}/{tables.length})
          </span>
        </label>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={selectAll}>
            Selecionar tudo
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={clearAll}>
            Limpar
          </Button>
        </div>
      </div>
      <div className="rounded-md border max-h-64 overflow-auto">
        {tables.length === 0 ? (
          <p className="text-sm text-muted-foreground p-3">
            Nenhuma tabela visível neste schema.
          </p>
        ) : (
          <ul className="divide-y">
            {tables.map((t) => (
              <li key={t.name} className="flex items-center gap-2 px-3 py-2">
                <input
                  type="checkbox"
                  checked={selected.includes(t.name)}
                  onChange={() => toggle(t.name)}
                />
                <TableProperties className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-sm font-mono">{t.name}</span>
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {t.table_type}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Step4Summary({
  name,
  domain,
  technology,
  source,
  sandboxId,
  lakebaseSchemas,
  ucCatalog,
  ucSchema,
  ucTables,
}: {
  name: string;
  domain: string;
  technology: string;
  source: SourceKind;
  sandboxId: string;
  lakebaseSchemas: string[];
  ucCatalog: string;
  ucSchema: string;
  ucTables: string[];
}) {
  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h3 className="text-base font-semibold">Revise antes de criar</h3>
        <p className="text-sm text-muted-foreground">
          O sistema é criado primeiro; o discovery (se houver) roda em seguida
          e abre um ticket de reconciliação.
        </p>
      </div>

      <dl className="rounded-md border divide-y text-sm">
        <SummaryRow label="Nome" value={name} />
        <SummaryRow label="Domínio" value={domain || "—"} />
        <SummaryRow label="Tecnologia" value={technology || "—"} />
        <SummaryRow
          label="Fonte"
          value={
            source === "NONE"
              ? "Sem fonte (vazio)"
              : source === "LAKEBASE"
                ? "Lakebase sandbox"
                : "Unity Catalog"
          }
        />
        {source === "LAKEBASE" && (
          <>
            <SummaryRow label="Sandbox" value={sandboxId} />
            <SummaryRow
              label="Schemas"
              value={
                lakebaseSchemas.length
                  ? lakebaseSchemas.join(", ")
                  : "—"
              }
            />
          </>
        )}
        {source === "UC" && (
          <>
            <SummaryRow label="Catalog" value={ucCatalog} />
            <SummaryRow label="Schema" value={ucSchema} />
            <SummaryRow
              label="Tables"
              value={ucTables.length ? ucTables.join(", ") : "—"}
            />
          </>
        )}
      </dl>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-3 gap-3 px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="col-span-2 text-sm break-words">{value}</dd>
    </div>
  );
}

function BrowseError({
  title,
  error,
  hint,
  onRetry,
}: {
  title: string;
  error: unknown;
  hint?: string;
  onRetry: () => void;
}) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm space-y-2">
      <div className="flex items-center gap-2 font-medium">
        <AlertCircle className="h-4 w-4 text-destructive" />
        {title}
      </div>
      <p className="text-xs text-muted-foreground break-words">{msg}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      <div className="pt-1">
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </div>
    </div>
  );
}
