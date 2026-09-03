import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useEffect, useMemo, useState } from "react";
import { selectDefaultSystemId, saveLastSystemId } from "@/lib/persist-search";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useExportDdl,
  useListDdlDialectsSuspense,
  useListSystemsSuspense,
  usePreviewDdl,
  type DDLDialect,
  type DDLExportResult,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  ClipboardCopy,
  Code2,
  Download,
  Eye,
  FileWarning,
  RefreshCw,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/ddl")({
  component: DdlPage,
});

function DdlPage() {
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
                    Erro ao carregar exportação DDL
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
            <Suspense fallback={<FormSkeleton />}>
              <DdlForm />
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
        <h1 className="text-3xl font-bold tracking-tight">Exportar DDL</h1>
        <Badge variant="outline" className="font-mono">
          M10
        </Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Gere scripts DDL a partir das entidades catalogadas em 6 dialetos:
        ANSI, T-SQL, PL/SQL, PostgreSQL, MySQL e Spark SQL / Delta. Use para
        documentação, migração ou recriação de estruturas em outros bancos.
      </p>
    </div>
  );
}

function DdlForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: dialects } = useListDdlDialectsSuspense(selector());

  // "Sistema atual" compartilhado (sessionStorage) — antes esta aba caía sempre
  // no 1º da lista, ignorando o sistema escolhido em outra tela.
  const [systemId, setSystemId] = useState<string>(
    selectDefaultSystemId(undefined, systems),
  );
  useEffect(() => {
    if (systemId) saveLastSystemId(systemId);
  }, [systemId]);
  const [dialect, setDialect] = useState<DDLDialect>("SPARKSQL");
  const [includeComments, setIncludeComments] = useState(true);
  const [qualifySchema, setQualifySchema] = useState(true);
  const [includeDropIfExists, setIncludeDropIfExists] = useState(false);
  const [oneFilePerObject, setOneFilePerObject] = useState(false);

  const [result, setResult] = useState<DDLExportResult | null>(null);
  const [isPreview, setIsPreview] = useState(false);

  const preview = usePreviewDdl({
    mutation: {
      onSuccess: (data) => {
        setResult(data);
        setIsPreview(true);
      },
    },
  });
  const exportMut = useExportDdl({
    mutation: {
      onSuccess: (data) => {
        setResult(data);
        setIsPreview(false);
        // Nome do arquivo = nome do sistema (round 5, pt 17), com fallback ao id.
        triggerDownload(
          data,
          systems.find((s) => s.system_id === systemId)?.system_name || systemId,
          dialect,
        );
      },
    },
  });

  const isBusy = preview.isPending || exportMut.isPending;
  const error = preview.error || exportMut.error;

  const payload = useMemo(
    () => ({
      system_id: systemId,
      dialect,
      include_comments: includeComments,
      qualify_schema: qualifySchema,
      include_drop_if_exists: includeDropIfExists,
      one_file_per_object: oneFilePerObject,
    }),
    [
      systemId,
      dialect,
      includeComments,
      qualifySchema,
      includeDropIfExists,
      oneFilePerObject,
    ],
  );

  const onPreview = () => preview.mutate({ data: payload });
  const onExport = () => exportMut.mutate({ data: payload });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code2 className="h-5 w-5 text-nuclea-primary" />
            Configuração
          </CardTitle>
          <CardDescription>
            Selecione o sistema, o dialeto SQL e as opções de geração.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Sistema" required>
              {systems.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Cadastre um sistema primeiro.
                </p>
              ) : (
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={systemId}
                  onChange={(e) => setSystemId(e.target.value)}
                  required
                >
                  {systems.map((s) => (
                    <option key={s.system_id} value={s.system_id}>
                      {s.system_name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Dialeto SQL" required>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={dialect}
                onChange={(e) => setDialect(e.target.value as DDLDialect)}
              >
                {dialects.map((d) => (
                  <option key={d.code} value={d.code}>
                    {d.label} — {d.subtitle}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Toggle
              checked={includeComments}
              onChange={setIncludeComments}
              label="Incluir comentários"
              help="Adiciona descrições documentadas (tabela e colunas) como COMMENT no DDL."
            />
            <Toggle
              checked={qualifySchema}
              onChange={setQualifySchema}
              label="Qualificar com schema"
              help="Gera schema.tabela em vez de apenas tabela."
            />
            <Toggle
              checked={includeDropIfExists}
              onChange={setIncludeDropIfExists}
              label="DROP IF EXISTS"
              help="Adiciona DROP antes do CREATE — útil para recriar estruturas."
            />
            <Toggle
              checked={oneFilePerObject}
              onChange={setOneFilePerObject}
              label="Um arquivo por objeto"
              help="Mantém DDL separado por objeto na seção de preview. O download é sempre um arquivo .sql consolidado."
            />
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={onPreview}
              disabled={isBusy || !systemId}
            >
              <Eye className="mr-2 h-4 w-4" />
              {preview.isPending ? "Gerando..." : "Visualizar"}
            </Button>
            <Button onClick={onExport} disabled={isBusy || !systemId}>
              <Download className="mr-2 h-4 w-4" />
              {exportMut.isPending ? "Gerando..." : "Gerar e baixar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              Erro na geração
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs whitespace-pre-wrap text-destructive">
              {String(error)}
            </pre>
          </CardContent>
        </Card>
      )}

      {result && <PreviewSection result={result} isPreview={isPreview} oneFilePerObject={oneFilePerObject} />}
    </div>
  );
}

function PreviewSection({
  result,
  isPreview,
  oneFilePerObject,
}: {
  result: DDLExportResult;
  isPreview: boolean;
  oneFilePerObject: boolean;
}) {
  const failed = result.files.filter((f) => f.errors.length > 0);

  return (
    <div className="space-y-4">
      {failed.length > 0 && (
        <Card className="border-amber-500/40">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
              <FileWarning className="h-5 w-5" />
              {failed.length} objeto(s) com erro
            </CardTitle>
            <CardDescription>
              Esses objetos foram incluídos com um comentário de erro no DDL.
              Revise o catálogo e tente novamente.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="text-sm space-y-1">
              {failed.map((f) => (
                <li key={f.object_name} className="font-mono text-xs">
                  <span className="text-amber-700 dark:text-amber-300">
                    {f.object_name}
                  </span>{" "}
                  — {f.errors.join("; ")}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>
                Preview {isPreview ? "(parcial — até 10 objetos)" : ""}
              </CardTitle>
              <CardDescription>
                {result.success_count} de {result.total_objects} objeto(s)
                gerado(s) em <Badge variant="outline">{result.dialect}</Badge>
              </CardDescription>
            </div>
            <CopyButton text={result.combined_text} label="Copiar tudo" />
          </div>
        </CardHeader>
        <CardContent>
          {oneFilePerObject ? (
            <div className="space-y-4">
              {result.files.map((f) => (
                <div
                  key={f.object_name}
                  className="rounded-md border bg-muted/30"
                >
                  <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
                    <span className="text-sm font-mono">{f.object_name}</span>
                    <CopyButton text={f.ddl_text} label="Copiar" small />
                  </div>
                  <SqlBlock text={f.ddl_text} />
                </div>
              ))}
            </div>
          ) : (
            <SqlBlock text={result.combined_text} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SqlBlock({ text }: { text: string }) {
  return (
    <pre className="max-h-[480px] overflow-auto rounded-md bg-muted/50 p-3 text-xs leading-relaxed font-mono whitespace-pre">
      <code className="language-sql">{text || "-- (vazio)"}</code>
    </pre>
  );
}

function CopyButton({
  text,
  label,
  small,
}: {
  text: string;
  label: string;
  small?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };
  return (
    <Button
      type="button"
      size={small ? "sm" : "default"}
      variant="outline"
      onClick={onClick}
    >
      <ClipboardCopy className="mr-2 h-4 w-4" />
      {copied ? "Copiado!" : label}
    </Button>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  help,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  help: string;
}) {
  return (
    <label className="flex items-start gap-3 rounded-md border bg-background px-3 py-2 cursor-pointer hover:bg-muted/40">
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 accent-nuclea-primary"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="space-y-0.5">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block text-xs text-muted-foreground">{help}</span>
      </span>
    </label>
  );
}

function Field({
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

function FormSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

function triggerDownload(
  result: DDLExportResult,
  systemName: string,
  dialect: DDLDialect,
) {
  const blob = new Blob([result.combined_text], { type: "text/sql" });
  const url = URL.createObjectURL(blob);
  // Nome do arquivo = nome do sistema "slugificado" (round 5, pt 17). Antes usávamos
  // o systemId (UUID), pouco legível. Ex.: "Cadastro de Clientes" → "cadastro-de-clientes".
  const slug =
    (systemName || "system")
      .normalize("NFD") // separa letra-base + acento (é → e + ´)
      .replace(/\p{Diacritic}/gu, "") // remove os acentos (ç, ã, é…)
      .replace(/[^a-zA-Z0-9]+/g, "-") // não-alfanumérico → hífen
      .replace(/^-+|-+$/g, "") // apara hífens das pontas
      .toLowerCase() || "system";
  const a = document.createElement("a");
  a.href = url;
  a.download = `${slug}-${dialect.toLowerCase()}.sql`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
