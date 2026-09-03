import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useGetTicketSuspense,
  useApproveTicket,
  useApproveAndApplyTicket,
  useRejectTicket,
  useApplyTicket,
  useReopenTicket,
  useMyRolesSuspense,
  useListSandboxesSuspense,
  type TicketStatus,
  type DiffEntity,
  type DecisionAction,
  type EntityDecision,
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
  const qc = useQueryClient();
  const { data: ticket } = useGetTicketSuspense(id, selector());
  const { data: me } = useMyRolesSuspense(selector());
  const { data: sandboxes } = useListSandboxesSuspense(selector());

  // Estado de decisões: keyed por "schema.technical_name.op", e dentro de cada
  // entity, um map field → action. Default é 'apply' (= comportamento atual).
  type EntityDecMap = Map<string, EntityDecision>;
  const decisionsKey = (e: DiffEntity) => `${e.schema_name}.${e.technical_name}.${e.op}`;
  const [decisions, setDecisions] = useState<EntityDecMap>(() => {
    const m = new Map<string, EntityDecision>();
    for (const e of ticket.diff?.entities ?? []) {
      m.set(decisionsKey(e), {
        schema_name: e.schema_name,
        technical_name: e.technical_name,
        op: e.op,
        action: "apply",
        field_decisions: (e.field_changes ?? []).map((fc) => ({
          field: String((fc as { field: string }).field),
          action: "apply" as DecisionAction,
        })),
      });
    }
    return m;
  });

  const setEntityAction = (e: DiffEntity, action: DecisionAction) => {
    setDecisions((prev) => {
      const next = new Map(prev);
      const cur = next.get(decisionsKey(e));
      if (cur) next.set(decisionsKey(e), { ...cur, action });
      return next;
    });
  };

  const setFieldAction = (e: DiffEntity, field: string, action: DecisionAction) => {
    setDecisions((prev) => {
      const next = new Map(prev);
      const cur = next.get(decisionsKey(e));
      if (!cur) return prev;
      next.set(decisionsKey(e), {
        ...cur,
        field_decisions: cur.field_decisions.map((fd) =>
          fd.field === field ? { ...fd, action } : fd,
        ),
      });
      return next;
    });
  };

  // Se alguma decisão é "reverse", precisamos de um sandbox alvo.
  // Default = primeira sandbox disponível (se houver).
  const [reverseSandboxId, setReverseSandboxId] = useState<string>(
    sandboxes[0]?.sandbox_id || "",
  );

  const hasReverse = Array.from(decisions.values()).some(
    (d) => d.action === "reverse" || d.field_decisions.some((fd) => fd.action === "reverse"),
  );

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
  const { mutate: approveApply, isPending: approveApplying } = useApproveAndApplyTicket({
    mutation: {
      onSuccess: (result) => {
        qc.invalidateQueries({ queryKey: ["getTicket", id] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        if (result.errors && result.errors.length > 0) {
          toast.warning("Aprovado, mas com avisos na aplicação", {
            description: result.errors.slice(0, 2).join("; "),
          });
        } else {
          toast.success("Aprovado e aplicado", {
            description: `${result.applied_entities} entidades · ${result.applied_attributes} atributos`,
          });
        }
      },
      onError: (err) => {
        toast.error("Falha ao aprovar e aplicar", {
          description: err instanceof Error ? err.message : "Falha desconhecida",
        });
      },
    },
  });
  const { mutate: reopen, isPending: reopening } = useReopenTicket({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getTicket", id] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success("Ticket reaberto — clique 'Aplicar' para tentar de novo");
      },
      onError: (err) => toast.error(String(err)),
    },
  });

  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);

  const canApprove = me.can_approve_tickets && ticket.status === "OPEN";
  // Quem pode aplicar (Architect/Admin) resolve OPEN numa ação só — evita o
  // ticket ficar preso em APPROVED sem nunca refletir no catálogo.
  const canApproveAndApply = me.can_apply_tickets && ticket.status === "OPEN";
  const canReject = me.can_approve_tickets && ["OPEN", "APPROVED"].includes(ticket.status);
  const canApply = me.can_apply_tickets && ticket.status === "APPROVED";
  const canReopen = me.can_apply_tickets && ticket.status === "APPLIED";

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
          {canApproveAndApply && (
            <Button
              onClick={() => approveApply({ ticketId: id })}
              disabled={approveApplying}
              className="bg-emerald-700 hover:bg-emerald-800 text-white"
              title="Aprova e materializa as mudanças no catálogo numa única ação"
            >
              <PlayCircle className="mr-2 h-4 w-4" />
              {approveApplying ? "Aplicando..." : "Aprovar e aplicar"}
            </Button>
          )}
          {canApply && (
            <Button
              onClick={() =>
                apply({
                  ticketId: id,
                  data: {
                    decisions: Array.from(decisions.values()),
                    reverse_sandbox_id: hasReverse ? reverseSandboxId : null,
                  },
                })
              }
              disabled={applying || (hasReverse && !reverseSandboxId)}
              title={hasReverse && !reverseSandboxId ? "Selecione uma sandbox abaixo para reverter" : undefined}
            >
              <PlayCircle className="mr-2 h-4 w-4" />
              {applying ? "Aplicando..." : "Aplicar com decisões"}
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
          {canReopen && (
            <Button
              variant="outline"
              onClick={() => reopen({ ticketId: id })}
              disabled={reopening}
              title="Volta o status para APPROVED para tentar aplicar de novo (útil se houve falha silenciosa)"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {reopening ? "Reabrindo..." : "Reabrir"}
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

      {hasReverse && canApply && (
        <Card className="border-nuclea-primary/30 bg-nuclea-primary/5">
          <CardContent className="pt-4 text-sm space-y-2">
            <div className="flex items-center gap-2 text-nuclea-primary font-medium">
              <PlayCircle className="h-4 w-4" />
              Reverso para a fonte
            </div>
            <p className="text-muted-foreground text-xs">
              Algumas decisões pedem que o catálogo propague mudanças para a base.
              Selecione a sandbox Lakebase onde o ALTER/CREATE TABLE será executado:
            </p>
            <select
              value={reverseSandboxId}
              onChange={(e) => setReverseSandboxId(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              <option value="">— selecione uma sandbox —</option>
              {sandboxes.map((sb) => (
                <option key={sb.sandbox_id} value={sb.sandbox_id}>
                  {sb.name} ({sb.instance_name} · {sb.database_name})
                </option>
              ))}
            </select>
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
              {applyResult.applied_entities} entidades, {applyResult.applied_attributes}{" "}
              atributos
              {applyResult.reversed_items ? <>, {applyResult.reversed_items} revertidos para a fonte</> : null}
              {applyResult.ignored_items ? <>, {applyResult.ignored_items} ignorados</> : null}.
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
            <div className="mb-3 rounded-md border bg-muted/30 p-3 text-xs space-y-1">
              <p className="font-medium text-foreground">Como ler o diff:</p>
              <p className="text-muted-foreground">
                <span className="text-destructive font-medium">vermelho</span> = como está no <strong>catálogo</strong> (Núclea Modeler)
                <span className="mx-2">·</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-medium">verde</span> = como está na <strong>fonte</strong> (base de dados real, ex: Lakebase)
              </p>
              <p className="text-muted-foreground">
                Cada linha tem 3 opções: <em>Aplicar</em> faz o catálogo seguir a fonte (verde).
                <em> Reverter</em> propaga a mudança do catálogo (vermelho) <strong>de volta</strong> pra fonte via DDL.
                <em> Ignorar</em> não muda nada.
              </p>
            </div>
            <DiffList
              entities={ticket.diff?.entities || []}
              decisions={decisions}
              onEntityAction={setEntityAction}
              onFieldAction={setFieldAction}
              editable={canApply}
            />
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

// Traduz um field do diff (cru do backend) para uma descrição em PT-BR.
// Inclui também uma frase explicando o que significa a mudança.
function humanizeField(field: string): { label: string; hint: string } {
  if (field.startsWith("attribute_add:")) {
    const col = field.split(":", 2)[1];
    return {
      label: `coluna "${col}" só na fonte`,
      hint: "Está na base de dados real, mas não no catálogo. Aplicar = adicionar ao catálogo.",
    };
  }
  if (field.startsWith("attribute_remove:")) {
    const col = field.split(":", 2)[1];
    return {
      label: `coluna "${col}" só no catálogo`,
      hint: "Está no catálogo, mas não na base de dados real. Aplicar = remover do catálogo; Reverter = criar na base.",
    };
  }
  if (field.startsWith("attribute:") && field.endsWith(".native_data_type")) {
    const col = field.slice("attribute:".length).split(".")[0];
    return {
      label: `tipo da coluna "${col}"`,
      hint: "O tipo no catálogo e na base diferem. Aplicar = catálogo segue a base; Reverter = base recebe ALTER TYPE.",
    };
  }
  if (field.startsWith("attribute:") && field.endsWith(".is_primary_key")) {
    const col = field.slice("attribute:".length).split(".")[0];
    return {
      label: `chave primária "${col}"`,
      hint: "A definição de PK no catálogo e na base diferem.",
    };
  }
  // Campos de entity (top-level)
  const map: Record<string, { label: string; hint: string }> = {
    row_count_approx: {
      label: "linhas (estimativa)",
      hint: "Estimativa do Postgres (pg_class.reltuples) — atualizada por ANALYZE/autovacuum, não é COUNT(*). -1 significa tabela nunca analisada.",
    },
    native_comment: { label: "comentário (DB)", hint: "Comment SQL declarado na base." },
    logical_name: { label: "nome lógico", hint: "Nome amigável da entidade no catálogo." },
    description_md: { label: "descrição", hint: "Documentação Markdown da entidade." },
    domain: { label: "domínio", hint: "Categoria de negócio (Cadastro, Comercial, etc.)." },
    entity_type: { label: "tipo de entidade", hint: "TABLE, VIEW, etc." },
  };
  if (map[field]) return map[field];
  return { label: field, hint: "" };
}

function humanizeValue(value: unknown, fieldHint?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  // row_count_approx = -1 quando o Postgres nunca rodou ANALYZE na tabela.
  if (fieldHint === "row_count_approx" && (value === -1 || value === "-1")) {
    return "sem stats";
  }
  // Mudança/adição de COLUNA vinda do import CSV/XLSX vem como PAYLOAD (objeto),
  // não escalar — antes o String(obj) virava "[object Object]" no ticket. Resume
  // os campos úteis do atributo (tipo · PK · NOT NULL · "descrição" · lógico).
  if (typeof value === "object") {
    const o = value as Record<string, unknown>;
    const parts: string[] = [];
    if (o.native_data_type) parts.push(String(o.native_data_type));
    if (o.is_primary_key === true) parts.push("PK");
    if (o.is_nullable === false) parts.push("NOT NULL");
    if (o.description_md) parts.push(`“${String(o.description_md)}”`);
    if (o.logical_name) parts.push(`(${String(o.logical_name)})`);
    return parts.length ? parts.join(" · ") : JSON.stringify(o);
  }
  return String(value);
}

type DiffListProps = {
  entities: DiffEntity[];
  decisions: Map<string, EntityDecision>;
  onEntityAction: (e: DiffEntity, a: DecisionAction) => void;
  onFieldAction: (e: DiffEntity, field: string, a: DecisionAction) => void;
  editable: boolean;
};

function DiffList({ entities, decisions, onEntityAction, onFieldAction, editable }: DiffListProps) {
  if (entities.length === 0) {
    return <p className="text-sm text-muted-foreground italic">Sem mudanças detalhadas.</p>;
  }
  return (
    <div className="divide-y rounded-md border">
      {entities.map((e, i) => {
        const key = `${e.schema_name}.${e.technical_name}.${e.op}`;
        const dec = decisions.get(key);
        return (
          <DiffRow
            key={i}
            entity={e}
            entityAction={dec?.action ?? "apply"}
            fieldActions={dec ? new Map(dec.field_decisions.map((fd) => [fd.field, fd.action])) : new Map()}
            onEntityAction={(a) => onEntityAction(e, a)}
            onFieldAction={(field, a) => onFieldAction(e, field, a)}
            editable={editable}
          />
        );
      })}
    </div>
  );
}

type DiffRowProps = {
  entity: DiffEntity;
  entityAction: DecisionAction;
  fieldActions: Map<string, DecisionAction>;
  onEntityAction: (a: DecisionAction) => void;
  onFieldAction: (field: string, a: DecisionAction) => void;
  editable: boolean;
};

function DecisionSelect({
  value,
  onChange,
  disabled,
  variant = "default",
}: {
  value: DecisionAction;
  onChange: (a: DecisionAction) => void;
  disabled: boolean;
  variant?: "default" | "compact";
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as DecisionAction)}
      disabled={disabled}
      className={`rounded-md border bg-background text-xs ${
        variant === "compact" ? "px-1.5 py-0.5" : "px-2 py-1"
      } ${disabled ? "opacity-60" : ""}`}
    >
      <option value="apply">Aplicar (segue a fonte)</option>
      <option value="ignore">Ignorar</option>
      <option value="reverse">Reverter (propaga p/ fonte)</option>
    </select>
  );
}

/** Bug D: descreve um diff de RELACIONAMENTO (schema "__relationship__") de forma
 * legível — quais tabelas e colunas estão sendo ligadas — a partir dos rótulos que
 * o backend grava no payload. Cai num texto neutro se o payload não tiver rótulos
 * (relacionamentos antigos, criados antes do enriquecimento). */
function relationshipSummary(entity: DiffEntity): {
  title: string;
  columns: string | null;
} {
  const p = (entity.payload || {}) as Record<string, unknown>;
  const src = (p.source_label as string) || "(tabela-pai)";
  const tgt = (p.target_label as string) || "(tabela-filha)";
  const relType = (p.rel_type as string) || "";
  const srcCols = (p.source_columns as string[]) || [];
  const tgtCols = (p.target_columns as string[]) || [];
  const title = `${src} → ${tgt}${relType ? `  (${relType})` : ""}`;
  const columns =
    srcCols.length || tgtCols.length
      ? `chaves: ${src}(${srcCols.join(", ") || "?"}) → ${tgt}(${tgtCols.join(", ") || "?"})`
      : null;
  return { title, columns };
}

function DiffRow({
  entity,
  entityAction,
  fieldActions,
  onEntityAction,
  onFieldAction,
  editable,
}: DiffRowProps) {
  const opConfig = {
    add: { icon: <Plus className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />, label: "adicionar" },
    remove: { icon: <Minus className="h-4 w-4 text-destructive" />, label: "remover" },
    change: { icon: <RefreshCw className="h-4 w-4 text-amber-600 dark:text-amber-400" />, label: "alterar" },
  }[entity.op];

  // Relacionamento (FK): schema sentinela "__relationship__" + technical_name = id
  // (ilegível). Renderizamos "pai → filho (colunas)" a partir do payload enriquecido.
  const isRel = entity.schema_name === "__relationship__";
  const relInfo = isRel ? relationshipSummary(entity) : null;

  const attrsCount = entity.attributes?.length ?? 0;
  // Para relacionamento, o field_changes é só o marcador "relationship_update" —
  // não é útil listar; o resumo legível acima já cobre. Suprimimos a lista genérica.
  const fcsCount = isRel ? 0 : (entity.field_changes?.length ?? 0);
  const isChange = entity.op === "change";

  return (
    <div className="p-3">
      <div className="flex items-start gap-3">
        <span className="mt-0.5">{opConfig.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-sm">
              {isRel ? (
                <>
                  <Badge variant="outline" className="mr-2 text-[10px] align-middle">
                    Relacionamento
                  </Badge>
                  <strong className="font-mono">{relInfo!.title}</strong>{" "}
                  <span className="text-muted-foreground">— {opConfig.label}</span>
                </>
              ) : (
                <>
                  <strong className="font-mono">
                    {entity.schema_name}.{entity.technical_name}
                  </strong>{" "}
                  <span className="text-muted-foreground">— {opConfig.label}</span>
                  {entity.entity_type && entity.entity_type !== "TABLE" && (
                    <Badge variant="outline" className="ml-2 text-xs">{entity.entity_type}</Badge>
                  )}
                </>
              )}
            </p>
            {/* Para add/remove de entity inteira, mostrar select aqui.
                Para change, o select da entity é só fallback — fields têm os próprios.
                Relacionamento é sempre wholesale (não tem field rows) → mostra o
                select da entity mesmo em op=change, senão ficaria sem decisão. */}
            {(!isChange || isRel) && (
              <DecisionSelect
                value={entityAction}
                onChange={onEntityAction}
                disabled={!editable}
              />
            )}
          </div>
          {isRel && relInfo!.columns && (
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              {relInfo!.columns}
            </p>
          )}
          {attrsCount > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              + {attrsCount} atributo{attrsCount !== 1 ? "s" : ""}
            </p>
          )}
          {fcsCount > 0 && entity.field_changes && (
            <ul className="text-xs text-muted-foreground mt-2 ml-2 space-y-1.5">
              {entity.field_changes.map((fc, i) => {
                const fieldStr = String((fc as { field: string }).field);
                const action = fieldActions.get(fieldStr) ?? "apply";
                const h = humanizeField(fieldStr);
                const before = (fc as { before: unknown }).before;
                const after = (fc as { after: unknown }).after;
                return (
                  <li key={i} className="flex items-start justify-between gap-3" title={h.hint}>
                    <div className="flex-1 min-w-0">
                      <div className="text-foreground font-medium">{h.label}</div>
                      <div className="text-[11px]">
                        <span className="text-destructive">catálogo: {humanizeValue(before, fieldStr)}</span>
                        <span className="mx-2 text-muted-foreground">·</span>
                        <span className="text-emerald-600 dark:text-emerald-400">
                          fonte: {humanizeValue(after, fieldStr)}
                        </span>
                      </div>
                      {h.hint && (
                        <div className="text-[11px] text-muted-foreground/80 italic mt-0.5">
                          {h.hint}
                        </div>
                      )}
                    </div>
                    <DecisionSelect
                      value={action}
                      onChange={(a) => onFieldAction(fieldStr, a)}
                      disabled={!editable}
                      variant="compact"
                    />
                  </li>
                );
              })}
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
