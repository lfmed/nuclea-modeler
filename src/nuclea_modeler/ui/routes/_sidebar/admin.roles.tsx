import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListRolesSuspense,
  useGrantRole,
  useRevokeRole,
  useMyRolesSuspense,
  type RoleName,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Shield, ShieldOff, Trash2, UserPlus } from "lucide-react";

export const Route = createFileRoute("/_sidebar/admin/roles")({
  component: RolesPage,
});

const ROLES: RoleName[] = ["DATA_ARCHITECT", "DATA_STEWARD", "DATA_ENGINEER", "CDE", "ADMIN"];

function RolesPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Papéis (RBAC)</h1>
          <Badge variant="outline" className="font-mono">Admin</Badge>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Gerencia quem pode aprovar tickets, criar conexões e administrar o app.
          Apenas usuários com papel <strong>ADMIN</strong> podem ver e editar esta página.
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
                    Sem acesso ou erro
                  </CardTitle>
                  <CardDescription>
                    Você precisa ser ADMIN para gerenciar papéis. Verifique também se o backend está online.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-60 w-full" />}>
              <RolesAdmin />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function RolesAdmin() {
  const { data: me } = useMyRolesSuspense(selector());
  const { data: roles } = useListRolesSuspense(selector());
  const qc = useQueryClient();

  const { mutate: grant, isPending: granting } = useGrantRole({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRoles"] });
      },
    },
  });
  const { mutate: revoke } = useRevokeRole({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listRoles"] });
      },
    },
  });

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RoleName>("DATA_STEWARD");

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

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    grant({ data: { user_email: email, role_name: role } });
    setEmail("");
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Atribuir papel
          </CardTitle>
          <CardDescription>Conceda um papel a um email de usuário Databricks</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-wrap gap-3">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@nuclea.com.br"
              className="flex-1 min-w-[240px]"
              required
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as RoleName)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
            <Button type="submit" disabled={granting || !email}>
              {granting ? "Salvando..." : "Conceder"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Papéis ativos ({roles.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {roles.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">Nenhum papel atribuído ainda.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Email</th>
                    <th className="py-2 pr-3 font-medium">Papel</th>
                    <th className="py-2 pr-3 font-medium">Concedido em</th>
                    <th className="py-2 pr-3 font-medium">Por</th>
                    <th className="py-2 pr-3 font-medium w-12"></th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((r) => (
                    <tr key={r.user_role_id} className="border-b hover:bg-muted/40">
                      <td className="py-2 pr-3">{r.user_email}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline">{r.role_name}</Badge>
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">
                        {new Date(r.granted_at).toLocaleString("pt-BR")}
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">{r.granted_by}</td>
                      <td className="py-2 pr-3">
                        <button
                          onClick={() => {
                            if (confirm(`Revogar ${r.role_name} de ${r.user_email}?`))
                              revoke({ userRoleId: r.user_role_id });
                          }}
                          className="text-muted-foreground hover:text-destructive"
                          title="Revogar"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
