import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useEffect, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useGetViewSuspense, useUpsertView } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, AlertCircle, Eye, Save } from "lucide-react";
import { SqlEditor } from "@/components/code/sql-editor";

export const Route = createFileRoute("/_sidebar/code/views/$id")({
  component: ViewDetailPage,
});

function ViewDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/code">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Voltar
        </Link>
      </Button>
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar view
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-96 w-full" />}>
              <ViewDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ViewDetail() {
  const { id } = Route.useParams();
  const { data: view } = useGetViewSuspense(id, selector());
  const qc = useQueryClient();
  const { mutate: save, isPending } = useUpsertView({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getView", id] });
        qc.invalidateQueries({ queryKey: ["listViews"] });
      },
    },
  });

  const [purpose, setPurpose] = useState(view.purpose || "");
  const [sql, setSql] = useState(view.definition_sql || "");

  useEffect(() => {
    setPurpose(view.purpose || "");
    setSql(view.definition_sql || "");
  }, [view.view_entity_id, view.purpose, view.definition_sql]);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Eye className="h-5 w-5 text-nuclea-primary" />
          <Badge variant="outline">VIEW</Badge>
        </div>
        <h1 className="text-3xl font-bold tracking-tight font-mono">{view.entity_label}</h1>
        <p className="text-sm text-muted-foreground">{view.system_name || view.system_id}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Propósito</CardTitle>
          <CardDescription>Por que essa view existe, quem a utiliza</CardDescription>
        </CardHeader>
        <CardContent>
          <textarea
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            rows={3}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Definição SQL</CardTitle>
          <CardDescription>Editor com syntax highlight. Exibição apenas — não executa.</CardDescription>
        </CardHeader>
        <CardContent>
          <SqlEditor value={sql} onChange={setSql} height={420} language="sql" />
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button
          onClick={() =>
            save({
              viewEntityId: id,
              data: {
                view_entity_id: id,
                purpose: purpose || null,
                definition_sql: sql || null,
                base_entity_ids: view.base_entity_ids,
              },
            })
          }
          disabled={isPending}
        >
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Salvando..." : "Salvar"}
        </Button>
      </div>
    </div>
  );
}
