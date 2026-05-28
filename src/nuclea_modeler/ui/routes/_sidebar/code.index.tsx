import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListViewsSuspense,
  useListProceduresSuspense,
  useListTriggersSuspense,
  useListSequencesSuspense,
  useListSystemsSuspense,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  Code2,
  Eye,
  Zap,
  Hash,
  Plus,
  RefreshCw,
} from "lucide-react";

type Tab = "views" | "procedures" | "triggers" | "sequences";

export const Route = createFileRoute("/_sidebar/code/")({
  component: CodePage,
});

function CodePage() {
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
                    Erro ao carregar objetos de código
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
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <CodeBody />
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
        <h1 className="text-3xl font-bold tracking-tight">Objetos de Código</h1>
        <Badge variant="outline" className="font-mono">M3+</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Catálogo de Views (com definição SQL), Stored Procedures (parâmetros + corpo),
        Triggers (evento + timing + corpo) e Sequences. Editor SQL com syntax highlight.
      </p>
    </div>
  );
}

function CodeBody() {
  const { data: systems } = useListSystemsSuspense(selector());
  const [systemId, setSystemId] = useState<string>("");
  const [tab, setTab] = useState<Tab>("views");

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[240px]">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Sistema (opcional)
              </label>
              <select
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">— Todos os sistemas —</option>
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.system_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-1 border-b">
        <TabButton active={tab === "views"} onClick={() => setTab("views")} icon={<Eye className="h-4 w-4 mr-2" />}>
          Views
        </TabButton>
        <TabButton active={tab === "procedures"} onClick={() => setTab("procedures")} icon={<Code2 className="h-4 w-4 mr-2" />}>
          Procedures
        </TabButton>
        <TabButton active={tab === "triggers"} onClick={() => setTab("triggers")} icon={<Zap className="h-4 w-4 mr-2" />}>
          Triggers
        </TabButton>
        <TabButton active={tab === "sequences"} onClick={() => setTab("sequences")} icon={<Hash className="h-4 w-4 mr-2" />}>
          Sequences
        </TabButton>
      </div>

      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        {tab === "views" && <ViewsTab systemId={systemId || undefined} />}
        {tab === "procedures" && <ProceduresTab systemId={systemId || undefined} />}
        {tab === "triggers" && <TriggersTab systemId={systemId || undefined} />}
        {tab === "sequences" && <SequencesTab systemId={systemId || undefined} />}
      </Suspense>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-nuclea-primary text-nuclea-primary"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function ViewsTab({ systemId }: { systemId?: string }) {
  const { data: views } = useListViewsSuspense(systemId, selector());

  if (views.length === 0) {
    return (
      <EmptyState
        icon={<Eye className="h-10 w-10" />}
        title="Nenhuma view"
        description="Crie uma entidade com tipo VIEW em /entities/new e depois adicione a definição SQL aqui."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Views ({views.length})</CardTitle>
        <CardDescription>Visões catalogadas com definição SQL</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Nome</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium">Propósito</th>
                <th className="py-2 pr-3 font-medium text-right"># Base</th>
              </tr>
            </thead>
            <tbody>
              {views.map((v) => (
                <tr key={v.view_entity_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link
                      to="/code/views/$id"
                      params={{ id: v.view_entity_id }}
                      className="hover:text-nuclea-primary"
                    >
                      {v.entity_label}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{v.system_name || v.system_id}</td>
                  <td className="py-2 pr-3 text-muted-foreground">
                    {v.purpose ? (v.purpose.length > 80 ? v.purpose.slice(0, 80) + "…" : v.purpose) : "—"}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{v.base_entity_ids.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function ProceduresTab({ systemId }: { systemId?: string }) {
  const { data: procs } = useListProceduresSuspense(systemId, selector());

  if (procs.length === 0) {
    return (
      <EmptyState
        icon={<Code2 className="h-10 w-10" />}
        title="Nenhuma procedure"
        description="Adicione stored procedures com parâmetros e corpo."
        actionLabel="Nova procedure"
        actionTo="/code/procedures/new"
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Stored Procedures ({procs.length})</CardTitle>
          </div>
          <Button asChild size="sm">
            <Link to="/code/procedures/new">
              <Plus className="mr-2 h-4 w-4" />
              Nova
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Nome</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium">Risco</th>
              </tr>
            </thead>
            <tbody>
              {procs.map((p) => (
                <tr key={p.procedure_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link
                      to="/code/procedures/$id"
                      params={{ id: p.procedure_id }}
                      className="hover:text-nuclea-primary"
                    >
                      {p.schema_name}.{p.technical_name}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{p.system_name || p.system_id}</td>
                  <td className="py-2 pr-3">
                    <RiskBadge value={p.change_risk_level} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function TriggersTab({ systemId }: { systemId?: string }) {
  const { data: triggers } = useListTriggersSuspense(systemId, selector());

  if (triggers.length === 0) {
    return (
      <EmptyState
        icon={<Zap className="h-10 w-10" />}
        title="Nenhum trigger"
        description="Cadastre triggers associados às tabelas."
        actionLabel="Novo trigger"
        actionTo="/code/triggers/new"
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Triggers ({triggers.length})</CardTitle>
          <Button asChild size="sm">
            <Link to="/code/triggers/new">
              <Plus className="mr-2 h-4 w-4" />
              Novo
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Nome</th>
                <th className="py-2 pr-3 font-medium">Entidade</th>
                <th className="py-2 pr-3 font-medium">Evento</th>
                <th className="py-2 pr-3 font-medium">Timing</th>
                <th className="py-2 pr-3 font-medium">Risco</th>
              </tr>
            </thead>
            <tbody>
              {triggers.map((t) => (
                <tr key={t.trigger_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link to="/code/triggers/$id" params={{ id: t.trigger_id }} className="hover:text-nuclea-primary">
                      {t.schema_name}.{t.technical_name}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">{t.associated_entity_label || "—"}</td>
                  <td className="py-2 pr-3">
                    {t.event_type ? <Badge variant="outline">{t.event_type}</Badge> : "—"}
                  </td>
                  <td className="py-2 pr-3">
                    {t.timing ? <Badge variant="secondary">{t.timing}</Badge> : "—"}
                  </td>
                  <td className="py-2 pr-3"><RiskBadge value={t.change_risk_level} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function SequencesTab({ systemId }: { systemId?: string }) {
  const { data: seqs } = useListSequencesSuspense(systemId, selector());

  if (seqs.length === 0) {
    return (
      <EmptyState
        icon={<Hash className="h-10 w-10" />}
        title="Nenhuma sequence"
        description="Sequences (PG/Oracle/SQL Server/Snowflake)."
        actionLabel="Nova sequence"
        actionTo="/code/sequences/new"
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Sequences ({seqs.length})</CardTitle>
          <Button asChild size="sm">
            <Link to="/code/sequences/new">
              <Plus className="mr-2 h-4 w-4" />
              Nova
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Nome</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium text-right">Incremento</th>
                <th className="py-2 pr-3 font-medium text-right">Valor atual</th>
              </tr>
            </thead>
            <tbody>
              {seqs.map((q) => (
                <tr key={q.sequence_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link to="/code/sequences/$id" params={{ id: q.sequence_id }} className="hover:text-nuclea-primary">
                      {q.schema_name}.{q.technical_name}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{q.system_name || q.system_id}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{q.increment_by ?? "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{q.current_value ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function RiskBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const color =
    value === "CRITICAL"
      ? "bg-destructive/10 text-destructive border-destructive/30"
      : value === "MODERATE"
        ? "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300"
        : "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300";
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}>
      {value}
    </span>
  );
}

function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  actionTo,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  actionTo?: string;
}) {
  return (
    <Card className="border-dashed">
      <CardContent className="pt-10 pb-10 text-center">
        <div className="mx-auto text-muted-foreground/50 mb-3">{icon}</div>
        <h3 className="font-semibold mb-1">{title}</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">{description}</p>
        {actionLabel && actionTo && (
          <Button asChild>
            <Link to={actionTo}>
              <Plus className="mr-2 h-4 w-4" />
              {actionLabel}
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
