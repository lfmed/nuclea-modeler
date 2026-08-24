/**
 * Admin — Catálogo de sync do Unity Catalog (v1.0035).
 *
 * Feedback do cliente: precisa de uma tela onde o admin escolhe, entre os
 * catálogos disponíveis no Unity Catalog, qual será usado como destino do sync.
 * A escolha é persistida (app_settings) e vira o default da tela de Sync.
 * Só ADMIN vê/edita (mesmo padrão de admin.roles.tsx).
 */
import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useSyncCatalogSuspense,
  useSetSyncCatalog,
  useListUCCatalogsSuspense,
  useMyRolesSuspense,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Database, Save } from "lucide-react";

export const Route = createFileRoute("/_sidebar/admin/sync-config")({
  component: SyncConfigPage,
});

function SyncConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Configuração de Sync</h1>
          <Badge variant="outline" className="font-mono">Admin</Badge>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Escolhe o <strong>catálogo do Unity Catalog</strong> usado como destino na
          sincronização (Sync UC). A escolha vale para todos e vira o default da tela de Sync.
          Apenas <strong>ADMIN</strong> pode alterar.
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
                    Sem acesso ou erro
                  </CardTitle>
                  <CardDescription>
                    Você precisa ser ADMIN. Verifique também se o backend está online.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-60 w-full" />}>
              <SyncConfigForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function SyncConfigForm() {
  const { data: me } = useMyRolesSuspense(selector());
  const { data: current } = useSyncCatalogSuspense(selector());
  const { data: catalogs } = useListUCCatalogsSuspense(selector());
  const qc = useQueryClient();

  const [choice, setChoice] = useState(current.catalog);
  const isAdmin = me.is_admin;

  const { mutate: save, isPending } = useSetSyncCatalog({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["getSyncCatalog"] });
        toast.success(`Catálogo de sync definido: ${data.catalog}`);
      },
      onError: (e) =>
        toast.error("Falha ao salvar", {
          description: e instanceof Error ? e.message : "Erro desconhecido",
        }),
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-5 w-5" />
          Catálogo de destino do Sync
        </CardTitle>
        <CardDescription>
          Atual: <strong className="font-mono">{current.catalog}</strong>
          {current.is_custom
            ? " (escolhido pelo admin)"
            : ` (default do app: ${current.default})`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="max-w-md space-y-2">
          <label className="text-xs font-medium text-muted-foreground block">
            Catálogo (Unity Catalog)
          </label>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-60"
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            disabled={!isAdmin}
          >
            {/* Garante que o valor atual apareça mesmo se não estiver na lista. */}
            {!catalogs.some((c) => c.name === choice) && (
              <option value={choice}>{choice} (atual)</option>
            )}
            {catalogs.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
                {c.catalog_type ? ` · ${c.catalog_type}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <Button
            onClick={() => save({ catalog: choice })}
            disabled={!isAdmin || isPending || choice === current.catalog}
            size="sm"
          >
            <Save className="mr-2 h-4 w-4" />
            {isPending ? "Salvando…" : "Salvar catálogo"}
          </Button>
          {!isAdmin && (
            <span className="text-xs text-muted-foreground">
              Somente ADMIN pode alterar.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
