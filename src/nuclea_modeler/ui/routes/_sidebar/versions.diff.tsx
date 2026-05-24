import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetVersionSuspense,
  useVersionDiffSuspense,
  type VersionOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, ArrowLeft, ArrowRight } from "lucide-react";

import { StatusBadge } from "./versions";
import { DiffSections } from "./versions.$id";

interface DiffSearch {
  from: string;
  to: string;
}

export const Route = createFileRoute("/_sidebar/versions/diff")({
  validateSearch: (search: Record<string, unknown>): DiffSearch => ({
    from: String(search.from ?? ""),
    to: String(search.to ?? ""),
  }),
  component: DiffPage,
});

function DiffPage() {
  const { from, to } = Route.useSearch();

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/versions">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Versões
        </Link>
      </Button>

      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Diff de Versões</h1>
          <Badge variant="outline" className="font-mono">M8</Badge>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Comparativo lado a lado entre dois snapshots imutáveis.
        </p>
      </div>

      {!from || !to ? (
        <Card className="border-amber-500/40">
          <CardContent className="pt-6 text-sm">
            Selecione duas versões em <Link to="/versions" className="underline">/versions</Link>{" "}
            para comparar.
          </CardContent>
        </Card>
      ) : from === to ? (
        <Card className="border-destructive/50">
          <CardContent className="pt-6 text-sm text-destructive">
            As versões selecionadas para comparação devem ser diferentes.
          </CardContent>
        </Card>
      ) : (
        <QueryErrorResetBoundary>
          {({ reset }) => (
            <ErrorBoundary
              onReset={reset}
              fallbackRender={({ resetErrorBoundary, error }) => (
                <Card className="border-destructive/50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-destructive">
                      <AlertCircle className="h-5 w-5" />
                      Erro ao calcular o diff
                    </CardTitle>
                    <CardDescription>{(error as Error).message}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                  </CardContent>
                </Card>
              )}
            >
              <Suspense fallback={<Skeleton className="h-80 w-full" />}>
                <DiffBody fromId={from} toId={to} />
              </Suspense>
            </ErrorBoundary>
          )}
        </QueryErrorResetBoundary>
      )}
    </div>
  );
}

function DiffBody({ fromId, toId }: { fromId: string; toId: string }) {
  const { data: vFrom } = useGetVersionSuspense(fromId, selector());
  const { data: vTo } = useGetVersionSuspense(toId, selector());
  const { data: diff } = useVersionDiffSuspense(
    { from: fromId, to: toId },
    selector(),
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] items-stretch">
        <VersionSummary version={vFrom} side="from" />
        <div className="hidden md:flex items-center justify-center text-muted-foreground">
          <ArrowRight className="h-6 w-6" />
        </div>
        <VersionSummary version={vTo} side="to" />
      </div>

      <DiffSections diff={diff} />
    </div>
  );
}

function VersionSummary({
  version,
  side,
}: {
  version: VersionOut;
  side: "from" | "to";
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription className="uppercase tracking-wide text-[11px]">
          {side === "from" ? "De" : "Até"}
        </CardDescription>
        <CardTitle className="flex items-center gap-2 flex-wrap text-base">
          <Link
            to="/versions/$id"
            params={{ id: version.version_id }}
            className="font-mono hover:text-nuclea-primary"
          >
            {version.version_number}
          </Link>
          <StatusBadge status={version.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-xs text-muted-foreground">
        <p>
          <strong className="text-foreground">{version.title || "(sem título)"}</strong>
        </p>
        <p>Sistema: {version.system_name || version.system_id}</p>
        <p>
          {version.published_at
            ? `Publicada em ${new Date(version.published_at).toLocaleString("pt-BR")}`
            : `Rascunho desde ${new Date(version.created_at).toLocaleString("pt-BR")}`}
          {(version.published_by || version.created_by) && (
            <> por {version.published_by || version.created_by}</>
          )}
        </p>
      </CardContent>
    </Card>
  );
}
