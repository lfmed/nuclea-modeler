import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListSystemsSuspense,
  useListVersionsSuspense,
  useMyRolesSuspense,
  usePublishVersion,
  type VersionListOut,
  type VersionStatus,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  CheckCircle2,
  FileClock,
  GitCompareArrows,
  History,
  RefreshCw,
  ShieldOff,
  Sparkles,
  XCircle,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/versions")({
  component: VersionsPage,
});

function VersionsPage() {
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
                    Erro ao carregar versões
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
            <Suspense fallback={<PageSkeleton />}>
              <VersionsBody />
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
        <h1 className="text-3xl font-bold tracking-tight">Versões dos Modelos</h1>
        <Badge variant="outline" className="font-mono">M8</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Histórico imutável de versões publicadas por sistema. Cada publicação congela
        um snapshot do modelo e permite comparações entre versões com diff lado a lado.
      </p>
    </div>
  );
}

function VersionsBody() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: me } = useMyRolesSuspense(selector());

  const [systemId, setSystemId] = useState<string>(systems[0]?.system_id ?? "");
  const [fromId, setFromId] = useState<string>("");
  const [toId, setToId] = useState<string>("");
  const [showPublish, setShowPublish] = useState(false);

  const canPublish = useMemo(
    () =>
      me.roles.some((r) => r === "DATA_ARCHITECT" || r === "ADMIN"),
    [me.roles],
  );

  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="pt-4 flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">
              Sistema
            </label>
            <select
              value={systemId}
              onChange={(e) => {
                setSystemId(e.target.value);
                setFromId("");
                setToId("");
              }}
              className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            >
              <option value="">— Todos os sistemas —</option>
              {systems.map((s) => (
                <option key={s.system_id} value={s.system_id}>
                  {s.system_name}
                </option>
              ))}
            </select>
          </div>

          {canPublish ? (
            <Button
              onClick={() => setShowPublish((v) => !v)}
              disabled={!systemId}
              className="bg-nuclea-primary hover:bg-nuclea-primary/90 text-white"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              Publicar nova versão
            </Button>
          ) : (
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <ShieldOff className="h-3.5 w-3.5" />
              Sem permissão para publicar
            </span>
          )}
        </CardContent>
      </Card>

      {showPublish && systemId && (
        <PublishForm
          systemId={systemId}
          onClose={() => setShowPublish(false)}
        />
      )}

      <VersionsTable
        systemId={systemId}
        fromId={fromId}
        toId={toId}
        onSelectFrom={setFromId}
        onSelectTo={setToId}
      />
    </div>
  );
}

function PublishForm({
  systemId,
  onClose,
}: {
  systemId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { mutate, isPending, error } = usePublishVersion({
    mutation: {
      onSuccess: (v) => {
        qc.invalidateQueries({ queryKey: ["listVersions"] });
        onClose();
        navigate({ to: "/versions/$id", params: { id: v.version_id } });
      },
    },
  });

  const [title, setTitle] = useState("");
  const [changelog, setChangelog] = useState("");
  const [makeActive, setMakeActive] = useState(true);

  return (
    <Card className="border-nuclea-primary/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-nuclea-primary" />
          Publicar nova versão
        </CardTitle>
        <CardDescription>
          Cria um snapshot imutável do estado atual do modelo para este sistema.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">
            Título <span className="text-destructive">*</span>
          </label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ex.: Inclusão da entidade Cliente_PF"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">
            Changelog (Markdown)
          </label>
          <textarea
            value={changelog}
            onChange={(e) => setChangelog(e.target.value)}
            rows={5}
            placeholder={"- Adicionada tabela X\n- Coluna Y agora é NOT NULL"}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={makeActive}
            onChange={(e) => setMakeActive(e.target.checked)}
          />
          Marcar como <strong>versão ativa</strong> (a anterior vira PUBLISHED)
        </label>

        {error && (
          <p className="text-sm text-destructive">
            Erro ao publicar: {(error as Error).message}
          </p>
        )}

        <div className="flex gap-2">
          <Button
            onClick={() =>
              mutate({
                data: {
                  system_id: systemId,
                  title,
                  changelog,
                  make_active: makeActive,
                },
              })
            }
            disabled={isPending || title.trim().length === 0}
          >
            {isPending ? "Publicando..." : "Publicar"}
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function VersionsTable({
  systemId,
  fromId,
  toId,
  onSelectFrom,
  onSelectTo,
}: {
  systemId: string;
  fromId: string;
  toId: string;
  onSelectFrom: (v: string) => void;
  onSelectTo: (v: string) => void;
}) {
  const { data: versions } = useListVersionsSuspense(
    systemId || undefined,
    selector(),
  );
  const navigate = useNavigate();

  const canCompare = fromId && toId && fromId !== toId;

  if (versions.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <FileClock className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">
            Nenhuma versão publicada{systemId ? " para este sistema" : ""} ainda.
            Use o botão acima para criar a primeira.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-3">
        <div>
          <CardTitle>Versões ({versions.length})</CardTitle>
          <CardDescription>
            Marque duas versões abaixo para comparar lado a lado
          </CardDescription>
        </div>
        <Button
          variant="outline"
          disabled={!canCompare}
          onClick={() => {
            if (canCompare) {
              navigate({
                to: "/versions/diff",
                search: { from: fromId, to: toId },
              });
            }
          }}
        >
          <GitCompareArrows className="mr-2 h-4 w-4" />
          Comparar versões
        </Button>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">De</th>
                <th className="py-2 pr-3 font-medium">Até</th>
                <th className="py-2 pr-3 font-medium">Versão</th>
                <th className="py-2 pr-3 font-medium">Título</th>
                <th className="py-2 pr-3 font-medium">Sistema</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Publicada</th>
                <th className="py-2 pr-3 font-medium">Por</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <VersionRow
                  key={v.version_id}
                  v={v}
                  fromId={fromId}
                  toId={toId}
                  onSelectFrom={onSelectFrom}
                  onSelectTo={onSelectTo}
                />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function VersionRow({
  v,
  fromId,
  toId,
  onSelectFrom,
  onSelectTo,
}: {
  v: VersionListOut;
  fromId: string;
  toId: string;
  onSelectFrom: (id: string) => void;
  onSelectTo: (id: string) => void;
}) {
  return (
    <tr className="border-b hover:bg-muted/40">
      <td className="py-2 pr-3">
        <input
          type="radio"
          name="from"
          checked={fromId === v.version_id}
          onChange={() => onSelectFrom(v.version_id)}
        />
      </td>
      <td className="py-2 pr-3">
        <input
          type="radio"
          name="to"
          checked={toId === v.version_id}
          onChange={() => onSelectTo(v.version_id)}
        />
      </td>
      <td className="py-2 pr-3 font-mono">
        <Link
          to="/versions/$id"
          params={{ id: v.version_id }}
          className="hover:text-nuclea-primary"
        >
          {v.version_number}
        </Link>
      </td>
      <td className="py-2 pr-3">{v.title || "—"}</td>
      <td className="py-2 pr-3 text-muted-foreground">
        {v.system_name || v.system_id}
      </td>
      <td className="py-2 pr-3">
        <StatusBadge status={v.status} />
      </td>
      <td className="py-2 pr-3 text-xs text-muted-foreground">
        {v.published_at
          ? new Date(v.published_at).toLocaleString("pt-BR")
          : "—"}
      </td>
      <td className="py-2 pr-3 text-xs">{v.published_by || v.created_by}</td>
    </tr>
  );
}

export function StatusBadge({ status }: { status: VersionStatus }) {
  const cfg = {
    DRAFT: {
      icon: <History className="h-3.5 w-3.5" />,
      color:
        "bg-muted text-muted-foreground border-muted-foreground/30",
    },
    PUBLISHED: {
      icon: <FileClock className="h-3.5 w-3.5" />,
      color:
        "bg-sky-500/10 text-sky-700 border-sky-500/30 dark:text-sky-300",
    },
    ACTIVE: {
      icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      color: "bg-nuclea-primary/10 text-nuclea-primary border-nuclea-primary/40",
    },
    DEPRECATED: {
      icon: <XCircle className="h-3.5 w-3.5" />,
      color:
        "bg-destructive/10 text-destructive border-destructive/30",
    },
  }[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${cfg.color}`}
    >
      {cfg.icon}
      {status}
    </span>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
