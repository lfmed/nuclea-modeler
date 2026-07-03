import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListSystemsSuspense,
  useListSchemasSuspense,
  useListDiagramsSuspense,
  useListEntitiesSuspense,
  useMyRolesSuspense,
  useArchiveSystem,
  useRestoreSystem,
  useArchivedSystems,
  useRequestSystemDeletion,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChevronRight,
  ChevronDown,
  Database,
  FolderTree,
  Network,
  Table2,
  AlertCircle,
  Archive,
  ArchiveRestore,
  Trash2,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/explorer")({
  component: ExplorerPage,
});

function ExplorerPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">Navegador</h1>
          <Badge variant="outline" className="font-mono">Sistema · Schema · Diagrama · Tabela</Badge>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Árvore de navegação pela estrutura de dados: expanda um sistema para ver seus
          schemas, e cada schema para ver seus diagramas e tabelas. Clique numa tabela
          para abrir seus atributos.
        </p>
      </div>
      <div className="rounded-md border p-2">
        <TreeBoundary>
          <SystemsLevel />
        </TreeBoundary>
      </div>
    </div>
  );
}

function TreeBoundary({ children }: { children: React.ReactNode }) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="flex items-center gap-2 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" />
              Erro ao carregar.
              <Button size="sm" variant="ghost" onClick={resetErrorBoundary}>
                Tentar novamente
              </Button>
            </div>
          )}
        >
          <Suspense fallback={<RowSkeleton />}>{children}</Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

function RowSkeleton() {
  return (
    <div className="space-y-2 p-2">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-5 w-40" />
    </div>
  );
}

function Caret({ open }: { open: boolean }) {
  return open ? (
    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
  ) : (
    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
  );
}

function SystemsLevel() {
  const { data: systems } = useListSystemsSuspense(selector());
  return (
    <>
      {systems.length === 0 ? (
        <p className="p-3 text-sm text-muted-foreground">Nenhum sistema cadastrado.</p>
      ) : (
        <ul>
          {systems.map((sys) => (
            <SystemNode key={sys.system_id} systemId={sys.system_id} name={sys.system_name} />
          ))}
        </ul>
      )}
      <ArchivedSystemsSection />
    </>
  );
}

function ArchivedSystemsSection() {
  const { data: me } = useMyRolesSuspense(selector());
  const canManage = me.can_apply_tickets || me.is_admin;
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data: archived = [] } = useArchivedSystems();
  const restore = useRestoreSystem({
    mutation: {
      onSuccess: () => {
        toast.success("Sistema restaurado.");
        qc.invalidateQueries({ queryKey: ["listSystems"] });
        qc.invalidateQueries({ queryKey: ["listArchivedSystems"] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        qc.invalidateQueries({ queryKey: ["listSchemas"] });
      },
      onError: (e) => toast.error("Falha ao restaurar", { description: e.message }),
    },
  });
  const reqDel = useRequestSystemDeletion({
    mutation: {
      onSuccess: () =>
        toast.success(
          "Exclusão solicitada — abra Tickets para aprovar. Só após aprovado o sistema é excluído definitivamente.",
        ),
      onError: (e) => toast.error("Falha ao solicitar exclusão", { description: e.message }),
    },
  });
  if (!canManage || archived.length === 0) return null;
  return (
    <div className="mt-3 border-t pt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted/50"
      >
        <Caret open={open} />
        <Archive className="h-3.5 w-3.5" />
        Sistemas arquivados ({archived.length})
      </button>
      {open && (
        <ul className="ml-6 border-l pl-2">
          {archived.map((sys) => (
            <li
              key={sys.system_id}
              className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm"
            >
              <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
                <Database className="h-4 w-4 shrink-0" />
                <span className="truncate">{sys.system_name}</span>
              </span>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7"
                  disabled={restore.isPending}
                  onClick={() => restore.mutate({ systemId: sys.system_id })}
                  title="Restaurar este sistema"
                >
                  <ArchiveRestore className="mr-1 h-3.5 w-3.5" />
                  Restaurar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-destructive"
                  disabled={reqDel.isPending}
                  title="Solicitar exclusão definitiva (precisa de aprovação via ticket)"
                  onClick={() => {
                    if (
                      confirm(
                        `Solicitar EXCLUSÃO DEFINITIVA de "${sys.system_name}"? Isso abre um ticket; o sistema só é apagado depois de APROVADO em Tickets.`,
                      )
                    )
                      reqDel.mutate({ systemId: sys.system_id });
                  }}
                >
                  <Trash2 className="mr-1 h-3.5 w-3.5" />
                  Excluir…
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SystemNode({ systemId, name }: { systemId: string; name: string }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data: me } = useMyRolesSuspense(selector());
  // Limpar/excluir são destrutivos → só para quem aplica tickets (Architect/Admin).
  const canManage = me.can_apply_tickets || me.is_admin;

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["listSystems"] });
    qc.invalidateQueries({ queryKey: ["listArchivedSystems"] });
    qc.invalidateQueries({ queryKey: ["listSchemas"] });
    qc.invalidateQueries({ queryKey: ["listEntities"] });
  };
  const archive = useArchiveSystem({
    mutation: {
      onSuccess: () => {
        toast.success(
          `"${name}" arquivado. Nada foi perdido — restaure em "Sistemas arquivados".`,
        );
        invalidateAll();
      },
      onError: (e) => toast.error("Falha ao arquivar", { description: e.message }),
    },
  });

  return (
    <li>
      <div className="flex items-center gap-1 rounded px-2 py-1.5 hover:bg-muted/50">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex flex-1 items-center gap-2 text-left text-sm"
        >
          <Caret open={open} />
          <Database className="h-4 w-4 shrink-0 text-nuclea-primary" />
          <span className="font-medium">{name}</span>
        </button>
        {canManage && (
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            disabled={archive.isPending}
            title="Arquivar o sistema (reversível — nada é apagado; restaurável depois)"
            onClick={() => {
              if (
                confirm(
                  `Arquivar o sistema "${name}"? Ele sai das listas e do navegador, mas NADA é apagado — você pode restaurar a qualquer momento em "Sistemas arquivados".`,
                )
              )
                archive.mutate({ systemId });
            }}
          >
            <Archive className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      {open && (
        <div className="ml-6 border-l pl-2">
          <TreeBoundary>
            <SchemasLevel systemId={systemId} />
          </TreeBoundary>
        </div>
      )}
    </li>
  );
}

function SchemasLevel({ systemId }: { systemId: string }) {
  const { data: schemas } = useListSchemasSuspense({ systemId }, selector());
  if (schemas.length === 0) {
    return <p className="px-2 py-1.5 text-xs text-muted-foreground">Sem schemas.</p>;
  }
  return (
    <ul>
      {schemas.map((sc) => (
        <SchemaNode
          key={sc.schema_id}
          systemId={systemId}
          schemaId={sc.schema_id}
          schemaName={sc.schema_name}
          entityCount={sc.entity_count}
          diagramCount={sc.diagram_count}
        />
      ))}
    </ul>
  );
}

function SchemaNode({
  systemId,
  schemaId,
  schemaName,
  entityCount,
  diagramCount,
}: {
  systemId: string;
  schemaId: string;
  schemaName: string;
  entityCount: number;
  diagramCount: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted/50"
      >
        <Caret open={open} />
        <FolderTree className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>{schemaName}</span>
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
          <span title="diagramas">{diagramCount}◫</span>
          <span title="tabelas">{entityCount}⊞</span>
        </span>
      </button>
      {open && (
        <div className="ml-6 border-l pl-2">
          <TreeBoundary>
            <DiagramsLevel schemaId={schemaId} />
          </TreeBoundary>
          <TreeBoundary>
            <TablesLevel systemId={systemId} schemaName={schemaName} />
          </TreeBoundary>
        </div>
      )}
    </li>
  );
}

function DiagramsLevel({ schemaId }: { schemaId: string }) {
  const { data: diagrams } = useListDiagramsSuspense({ schemaId }, selector());
  if (diagrams.length === 0) return null;
  return (
    <ul className="py-0.5">
      {diagrams.map((d) => (
        <li key={d.diagram_id}>
          <Link
            to="/diagram"
            className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50"
          >
            <span className="w-4" />
            <Network className="h-4 w-4 shrink-0 text-nuclea-primary" />
            <span>{d.diagram_name}</span>
            {d.is_default && <Badge variant="outline" className="text-[10px]">default</Badge>}
            <span className="ml-auto text-xs text-muted-foreground">{d.entity_count}⊞</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function TablesLevel({ systemId, schemaName }: { systemId: string; schemaName: string }) {
  const { data: entities } = useListEntitiesSuspense({ systemId }, selector());
  const tables = entities.filter((e) => e.schema_name === schemaName);
  if (tables.length === 0) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">Sem tabelas.</p>;
  }
  return (
    <ul className="py-0.5">
      {tables.map((e) => (
        <li key={e.entity_id}>
          <Link
            to="/entities/$id"
            params={{ id: e.entity_id }}
            className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50"
          >
            <span className="w-4" />
            <Table2 className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{e.technical_name}</span>
            {e.logical_name && (
              <span className="truncate text-xs text-muted-foreground">· {e.logical_name}</span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
