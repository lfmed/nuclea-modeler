import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState, useEffect } from "react";
import { QueryErrorResetBoundary, useSuspenseQuery } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useMyRolesSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  AlertCircle,
  RefreshCw,
  ShieldOff,
  TrendingUp,
  Timer,
  CircleAlert,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/admin/metrics")({
  component: MetricsPage,
});

// ─── Types ─────────────────────────────────────────────────────────────────

interface LatencyBucket {
  count: number;
  p50: number | null;
  p95: number | null;
  max: number | null;
}

interface RouteRow {
  counts: Record<string, number>;
  latency_ms: LatencyBucket;
}

interface MetricsSnapshot {
  uptime_seconds: number;
  routes: Record<string, RouteRow>;
}

// ─── Data hook ─────────────────────────────────────────────────────────────

function useMetricsSnapshot() {
  return useSuspenseQuery({
    queryKey: ["metrics"],
    queryFn: async () => {
      const r = await fetch("/api/metrics", { credentials: "include" });
      if (!r.ok) {
        throw new Error(`metrics fetch failed: HTTP ${r.status}`);
      }
      return (await r.json()) as MetricsSnapshot;
    },
    // Refresh every 10s automatically. Cheap query, in-memory only.
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

// ─── Page ──────────────────────────────────────────────────────────────────

function MetricsPage() {
  return (
    <div className="space-y-6">
      <Header />
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ error, resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" /> Erro ao carregar métricas
                  </CardTitle>
                  <CardDescription>{String(error)}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>
                    <RefreshCw className="mr-2 h-4 w-4" /> Tentar de novo
                  </Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<MetricsSkeleton />}>
              <RoleGate>
                <MetricsContent />
              </RoleGate>
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
        <Activity className="h-7 w-7 text-nuclea-primary" />
        <h1 className="text-3xl font-bold tracking-tight">Métricas</h1>
        <Badge variant="outline" className="font-mono">Admin</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Contadores in-process por rota (status class + latência p50/p95/max).
        Refresh automático a cada 10s. Resetam a cada restart do app, por worker.
      </p>
    </div>
  );
}

function RoleGate({ children }: { children: React.ReactNode }) {
  const { data: roles } = useMyRolesSuspense(selector());
  const isAdmin = roles?.roles?.includes("ADMIN");
  if (!isAdmin) {
    return (
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <ShieldOff className="h-5 w-5" /> Acesso restrito
          </CardTitle>
          <CardDescription>
            Esta página requer o papel <strong>ADMIN</strong>. Solicite acesso ao responsável.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link to="/">Voltar ao início</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }
  return <>{children}</>;
}

function MetricsContent() {
  const { data: snap } = useMetricsSnapshot();

  const rows = Object.entries(snap.routes).map(([route, row]) => {
    const counts = row.counts || {};
    const total =
      (counts["2xx"] || 0) +
      (counts["3xx"] || 0) +
      (counts["4xx"] || 0) +
      (counts["5xx"] || 0);
    const errorRate = total === 0 ? 0 : (counts["5xx"] || 0) / total;
    return {
      route,
      total,
      counts,
      errorRate,
      latency: row.latency_ms,
    };
  });
  rows.sort((a, b) => b.total - a.total);

  const grandTotal = rows.reduce((s, r) => s + r.total, 0);
  const grandErrors = rows.reduce((s, r) => s + (r.counts["5xx"] || 0), 0);
  const slowest = rows
    .filter((r) => r.latency.p95 != null)
    .sort((a, b) => (b.latency.p95 || 0) - (a.latency.p95 || 0))[0];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Total de requests"
          value={grandTotal.toLocaleString("pt-BR")}
          hint={`uptime: ${formatUptime(snap.uptime_seconds)}`}
        />
        <SummaryCard
          icon={<CircleAlert className="h-4 w-4" />}
          label="Erros 5xx"
          value={grandErrors.toLocaleString("pt-BR")}
          hint={
            grandTotal > 0
              ? `${((grandErrors / grandTotal) * 100).toFixed(2)}% da volumetria`
              : "—"
          }
          tone={grandErrors > 0 ? "warning" : "default"}
        />
        <SummaryCard
          icon={<Timer className="h-4 w-4" />}
          label="Rota mais lenta (p95)"
          value={slowest ? `${slowest.latency.p95?.toFixed(0)} ms` : "—"}
          hint={slowest ? slowest.route : ""}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tráfego por rota</CardTitle>
          <CardDescription>
            Ordenado por volume. Latências em ms (ring buffer de 512 últimas).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Rota</th>
                  <th className="py-2 pr-3 font-medium text-right">2xx</th>
                  <th className="py-2 pr-3 font-medium text-right">3xx</th>
                  <th className="py-2 pr-3 font-medium text-right">4xx</th>
                  <th className="py-2 pr-3 font-medium text-right">5xx</th>
                  <th className="py-2 pr-3 font-medium text-right">p50</th>
                  <th className="py-2 pr-3 font-medium text-right">p95</th>
                  <th className="py-2 pr-3 font-medium text-right">max</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      Nenhum tráfego registrado ainda — gere algumas requests e atualize.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.route} className="border-b">
                      <td className="py-2 pr-3 font-mono text-xs">{r.route}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {r.counts["2xx"] || 0}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                        {r.counts["3xx"] || 0}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-orange-500">
                        {r.counts["4xx"] || 0}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums font-medium text-destructive">
                        {r.counts["5xx"] || 0}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {fmtLatency(r.latency.p50)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {fmtLatency(r.latency.p95)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                        {fmtLatency(r.latency.max)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Atualizado automaticamente a cada 10s · Snapshot é por worker (uvicorn workers=2).
      </p>
    </div>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "warning";
}) {
  return (
    <Card className={tone === "warning" ? "border-orange-500/50" : ""}>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider mb-2">
          {icon}
          {label}
        </div>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function MetricsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function fmtLatency(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`;
  return `${ms.toFixed(0)} ms`;
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}
