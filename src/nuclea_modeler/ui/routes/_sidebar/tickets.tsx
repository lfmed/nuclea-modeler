import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useListTicketsSuspense, type TicketStatus } from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  Inbox,
  CheckCircle2,
  PlayCircle,
  XCircle,
  Plus,
  Minus,
  RefreshCw,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/tickets")({
  component: TicketsPage,
});

function TicketsPage() {
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
                    Erro ao carregar tickets
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
            <Suspense fallback={<TableSkeleton />}>
              <TicketsList />
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
        <h1 className="text-3xl font-bold tracking-tight">Tickets de Reconciliação</h1>
        <Badge variant="outline" className="font-mono">Aprovações</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Toda alteração detectada por engenharia reversa, import de DDL ou validação no Lakebase
        gera um ticket que precisa ser <strong>aprovado</strong> e <strong>aplicado</strong> antes
        de modificar o catálogo. Apenas Data Architects ou Stewards podem aprovar.
      </p>
    </div>
  );
}

function TicketsList() {
  const [filter, setFilter] = useState<TicketStatus | "ALL">("OPEN");
  const params = filter === "ALL" ? {} : { status: filter };
  const { data: tickets } = useListTicketsSuspense(params, selector());

  return (
    <div className="space-y-4">
      <FilterTabs current={filter} onChange={setFilter} />
      {tickets.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y">
              {tickets.map((t) => (
                <Link
                  key={t.ticket_id}
                  to="/tickets/$id"
                  params={{ id: t.ticket_id }}
                  className="flex items-start gap-4 p-4 hover:bg-muted/40 transition-colors"
                >
                  <StatusBadge status={t.status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <h3 className="font-medium truncate">{t.title}</h3>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {new Date(t.created_at).toLocaleString("pt-BR")}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">
                      Sistema: <strong>{t.system_name || t.system_id}</strong>
                      <span className="mx-2">·</span>
                      Fonte: <code className="text-xs">{t.source_type}</code>
                      <span className="mx-2">·</span>
                      por <span>{t.created_by}</span>
                    </p>
                    <DiffCounts
                      additions={t.additions_count}
                      removals={t.removals_count}
                      changes={t.changes_count}
                    />
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FilterTabs({
  current,
  onChange,
}: {
  current: TicketStatus | "ALL";
  onChange: (s: TicketStatus | "ALL") => void;
}) {
  const tabs: { value: TicketStatus | "ALL"; label: string }[] = [
    { value: "OPEN", label: "Abertos" },
    { value: "APPROVED", label: "Aprovados" },
    { value: "APPLIED", label: "Aplicados" },
    { value: "REJECTED", label: "Rejeitados" },
    { value: "ALL", label: "Todos" },
  ];
  return (
    <div className="flex flex-wrap gap-1 border-b">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
            current === t.value
              ? "border-nuclea-primary text-nuclea-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: TicketStatus }) {
  const config = {
    OPEN: { icon: <Inbox className="h-4 w-4" />, color: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300" },
    APPROVED: { icon: <CheckCircle2 className="h-4 w-4" />, color: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300" },
    APPLIED: { icon: <PlayCircle className="h-4 w-4" />, color: "bg-nuclea-primary/10 text-nuclea-primary border-nuclea-primary/30" },
    REJECTED: { icon: <XCircle className="h-4 w-4" />, color: "bg-destructive/10 text-destructive border-destructive/30" },
  }[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium shrink-0 ${config.color}`}>
      {config.icon}
      {status}
    </span>
  );
}

function DiffCounts({
  additions,
  removals,
  changes,
}: {
  additions: number;
  removals: number;
  changes: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      {additions > 0 && (
        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
          <Plus className="h-3 w-3" /> {additions} adições
        </span>
      )}
      {removals > 0 && (
        <span className="inline-flex items-center gap-1 text-destructive">
          <Minus className="h-3 w-3" /> {removals} remoções
        </span>
      )}
      {changes > 0 && (
        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
          <RefreshCw className="h-3 w-3" /> {changes} alterações
        </span>
      )}
      {additions + removals + changes === 0 && (
        <span className="text-muted-foreground">sem mudanças</span>
      )}
    </div>
  );
}

function EmptyState({ filter }: { filter: TicketStatus | "ALL" }) {
  return (
    <Card className="border-dashed">
      <CardContent className="pt-10 pb-10 text-center">
        <Inbox className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
        <p className="text-sm text-muted-foreground">
          {filter === "OPEN"
            ? "Nenhum ticket aberto. Rode uma engenharia reversa em /extractions para gerar um."
            : `Nenhum ticket em ${filter.toLowerCase()}.`}
        </p>
      </CardContent>
    </Card>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-64" />
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-20 w-full" />
      ))}
    </div>
  );
}
