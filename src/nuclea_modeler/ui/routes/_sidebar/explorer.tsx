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
  useSetSystemTechnology,
  type SystemListOut,
} from "@/lib/api";
import { TECHNOLOGY_OPTIONS, technologyOptionLabel } from "@/lib/dialects";
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
  CheckSquare,
  X,
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

/**
 * Heurística do atalho "Selecionar sistemas de teste" (rodada 9, item 6): o cliente
 * pediu exclusão em lote dos sistemas carregados durante testes/validações. Pega os
 * descartáveis do smoke test (`SMOKE-<ts>`), prefixo `tmp`, e nomes com a PALAVRA
 * teste/test (borda de palavra: "Contestação" não casa). É só um atalho de seleção —
 * o usuário revisa a lista e confirma antes de qualquer ação.
 */
const TEST_SYSTEM_RE = /^(smoke|tmp)[-_\s]|\b(test|testes?)\b/i;

/** Lista de nomes para o confirm(), truncada para não gerar um diálogo gigante. */
function namesForConfirm(items: SystemListOut[], max = 12): string {
  const shown = items.slice(0, max).map((s) => `• ${s.system_name}`);
  if (items.length > max) shown.push(`… e mais ${items.length - max}`);
  return shown.join("\n");
}

/**
 * Executa `fn` para cada sistema EM SEQUÊNCIA (não em paralelo): o backend tem rate
 * limit e cada ação é um round-trip no warehouse — disparar dezenas de uma vez
 * gerava 429/timeout. Uma falha não interrompe as demais; devolve quem falhou.
 */
async function runSequential(
  items: SystemListOut[],
  fn: (s: SystemListOut) => Promise<unknown>,
): Promise<{ ok: number; failed: string[] }> {
  let ok = 0;
  const failed: string[] = [];
  for (const it of items) {
    try {
      await fn(it);
      ok++;
    } catch {
      failed.push(it.system_name);
    }
  }
  return { ok, failed };
}

function reportBulk(action: string, r: { ok: number; failed: string[] }) {
  if (r.failed.length === 0) toast.success(`${r.ok} sistema(s) ${action}.`);
  else
    toast.error(`${r.ok} ${action}, ${r.failed.length} com falha`, {
      description: r.failed.join(", "),
    });
}

/** Barra de ações em lote (seleção por checkbox) — compartilhada por ativos e arquivados. */
function BulkBar({
  count,
  total,
  busy,
  onSelectAll,
  onSelectTests,
  onClear,
  onCancel,
  children,
}: {
  count: number;
  total: number;
  busy: boolean;
  onSelectAll: () => void;
  onSelectTests: () => void;
  onClear: () => void;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-2 py-1.5 text-xs">
      <span className="font-medium">
        {count} de {total} selecionado(s)
      </span>
      <Button size="sm" variant="ghost" className="h-7" onClick={onSelectAll} disabled={busy}>
        Todos
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-7"
        onClick={onSelectTests}
        disabled={busy}
        title="Seleciona SMOKE-*, tmp-* e nomes com a palavra teste/test"
      >
        Sistemas de teste
      </Button>
      <Button size="sm" variant="ghost" className="h-7" onClick={onClear} disabled={busy || count === 0}>
        Limpar
      </Button>
      <div className="ml-auto flex items-center gap-1">
        {children}
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onCancel} disabled={busy} title="Sair da seleção">
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function useSelection() {
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const stop = () => {
    setSelecting(false);
    setSelected(new Set());
  };
  return { selecting, setSelecting, selected, setSelected, toggle, stop };
}

function SystemsLevel() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: me } = useMyRolesSuspense(selector());
  // Arquivar é restrito a quem aplica tickets (Architect/Admin) — igual ao botão unitário.
  const canManage = me.can_apply_tickets || me.is_admin;
  const qc = useQueryClient();
  const sel = useSelection();
  const [busy, setBusy] = useState(false);
  const archive = useArchiveSystem();

  // Só conta o que ainda está na lista (um sistema arquivado por outra aba some daqui).
  const chosen = systems.filter((s) => sel.selected.has(s.system_id));

  const archiveSelected = async () => {
    if (chosen.length === 0) return;
    if (
      !confirm(
        `Arquivar ${chosen.length} sistema(s)? Nada é apagado — dá para restaurar em "Sistemas arquivados".\n\n${namesForConfirm(chosen)}`,
      )
    )
      return;
    setBusy(true);
    try {
      const r = await runSequential(chosen, (s) => archive.mutateAsync({ systemId: s.system_id }));
      reportBulk("arquivado(s)", r);
      sel.stop();
    } finally {
      setBusy(false);
      qc.invalidateQueries({ queryKey: ["listSystems"] });
      qc.invalidateQueries({ queryKey: ["listArchivedSystems"] });
      qc.invalidateQueries({ queryKey: ["listSchemas"] });
      qc.invalidateQueries({ queryKey: ["listEntities"] });
    }
  };

  return (
    <>
      {canManage && systems.length > 0 && (
        sel.selecting ? (
          <BulkBar
            count={chosen.length}
            total={systems.length}
            busy={busy}
            onSelectAll={() => sel.setSelected(new Set(systems.map((s) => s.system_id)))}
            onSelectTests={() =>
              sel.setSelected(
                new Set(systems.filter((s) => TEST_SYSTEM_RE.test(s.system_name)).map((s) => s.system_id)),
              )
            }
            onClear={() => sel.setSelected(new Set())}
            onCancel={sel.stop}
          >
            <Button size="sm" variant="outline" className="h-7" disabled={busy || chosen.length === 0} onClick={archiveSelected}>
              <Archive className="mr-1 h-3.5 w-3.5" />
              {busy ? "Arquivando…" : `Arquivar selecionados (${chosen.length})`}
            </Button>
          </BulkBar>
        ) : (
          <div className="mb-1 flex justify-end">
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => sel.setSelecting(true)}
              title="Selecionar vários sistemas para arquivar de uma vez"
            >
              <CheckSquare className="mr-1 h-3.5 w-3.5" />
              Selecionar vários
            </Button>
          </div>
        )
      )}
      {systems.length === 0 ? (
        <p className="p-3 text-sm text-muted-foreground">Nenhum sistema cadastrado.</p>
      ) : (
        <ul>
          {systems.map((sys) => (
            <SystemNode
              key={sys.system_id}
              systemId={sys.system_id}
              name={sys.system_name}
              technology={sys.technology}
              selecting={sel.selecting}
              checked={sel.selected.has(sys.system_id)}
              onToggle={() => sel.toggle(sys.system_id)}
            />
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
  const sel = useSelection();
  const [busy, setBusy] = useState(false);
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["listSystems"] });
    qc.invalidateQueries({ queryKey: ["listArchivedSystems"] });
    qc.invalidateQueries({ queryKey: ["listEntities"] });
    qc.invalidateQueries({ queryKey: ["listSchemas"] });
  };
  const restore = useRestoreSystem({
    mutation: {
      onSuccess: () => {
        toast.success("Sistema restaurado.");
        invalidate();
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
  // Mutações "cruas" para o lote: sem os toasts unitários acima (o lote dá um toast só).
  const restoreRaw = useRestoreSystem();
  const reqDelRaw = useRequestSystemDeletion();
  if (!canManage || archived.length === 0) return null;

  const chosen = archived.filter((s) => sel.selected.has(s.system_id));

  const restoreSelected = async () => {
    if (chosen.length === 0) return;
    setBusy(true);
    try {
      reportBulk("restaurado(s)", await runSequential(chosen, (s) => restoreRaw.mutateAsync({ systemId: s.system_id })));
      sel.stop();
    } finally {
      setBusy(false);
      invalidate();
    }
  };

  // Exclusão DEFINITIVA continua passando pela aprovação: o lote só abre 1 ticket
  // SYSTEM_DELETE por sistema (mesmo endpoint do botão unitário). Nada é apagado aqui.
  const requestDeletionSelected = async () => {
    if (chosen.length === 0) return;
    if (
      !confirm(
        `Solicitar EXCLUSÃO DEFINITIVA de ${chosen.length} sistema(s)? Abre 1 ticket por sistema; cada um só é apagado depois de APROVADO em Tickets.\n\n${namesForConfirm(chosen)}`,
      )
    )
      return;
    setBusy(true);
    try {
      const r = await runSequential(chosen, (s) => reqDelRaw.mutateAsync({ systemId: s.system_id }));
      reportBulk("com exclusão solicitada (aprove em Tickets)", r);
      sel.stop();
    } finally {
      setBusy(false);
      qc.invalidateQueries({ queryKey: ["listTickets"] });
    }
  };

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
        <div className="ml-6 border-l pl-2">
          {sel.selecting ? (
            <BulkBar
              count={chosen.length}
              total={archived.length}
              busy={busy}
              onSelectAll={() => sel.setSelected(new Set(archived.map((s) => s.system_id)))}
              onSelectTests={() =>
                sel.setSelected(
                  new Set(archived.filter((s) => TEST_SYSTEM_RE.test(s.system_name)).map((s) => s.system_id)),
                )
              }
              onClear={() => sel.setSelected(new Set())}
              onCancel={sel.stop}
            >
              <Button size="sm" variant="outline" className="h-7" disabled={busy || chosen.length === 0} onClick={restoreSelected}>
                <ArchiveRestore className="mr-1 h-3.5 w-3.5" />
                Restaurar ({chosen.length})
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-destructive"
                disabled={busy || chosen.length === 0}
                onClick={requestDeletionSelected}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Solicitar exclusão ({chosen.length})
              </Button>
            </BulkBar>
          ) : (
            <div className="mb-1 flex justify-end">
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => sel.setSelecting(true)}>
                <CheckSquare className="mr-1 h-3.5 w-3.5" />
                Selecionar vários
              </Button>
            </div>
          )}
          <ul>
            {archived.map((sys) => (
              <li
                key={sys.system_id}
                className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
                  {sel.selecting && (
                    <input
                      type="checkbox"
                      className="h-4 w-4 shrink-0"
                      checked={sel.selected.has(sys.system_id)}
                      onChange={() => sel.toggle(sys.system_id)}
                      aria-label={`Selecionar ${sys.system_name}`}
                    />
                  )}
                  <Database className="h-4 w-4 shrink-0" />
                  <span className="truncate">{sys.system_name}</span>
                </span>
                {!sel.selecting && (
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
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Dialeto do sistema, editável no Navegador (rodada 9, item 7 — "onde definir o
 * dialeto"). A tecnologia do sistema É o dialeto dele: define os tipos/índices/
 * particionamento oferecidos e o dialeto padrão do import de DDL (ver lib/dialects).
 * Editar: Architect/Steward/Admin (mesmos papéis do PATCH no backend).
 */
function SystemDialect({
  systemId,
  technology,
  canEdit,
}: {
  systemId: string;
  technology?: string | null;
  canEdit: boolean;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const save = useSetSystemTechnology({
    mutation: {
      onSuccess: (r) => {
        toast.success(`Dialeto de "${r.system_name}" definido: ${r.technology ?? "—"}`);
        qc.invalidateQueries({ queryKey: ["listSystems"] });
        setEditing(false);
      },
      onError: (e) => toast.error("Falha ao definir o dialeto", { description: e.message }),
    },
  });

  if (editing) {
    // Valor legado fora da lista (ex. "Postgres 14") aparece como opção própria
    // para não ser trocado sem querer só por abrir o select.
    const current = technologyOptionLabel(technology) ?? technology ?? "";
    const isLegacy = !!technology && !technologyOptionLabel(technology);
    return (
      <select
        autoFocus
        className="h-7 rounded border bg-background px-1 text-xs"
        value={current}
        disabled={save.isPending}
        onChange={(e) => save.mutate({ systemId, technology: e.target.value || null })}
        onBlur={() => !save.isPending && setEditing(false)}
        aria-label="Dialeto do sistema"
      >
        <option value="">— sem dialeto —</option>
        {isLegacy && <option value={technology!}>{technology}</option>}
        {TECHNOLOGY_OPTIONS.map((o) => (
          <option key={o.label} value={o.label}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }

  if (!technology) {
    return canEdit ? (
      <button
        className="rounded border border-dashed px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground hover:bg-muted"
        onClick={() => setEditing(true)}
        title="Definir o dialeto (banco) deste sistema"
      >
        + dialeto
      </button>
    ) : null;
  }
  return (
    <button
      className="rounded border border-nuclea-primary/30 bg-nuclea-primary/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-nuclea-primary enabled:hover:bg-nuclea-primary/20"
      title={
        canEdit
          ? `Dialeto do sistema: ${technology}. Clique para alterar — vale para tipos/índices e é o padrão do import de DDL.`
          : `Dialeto do sistema: ${technology}`
      }
      disabled={!canEdit}
      onClick={() => setEditing(true)}
    >
      {technology}
    </button>
  );
}

function SystemNode({
  systemId,
  name,
  technology,
  selecting = false,
  checked = false,
  onToggle,
}: {
  systemId: string;
  name: string;
  /** Tecnologia/dialeto do banco do sistema (ex.: "PostgreSQL", "DB2"). round 5, pt 19. */
  technology?: string | null;
  /** Modo de seleção em lote (rodada 9, item 6): mostra checkbox e esconde o arquivar unitário. */
  selecting?: boolean;
  checked?: boolean;
  onToggle?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data: me } = useMyRolesSuspense(selector());
  // Limpar/excluir são destrutivos → só para quem aplica tickets (Architect/Admin).
  const canManage = me.can_apply_tickets || me.is_admin;
  const canEditDialect =
    me.is_admin || me.roles.includes("DATA_ARCHITECT") || me.roles.includes("DATA_STEWARD");

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
        {selecting && (
          <input
            type="checkbox"
            className="h-4 w-4 shrink-0"
            checked={checked}
            onChange={onToggle}
            aria-label={`Selecionar ${name}`}
          />
        )}
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 text-left text-sm"
        >
          <Caret open={open} />
          <Database className="h-4 w-4 shrink-0 text-nuclea-primary" />
          <span className="font-medium">{name}</span>
        </button>
        {/* Dialeto ao lado do nome (round 5 pt 19); editável desde a rodada 9 item 7.
            Fora do <button> de expandir: botão dentro de botão é HTML inválido. */}
        <SystemDialect systemId={systemId} technology={technology} canEdit={canEditDialect} />
        <span className="flex-1" />
        {canManage && !selecting && (
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
            search={{ system: undefined }}
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
