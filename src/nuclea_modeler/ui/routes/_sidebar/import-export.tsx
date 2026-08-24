/**
 * Round-trip de edição via CSV (v1.0035, feedback do cliente).
 *
 * Exportar (por sistema) → editar o arquivo fora do app → reimportar → o app
 * compara com o catálogo, mostra o resumo do DIFF e abre um ticket editorial
 * (aprovação pelo fluxo normal em /tickets).
 */
import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useRef, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListSystemsSuspense,
  useExportSystemCsv,
  useImportSystemCsv,
  type CsvImportOut,
} from "@/lib/api";
import selector from "@/lib/selector";
import { getLastSystemId, saveLastSystemId } from "@/lib/persist-search";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Download, Upload, FileSpreadsheet } from "lucide-react";

export const Route = createFileRoute("/_sidebar/import-export")({
  component: ImportExportPage,
});

function ImportExportPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Exportar / Importar (CSV)</h1>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Exporte os dados de tabelas/colunas/esquema de um sistema, ajuste o arquivo
          fora do app e reimporte: o app mostra o que mudou e abre um <strong>ticket
          de aprovação</strong>. Nada é alterado no catálogo até a aprovação.
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
                    <AlertCircle className="h-5 w-5" /> Erro
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-72 w-full" />}>
              <RoundTripPanel />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function RoundTripPanel() {
  const { data: systems } = useListSystemsSuspense(selector());
  const [systemId, setSystemId] = useState(
    getLastSystemId() || systems[0]?.system_id || "",
  );
  const [summary, setSummary] = useState<CsvImportOut | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const onSystemChange = (id: string) => {
    setSystemId(id);
    if (id) saveLastSystemId(id);
    setSummary(null);
  };

  const exportCsv = useExportSystemCsv({
    mutation: {
      onSuccess: (data) => {
        // Monta o download do CSV recebido do backend.
        const blob = new Blob([data.csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.filename;
        a.click();
        URL.revokeObjectURL(url);
        toast.success("CSV exportado");
      },
      onError: (e) => toast.error(e instanceof Error ? e.message : "Falha ao exportar"),
    },
  });

  const importCsv = useImportSystemCsv({
    mutation: {
      onSuccess: (res) => {
        setSummary(res);
        if (res.ticket_id) toast.success(res.message);
        else toast.info(res.message);
      },
      onError: (e) => toast.error(e instanceof Error ? e.message : "Falha ao importar"),
    },
  });

  const onPickFile = async (file: File | null) => {
    if (!file || !systemId) return;
    const text = await file.text();
    importCsv.mutate({ systemId, csvText: text });
    if (fileRef.current) fileRef.current.value = ""; // permite reimportar o mesmo arquivo
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" /> Sistema
          </CardTitle>
          <CardDescription>Escolha o sistema para exportar/importar.</CardDescription>
        </CardHeader>
        <CardContent>
          <select
            className="w-full max-w-md rounded-md border bg-background px-3 py-2 text-sm"
            value={systemId}
            onChange={(e) => onSystemChange(e.target.value)}
          >
            {systems.map((s) => (
              <option key={s.system_id} value={s.system_id}>
                {s.environment ? `[${s.environment}] ` : ""}{s.system_name}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Download className="h-4 w-4" /> Exportar
            </CardTitle>
            <CardDescription>
              Baixa um CSV (uma linha por coluna) com esquema, tabela e coluna —
              editável e re-importável.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={() => exportCsv.mutate({ systemId })}
              disabled={!systemId || exportCsv.isPending}
              size="sm"
            >
              <Download className="mr-2 h-4 w-4" />
              {exportCsv.isPending ? "Exportando…" : "Exportar CSV"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Upload className="h-4 w-4" /> Importar (ajustes)
            </CardTitle>
            <CardDescription>
              Reimporte o CSV editado. Campos vazios = "não mexer". Gera um ticket
              com o diff para aprovação.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-nuclea-primary file:px-3 file:py-1.5 file:text-white"
              onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
              disabled={!systemId || importCsv.isPending}
            />
            {importCsv.isPending && (
              <p className="text-xs text-muted-foreground">Analisando o arquivo…</p>
            )}
          </CardContent>
        </Card>
      </div>

      {summary && (
        <Card className={summary.ticket_id ? "border-emerald-500/40" : ""}>
          <CardHeader>
            <CardTitle className="text-base">Resultado da importação</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>{summary.message}</p>
            <p className="text-muted-foreground">
              Tabelas com ajustes: <strong>{summary.entities_changed}</strong> · Colunas:{" "}
              <strong>{summary.columns_changed}</strong>
            </p>
            {summary.unknown_tables.length > 0 && (
              <p className="text-amber-600 dark:text-amber-400 text-xs">
                Ignoradas (não existem no catálogo): {summary.unknown_tables.join(", ")}
              </p>
            )}
            {summary.ticket_id && (
              <Button asChild size="sm">
                <Link to="/tickets/$id" params={{ id: summary.ticket_id }}>
                  Revisar diff e aprovar
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
