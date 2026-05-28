import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListTermsSuspense,
  type TermStatus,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  BookOpen,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";

export const Route = createFileRoute("/_sidebar/glossary")({
  component: GlossaryPage,
});

function GlossaryPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<TermStatus | "">("");
  const [domain, setDomain] = useState("");

  return (
    <div className="space-y-6">
      <Header />
      <Filters
        q={q}
        setQ={setQ}
        status={status}
        setStatus={setStatus}
        domain={domain}
        setDomain={setDomain}
      />
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar termos
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
              <TermsTable
                q={q || undefined}
                status={status || undefined}
                domain={domain || undefined}
              />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Dicionário Corporativo</h1>
          <Badge variant="outline" className="font-mono">M6</Badge>
        </div>
        <p className="text-muted-foreground max-w-2xl">
          Glossário centralizado de conceitos de dados. Cada termo pode ser vinculado
          a múltiplos atributos em diferentes sistemas, com herança de descrição.
        </p>
      </div>
      <Button asChild>
        <Link to="/glossary/new">
          <Plus className="mr-2 h-4 w-4" />
          Novo termo
        </Link>
      </Button>
    </div>
  );
}

function Filters({
  q, setQ, status, setStatus, domain, setDomain,
}: {
  q: string;
  setQ: (v: string) => void;
  status: TermStatus | "";
  setStatus: (v: TermStatus | "") => void;
  domain: string;
  setDomain: (v: string) => void;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="grid md:grid-cols-3 gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Buscar termo ou definição..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select
            className="rounded-md border bg-background px-3 py-2 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value as TermStatus | "")}
          >
            <option value="">Todos os status</option>
            <option value="DRAFT">Rascunho</option>
            <option value="IN_REVIEW">Em revisão</option>
            <option value="APPROVED">Aprovado</option>
            <option value="DEPRECATED">Depreciado</option>
          </select>
          <Input
            placeholder="Filtrar por domínio..."
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function TermsTable({
  q, status, domain,
}: {
  q?: string;
  status?: TermStatus;
  domain?: string;
}) {
  const { data: terms } = useListTermsSuspense({ q, status, domain }, selector());

  if (!terms || terms.length === 0) {
    return (
      <EmptyState
        icon={<BookOpen className="h-10 w-10" />}
        title="Dicionário corporativo vazio"
        description={
          <>
            Termos são a fonte da verdade conceitual ("CPF do Cliente", "Limite Pré-aprovado")
            que se ligam a múltiplos atributos físicos em sistemas distintos. Aprovação flui em
            <strong> DRAFT → IN_REVIEW → APPROVED</strong>.
          </>
        }
        primaryAction={{ label: "Criar primeiro termo", to: "/glossary/new" }}
        secondaryAction={{ label: "Ver fluxo de aprovação", to: "/help" }}
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Termos catalogados ({terms.length})</CardTitle>
        <CardDescription>Ordenado por nome canônico</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Termo</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Domínio</th>
                <th className="py-2 pr-3 font-medium">Tipo conceitual</th>
                <th className="py-2 pr-3 font-medium">Owner</th>
                <th className="py-2 pr-3 font-medium text-right"># Vínculos</th>
              </tr>
            </thead>
            <tbody>
              {terms.map((t) => (
                <tr key={t.term_id} className="border-b hover:bg-muted/40">
                  <td className="py-2 pr-3">
                    <Link
                      to="/glossary/$id"
                      params={{ id: t.term_id }}
                      className="font-medium hover:text-nuclea-primary"
                    >
                      {t.canonical_name}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="py-2 pr-3">
                    {t.domain ? (
                      <Badge variant="secondary">{t.domain}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-xs">
                    {t.conceptual_type ? (
                      <Badge variant="outline">{t.conceptual_type}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-muted-foreground">{t.owner_person || "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{t.mappings_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: TermStatus }) {
  const map: Record<TermStatus, { label: string; cls: string }> = {
    DRAFT: {
      label: "Rascunho",
      cls: "bg-muted text-muted-foreground border-muted-foreground/20",
    },
    IN_REVIEW: {
      label: "Em revisão",
      cls: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-300",
    },
    APPROVED: {
      label: "Aprovado",
      cls: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
    },
    DEPRECATED: {
      label: "Depreciado",
      cls: "bg-destructive/10 text-destructive border-destructive/30",
    },
  };
  const { label, cls } = map[status];
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

function TableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
      </CardHeader>
      <CardContent className="space-y-2">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
