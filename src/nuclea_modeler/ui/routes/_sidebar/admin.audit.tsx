import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useAuditStatsSuspense,
  useGetAuditDetailSuspense,
  useListAuditSuspense,
  useMyRolesSuspense,
  type AuditEntry,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Activity,
  AlertCircle,
  RefreshCw,
  ShieldOff,
  Filter,
  X,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/admin/audit")({
  component: AuditPage,
});

function AuditPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Activity className="h-7 w-7 text-nuclea-primary" />
          <h1 className="text-3xl font-bold tracking-tight">Auditoria</h1>
          <Badge variant="outline" className="font-mono">Admin</Badge>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Histórico imutável de todas as operações mutáveis (POST/PUT/PATCH/DELETE) realizadas via API.
          Apenas usuários com papel <strong>ADMIN</strong> podem visualizar esta página.
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
                    Erro ao carregar auditoria
                  </CardTitle>
                  <CardDescription>
                    Verifique se você é ADMIN e se o backend está online.
                  </CardDescription>
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
            <Suspense fallback={<Skeleton className="h-80 w-full" />}>
              <AuditView />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function AuditView() {
  const { data: me } = useMyRolesSuspense(selector());
  if (!me.is_admin) {
    return (
      <Card>
        <CardContent className="pt-10 pb-10 text-center">
          <ShieldOff className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">
            Você não tem permissão ADMIN.
            <br />
            Seu email: <code>{me.user_email}</code>
            <br />
            Seus papéis: {me.roles.length > 0 ? me.roles.join(", ") : "nenhum"}
          </p>
        </CardContent>
      </Card>
    );
  }
  return <AdminContent />;
}

function AdminContent() {
  return (
    <div className="space-y-6">
      <Suspense fallback={<Skeleton className="h-32 w-full" />}>
        <StatsCards />
      </Suspense>
      <Suspense fallback={<Skeleton className="h-80 w-full" />}>
        <AuditTable />
      </Suspense>
    </div>
  );
}

function StatsCards() {
  const { data } = useAuditStatsSuspense(7, selector());
  const topActions = data.by_action.slice(0, 4);
  const topTypes = data.by_object_type.slice(0, 4);
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Total (últimos 7 dias)</CardDescription>
          <CardTitle className="text-4xl">{data.total}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            de {new Date(data.since).toLocaleDateString("pt-BR")} até{" "}
            {new Date(data.until).toLocaleDateString("pt-BR")}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Por ação</CardDescription>
        </CardHeader>
        <CardContent>
          {topActions.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">Sem dados.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {topActions.map((a) => (
                <li key={a.key} className="flex items-center justify-between">
                  <Badge variant="outline">{a.key}</Badge>
                  <span className="font-mono text-muted-foreground">{a.count}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Por tipo de objeto</CardDescription>
        </CardHeader>
        <CardContent>
          {topTypes.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">Sem dados.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {topTypes.map((t) => (
                <li key={t.key} className="flex items-center justify-between">
                  <Badge variant="outline">{t.key}</Badge>
                  <span className="font-mono text-muted-foreground">{t.count}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const ACTIONS = ["", "CREATE", "UPDATE", "DELETE"];

function AuditTable() {
  const [actorEmail, setActorEmail] = useState("");
  const [action, setAction] = useState("");
  const [objectType, setObjectType] = useState("");
  const [sinceDays, setSinceDays] = useState<number | "">(7);
  const [selected, setSelected] = useState<AuditEntry | null>(null);

  const since = useMemo(() => {
    if (sinceDays === "" || !sinceDays) return undefined;
    const d = new Date();
    d.setDate(d.getDate() - Number(sinceDays));
    return d.toISOString();
  }, [sinceDays]);

  const params = {
    actor_email: actorEmail || undefined,
    action: action || undefined,
    object_type: objectType || undefined,
    since,
    limit: 200,
  };

  const { data: rows } = useListAuditSuspense(params, selector());

  const reset = () => {
    setActorEmail("");
    setAction("");
    setObjectType("");
    setSinceDays(7);
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filtros
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <Input
              placeholder="Email do ator"
              value={actorEmail}
              onChange={(e) => setActorEmail(e.target.value)}
            />
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-nuclea-primary"
            >
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a || "todas ações"}
                </option>
              ))}
            </select>
            <Input
              placeholder="Tipo de objeto (ex: entities)"
              value={objectType}
              onChange={(e) => setObjectType(e.target.value)}
            />
            <select
              value={sinceDays}
              onChange={(e) =>
                setSinceDays(e.target.value === "" ? "" : Number(e.target.value))
              }
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-nuclea-primary"
            >
              <option value={1}>Últimas 24h</option>
              <option value={7}>Últimos 7 dias</option>
              <option value={30}>Últimos 30 dias</option>
              <option value="">Todo período</option>
            </select>
            <Button variant="outline" onClick={reset} className="gap-2">
              <X className="h-3.5 w-3.5" /> Limpar
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Eventos ({rows.length})</CardTitle>
          <CardDescription>
            Clique em uma linha para visualizar o payload completo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground italic text-center py-10">
              Nenhum evento de auditoria encontrado com os filtros atuais.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Quando</th>
                    <th className="py-2 pr-3 font-medium">Ator</th>
                    <th className="py-2 pr-3 font-medium">Ação</th>
                    <th className="py-2 pr-3 font-medium">Objeto</th>
                    <th className="py-2 pr-3 font-medium">ID</th>
                    <th className="py-2 pr-3 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.audit_id}
                      className="border-b hover:bg-muted/50 cursor-pointer focus-within:bg-muted/50"
                      onClick={() => setSelected(r)}
                    >
                      <td className="py-2 pr-3 font-mono text-xs">
                        {new Date(r.occurred_at).toLocaleString("pt-BR")}
                      </td>
                      <td className="py-2 pr-3">{r.actor_email}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline">{r.action}</Badge>
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">{r.object_type}</td>
                      <td className="py-2 pr-3 text-muted-foreground font-mono text-xs truncate max-w-[160px]">
                        {r.object_id || "—"}
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground font-mono text-xs">
                        {r.client_ip || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>Evento de auditoria</SheetTitle>
                <SheetDescription>
                  {selected.action} · {selected.object_type} ·{" "}
                  {new Date(selected.occurred_at).toLocaleString("pt-BR")}
                </SheetDescription>
              </SheetHeader>
              <Suspense
                fallback={<Skeleton className="h-40 w-full mt-4" />}
              >
                <AuditDetail auditId={selected.audit_id} />
              </Suspense>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

function AuditDetail({ auditId }: { auditId: string }) {
  const { data: detail } = useGetAuditDetailSuspense(auditId, selector());
  const pretty = (raw?: string | null) => {
    if (!raw) return null;
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  };
  return (
    <div className="mt-4 space-y-4 text-sm">
      <DetailRow label="Audit ID" value={detail.audit_id} mono />
      <DetailRow label="Ator" value={detail.actor_email} />
      <DetailRow label="Ação" value={detail.action} />
      <DetailRow label="Tipo de objeto" value={detail.object_type} />
      <DetailRow label="ID do objeto" value={detail.object_id || "—"} mono />
      <DetailRow label="Request ID" value={detail.request_id || "—"} mono />
      <DetailRow label="Cliente (IP)" value={detail.client_ip || "—"} mono />
      <DetailRow label="User-Agent" value={detail.user_agent || "—"} small />
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground mb-1">
          Antes (before_json)
        </div>
        <pre className="bg-muted rounded p-3 text-xs overflow-x-auto max-h-60">
          {pretty(detail.before_json) || "(vazio)"}
        </pre>
      </div>
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground mb-1">
          Depois (after_json)
        </div>
        <pre className="bg-muted rounded p-3 text-xs overflow-x-auto max-h-80">
          {pretty(detail.after_json) || "(vazio)"}
        </pre>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
  small,
}: {
  label: string;
  value: string;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase text-muted-foreground">{label}</span>
      <span
        className={
          (mono ? "font-mono text-xs " : "") +
          (small ? "text-xs " : "") +
          "break-all"
        }
      >
        {value}
      </span>
    </div>
  );
}
