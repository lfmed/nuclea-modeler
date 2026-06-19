import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListTicketsSuspense,
  useMyRolesSuspense,
  useBatchTicketAction,
  type TicketStatus,
  type BatchAction,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { EmptyState as SharedEmptyState } from "@/components/apx/empty-state";

export const Route = createFileRoute("/_sidebar/tickets/")({
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
  const { data: me } = useMyRolesSuspense(selector());
  const qc = useQueryClient();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const canSelect = me.can_approve_tickets || me.can_apply_tickets;

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const clearSelection = () => setSelected(new Set());

  const { mutate: runBatch, isPending: batching } = useBatchTicketAction({
    mutation: {
      onSuccess: (result) => {
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        clearSelection();
        const desc = `${result.succeeded} ok · ${result.failed} com falha`;
        if (result.failed > 0) {
          const firstErr = result.results.find((r) => !r.ok && r.error)?.error;
          toast.warning(`Lote: ${desc}`, { description: firstErr ?? undefined });
        } else {
          toast.success(`Lote concluído: ${desc}`);
        }
      },
      onError: (err) =>
        toast.error("Falha na ação em lote", {
          description: err instanceof Error ? err.message : "Falha desconhecida",
        }),
    },
  });

  const ids = Array.from(selected);
  const doBatch = (action: BatchAction, reason?: string) =>
    runBatch({ data: { ticket_ids: ids, action, reason } });

  return (
    <div className="space-y-4">
      <FilterTabs current={filter} onChange={setFilter} />

      {canSelect && selected.size > 0 && (
        <BatchBar
          count={selected.size}
          busy={batching}
          canApprove={me.can_approve_tickets}
          canApply={me.can_apply_tickets}
          onClear={clearSelection}
          onAction={doBatch}
        />
      )}

      {tickets.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y">
              {tickets.map((t) => (
                <div
                  key={t.ticket_id}
                  className="flex items-start gap-3 p-4 hover:bg-muted/40 transition-colors"
                >
                  {canSelect && (
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-nuclea-primary"
                      checked={selected.has(t.ticket_id)}
                      onChange={() => toggle(t.ticket_id)}
                      aria-label={`Selecionar ticket ${t.title}`}
                    />
                  )}
                  <Link
                    to="/tickets/$id"
                    params={{ id: t.ticket_id }}
                    className="flex items-start gap-4 flex-1 min-w-0"
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
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function BatchBar({
  count,
  busy,
  canApprove,
  canApply,
  onClear,
  onAction,
}: {
  count: number;
  busy: boolean;
  canApprove: boolean;
  canApply: boolean;
  onClear: () => void;
  onAction: (action: BatchAction, reason?: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-3">
      <span className="text-sm font-medium">{count} selecionado(s)</span>
      <div className="flex-1" />
      {canApply && (
        <Button
          size="sm"
          disabled={busy}
          className="bg-emerald-700 hover:bg-emerald-800 text-white"
          onClick={() => onAction("approve_and_apply")}
        >
          <PlayCircle className="mr-2 h-4 w-4" />
          Aprovar e aplicar
        </Button>
      )}
      {canApprove && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onAction("approve")}
        >
          <CheckCircle2 className="mr-2 h-4 w-4" />
          Aprovar
        </Button>
      )}
      {canApply && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("apply")}>
          <PlayCircle className="mr-2 h-4 w-4" />
          Aplicar
        </Button>
      )}
      {canApprove && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            const reason = window.prompt("Motivo da rejeição em lote:");
            if (reason && reason.trim()) onAction("reject", reason.trim());
          }}
        >
          <XCircle className="mr-2 h-4 w-4" />
          Rejeitar
        </Button>
      )}
      <Button size="sm" variant="ghost" disabled={busy} onClick={onClear}>
        Limpar
      </Button>
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
  const isOpen = filter === "OPEN" || filter === "ALL";
  return (
    <SharedEmptyState
      icon={<Inbox className="h-10 w-10" />}
      title={isOpen ? "Inbox vazia — bom sinal!" : `Sem tickets ${filter.toLowerCase()}`}
      description={
        isOpen ? (
          <>
            Tickets de reconciliação são gerados <strong>automaticamente</strong> quando uma
            engenharia reversa detecta divergências entre o banco real e o catálogo. Rode uma
            extração para começar.
          </>
        ) : (
          <>Não há tickets no estado <strong>{filter}</strong> no momento.</>
        )
      }
      primaryAction={
        isOpen ? { label: "Rodar engenharia reversa", to: "/extractions" } : undefined
      }
    />
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
