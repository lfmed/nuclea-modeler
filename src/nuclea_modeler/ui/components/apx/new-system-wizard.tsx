import { Suspense, useEffect, useMemo, useState } from "react";
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
  FileCode,
  FileText,
  Loader2,
  Network,
  Plus,
  Sparkles,
  TableProperties,
  Upload,
  X,
} from "lucide-react";

import {
  useCreateSystem,
  useListSandboxesSuspense,
  useListSandboxSchemasSuspense,
  useListUCCatalogsSuspense,
  useListUCSchemasSuspense,
  useListUCTablesSuspense,
  useRunDDLImport,
  useRunEmbarcaderoImport,
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
 * Wizard de Novo Sistema em 2 passos:
 *  1. Configurar (fonte + discovery + identificação consolidados)
 *  2. Resumo + submit
 *
 * Auto-sugestões:
 *  - Lakebase: nome ← sandbox.name; tecnologia ← "PostgreSQL"
 *  - UC: nome ← `<catalog>.<schema>`; tecnologia ← "Databricks"
 *  Só preenche se o user ainda não tocou no campo.
 */

type SourceKind = "NONE" | "LAKEBASE" | "UC" | "DDL" | "EMBARCADERO";

const TECH_OPTIONS = [
  "PostgreSQL",
  "Oracle",
  "SQL Server",
  "MySQL",
  "Databricks",
  "DB2",
  "Outro",
];

const DDL_DIALECTS = [
  { value: "ANSI", label: "ANSI / Genérico" },
  { value: "POSTGRESQL", label: "PostgreSQL" },
  { value: "ORACLE", label: "Oracle" },
  { value: "MSSQL", label: "SQL Server" },
  { value: "MYSQL", label: "MySQL" },
  { value: "DATABRICKS", label: "Databricks" },
  { value: "DB2", label: "DB2 (IBM Db2)" },
];

// Cap para upload .DM1 — 50 MB (alinhado ao backend EmbarcaderoImportIn).
const DM1_MAX_BYTES = 50 * 1024 * 1024;
// Cap para .sql — 5 MB.
const DDL_MAX_BYTES = 5 * 1024 * 1024;

const MAX_SCHEMAS = 50;

export function NewSystemWizard({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  /** Chamado depois que o sistema é criado com sucesso. */
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
  const [step, setStep] = useState<1 | 2>(1);

  // Identificação
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [domain, setDomain] = useState("");
  const [technology, setTechnology] = useState("");
  const [techTouched, setTechTouched] = useState(false);
  const [environment, setEnvironment] = useState<"DEV" | "HINT" | "PRD" | "">("");

  // Fonte
  const [source, setSource] = useState<SourceKind>("NONE");

  // Lakebase
  const [sandboxId, setSandboxId] = useState("");
  const [sandboxName, setSandboxName] = useState(""); // pra suggest nome
  const [lakebaseSchemas, setLakebaseSchemas] = useState<string[]>([]);

  // UC
  const [ucCatalog, setUcCatalog] = useState("");
  const [ucSchema, setUcSchema] = useState("");
  const [ucTables, setUcTables] = useState<string[]>([]);

  // DDL paste/upload
  const [ddlText, setDdlText] = useState("");
  const [ddlDialect, setDdlDialect] = useState("ANSI");
  const [ddlFileName, setDdlFileName] = useState("");

  // Embarcadero .DM1
  const [dm1Text, setDm1Text] = useState("");
  const [dm1FileName, setDm1FileName] = useState("");

  const qc = useQueryClient();
  const [submitting, setSubmitting] = useState(false);

  const createSystem = useCreateSystem();
  const runLakebase = useRunLakebaseExtraction();
  const runUC = useRunUCExtraction();
  const runDDL = useRunDDLImport();
  const runEmbarcadero = useRunEmbarcaderoImport();

  // ─── Auto-sugestões ─────────────────────────────────────────────────────────
  // Tecnologia FIXA pela fonte: Lakebase=PostgreSQL, UC=Databricks.
  // DDL: usa o dialect escolhido (mapping para o select de tech).
  // EMBARCADERO/NONE: livre — só preenche se user não tocou.
  useEffect(() => {
    if (source === "LAKEBASE") {
      setTechnology("PostgreSQL");
    } else if (source === "UC") {
      setTechnology("Databricks");
    } else if (source === "DDL") {
      const map: Record<string, string> = {
        POSTGRESQL: "PostgreSQL",
        ORACLE: "Oracle",
        MSSQL: "SQL Server",
        MYSQL: "MySQL",
        DATABRICKS: "Databricks",
      };
      setTechnology(map[ddlDialect] || "");
    } else if (!techTouched) {
      setTechnology("");
    }
  }, [source, ddlDialect, techTouched]);

  // Nome automático conforme escolhe sandbox/schema/arquivo (só se user não tocou)
  useEffect(() => {
    if (nameTouched) return;
    if (source === "LAKEBASE" && sandboxName) {
      setName(sandboxName);
    } else if (source === "UC" && ucCatalog && ucSchema) {
      setName(`${ucCatalog}.${ucSchema}`);
    } else if (source === "UC" && ucCatalog) {
      setName(ucCatalog);
    } else if (source === "DDL" && ddlFileName) {
      setName(ddlFileName.replace(/\.[^.]+$/, ""));
    } else if (source === "EMBARCADERO" && dm1FileName) {
      setName(dm1FileName.replace(/\.[^.]+$/, ""));
    }
  }, [
    source, sandboxName, ucCatalog, ucSchema,
    ddlFileName, dm1FileName, nameTouched,
  ]);

  // ─── Validação pra avançar ──────────────────────────────────────────────────
  const sourceReady =
    source === "NONE" ||
    (source === "LAKEBASE" && !!sandboxId && lakebaseSchemas.length > 0) ||
    (source === "UC" && !!ucCatalog && !!ucSchema && ucTables.length > 0) ||
    (source === "DDL" && ddlText.trim().length > 0) ||
    (source === "EMBARCADERO" && dm1Text.trim().length > 0);
  const canNext = step === 1 && name.trim().length > 0 && sourceReady;

  // ─── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit() {
    setSubmitting(true);
    try {
      const created = await createSystem.mutateAsync({
        data: {
          system_name: name.trim(),
          domain: domain.trim() || null,
          technology: technology || null,
          environment: environment || null,
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
      } else if (source === "DDL") {
        try {
          await runDDL.mutateAsync({
            data: {
              system_id: created.system_id,
              dialect: ddlDialect,
              ddl_text: ddlText,
              open_ticket: true,
            },
          });
        } catch (e) {
          toast.error("Sistema criado, mas import DDL falhou", {
            description: e instanceof Error ? e.message : String(e),
          });
        }
      } else if (source === "EMBARCADERO") {
        try {
          await runEmbarcadero.mutateAsync({
            data: {
              system_id: created.system_id,
              dm1_text: dm1Text,
              open_ticket: true,
            },
          });
        } catch (e) {
          toast.error("Sistema criado, mas import Embarcadero falhou", {
            description: e instanceof Error ? e.message : String(e),
          });
        }
      }

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

  const steps: { n: 1 | 2; label: string }[] = [
    { n: 1, label: "Configurar" },
    { n: 2, label: "Revisar" },
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
              return (
                <li key={s.n} className="flex items-center gap-2">
                  <span
                    className={
                      "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold " +
                      (active
                        ? "bg-nuclea-primary text-white border-nuclea-primary"
                        : done
                          ? "bg-emerald-500 text-white border-emerald-500"
                          : "bg-background text-muted-foreground")
                    }
                  >
                    {done ? <CheckCircle2 className="h-3 w-3" /> : s.n}
                  </span>
                  <span className={active ? "font-medium" : "text-muted-foreground"}>
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
        <CardContent className="flex-1 overflow-auto px-6 py-6 min-h-[420px] space-y-6">
          {step === 1 && (
            <StepConfigure
              name={name}
              setName={(v) => {
                setName(v);
                setNameTouched(true);
              }}
              domain={domain}
              setDomain={setDomain}
              technology={technology}
              setTechnology={(v) => {
                setTechnology(v);
                setTechTouched(true);
              }}
              environment={environment}
              setEnvironment={setEnvironment}
              source={source}
              setSource={(s) => {
                setSource(s);
                // Reset state da fonte anterior
                if (s !== "LAKEBASE") {
                  setSandboxId("");
                  setSandboxName("");
                  setLakebaseSchemas([]);
                }
                if (s !== "UC") {
                  setUcCatalog("");
                  setUcSchema("");
                  setUcTables([]);
                }
                if (s !== "DDL") {
                  setDdlText("");
                  setDdlFileName("");
                }
                if (s !== "EMBARCADERO") {
                  setDm1Text("");
                  setDm1FileName("");
                }
              }}
              sandboxId={sandboxId}
              setSandboxId={setSandboxId}
              setSandboxName={setSandboxName}
              lakebaseSchemas={lakebaseSchemas}
              setLakebaseSchemas={setLakebaseSchemas}
              ucCatalog={ucCatalog}
              setUcCatalog={(v) => {
                setUcCatalog(v);
                setUcSchema("");
                setUcTables([]);
              }}
              ucSchema={ucSchema}
              setUcSchema={(v) => {
                setUcSchema(v);
                setUcTables([]);
              }}
              ucTables={ucTables}
              setUcTables={setUcTables}
              ddlText={ddlText}
              setDdlText={setDdlText}
              ddlDialect={ddlDialect}
              setDdlDialect={setDdlDialect}
              ddlFileName={ddlFileName}
              setDdlFileName={setDdlFileName}
              dm1Text={dm1Text}
              setDm1Text={setDm1Text}
              dm1FileName={dm1FileName}
              setDm1FileName={setDm1FileName}
            />
          )}

          {step === 2 && (
            <StepSummary
              name={name}
              domain={domain}
              technology={technology}
              source={source}
              sandboxId={sandboxId}
              sandboxName={sandboxName}
              lakebaseSchemas={lakebaseSchemas}
              ucCatalog={ucCatalog}
              ucSchema={ucSchema}
              ucTables={ucTables}
              ddlDialect={ddlDialect}
              ddlFileName={ddlFileName}
              ddlText={ddlText}
              dm1FileName={dm1FileName}
              dm1Text={dm1Text}
            />
          )}
        </CardContent>

        {/* Footer */}
        <div className="border-t px-6 py-3 flex items-center justify-between bg-muted/20">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setStep(1)}
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
            {step === 1 ? (
              <Button
                type="button"
                size="sm"
                onClick={() => setStep(2)}
                disabled={!canNext}
                title={
                  !name.trim()
                    ? "Defina o nome"
                    : !sourceReady
                      ? "Complete a seleção da fonte"
                      : undefined
                }
              >
                Revisar
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={handleSubmit}
                disabled={submitting || !name.trim()}
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

// ─── Step 1: Configurar (consolidado) ─────────────────────────────────────────

function StepConfigure(props: {
  name: string;
  setName: (v: string) => void;
  domain: string;
  setDomain: (v: string) => void;
  technology: string;
  setTechnology: (v: string) => void;
  environment: "DEV" | "HINT" | "PRD" | "";
  setEnvironment: (v: "DEV" | "HINT" | "PRD" | "") => void;
  source: SourceKind;
  setSource: (s: SourceKind) => void;
  sandboxId: string;
  setSandboxId: (v: string) => void;
  setSandboxName: (v: string) => void;
  lakebaseSchemas: string[];
  setLakebaseSchemas: (v: string[]) => void;
  ucCatalog: string;
  setUcCatalog: (v: string) => void;
  ucSchema: string;
  setUcSchema: (v: string) => void;
  ucTables: string[];
  setUcTables: (v: string[]) => void;
  ddlText: string;
  setDdlText: (v: string) => void;
  ddlDialect: string;
  setDdlDialect: (v: string) => void;
  ddlFileName: string;
  setDdlFileName: (v: string) => void;
  dm1Text: string;
  setDm1Text: (v: string) => void;
  dm1FileName: string;
  setDm1FileName: (v: string) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Fonte */}
      <section className="space-y-3">
        <div>
          <h3 className="text-base font-semibold">De onde vem o modelo?</h3>
          <p className="text-xs text-muted-foreground">
            A escolha pré-preenche nome e tecnologia. Você pode ajustar depois.
          </p>
        </div>
        <SourceCards source={props.source} setSource={props.setSource} />
      </section>

      {/* Discovery condicional */}
      {props.source === "LAKEBASE" && (
        <section className="space-y-3 rounded-md border bg-muted/20 p-4">
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
                <Suspense fallback={<Skeleton className="h-32 w-full" />}>
                  <LakebaseDiscovery
                    sandboxId={props.sandboxId}
                    setSandboxId={props.setSandboxId}
                    setSandboxName={props.setSandboxName}
                    selected={props.lakebaseSchemas}
                    setSelected={props.setLakebaseSchemas}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
          </QueryErrorResetBoundary>
        </section>
      )}

      {props.source === "UC" && (
        <section className="space-y-3 rounded-md border bg-muted/20 p-4">
          <UCDiscovery
            catalog={props.ucCatalog}
            setCatalog={props.setUcCatalog}
            schema={props.ucSchema}
            setSchema={props.setUcSchema}
            tables={props.ucTables}
            setTables={props.setUcTables}
          />
        </section>
      )}

      {props.source === "DDL" && (
        <section className="space-y-3 rounded-md border bg-muted/20 p-4">
          <DDLDiscovery
            ddlText={props.ddlText}
            setDdlText={props.setDdlText}
            dialect={props.ddlDialect}
            setDialect={props.setDdlDialect}
            fileName={props.ddlFileName}
            setFileName={props.setDdlFileName}
          />
        </section>
      )}

      {props.source === "EMBARCADERO" && (
        <section className="space-y-3 rounded-md border bg-muted/20 p-4">
          <EmbarcaderoDiscovery
            dm1Text={props.dm1Text}
            setDm1Text={props.setDm1Text}
            fileName={props.dm1FileName}
            setFileName={props.setDm1FileName}
          />
        </section>
      )}

      {/* Identificação */}
      <section className="space-y-3">
        <div>
          <h3 className="text-base font-semibold">Identifique o sistema</h3>
          <p className="text-xs text-muted-foreground">
            O nome foi sugerido a partir da fonte — edite à vontade.
          </p>
        </div>
        <div>
          <label className="text-xs font-medium block mb-1">
            Nome <span className="text-destructive">*</span>
          </label>
          <Input
            autoFocus
            value={props.name}
            onChange={(e) => props.setName(e.target.value)}
            placeholder="Cadastro de Clientes"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium block mb-1">Domínio</label>
            <Input
              value={props.domain}
              onChange={(e) => props.setDomain(e.target.value)}
              placeholder="Cadastro, Risco, Cobrança..."
            />
          </div>
          <div>
            <label className="text-xs font-medium block mb-1">
              Tecnologia
              {props.source !== "NONE" && (
                <span className="ml-2 text-[10px] uppercase tracking-wider text-muted-foreground font-normal">
                  determinada pela fonte
                </span>
              )}
            </label>
            <select
              value={props.technology}
              onChange={(e) => props.setTechnology(e.target.value)}
              disabled={props.source !== "NONE"}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9 disabled:opacity-70 disabled:cursor-not-allowed"
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
        <div>
          <label className="text-xs font-medium block mb-1">
            Ambiente
            <span className="ml-2 text-[10px] uppercase tracking-wider text-muted-foreground font-normal">
              opcional
            </span>
          </label>
          <div className="flex gap-2">
            {(["", "DEV", "HINT", "PRD"] as const).map((env) => (
              <button
                key={env || "none"}
                type="button"
                onClick={() => props.setEnvironment(env)}
                className={
                  "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors " +
                  (props.environment === env
                    ? envBadgeClasses(env, true)
                    : envBadgeClasses(env, false))
                }
              >
                {env || "— nenhum —"}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            O mesmo modelo pode coexistir em DEV/HINT/PRD como sistemas
            separados — útil pra rastrear divergências entre ambientes.
          </p>
        </div>
      </section>
    </div>
  );
}

function envBadgeClasses(
  env: "" | "DEV" | "HINT" | "PRD",
  active: boolean,
): string {
  if (!active) return "border-border text-muted-foreground hover:bg-muted/40";
  if (env === "DEV") return "border-blue-500 bg-blue-500/10 text-blue-700 dark:text-blue-300";
  if (env === "HINT") return "border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  if (env === "PRD") return "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  return "border-nuclea-primary bg-nuclea-primary/10 text-nuclea-primary";
}

function SourceCards({
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
      value: "LAKEBASE",
      title: "Lakebase sandbox",
      description: "Descobre tabelas Postgres de uma sandbox cadastrada.",
      icon: <Database className="h-5 w-5" />,
    },
    {
      value: "UC",
      title: "Unity Catalog",
      description: "Descobre tabelas no UC: catalog → schema → tables.",
      icon: <Network className="h-5 w-5" />,
    },
    {
      value: "DDL",
      title: "Arquivo SQL (DDL)",
      description: "Cole ou faça upload de um .sql com CREATE TABLE — funciona pra qualquer banco.",
      icon: <FileCode className="h-5 w-5" />,
    },
    {
      value: "EMBARCADERO",
      title: "Embarcadero (.DM1)",
      description: "Upload do arquivo do ER/Studio — modelo lógico completo.",
      icon: <FileText className="h-5 w-5" />,
    },
    {
      value: "NONE",
      title: "Sem fonte (vazio)",
      description: "Cria sistema vazio. Adicione entidades manualmente no DER.",
      icon: <FileBox className="h-5 w-5" />,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
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
  );
}

function LakebaseDiscovery({
  sandboxId,
  setSandboxId,
  setSandboxName,
  selected,
  setSelected,
}: {
  sandboxId: string;
  setSandboxId: (v: string) => void;
  setSandboxName: (v: string) => void;
  selected: string[];
  setSelected: (v: string[]) => void;
}) {
  const { data: sandboxes } = useListSandboxesSuspense(selector());
  const active = useMemo(() => sandboxes.filter((s) => s.is_active), [sandboxes]);

  if (active.length === 0) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
        <p className="font-medium mb-1">Nenhuma sandbox Lakebase ativa</p>
        <p className="text-muted-foreground text-xs">
          Cadastre uma sandbox em <strong>Lakebase Sandbox</strong> antes de
          rodar discovery. Ou volte e escolha "Sem fonte".
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs font-medium block mb-1">Sandbox</label>
        <select
          value={sandboxId}
          onChange={(e) => {
            const id = e.target.value;
            setSandboxId(id);
            const sb = active.find((s) => s.sandbox_id === id);
            setSandboxName(sb?.name || "");
            setSelected([]);
          }}
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

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-medium">
          Schemas{" "}
          <span className="text-muted-foreground">
            ({selected.length}/{capped.length})
          </span>
        </label>
        <div className="flex gap-1">
          <Button type="button" size="sm" variant="ghost" onClick={() => setSelected(capped)}>
            Selecionar todos
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setSelected([])}>
            Limpar
          </Button>
        </div>
      </div>
      {truncated && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
          Mostrando os primeiros {MAX_SCHEMAS} schemas.
        </p>
      )}
      <div className="rounded-md border max-h-56 overflow-auto bg-background">
        {capped.length === 0 ? (
          <p className="text-sm text-muted-foreground p-3">
            Nenhum schema visível para o app nessa sandbox.
          </p>
        ) : (
          <ul className="divide-y">
            {capped.map((s) => (
              <li key={s} className="flex items-center gap-2 px-3 py-1.5">
                <input
                  type="checkbox"
                  checked={selected.includes(s)}
                  onChange={() =>
                    setSelected(
                      selected.includes(s)
                        ? selected.filter((x) => x !== s)
                        : [...selected, s],
                    )
                  }
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

function UCDiscovery({
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
    <div className="space-y-3">
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ error, resetErrorBoundary }) => (
              <BrowseError
                title="Não foi possível listar catalogs"
                hint="Verifique se o app tem permissão USE_CATALOG no Unity Catalog."
                error={error}
                onRetry={resetErrorBoundary}
              />
            )}
          >
            <Suspense fallback={<Skeleton className="h-9 w-full" />}>
              <UCCatalogPicker catalog={catalog} setCatalog={setCatalog} />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>

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

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-medium">
          Tables{" "}
          <span className="text-muted-foreground">
            ({selected.length}/{tables.length})
          </span>
        </label>
        <div className="flex gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setSelected(tables.map((t) => t.name))}
          >
            Selecionar tudo
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setSelected([])}>
            Limpar
          </Button>
        </div>
      </div>
      <div className="rounded-md border max-h-56 overflow-auto bg-background">
        {tables.length === 0 ? (
          <p className="text-sm text-muted-foreground p-3">
            Nenhuma tabela visível neste schema.
          </p>
        ) : (
          <ul className="divide-y">
            {tables.map((t) => (
              <li key={t.name} className="flex items-center gap-2 px-3 py-1.5">
                <input
                  type="checkbox"
                  checked={selected.includes(t.name)}
                  onChange={() =>
                    setSelected(
                      selected.includes(t.name)
                        ? selected.filter((x) => x !== t.name)
                        : [...selected, t.name],
                    )
                  }
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

// ─── Step 2: Resumo ───────────────────────────────────────────────────────────

// ─── DDL / Embarcadero file pickers ───────────────────────────────────────────

function DDLDiscovery({
  ddlText,
  setDdlText,
  dialect,
  setDialect,
  fileName,
  setFileName,
}: {
  ddlText: string;
  setDdlText: (v: string) => void;
  dialect: string;
  setDialect: (v: string) => void;
  fileName: string;
  setFileName: (v: string) => void;
}) {
  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > DDL_MAX_BYTES) {
      toast.error(`Arquivo muito grande (${(f.size / 1024 / 1024).toFixed(1)} MB > 5 MB)`);
      return;
    }
    try {
      const text = await f.text();
      setDdlText(text);
      setFileName(f.name);
    } catch (err) {
      toast.error("Falha ao ler arquivo", {
        description: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
        <div>
          <label className="text-xs font-medium block mb-1">Dialeto SQL</label>
          <select
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm h-9"
          >
            {DDL_DIALECTS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium block mb-1 sr-only">Upload</label>
          <label className="inline-flex items-center gap-2 cursor-pointer rounded-md border bg-background px-3 py-2 text-xs hover:bg-muted/40 h-9">
            <Upload className="h-3.5 w-3.5" />
            <span>Carregar .sql</span>
            <input
              type="file"
              accept=".sql,.ddl,text/plain"
              onChange={onFile}
              className="hidden"
            />
          </label>
        </div>
      </div>
      {fileName && (
        <p className="text-[11px] text-muted-foreground">
          Arquivo carregado: <strong>{fileName}</strong> ({ddlText.length.toLocaleString()} chars)
        </p>
      )}
      <div>
        <label className="text-xs font-medium block mb-1">
          Conteúdo DDL (CREATE TABLE, etc.)
        </label>
        <textarea
          value={ddlText}
          onChange={(e) => {
            setDdlText(e.target.value);
            if (fileName) setFileName(""); // user editou manualmente, sai do "modo arquivo"
          }}
          rows={8}
          placeholder="-- Cole o DDL aqui ou use 'Carregar .sql'&#10;CREATE TABLE clientes (&#10;  cliente_id BIGINT PRIMARY KEY,&#10;  nome VARCHAR(200) NOT NULL&#10;);"
          className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono"
        />
      </div>
    </div>
  );
}

function EmbarcaderoDiscovery({
  dm1Text,
  setDm1Text,
  fileName,
  setFileName,
}: {
  dm1Text: string;
  setDm1Text: (v: string) => void;
  fileName: string;
  setFileName: (v: string) => void;
}) {
  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > DM1_MAX_BYTES) {
      toast.error(`Arquivo muito grande (${(f.size / 1024 / 1024).toFixed(1)} MB > 50 MB)`);
      return;
    }
    try {
      const text = await f.text();
      setDm1Text(text);
      setFileName(f.name);
    } catch (err) {
      toast.error("Falha ao ler arquivo", {
        description: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs font-medium block mb-1">Arquivo .DM1</label>
        <label className="inline-flex items-center gap-2 cursor-pointer rounded-md border bg-background px-3 py-2 text-xs hover:bg-muted/40">
          <Upload className="h-3.5 w-3.5" />
          <span>{fileName ? "Trocar arquivo" : "Selecionar .DM1"}</span>
          <input
            type="file"
            accept=".dm1,.DM1"
            onChange={onFile}
            className="hidden"
          />
        </label>
      </div>
      {fileName ? (
        <div className="rounded-md border bg-emerald-500/5 p-3 text-xs space-y-1">
          <p className="font-medium">{fileName}</p>
          <p className="text-muted-foreground">
            {dm1Text.length.toLocaleString()} caracteres carregados. O parser
            extrai entities, atributos e relacionamentos do modelo ER/Studio.
          </p>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Aceita arquivos até 50 MB. Formato nativo do Embarcadero ER/Studio.
        </p>
      )}
    </div>
  );
}

function StepSummary({
  name,
  domain,
  technology,
  source,
  sandboxId,
  sandboxName,
  lakebaseSchemas,
  ucCatalog,
  ucSchema,
  ucTables,
  ddlDialect,
  ddlFileName,
  ddlText,
  dm1FileName,
  dm1Text,
}: {
  name: string;
  domain: string;
  technology: string;
  source: SourceKind;
  sandboxId: string;
  sandboxName: string;
  lakebaseSchemas: string[];
  ucCatalog: string;
  ucSchema: string;
  ucTables: string[];
  ddlDialect: string;
  ddlFileName: string;
  ddlText: string;
  dm1FileName: string;
  dm1Text: string;
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
                : source === "UC"
                  ? "Unity Catalog"
                  : source === "DDL"
                    ? "Arquivo SQL (DDL)"
                    : "Embarcadero (.DM1)"
          }
        />
        {source === "LAKEBASE" && (
          <>
            <SummaryRow label="Sandbox" value={sandboxName || sandboxId} />
            <SummaryRow
              label="Schemas"
              value={lakebaseSchemas.length ? lakebaseSchemas.join(", ") : "—"}
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
        {source === "DDL" && (
          <>
            <SummaryRow label="Dialeto" value={ddlDialect} />
            <SummaryRow
              label="Origem"
              value={ddlFileName ? `arquivo ${ddlFileName}` : "DDL colado"}
            />
            <SummaryRow label="Tamanho" value={`${ddlText.length.toLocaleString()} chars`} />
          </>
        )}
        {source === "EMBARCADERO" && (
          <>
            <SummaryRow label="Arquivo" value={dm1FileName || "—"} />
            <SummaryRow label="Tamanho" value={`${dm1Text.length.toLocaleString()} chars`} />
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
