import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useGetTicketSuspense,
  useApproveTicket,
  useRejectTicket,
  useApplyTicket,
  useMyRolesSuspense,
  type TicketStatus,
  type DiffEntity,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  XCircle,
  PlayCircle,
  Inbox,
  Plus,
  Minus,
  RefreshCw,
  ShieldOff,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/tickets/$id")({
  component: TicketDetailPage,
});

function TicketDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/tickets">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Tickets
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
                    Erro ao carregar ticket
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <TicketDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function TicketDetail() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: ticket } = useGetTicketSuspense(id, selector());
  const { data: me } = useMyRolesSuspense(selector());

  const { mutate: approve, isPending: approving } = useApproveTicket({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getTicket", id] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
      },
    },
  });
  const { mutate: reject, isPending: rejecting } = useRejectTicket({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getTicket", id] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
      },
    },
  });
  const { mutate: apply, isPending: applying, data: applyResult } = useApplyTicket({
    mutation: {
      onSuccess: (result) => {
        qc.invalidateQueries({ queryKey: ["getTicket", id] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        toast.success("Ticket aplicado", {
          description: `${result.applied_entities} entidades · ${result.applied_attributes} atributos`,
        });
      },
      onError: (err) => {
        toast.error("Falha ao aplicar ticket", {
          description: err instanceof Error ? err.message : "Falha desconhecida",
        });
      },
    },
  });

  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);

  const canApprove = me.can_approve_tickets && ticket.status === "OPEN";
  const canReject = me.can_approve_tickets && ["OPEN", "APPROVED"].includes(ticket.status);
  const canApply = me.can_apply_tickets && ticket.status === "APPROVED";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <StatusBadge status={ticket.status} />
            <Badge variant="outline">{ticket.source_type}</Badge>
            <span className="text-sm text-muted-foreground">
              Sistema: <strong>{ticket.system_name || ticket.system_id}</strong>
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{ticket.title}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Aberto por <strong>{ticket.created_by}</strong> em{" "}
            {new Date(ticket.created_at).toLocaleString("pt-BR")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canApprove && (
            <Button
              onClick={() => approve({ ticketId: id })}
              disabled={approving}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              {approving ? "Aprovando..." : "Aprovar"}
            </Button>
          )}
          {canApply && (
            <Button
              onClick={() => apply({ ticketId: id })}
              disabled={applying}
            >
              <PlayCircle className="mr-2 h-4 w-4" />
              {applying ? "Aplicando..." : "Aplicar"}
            </Button>
          )}
          {canReject && (
            <Button
              variant="outline"
              onClick={() => setShowRejectInput(!showRejectInput)}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Rejeitar
            </Button>
          )}
          {!canApprove && !canApply && !canReject && (
            <div className="text-sm text-muted-foreground flex items-center gap-2">
              <ShieldOff className="h-4 w-4" />
              {ticket.status === "REJECTED" || ticket.status === "APPLIED"
                ? "Ticket finalizado"
                : "Sem permissão para agir"}
            </div>
          )}
        </div>
      </div>

      {showRejectInput && (
        <Card className="border-destructive/50">
          <CardContent className="pt-4">
            <label className="text-sm font-medium mb-2 block">Motivo da rejeição</label>
            <div className="flex gap-2">
              <Input
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Explique por que está rejeitando..."
              />
              <Button
                variant="destructive"
                onClick={() => reject({ ticketId: id, reason: rejectReason })}
                disabled={rejecting || rejectReason.length === 0}
              >
                Confirmar rejeição
              </Button>
              <Button variant="ghost" onClick={() => setShowRejectInput(false)}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {applyResult && applyResult.errors.length === 0 && (
        <Card className="border-emerald-500/50 bg-emerald-500/5">
          <CardContent className="pt-4 text-sm">
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400 mb-1">
              <CheckCircle2 className="h-4 w-4" />
              <strong>Aplicado com sucesso</strong>
            </div>
            <p>
              {applyResult.applied_entities} entidades e {applyResult.applied_attributes}{" "}
              atributos criados/atualizados no catálogo.
            </p>
          </CardContent>
        </Card>
      )}

      {applyResult && applyResult.errors.length > 0 && (
        <Card className="border-amber-500/50 bg-amber-500/5">
          <CardContent className="pt-4 text-sm">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400 mb-1">
              <AlertCircle className="h-4 w-4" />
              <strong>Aplicado com avisos</strong>
            </div>
            <p className="mb-2">
              {applyResult.applied_entities} entidades aplicadas, {applyResult.errors.length} avisos:
            </p>
            <ul className="list-disc pl-5 space-y-1 text-xs">
              {applyResult.errors.map((e, i) => (
                <li key={i} className="font-mono">{e}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Diff proposta</CardTitle>
            <CardDescription>
              Mudanças que serão aplicadas ao catálogo após aprovação
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3 mb-4 text-sm">
              <CounterChip
                icon={<Plus className="h-3.5 w-3.5" />}
                label="adições"
                count={ticket.additions_count}
                tone="positive"
              />
              <CounterChip
                icon={<RefreshCw className="h-3.5 w-3.5" />}
                label="alterações"
                count={ticket.changes_count}
                tone="warning"
              />
              <CounterChip
                icon={<Minus className="h-3.5 w-3.5" />}
                label="remoções"
                count={ticket.removals_count}
                tone="negative"
              />
            </div>
            <DiffList entities={ticket.diff?.entities || []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Linha do tempo</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <TimelineItem
              icon={<Inbox className="h-4 w-4" />}
              label="Aberto"
              by={ticket.created_by}
              at={ticket.created_at}
              active
            />
            <TimelineItem
              icon={<CheckCircle2 className="h-4 w-4" />}
              label="Aprovado"
              by={ticket.approved_by}
              at={ticket.approved_at}
              active={!!ticket.approved_at}
            />
            <TimelineItem
              icon={<PlayCircle className="h-4 w-4" />}
              label="Aplicado"
              by={ticket.applied_by}
              at={ticket.applied_at}
              active={!!ticket.applied_at}
            />
            {ticket.rejected_at && (
              <TimelineItem
                icon={<XCircle className="h-4 w-4" />}
                label="Rejeitado"
                by={ticket.rejected_by}
                at={ticket.rejected_at}
                active
                isError
                detail={ticket.rejection_reason}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {ticket.summary_md && (
        <Card>
          <CardHeader>
            <CardTitle>Resumo</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
              {ticket.summary_md}
            </pre>
          </CardContent>
        </Card>
      )}
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
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${config.color}`}>
      {config.icon}
      {status}
    </span>
  );
}

function CounterChip({
  icon,
  label,
  count,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  tone: "positive" | "negative" | "warning";
}) {
  const color =
    tone === "positive"
      ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-destructive/10 text-destructive border-destructive/30";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 ${color}`}>
      {icon}
      <strong>{count}</strong>
      <span>{label}</span>
    </span>
  );
}

function DiffList({ entities }: { entities: DiffEntity[] }) {
  if (entities.length === 0) {
    return <p className="text-sm text-muted-foreground italic">Sem mudanças detalhadas.</p>;
  }
  return (
    <div className="divide-y rounded-md border">
      {entities.map((e, i) => (
        <DiffRow key={i} entity={e} />
      ))}
    </div>
  );
}

function DiffRow({ entity }: { entity: DiffEntity }) {
  const opConfig = {
    add: { icon: <Plus className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />, label: "adicionar" },
    remove: { icon: <Minus className="h-4 w-4 text-destructive" />, label: "remover" },
    change: { icon: <RefreshCw className="h-4 w-4 text-amber-600 dark:text-amber-400" />, label: "alterar" },
  }[entity.op];

  const attrsCount = entity.attributes?.length ?? 0;
  const fcsCount = entity.field_changes?.length ?? 0;

  return (
    <div className="p-3">
      <div className="flex items-start gap-3">
        <span className="mt-0.5">{opConfig.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm">
            <strong className="font-mono">
              {entity.schema_name}.{entity.technical_name}
            </strong>{" "}
            <span className="text-muted-foreground">— {opConfig.label}</span>
            {entity.entity_type && entity.entity_type !== "TABLE" && (
              <Badge variant="outline" className="ml-2 text-xs">{entity.entity_type}</Badge>
            )}
          </p>
          {attrsCount > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              + {attrsCount} atributo{attrsCount !== 1 ? "s" : ""}
            </p>
          )}
          {fcsCount > 0 && entity.field_changes && (
            <ul className="text-xs text-muted-foreground mt-1 ml-2 space-y-0.5">
              {entity.field_changes.map((fc, i) => (
                <li key={i}>
                  <code>{String(fc.field)}</code>:{" "}
                  <span className="text-destructive">{String(fc.before || "—")}</span> →{" "}
                  <span className="text-emerald-600 dark:text-emerald-400">{String(fc.after || "—")}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function TimelineItem({
  icon,
  label,
  by,
  at,
  active,
  isError,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  by?: string | null;
  at?: string | null;
  active: boolean;
  isError?: boolean;
  detail?: string | null;
}) {
  return (
    <div className="flex gap-3">
      <div
        className={`mt-0.5 ${
          active
            ? isError
              ? "text-destructive"
              : "text-nuclea-primary"
            : "text-muted-foreground/40"
        }`}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${active ? "" : "text-muted-foreground"}`}>{label}</p>
        {active && (by || at) && (
          <p className="text-xs text-muted-foreground">
            {by && <>por {by}</>} {at && <>· {new Date(at).toLocaleString("pt-BR")}</>}
          </p>
        )}
        {detail && (
          <p className="text-xs text-muted-foreground mt-1 italic">"{detail}"</p>
        )}
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-12 w-2/3" />
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="lg:col-span-2 h-80" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}
