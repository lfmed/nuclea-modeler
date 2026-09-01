import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useDeprecateVersion,
  useGetVersionSuspense,
  useListVersionsSuspense,
  useMyRolesSuspense,
  useRestoreVersion,
  useVersionDiffSuspense,
  type DiffEntry,
  type VersionDiff,
  type VersionOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  ArrowLeft,
  ClipboardCopy,
  Download,
  History,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldOff,
  Trash2,
} from "lucide-react";

import { StatusBadge } from "./versions.index";

export const Route = createFileRoute("/_sidebar/versions/$id")({
  component: VersionDetailPage,
});

function VersionDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/versions">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Versões
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
                    Erro ao carregar versão
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<DetailSkeleton />}>
              <VersionDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

type Tab = "metadata" | "snapshot" | "diff" | "diff_current";

function VersionDetail() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: version } = useGetVersionSuspense(id, selector());
  const { data: me } = useMyRolesSuspense(selector());

  const canManage = useMemo(
    () => me.roles.some((r) => r === "DATA_ARCHITECT" || r === "ADMIN"),
    [me.roles],
  );

  const { mutate: restore, isPending: restoring } = useRestoreVersion({
    mutation: {
      onSuccess: (v) => {
        qc.invalidateQueries({ queryKey: ["listVersions"] });
        navigate({ to: "/versions/$id", params: { id: v.version_id } });
      },
    },
  });

  const { mutate: deprecate, isPending: deprecating } = useDeprecateVersion({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getVersion", id] });
        qc.invalidateQueries({ queryKey: ["listVersions"] });
      },
    },
  });

  const [tab, setTab] = useState<Tab>("metadata");

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <StatusBadge status={version.status} />
            <Badge variant="outline" className="font-mono">
              {version.version_number}
            </Badge>
            <span className="text-sm text-muted-foreground">
              Sistema: <strong>{version.system_name || version.system_id}</strong>
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            {version.title || "(sem título)"}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {version.published_at ? (
              <>
                Publicada por <strong>{version.published_by}</strong> em{" "}
                {new Date(version.published_at).toLocaleString("pt-BR")}
              </>
            ) : (
              <>
                Rascunho criado por <strong>{version.created_by}</strong> em{" "}
                {new Date(version.created_at).toLocaleString("pt-BR")}
              </>
            )}
            {version.based_on_version && (
              <>
                {" "}· baseada em <code>{version.based_on_version}</code>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage ? (
            <>
              <Button
                variant="outline"
                onClick={() => restore({ versionId: version.version_id })}
                disabled={restoring}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                {restoring ? "Restaurando..." : "Restaurar como rascunho"}
              </Button>
              {version.status !== "ACTIVE" && version.status !== "DEPRECATED" && (
                <Button
                  variant="ghost"
                  onClick={() => deprecate({ versionId: version.version_id })}
                  disabled={deprecating}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {deprecating ? "Depreciando..." : "Depreciar"}
                </Button>
              )}
            </>
          ) : (
            <span className="text-xs text-muted-foreground inline-flex items-center gap-1.5">
              <ShieldOff className="h-3.5 w-3.5" />
              Sem permissão para gerenciar
            </span>
          )}
        </div>
      </div>

      <div className="flex gap-1 border-b">
        <TabButton active={tab === "metadata"} onClick={() => setTab("metadata")}>
          Metadados
        </TabButton>
        <TabButton active={tab === "snapshot"} onClick={() => setTab("snapshot")}>
          Snapshot
        </TabButton>
        <TabButton active={tab === "diff"} onClick={() => setTab("diff")}>
          Diff vs. anterior
        </TabButton>
        <TabButton active={tab === "diff_current"} onClick={() => setTab("diff_current")}>
          Diff vs. atual
        </TabButton>
      </div>

      {tab === "metadata" && <MetadataTab version={version} />}
      {tab === "snapshot" && <SnapshotTab version={version} />}
      {tab === "diff" && (
        <Suspense fallback={<Skeleton className="h-40 w-full" />}>
          <DiffVsPreviousTab version={version} />
        </Suspense>
      )}
      {tab === "diff_current" && (
        <Suspense fallback={<Skeleton className="h-40 w-full" />}>
          <DiffVsCurrentTab version={version} />
        </Suspense>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-nuclea-primary text-nuclea-primary"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function MetadataTab({ version }: { version: VersionOut }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Changelog</CardTitle>
        <CardDescription>Notas Markdown registradas na publicação</CardDescription>
      </CardHeader>
      <CardContent>
        {version.changelog && version.changelog.trim().length > 0 ? (
          <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
            {version.changelog}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground italic">
            Nenhum changelog registrado.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SnapshotTab({ version }: { version: VersionOut }) {
  const text = useMemo(
    () => JSON.stringify(version.snapshot_json, null, 2),
    [version.snapshot_json],
  );
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available */
    }
  };

  // Export do snapshot como arquivo .json (round 5, pt 18) — para arquivar a versão
  // ou alimentar ferramentas externas. Usa o snapshot_json já carregado (sem backend).
  const download = () => {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nuclea-snapshot-${version.version_number || version.version_id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base">Snapshot imutável</CardTitle>
          <CardDescription>
            JSON congelado no momento da publicação
          </CardDescription>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={copy}>
            <ClipboardCopy className="mr-2 h-3.5 w-3.5" />
            {copied ? "Copiado!" : "Copiar"}
          </Button>
          <Button variant="outline" size="sm" onClick={download}>
            <Download className="mr-2 h-3.5 w-3.5" />
            Baixar JSON
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <pre className="text-xs font-mono p-3 rounded-md bg-muted/50 max-h-[600px] overflow-auto whitespace-pre">
          {text}
        </pre>
      </CardContent>
    </Card>
  );
}

function DiffVsPreviousTab({ version }: { version: VersionOut }) {
  const { data: versions } = useListVersionsSuspense(
    version.system_id,
    selector(),
  );

  // Find the version immediately preceding this one for the same system,
  // ordered by published_at (or created_at). Excludes itself.
  const previous = useMemo(() => {
    const others = versions
      .filter((v) => v.version_id !== version.version_id)
      .sort((a, b) => {
        const ka = a.published_at || a.created_at;
        const kb = b.published_at || b.created_at;
        return new Date(kb).getTime() - new Date(ka).getTime();
      });
    // First "older than current" (current was created_at)
    const cur = new Date(version.published_at || version.created_at).getTime();
    return others.find(
      (v) =>
        new Date(v.published_at || v.created_at).getTime() < cur,
    );
  }, [versions, version]);

  if (!previous) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-8 pb-8 text-center text-sm text-muted-foreground">
          <History className="mx-auto mb-3 h-8 w-8 text-muted-foreground/40" />
          Não há versão anterior para comparar.
        </CardContent>
      </Card>
    );
  }

  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <DiffPanel fromId={previous.version_id} toId={version.version_id} />
    </Suspense>
  );
}

/**
 * Diff da versão contra o MODELO ATUAL (ao vivo) — round 5, pt 18. Usa o mesmo
 * endpoint de diff com `to="current"` (o backend monta o snapshot atual na hora).
 * Deixa ver "o que mudou desde esta versão" sem publicar uma versão nova.
 */
function DiffVsCurrentTab({ version }: { version: VersionOut }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Comparando o snapshot desta versão com o <strong>estado atual do modelo</strong>{" "}
        (não publicado). Útil para revisar o que mudou antes de publicar uma nova versão.
      </p>
      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <DiffPanel fromId={version.version_id} toId="current" />
      </Suspense>
    </div>
  );
}

function DiffPanel({ fromId, toId }: { fromId: string; toId: string }) {
  const { data: diff } = useVersionDiffSuspense({ from: fromId, to: toId }, selector());
  return <DiffSections diff={diff} />;
}

export function DiffSections({ diff }: { diff: VersionDiff }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-sm">
        <CounterChip
          icon={<Plus className="h-3.5 w-3.5" />}
          label="adições"
          count={diff.totals.additions ?? diff.additions.length}
          tone="positive"
        />
        <CounterChip
          icon={<RefreshCw className="h-3.5 w-3.5" />}
          label="alterações"
          count={diff.totals.changes ?? diff.changes.length}
          tone="warning"
        />
        <CounterChip
          icon={<Minus className="h-3.5 w-3.5" />}
          label="remoções"
          count={diff.totals.removals ?? diff.removals.length}
          tone="negative"
        />
      </div>

      <DiffSection
        title="Adições"
        tone="positive"
        icon={<Plus className="h-4 w-4" />}
        entries={diff.additions}
        emptyText="Nenhuma adição."
      />
      <DiffSection
        title="Alterações"
        tone="warning"
        icon={<RefreshCw className="h-4 w-4" />}
        entries={diff.changes}
        emptyText="Nenhuma alteração de campo."
      />
      <DiffSection
        title="Remoções"
        tone="negative"
        icon={<Minus className="h-4 w-4" />}
        entries={diff.removals}
        emptyText="Nenhuma remoção."
      />
    </div>
  );
}

export function CounterChip({
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
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 ${color}`}
    >
      {icon}
      <strong>{count}</strong>
      <span>{label}</span>
    </span>
  );
}

export function DiffSection({
  title,
  tone,
  icon,
  entries,
  emptyText,
}: {
  title: string;
  tone: "positive" | "negative" | "warning";
  icon: React.ReactNode;
  entries: DiffEntry[];
  emptyText: string;
}) {
  const headerColor =
    tone === "positive"
      ? "text-emerald-700 dark:text-emerald-400"
      : tone === "warning"
        ? "text-amber-700 dark:text-amber-400"
        : "text-destructive";
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className={`text-base flex items-center gap-2 ${headerColor}`}>
          {icon}
          {title} ({entries.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">{emptyText}</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {entries.map((e, i) => (
              <li key={i} className="p-3 text-sm">
                <DiffEntryRow entry={e} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function DiffEntryRow({ entry }: { entry: DiffEntry }) {
  const isAdd = entry.type.endsWith("_added");
  const isRemove = entry.type.endsWith("_removed");
  const isChange = entry.type.endsWith("_changed");

  const label = entry.type
    .replace("entity_", "entidade ")
    .replace("attribute_", "atributo ")
    .replace("_added", "adicionada/o")
    .replace("_removed", "removida/o")
    .replace("_changed", "alterada/o");

  const tone = isAdd
    ? "text-emerald-700 dark:text-emerald-400"
    : isRemove
      ? "text-destructive"
      : "text-amber-700 dark:text-amber-400";

  return (
    <div>
      <p className="text-xs">
        <span className={`font-medium ${tone}`}>{label}</span>
        {" — "}
        <code className="font-mono">{entry.entity_key}</code>
        {entry.attribute_key && (
          <>
            {" · "}
            <code className="font-mono">{entry.attribute_key}</code>
          </>
        )}
        {entry.field && (
          <>
            {" · campo "}
            <code className="font-mono">{entry.field}</code>
          </>
        )}
      </p>
      {isChange && (
        <p className="text-xs text-muted-foreground mt-1 ml-1">
          <span className="line-through text-destructive">
            {formatVal(entry.before)}
          </span>
          {" → "}
          <span className="text-emerald-700 dark:text-emerald-400">
            {formatVal(entry.after)}
          </span>
        </p>
      )}
      {(isAdd || isRemove) && Boolean(entry.before ?? entry.after) && (
        <pre className="text-[11px] font-mono text-muted-foreground bg-muted/40 rounded p-2 mt-1 overflow-x-auto">
          {JSON.stringify(isAdd ? entry.after : entry.before, null, 2)}
        </pre>
      )}
    </div>
  );
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-16 w-2/3" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-60 w-full" />
    </div>
  );
}
