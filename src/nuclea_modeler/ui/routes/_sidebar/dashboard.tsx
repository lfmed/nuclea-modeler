import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Database,
  FileText,
  Inbox,
  Link2,
  Network,
  PlayCircle,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  useDashboardSummarySuspense,
  type DashboardRecentItem,
  type DashboardSummary,
} from "@/lib/api";
import selector from "@/lib/selector";

export const Route = createFileRoute("/_sidebar/dashboard")({
  component: DashboardPage,
});

function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Visão geral do catálogo de dados Núclea — sistemas, entidades,
          tickets em andamento e atividade recente.
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
                    Erro ao carregar métricas
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <button
                    onClick={resetErrorBoundary}
                    className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Tentar de novo
                  </button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DashboardSkeleton />}>
              <DashboardBody />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function DashboardBody() {
  const { data: s } = useDashboardSummarySuspense(selector());

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={<Database className="h-4 w-4" />}
          label="Sistemas"
          value={s.systems_total.toString()}
          hint={`${s.systems_active} ativos`}
        />
        <KpiCard
          icon={<FileText className="h-4 w-4" />}
          label="Entidades"
          value={s.entities_total.toString()}
          hint={`${s.attributes_total.toLocaleString()} atributos`}
        />
        <KpiCard
          icon={<Link2 className="h-4 w-4" />}
          label="Relacionamentos"
          value={s.relationships_total.toString()}
          hint={`${s.entities_shared} entities compartilhadas`}
        />
        <KpiCard
          icon={<ScanSearch className="h-4 w-4" />}
          label="Extrações (7d)"
          value={s.extractions_last_7d.toString()}
          hint="últimos 7 dias"
        />
      </div>

      {/* Tickets + Ambientes */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Inbox className="h-5 w-5" />
                Tickets de reconciliação
              </CardTitle>
              <Link
                to="/tickets"
                className="text-xs underline text-muted-foreground hover:text-foreground"
              >
                ver todos →
              </Link>
            </div>
            <CardDescription>
              Aprovações pendentes e mudanças aplicadas no catálogo
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <TicketRow
              label="Abertos"
              count={s.tickets.open}
              icon={<Inbox className="h-4 w-4 text-amber-600" />}
              tone="amber"
            />
            <TicketRow
              label="Aprovados"
              count={s.tickets.approved}
              icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" />}
              tone="emerald"
            />
            <TicketRow
              label="Aplicados"
              count={s.tickets.applied}
              icon={<PlayCircle className="h-4 w-4 text-nuclea-primary" />}
              tone="primary"
            />
            <TicketRow
              label="Rejeitados"
              count={s.tickets.rejected}
              icon={<XCircle className="h-4 w-4 text-destructive" />}
              tone="destructive"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                Sistemas por ambiente
              </CardTitle>
            </div>
            <CardDescription>
              Modelos podem coexistir em DEV / HINT / PRD
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <EnvironmentBars summary={s} />
          </CardContent>
        </Card>
      </div>

      {/* Atividade recente */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Atividade recente
          </CardTitle>
          <CardDescription>
            Últimos tickets e extrações
          </CardDescription>
        </CardHeader>
        <CardContent>
          {s.recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Sem atividade recente. Crie um sistema novo ou rode engenharia
              reversa pra começar.
            </p>
          ) : (
            <ul className="divide-y">
              {s.recent.map((r, i) => (
                <RecentRow key={`${r.kind}-${r.id}-${i}`} item={r} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-2 text-xs uppercase tracking-wider">
          <span className="text-nuclea-primary">{icon}</span>
          {label}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  );
}

function TicketRow({
  label,
  count,
  icon,
  tone,
}: {
  label: string;
  count: number;
  icon: React.ReactNode;
  tone: "amber" | "emerald" | "primary" | "destructive";
}) {
  const bg = {
    amber: "bg-amber-500/10",
    emerald: "bg-emerald-500/10",
    primary: "bg-nuclea-primary/10",
    destructive: "bg-destructive/10",
  }[tone];
  return (
    <div className={`flex items-center justify-between rounded-md border px-3 py-2 ${bg}`}>
      <div className="flex items-center gap-2 text-sm">
        {icon}
        <span>{label}</span>
      </div>
      <span className="text-xl font-bold">{count}</span>
    </div>
  );
}

function EnvironmentBars({ summary }: { summary: DashboardSummary }) {
  // Garante que DEV/HINT/PRD apareçam mesmo com count=0; "sem ambiente"
  // aparece se houver sistemas sem env preenchido.
  const known = new Map(
    summary.systems_by_env.map((e) => [e.environment ?? "__none__", e.count]),
  );
  const total = summary.systems_total || 1;
  const rows: { label: string; key: "DEV" | "HINT" | "PRD" | "__none__"; color: string }[] = [
    { label: "DEV", key: "DEV", color: "bg-blue-500" },
    { label: "HINT", key: "HINT", color: "bg-amber-500" },
    { label: "PRD", key: "PRD", color: "bg-emerald-500" },
    { label: "Sem ambiente", key: "__none__", color: "bg-muted-foreground/40" },
  ];

  return (
    <>
      {rows.map((r) => {
        const c = known.get(r.key) ?? 0;
        const pct = total > 0 ? (c / total) * 100 : 0;
        return (
          <div key={r.key}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-medium">{r.label}</span>
              <span className="text-muted-foreground">
                {c} {c === 1 ? "sistema" : "sistemas"}
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${r.color}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </>
  );
}

function RecentRow({ item }: { item: DashboardRecentItem }) {
  const ts = item.at ? new Date(item.at) : null;
  const ago = ts ? formatAgo(ts) : "—";
  const icon =
    item.kind === "ticket" ? (
      <Inbox className="h-3.5 w-3.5 text-amber-600" />
    ) : item.kind === "extraction" ? (
      <ScanSearch className="h-3.5 w-3.5 text-nuclea-primary" />
    ) : (
      <Network className="h-3.5 w-3.5 text-muted-foreground" />
    );
  const link =
    item.kind === "ticket"
      ? `/tickets/${encodeURIComponent(item.id)}`
      : item.kind === "extraction"
        ? `/extractions`
        : undefined;
  const body = (
    <div className="flex items-center gap-3 py-2">
      {icon}
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate">{item.label}</p>
        <p className="text-xs text-muted-foreground">
          {item.actor || "—"} · {ago}
        </p>
      </div>
      {item.status && (
        <Badge variant="outline" className="text-[10px] font-mono">
          {item.status}
        </Badge>
      )}
    </div>
  );
  if (link) {
    return (
      <li className="hover:bg-muted/30 -mx-3 px-3">
        <Link to={link}>{body}</Link>
      </li>
    );
  }
  return <li className="px-0">{body}</li>;
}

function formatAgo(d: Date): string {
  const sec = Math.max(1, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `há ${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `há ${min}min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `há ${hr}h`;
  const days = Math.floor(hr / 24);
  return `há ${days}d`;
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
      <Skeleton className="h-48" />
    </div>
  );
}
