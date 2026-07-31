import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  Background,
  Controls,
  MiniMap,
  applyNodeChanges,
  applyEdgeChanges,
  type Node,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type NodeTypes,
  type Connection,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng } from "html-to-image";

import {
  useCreateRelationship,
  useGetDiagramSuspense,
  useSystemOpenTickets,
  useListSchemasSuspense,
  useListDiagramsSuspense,
  useGetDiagramById,
  useCreateDiagram,
  useSetDiagramMembers,
  useSaveDiagramLayout,
  useGetSessionStatusSuspense,
  useDiscardSession,
  useListSystemsSuspense,
  useListSandboxesSuspense,
  useSaveLayout,
  useQuickAddEntity,
  useUpdateEntity,
  useValidateSource,
  useDeleteEntity,
  useListAttributesSuspense,
  useCreateAttribute,
  useUpdateAttribute,
  useDeleteAttribute,
  useListEntityFlagsSuspense,
  useBatchApplyEntityFlags,
  useRemoveEntityFlag,
  useListAttributeFlagsSuspense,
  useBatchApplyAttributeFlags,
  useRemoveAttributeFlag,
  type Cardinality,
  type DiagramEntity,
  type DiagramRelationship,
  type RelType,
  type SourceCheckResult,
  type SourceValidationOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  Download,
  Eye,
  EyeOff,
  ImageDown,
  LayoutGrid,
  Maximize2,
  Network,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  FileJson,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { FlagPicker } from "@/components/flags/flag-picker";
import { NewSystemWizard } from "@/components/apx/new-system-wizard";

import { EntityNode } from "@/components/diagram/entity-node";
import {
  applyIncrementalLayout,
  layoutWithSavedPositions,
  applyLayoutByMode,
  type LayoutDirection,
  type LayoutMode,
} from "@/components/diagram/layout";
import { getTypesForTechnology } from "@/components/diagram/types-by-tech";
import { TypePicker } from "@/components/diagram/type-picker";
import {
  PkToggle,
  computePkOrdinals,
  getPkWarnings,
} from "@/components/attributes/pk-controls";

const nodeTypes: NodeTypes = { entity: EntityNode };

export const Route = createFileRoute("/_sidebar/diagram")({
  component: DiagramPage,
  validateSearch: (search: Record<string, unknown>) => ({
    system: (search.system as string) || undefined,
  }),
});

function DiagramPage() {
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
                    Erro ao carregar diagrama
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
            <Suspense fallback={<Skeleton className="h-[600px] w-full" />}>
              <DiagramBody />
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
        <h1 className="text-3xl font-bold tracking-tight">Diagrama Entidade-Relacionamento</h1>
        <Badge variant="outline" className="font-mono">M4</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Canvas interativo do modelo de dados. Arraste para reposicionar, ative o auto-layout
        ou ajuste manualmente. Entidades com dados LGPD são destacadas em roxo.
        Exporte o diagrama como imagem ou JSON.
      </p>
    </div>
  );
}

function DiagramBody() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { system: systemFromUrl } = Route.useSearch();
  // Se houver 'system' na query string, use-a. Caso contrário, use o primeiro sistema.
  const initialSystem =
    systemFromUrl && systems.some((s) => s.system_id === systemFromUrl)
      ? systemFromUrl
      : systems[0]?.system_id || "";
  const [systemId, setSystemId] = useState(initialSystem);
  const [showNewSystem, setShowNewSystem] = useState(false);

  if (systems.length === 0) {
    return (
      <EmptyState
        icon={<Network className="h-10 w-10" />}
        title="Nada para diagramar ainda"
        description={
          <>
            O DER (Diagrama Entidade-Relacionamento) precisa de pelo menos um
            <strong> sistema</strong> com entidades. Cadastre o primeiro sistema
            e suas tabelas — o diagrama é gerado automaticamente com auto-layout
            Dagre.
          </>
        }
        primaryAction={{ label: "Ir para Entidades", to: "/entities" }}
        secondaryAction={{ label: "Engenharia reversa", to: "/extractions" }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[240px]">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Sistema (modelo)
              </label>
              <select
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.environment ? `[${s.environment}] ` : ""}{s.system_name}
                  </option>
                ))}
              </select>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowNewSystem(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              Novo sistema
            </Button>
          </div>
        </CardContent>
      </Card>

      <NewSystemWizard
        open={showNewSystem}
        onClose={() => setShowNewSystem(false)}
        onCreated={(sys) => setSystemId(sys.system_id)}
      />


      {systemId && (
        <Suspense fallback={<Skeleton className="h-[600px] w-full" />}>
          <ReactFlowProvider>
            <DiagramCanvas systemId={systemId} />
          </ReactFlowProvider>
        </Suspense>
      )}
    </div>
  );
}

function DiagramCanvas({ systemId }: { systemId: string }) {
  const { data: view } = useGetDiagramSuspense(systemId, "default", selector());
  // Import/mudança pendente de aprovação → o DER pode não mostrar o modelo todo.
  const { data: openTickets = [] } = useSystemOpenTickets(systemId);
  const { data: session } = useGetSessionStatusSuspense(systemId, selector());
  const { data: systems } = useListSystemsSuspense(selector());
  const systemTechnology = useMemo(
    () => systems.find((s) => s.system_id === systemId)?.technology || null,
    [systems, systemId],
  );
  const qc = useQueryClient();
  const canvasRef = useRef<HTMLDivElement>(null);

  // Descarte da sessão atual — invalida o diagrama e a query da sessão para
  // refletir o rollback imediato no canvas.
  const discardSession = useDiscardSession({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        qc.invalidateQueries({ queryKey: ["listTickets"] });
        toast.success("Sessão descartada");
      },
      onError: (e) =>
        toast.error("Erro ao descartar sessão", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });

  const totalChanges = session
    ? session.additions + session.changes + session.removals
    : 0;

  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("");
  const [direction, setDirection] = useState<LayoutDirection>("LR");
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("hierarchical");

  // M6 (fatia 4a): seletor de schema + diagrama. Schema restringe por
  // schema_name; diagrama restringe à membership (read-only nesta fatia).
  const { data: schemaList } = useListSchemasSuspense({ systemId }, selector());
  const { data: diagramList } = useListDiagramsSuspense({ systemId }, selector());
  const [schemaId, setSchemaId] = useState<string>("");
  const [diagramId, setDiagramId] = useState<string>("");
  const selectedSchema = useMemo(
    () => schemaList.find((sc) => sc.schema_id === schemaId) || null,
    [schemaList, schemaId],
  );
  const diagramsForSchema = useMemo(
    () => diagramList.filter((d) => !schemaId || d.schema_id === schemaId),
    [diagramList, schemaId],
  );
  const { data: selectedDiagram } = useGetDiagramById(diagramId || undefined);
  const memberIds = useMemo(
    () =>
      selectedDiagram ? new Set(selectedDiagram.members.map((m) => m.entity_id)) : null,
    [selectedDiagram],
  );
  // Posições salvas por diagrama (têm prioridade sobre o layout do sistema).
  const memberPos = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>();
    if (selectedDiagram) {
      for (const mm of selectedDiagram.members) {
        if (mm.pos_x != null && mm.pos_y != null) {
          m.set(mm.entity_id, { x: mm.pos_x, y: mm.pos_y });
        }
      }
    }
    return m;
  }, [selectedDiagram]);

  const { mutate: createDiagram, isPending: creatingDiagram } = useCreateDiagram({
    mutation: {
      onSuccess: () => qc.invalidateQueries({ queryKey: ["listDiagrams"] }),
      onError: (e) =>
        toast.error("Erro ao criar diagrama", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });
  const { mutate: setDiagramMembers, isPending: savingMembers } = useSetDiagramMembers({
    mutation: {
      onSuccess: (d) => {
        qc.invalidateQueries({ queryKey: ["getDiagramById", d.diagram_id] });
        qc.invalidateQueries({ queryKey: ["listDiagrams"] });
        toast.success("Tabelas do diagrama atualizadas");
      },
      onError: (e) =>
        toast.error("Erro ao salvar tabelas", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });
  const { mutate: saveDiagramLayout, isPending: savingDiagramLayout } = useSaveDiagramLayout({
    mutation: {
      onSuccess: (d) => {
        qc.invalidateQueries({ queryKey: ["getDiagramById", d.diagram_id] });
        toast.success("Layout do diagrama salvo");
      },
      onError: (e) =>
        toast.error("Erro ao salvar layout", {
          description: e instanceof Error ? e.message : String(e),
        }),
    },
  });

  const { mutate: saveLayout, isPending: saving } = useSaveLayout({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        toast.success(`Layout "${data.layout_name}" salvo`);
      },
      onError: (err) => {
        toast.error("Erro ao salvar layout", {
          description: err instanceof Error ? err.message : "Falha desconhecida",
        });
      },
    },
  });

  const [pendingConn, setPendingConn] = useState<{
    source: string;
    target: string;
  } | null>(null);

  const filteredEntities = useMemo(() => {
    const f = filter.toLowerCase();
    return view.entities.filter((e) => {
      if (selectedSchema && e.schema_name !== selectedSchema.schema_name) return false;
      if (diagramId && memberIds && !memberIds.has(e.entity_id)) return false;
      if (domainFilter && (e.domain || "") !== domainFilter) return false;
      if (!f) return true;
      return (
        e.technical_name.toLowerCase().includes(f) ||
        (e.logical_name || "").toLowerCase().includes(f) ||
        e.schema_name.toLowerCase().includes(f) ||
        (e.domain || "").toLowerCase().includes(f)
      );
    });
  }, [view.entities, filter, domainFilter, selectedSchema, diagramId, memberIds]);

  const visibleIds = useMemo(
    () => new Set(filteredEntities.map((e) => e.entity_id)),
    [filteredEntities],
  );

  // Resolve a posição SALVA de uma entidade (null quando não há posição salva).
  // Fundamental para o fix do bug de auto-distribuição: distinguimos "sem
  // posição" (NULL no backend) de uma posição real que por acaso é (0,0).
  // - Com diagrama (M6): a posição vem de diagram_entities.pos_x/pos_y, que o
  //   backend já entrega como null quando não gravada (diagrams/router.py).
  // - Sem diagrama (M4): vem do layout salvo do sistema (der_layouts) via
  //   view.layout, que só contém entidades cujo layout foi persistido.
  const savedPosOf = useCallback(
    (entityId: string): { x: number; y: number } | undefined =>
      (diagramId ? memberPos.get(entityId) : undefined) ?? view.layout[entityId],
    [diagramId, memberPos, view.layout],
  );

  // IDs das entidades visíveis que TÊM posição salva. Os demais são "novos"
  // (sem posição) e serão distribuídos pelo layout incremental — nunca mais
  // empilhados em (0,0).
  const positionedIds = useMemo(() => {
    const s = new Set<string>();
    for (const e of filteredEntities) {
      if (savedPosOf(e.entity_id)) s.add(e.entity_id);
    }
    return s;
  }, [filteredEntities, savedPosOf]);

  const baseNodes = useMemo<Node[]>(() => {
    return filteredEntities.map((e) => {
      const saved = savedPosOf(e.entity_id);
      return {
        id: e.entity_id,
        type: "entity",
        // Placeholder (0,0) apenas para nós SEM posição salva — eles serão
        // reposicionados pelo layout incremental. Quem decide se um nó é "novo"
        // é positionedIds, não a coordenada (evita o bug do sentinel (0,0)).
        position: saved ?? { x: 0, y: 0 },
        data: { entity: e, expanded } as any,
        draggable: true,
      };
    });
  }, [filteredEntities, savedPosOf, expanded]);

  const baseEdges = useMemo<Edge[]>(() => {
    return view.relationships
      .filter((r) => visibleIds.has(r.source_entity_id) && visibleIds.has(r.target_entity_id))
      .map((r) => relationshipToEdge(r));
  }, [view.relationships, visibleIds]);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Initialize / re-layout. Roda quando muda systemId, expanded, filter,
  // domainFilter, schema ou diagrama — momentos onde a estrutura de nós muda e
  // faz sentido recalcular o layout.
  //
  // FIX auto-distribuição: usamos layout INCREMENTAL em vez da detecção binária
  // antiga. Preserva as posições salvas e distribui apenas os nós SEM posição
  // (novos) ao redor/à direita dos existentes — se não houver nenhum salvo,
  // roda dagre em todos (diagrama novo).
  useEffect(() => {
    setNodes(layoutWithSavedPositions(baseNodes, positionedIds, baseEdges, direction, expanded));
    setEdges(baseEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [systemId, expanded, filter, domainFilter, schemaId, diagramId, memberIds]);

  // Re-sync data quando view.entities/relationships mudarem por refetch
  // (ex: invalidate após adicionar atributo OU após importar DDL/DM1 que traz
  // entidades novas). Preserva as posições ATUAIS dos nós já no canvas
  // (inclusive as arrastadas manualmente) e NÃO re-embaralha nada.
  //
  // FIX auto-distribuição (import): entidades novas chegam sem posição salva.
  // Em vez de largá-las em (0,0) — o bug —, rodamos layout INCREMENTAL usando
  // os nós já presentes como âncora, distribuindo só os novos à direita deles.
  useEffect(() => {
    setNodes((prev) => {
      const prevById = new Map(prev.map((n) => [n.id, n]));
      const kept: Node[] = [];
      const newWithSaved: Node[] = [];
      const newUnpositioned: Node[] = [];

      for (const n of baseNodes) {
        const existing = prevById.get(n.id);
        if (existing) {
          // Nó já no canvas: atualiza só os dados (entity + attrs), mantém a
          // posição corrente (pode ter sido arrastada pelo usuário).
          kept.push({ ...existing, data: n.data });
        } else if (positionedIds.has(n.id)) {
          // Nó novo mas com posição salva (ex.: trocou de diagrama): respeita.
          newWithSaved.push(n);
        } else {
          // Nó novo SEM posição (importado agora) → layout incremental.
          newUnpositioned.push(n);
        }
      }

      if (newUnpositioned.length === 0) {
        return [...kept, ...newWithSaved];
      }

      // Os novos entram distribuídos ao redor dos existentes (âncora = tudo o
      // que já está posicionado no canvas). O efeito de fitView keyado em
      // nodeIdSig reenquadra automaticamente quando o conjunto de ids muda.
      const anchor = [...kept, ...newWithSaved];
      return applyIncrementalLayout(anchor, newUnpositioned, baseEdges, direction, expanded);
    });
    setEdges(baseEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseNodes, baseEdges]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  // Click on a node → open edit panel
  const [editingEntity, setEditingEntity] = useState<DiagramEntity | null>(null);
  const onNodeClick = useCallback(
    (_evt: any, node: Node) => {
      const ent = (node.data as any)?.entity as DiagramEntity | undefined;
      if (ent) setEditingEntity(ent);
    },
    [],
  );

  const onConnect = useCallback((conn: Connection) => {
    if (!conn.source || !conn.target || conn.source === conn.target) return;
    setPendingConn({ source: conn.source, target: conn.target });
  }, []);

  const { fitView } = useReactFlow();

  const autoLayout = useCallback(() => {
    setNodes((nds) => applyLayoutByMode(nds, edges, layoutMode, direction, expanded));
  }, [edges, direction, expanded, layoutMode]);

  // Persiste posições de uma lista EXPLÍCITA de nós. Recebe a lista por
  // parâmetro (em vez de ler `nodes` do closure) para poder salvar logo após um
  // setNodes no mesmo tick — o state `nodes` ainda estaria stale nesse momento.
  const persistPositions = useCallback(
    (nodeList: Node[]) => {
      // Com um diagrama selecionado, salva as posições NELE (M6, diagram_entities);
      // senão, no layout "default" do sistema (M4, der_layouts — legado).
      if (diagramId) {
        saveDiagramLayout({
          diagramId,
          data: {
            positions: nodeList.map((n) => ({
              entity_id: n.id,
              pos_x: n.position.x,
              pos_y: n.position.y,
            })),
          },
        });
        return;
      }
      const positions: Record<string, { x: number; y: number }> = {};
      for (const n of nodeList) {
        positions[n.id] = { x: n.position.x, y: n.position.y };
      }
      saveLayout({ systemId, data: { layout_name: "default", positions } });
    },
    [saveLayout, saveDiagramLayout, systemId, diagramId],
  );

  const saveCurrentLayout = useCallback(
    () => persistPositions(nodes),
    [persistPositions, nodes],
  );

  // "Auto-organizar tudo": reroda o layout escolhido no diagrama INTEIRO (sobrescreve
  // posições manuais — por isso pede confirmação) e persiste automaticamente,
  // para o usuário não perder a organização ao sair sem "Salvar layout".
  const autoOrganizeAll = useCallback(() => {
    if (nodes.length === 0) return;
    const ok = window.confirm(
      "Reorganizar automaticamente TODAS as entidades deste diagrama?\n\n" +
        "As posições manuais atuais serão sobrescritas e o novo layout será " +
        "salvo automaticamente.",
    );
    if (!ok) return;
    const organized = applyLayoutByMode(nodes, edges, layoutMode, direction, expanded);
    setNodes(organized);
    // Salva o MESMO array recém-calculado (o state `nodes` só atualiza no
    // próximo render, então não dá pra reaproveitar saveCurrentLayout aqui).
    persistPositions(organized);
    fitView({ padding: 0.15, minZoom: 0.1, maxZoom: 1.5, duration: 300 });
  }, [nodes, edges, direction, expanded, layoutMode, persistPositions, fitView]);

  const onCreateDiagram = useCallback(() => {
    if (!schemaId) return;
    const name = window.prompt("Nome do novo diagrama:");
    if (!name || !name.trim()) return;
    createDiagram(
      { data: { system_id: systemId, schema_id: schemaId, diagram_name: name.trim() } },
      {
        onSuccess: (created) => {
          // novo diagrama começa com todas as tabelas do schema selecionado
          const schemaEntities = view.entities.filter(
            (e) => e.schema_name === selectedSchema?.schema_name,
          );
          setDiagramMembers({
            diagramId: created.diagram_id,
            data: { members: schemaEntities.map((e) => ({ entity_id: e.entity_id })) },
          });
          setDiagramId(created.diagram_id);
        },
      },
    );
  }, [schemaId, systemId, createDiagram, setDiagramMembers, view.entities, selectedSchema]);

  const [showMembers, setShowMembers] = useState(false);

  // Item 5: ao trocar a estrutura (schema/diagrama/filtro), reajusta o zoom
  // para o diagrama caber sempre na tela. Keyado na assinatura dos IDS dos nós
  // (não nas posições) para NÃO refazer o fit enquanto o usuário arrasta.
  const nodeIdSig = useMemo(
    () => nodes.map((n) => n.id).sort().join("|"),
    [nodes],
  );
  useEffect(() => {
    if (nodes.length === 0) return;
    const t = window.setTimeout(
      () => fitView({ padding: 0.15, minZoom: 0.1, maxZoom: 1.5, duration: 300 }),
      60,
    );
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeIdSig, fitView]);

  const fitToScreen = useCallback(
    () => fitView({ padding: 0.15, minZoom: 0.1, maxZoom: 1.5, duration: 300 }),
    [fitView],
  );

  const exportPng = useCallback(async () => {
    if (!canvasRef.current) return;
    const dataUrl = await toPng(canvasRef.current, { backgroundColor: "#ffffff" });
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = `nuclea-der-${view.system_name || systemId}.png`;
    link.click();
  }, [view.system_name, systemId]);

  // Item 4: exportar como imagem UM objeto (a tabela selecionada no canvas).
  const selectedNodeId = useMemo(
    () => nodes.find((n) => n.selected)?.id ?? null,
    [nodes],
  );
  const exportNodePng = useCallback(async () => {
    if (!canvasRef.current || !selectedNodeId) {
      toast.error("Selecione um objeto no diagrama para exportar");
      return;
    }
    const el = canvasRef.current.querySelector(
      `.react-flow__node[data-id="${CSS.escape(selectedNodeId)}"]`,
    ) as HTMLElement | null;
    if (!el) {
      toast.error("Objeto selecionado não encontrado no canvas");
      return;
    }
    const dataUrl = await toPng(el, { backgroundColor: "#ffffff", pixelRatio: 2 });
    const ent = view.entities.find((e) => e.entity_id === selectedNodeId);
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = `nuclea-obj-${ent?.technical_name || selectedNodeId}.png`;
    link.click();
  }, [selectedNodeId, view.entities]);

  const exportJson = useCallback(() => {
    const payload = {
      system_id: systemId,
      system_name: view.system_name,
      generated_at: new Date().toISOString(),
      entities: view.entities,
      relationships: view.relationships,
      layout: Object.fromEntries(nodes.map((n) => [n.id, n.position])),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `nuclea-der-${view.system_name || systemId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [systemId, view, nodes]);

  // Quick add entity + FK helper
  // Usa mutateAsync no callback do dialog (em vez de pendingFks state) pra
  // evitar closure stale entre múltiplos quickAdd consecutivos.
  const [showAddEntity, setShowAddEntity] = useState(false);
  const createFk = useCreateRelationship();

  const quickAdd = useQuickAddEntity({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        setShowAddEntity(false);
        toast.success("Entidade adicionada");
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  // Delete entity
  const deleteEntity = useDeleteEntity({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        toast.success("Entidade removida");
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  // Validate against source
  const [showValidation, setShowValidation] = useState(false);
  const [validationResult, setValidationResult] = useState<SourceValidationOut | null>(null);
  const { data: sandboxes } = useListSandboxesSuspense(selector());
  const [validateSandboxId, setValidateSandboxId] = useState(sandboxes[0]?.sandbox_id || "");
  const validate = useValidateSource({
    mutation: {
      onSuccess: (r) => {
        setValidationResult(r);
        setShowValidation(true);
        if (r.missing_count === 0) {
          toast.success(`Todas as ${r.found_count} entidades existem na fonte`);
        } else {
          toast.warning(`${r.found_count}/${r.total_entities} entidades encontradas`);
        }
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  const onValidate = () => {
    validate.mutate({
      systemId,
      sandboxId: validateSandboxId || undefined,
    });
  };

  // Bind delete to React Flow node selection (Backspace/Delete keys)
  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      for (const node of deleted) {
        if (confirm(`Excluir entidade "${(node.data as any)?.entity?.technical_name}"? Atributos serão removidos junto.`)) {
          deleteEntity.mutate({ entityId: node.id });
        }
      }
    },
    [deleteEntity],
  );

  const domains = useMemo(() => {
    const set = new Set<string>();
    for (const e of view.entities) if (e.domain) set.add(e.domain);
    return Array.from(set).sort();
  }, [view.entities]);

  if (view.entities.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <Network className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            Este sistema ainda não tem entidades catalogadas.
          </p>
          <Button onClick={() => setShowAddEntity(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Adicionar primeira tabela
          </Button>
        </CardContent>
        {showAddEntity && (
          <QuickAddEntityDialog
            systemId={systemId}
            systemTechnology={systemTechnology}
            existingEntities={view.entities}
            onClose={() => setShowAddEntity(false)}
            onSubmit={async (data, fks) => {
              try {
                const created = await quickAdd.mutateAsync({ systemId, data });
                for (const fk of fks) {
                  try {
                    await createFk.mutateAsync({
                      data: {
                        system_id: systemId,
                        source_entity_id: (created as { entity_id: string }).entity_id,
                        target_entity_id: fk.targetEntityId,
                        source_attr_ids: [],
                        target_attr_ids: [fk.targetAttrId],
                        rel_type: "1:N",
                        source_cardinality: "MANDATORY",
                        target_cardinality: "OPTIONAL",
                        description: `FK lógica: coluna "${fk.sourceColName}" → alvo`,
                      },
                    });
                  } catch (err) {
                    toast.error(`Falha ao criar FK para coluna "${fk.sourceColName}"`, {
                      description: err instanceof Error ? err.message : String(err),
                    });
                  }
                }
                if (fks.length > 0) {
                  qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
                  qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
                  toast.success(`${fks.length} relacionamento(s) criados`);
                }
              } catch (err) {
                // quickAdd.onError já mostra toast — só captura pra não quebrar a promise
                console.error("quickAdd failed", err);
              }
            }}
            submitting={quickAdd.isPending}
          />
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {openTickets.length > 0 && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            {openTickets.length === 1
              ? "Há 1 import/alteração aguardando aprovação"
              : `Há ${openTickets.length} imports/alterações aguardando aprovação`}
            {" "}— o diagrama só mostra o modelo completo depois de aprovar e aplicar.
          </span>
          <Link
            to="/tickets"
            className="shrink-0 font-medium underline underline-offset-2 hover:opacity-80"
          >
            Abrir Tickets
          </Link>
        </div>
      )}
      {session && totalChanges > 0 && (
        <SessionBanner
          session={session}
          totalChanges={totalChanges}
          onDiscard={() =>
            discardSession.mutate({ systemId } as { systemId?: string })
          }
          discarding={discardSession.isPending}
        />
      )}
      <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              {view.system_name || view.system_id}
              {(() => {
                const sys = systems.find((x) => x.system_id === systemId);
                if (!sys?.environment) return null;
                const colors: Record<string, string> = {
                  DEV: "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300",
                  HINT: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
                  PRD: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
                };
                return (
                  <Badge
                    variant="outline"
                    className={`font-mono text-[10px] ${colors[sys.environment] || ""}`}
                  >
                    {sys.environment}
                  </Badge>
                );
              })()}
            </CardTitle>
            <CardDescription>
              {filteredEntities.length} / {view.entities.length} entidades ·{" "}
              {edges.length} / {view.relationships.length} relacionamentos
              {view.entities.some((e) => e.has_lgpd_flag) && (
                <>
                  <span className="mx-2">·</span>
                  <span className="inline-flex items-center gap-1 text-nuclea-primary">
                    <ShieldAlert className="h-3 w-3" />
                    LGPD destacada
                  </span>
                </>
              )}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <>
                  <EyeOff className="mr-2 h-4 w-4" />
                  Modo compacto
                </>
              ) : (
                <>
                  <Eye className="mr-2 h-4 w-4" />
                  Modo expandido
                </>
              )}
            </Button>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as LayoutDirection)}
              className="rounded-md border bg-background px-2 py-1 text-xs"
              title="Direção do layout hierárquico"
            >
              <option value="LR">Esq → Dir</option>
              <option value="TB">Cima → Baixo</option>
              <option value="RL">Dir → Esq</option>
              <option value="BT">Baixo → Cima</option>
            </select>
            <select
              value={layoutMode}
              onChange={(e) => setLayoutMode(e.target.value as LayoutMode)}
              className="rounded-md border bg-background px-2 py-1 text-xs"
              title="Formato de layout automático"
            >
              <option value="hierarchical">Hierárquico</option>
              <option value="tree">Árvore</option>
              <option value="circular">Circular</option>
              <option value="orthogonal">Ortogonal</option>
              <option value="force">Força</option>
            </select>
            <Button
              variant="outline"
              size="sm"
              onClick={autoLayout}
              title="Reorganizar as posições no canvas (sem salvar). Use 'Salvar layout' para persistir."
            >
              <LayoutGrid className="mr-2 h-4 w-4" />
              Auto-layout
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={autoOrganizeAll}
              disabled={saving || savingDiagramLayout || nodes.length === 0}
              title="Reorganiza TODAS as entidades (sobrescreve posições manuais) e salva automaticamente"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              Auto-organizar tudo
            </Button>
            {schemaId && (
              <Button
                variant="outline"
                size="sm"
                onClick={onCreateDiagram}
                disabled={creatingDiagram}
                title="Criar um novo diagrama (recorte) neste schema"
              >
                + Novo diagrama
              </Button>
            )}
            {diagramId && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowMembers(true)}
                disabled={savingMembers}
                title="Escolher quais tabelas aparecem neste diagrama"
              >
                Editar tabelas
              </Button>
            )}
            <Button
              size="sm"
              onClick={saveCurrentLayout}
              disabled={saving || savingDiagramLayout}
            >
              <Save className="mr-2 h-4 w-4" />
              {saving || savingDiagramLayout
                ? "Salvando..."
                : diagramId
                  ? "Salvar layout do diagrama"
                  : "Salvar layout"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fitToScreen}
              title="Ajustar o zoom para o diagrama caber na tela"
            >
              <Maximize2 className="mr-2 h-4 w-4" />
              Encaixar
            </Button>
            <Button variant="outline" size="sm" onClick={exportPng}>
              <Download className="mr-2 h-4 w-4" />
              PNG
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={exportNodePng}
              disabled={!selectedNodeId}
              title="Exportar como PNG só o objeto selecionado no diagrama"
            >
              <ImageDown className="mr-2 h-4 w-4" />
              PNG objeto
            </Button>
            <Button variant="outline" size="sm" onClick={exportJson}>
              <FileJson className="mr-2 h-4 w-4" />
              JSON
            </Button>
            <Button size="sm" onClick={() => setShowAddEntity(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Adicionar tabela
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onValidate}
              disabled={validate.isPending}
              title="Verificar se as entidades existem na base de dados fonte"
            >
              <ShieldCheck className="mr-2 h-4 w-4" />
              {validate.isPending ? "Validando..." : "Validar na fonte"}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pt-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtrar entidades..."
              className="pl-9"
            />
          </div>
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
          >
            <option value="">Todos os domínios</option>
            {domains.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <select
            value={schemaId}
            onChange={(e) => {
              setSchemaId(e.target.value);
              setDiagramId("");
            }}
            className="rounded-md border bg-background px-3 py-2 text-sm"
            title="Filtrar por schema"
          >
            <option value="">Todos os schemas</option>
            {schemaList.map((sc) => (
              <option key={sc.schema_id} value={sc.schema_id}>
                {sc.schema_name}
              </option>
            ))}
          </select>
          <select
            value={diagramId}
            onChange={(e) => setDiagramId(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-50"
            title="Selecionar um diagrama (recorte do schema)"
            disabled={diagramsForSchema.length === 0}
          >
            <option value="">
              {schemaId ? "Todo o schema" : "Selecione um schema"}
            </option>
            {diagramsForSchema.map((d) => (
              <option key={d.diagram_id} value={d.diagram_id}>
                {d.diagram_name}
                {d.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
        </div>
      </CardHeader>
      <CardContent>
        <div
          ref={canvasRef}
          className="h-[calc(100vh-16rem)] min-h-[520px] w-full rounded-md border bg-background"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodesDelete={onNodesDelete}
            onNodeClick={onNodeClick}
            deleteKeyCode={["Backspace", "Delete"]}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.1}
            maxZoom={2}
            defaultEdgeOptions={{
              type: "smoothstep",
              markerEnd: { type: MarkerType.ArrowClosed },
            }}
          >
            <Background gap={20} size={1} color="rgba(123, 45, 142, 0.08)" />
            <Controls position="bottom-right" />
            <MiniMap
              pannable
              zoomable
              nodeColor={(n) => {
                const ent = (n.data as any)?.entity as DiagramEntity | undefined;
                if (ent?.has_lgpd_flag) return "#832ED9";
                if (ent?.criticality === "HIGH") return "#dc2626";
                if (ent?.criticality === "MEDIUM") return "#d97706";
                return "#94a3b8";
              }}
              style={{ background: "rgba(249, 245, 255, 0.6)" }}
            />
          </ReactFlow>
        </div>
      </CardContent>
      {pendingConn && (
        <CreateRelationshipDialog
          systemId={systemId}
          source={pendingConn.source}
          target={pendingConn.target}
          entities={view.entities}
          onClose={() => setPendingConn(null)}
          onCreated={() => {
            setPendingConn(null);
            qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
            qc.invalidateQueries({ queryKey: ["listRelationships"] });
          }}
        />
      )}
      {showAddEntity && (
        <QuickAddEntityDialog
          systemId={systemId}
          systemTechnology={systemTechnology}
          existingEntities={view.entities}
          onClose={() => setShowAddEntity(false)}
          onSubmit={async (data, fks) => {
            try {
              const created = await quickAdd.mutateAsync({ systemId, data });
              for (const fk of fks) {
                try {
                  await createFk.mutateAsync({
                    data: {
                      system_id: systemId,
                      source_entity_id: (created as { entity_id: string }).entity_id,
                      target_entity_id: fk.targetEntityId,
                      source_attr_ids: [],
                      target_attr_ids: [fk.targetAttrId],
                      rel_type: "1:N",
                      source_cardinality: "MANDATORY",
                      target_cardinality: "OPTIONAL",
                      description: `FK lógica: coluna "${fk.sourceColName}" → alvo`,
                    },
                  });
                } catch (err) {
                  toast.error(`Falha ao criar FK para coluna "${fk.sourceColName}"`, {
                    description: err instanceof Error ? err.message : String(err),
                  });
                }
              }
              if (fks.length > 0) {
                qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
                qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
                toast.success(`${fks.length} relacionamento(s) criados`);
              }
            } catch (err) {
              console.error("quickAdd failed", err);
            }
          }}
          submitting={quickAdd.isPending}
        />
      )}
      {showValidation && validationResult && (
        <ValidationDialog
          result={validationResult}
          sandboxes={sandboxes}
          currentSandboxId={validateSandboxId}
          onSandboxChange={setValidateSandboxId}
          onClose={() => setShowValidation(false)}
          onRerun={onValidate}
          rerunning={validate.isPending}
        />
      )}
      {editingEntity && (
        <EditEntityDialog
          entity={editingEntity}
          candidateEntities={view.entities}
          relationships={view.relationships}
          systemTechnology={systemTechnology}
          onClose={() => setEditingEntity(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
            qc.invalidateQueries({ queryKey: ["listEntities"] });
            setEditingEntity(null);
          }}
        />
      )}
      {showMembers && diagramId && selectedSchema && (
        <MembersDialog
          schemaName={selectedSchema.schema_name}
          schemaEntities={view.entities.filter(
            (e) => e.schema_name === selectedSchema.schema_name,
          )}
          initialIds={memberIds ?? new Set<string>()}
          saving={savingMembers}
          onClose={() => setShowMembers(false)}
          onSave={(ids) =>
            setDiagramMembers(
              {
                diagramId,
                data: { members: Array.from(ids).map((id) => ({ entity_id: id })) },
              },
              { onSuccess: () => setShowMembers(false) },
            )
          }
        />
      )}
    </Card>
    <AttachmentsPanel
      ownerKind={diagramId ? "diagram" : "system"}
      ownerId={diagramId || systemId}
      label="Anexos do modelo"
      description="Documentos anexados a este modelo (diagrama ou sistema). Máx. 25 MB por arquivo."
    />
    </div>
  );
}

function MembersDialog({
  schemaName,
  schemaEntities,
  initialIds,
  saving,
  onClose,
  onSave,
}: {
  schemaName: string;
  schemaEntities: DiagramEntity[];
  initialIds: Set<string>;
  saving: boolean;
  onClose: () => void;
  onSave: (ids: Set<string>) => void;
}) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(initialIds));
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg border shadow-xl max-w-lg w-full max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-base font-semibold">
            Tabelas do diagrama — schema <span className="font-mono">{schemaName}</span>
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="p-4 overflow-auto space-y-1">
          {schemaEntities.length === 0 && (
            <p className="text-sm text-muted-foreground">Schema sem tabelas.</p>
          )}
          {schemaEntities.map((e) => (
            <label
              key={e.entity_id}
              className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted/50 cursor-pointer"
            >
              <input
                type="checkbox"
                className="h-4 w-4 accent-nuclea-primary"
                checked={picked.has(e.entity_id)}
                onChange={() => toggle(e.entity_id)}
              />
              <span className="font-mono">{e.technical_name}</span>
              {e.logical_name && (
                <span className="text-xs text-muted-foreground">· {e.logical_name}</span>
              )}
            </label>
          ))}
        </div>
        <div className="flex items-center justify-between gap-2 p-4 border-t">
          <span className="text-xs text-muted-foreground">{picked.size} selecionada(s)</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancelar
            </Button>
            <Button size="sm" onClick={() => onSave(picked)} disabled={saving}>
              {saving ? "Salvando..." : "Salvar tabelas"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Banner exibido acima do canvas quando há mudanças pendentes na sessão atual
 * do usuário. Resume contadores (add/change/remove), oferece link para
 * revisar o ticket e botão para descartar a sessão inteira.
 */
function SessionBanner({
  session,
  totalChanges,
  onDiscard,
  discarding,
}: {
  session: { ticket_id: string; additions: number; removals: number; changes: number };
  totalChanges: number;
  onDiscard: () => void;
  discarding: boolean;
}) {
  return (
    <div className="rounded-md border border-nuclea-primary/40 bg-nuclea-primary/10 p-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-nuclea-primary/20 text-nuclea-primary p-1.5">
          <ClipboardList className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-medium">
            {totalChanges} mudança{totalChanges !== 1 ? "s" : ""} não aprovada
            {totalChanges !== 1 ? "s" : ""} nesta sessão
          </p>
          <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-2">
            {session.additions > 0 && (
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                {session.additions} adição{session.additions !== 1 ? "ões" : ""}
              </span>
            )}
            {session.changes > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />
                {session.changes} alteração{session.changes !== 1 ? "ões" : ""}
              </span>
            )}
            {session.removals > 0 && (
              <span className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-rose-500" />
                {session.removals} remoção{session.removals !== 1 ? "ões" : ""}
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button asChild size="sm">
          <Link to="/tickets/$id" params={{ id: session.ticket_id }}>
            Revisar e aprovar
          </Link>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onDiscard}
          disabled={discarding}
        >
          {discarding ? "Descartando..." : "Descartar"}
        </Button>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────

type AttrRow = {
  uid: string; // local ID pra key e tracking de FK targets dentro do dialog
  name: string;
  type: string;
  nullable: boolean;
  pk: boolean;
  fkTargetEntityId: string; // "" se não é FK
  fkTargetAttrId: string;   // "" se ainda não escolheu coluna
};

let _rowSeq = 0;
const newRow = (overrides: Partial<AttrRow> = {}): AttrRow => ({
  uid: `r${++_rowSeq}`,
  name: "",
  type: "",
  nullable: true,
  pk: false,
  fkTargetEntityId: "",
  fkTargetAttrId: "",
  ...overrides,
});

function QuickAddEntityDialog({
  systemId,
  systemTechnology,
  existingEntities,
  onClose,
  onSubmit,
  submitting,
}: {
  systemId: string;
  systemTechnology?: string | null;
  existingEntities: DiagramEntity[];
  onClose: () => void;
  onSubmit: (
    data: import("@/lib/api").QuickEntityIn,
    fks: { sourceColName: string; targetEntityId: string; targetAttrId: string }[],
  ) => void;
  submitting: boolean;
}) {
  const [schemaName, setSchemaName] = useState("public");
  const [technicalName, setTechnicalName] = useState("");
  const [logicalName, setLogicalName] = useState("");
  const [entityType, setEntityType] = useState<"TABLE" | "VIEW">("TABLE");
  const typeOptions = useMemo(
    () => getTypesForTechnology(systemTechnology),
    [systemTechnology],
  );
  const [rows, setRows] = useState<AttrRow[]>(() => [
    newRow({ name: "id", type: typeOptions[0] || "INTEGER", pk: true, nullable: false }),
  ]);

  const updateRow = (uid: string, patch: Partial<AttrRow>) =>
    setRows((prev) => prev.map((r) => (r.uid === uid ? { ...r, ...patch } : r)));
  const removeRow = (uid: string) =>
    setRows((prev) => prev.filter((r) => r.uid !== uid));
  const addRow = () => setRows((prev) => [...prev, newRow({ type: typeOptions[0] || "" })]);

  // Entities elegíveis pra FK target: do mesmo sistema OU compartilhadas
  const fkCandidates = useMemo(
    () =>
      existingEntities.filter(
        (e) => e.system_id === systemId || (e as { is_shared?: boolean }).is_shared,
      ),
    [existingEntities, systemId],
  );

  const handleSubmit = () => {
    const attrs = rows
      .filter((r) => r.name.trim())
      .map((r) => ({
        technical_name: r.name.trim(),
        native_data_type: r.type || null,
        is_primary_key: r.pk,
        is_nullable: r.nullable,
      }));
    const fks = rows
      .filter((r) => r.name.trim() && r.fkTargetEntityId && r.fkTargetAttrId)
      .map((r) => ({
        sourceColName: r.name.trim(),
        targetEntityId: r.fkTargetEntityId,
        targetAttrId: r.fkTargetAttrId,
      }));
    onSubmit(
      {
        system_id: systemId,
        schema_name: schemaName,
        technical_name: technicalName,
        logical_name: logicalName || null,
        entity_type: entityType,
        initial_attributes: attrs,
      },
      fks,
    );
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <CardHeader className="shrink-0">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Plus className="h-5 w-5 text-nuclea-primary" />
              Adicionar tabela
            </CardTitle>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <CardDescription>
            Defina colunas, tipos, PK e FKs. Tipos mostrados são os da tecnologia
            <strong> {systemTechnology || "genérica"}</strong>. FKs viram relacionamentos
            no DER e entram na mesma sessão de edição.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-1 space-y-4">
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium block mb-1">Schema</label>
              <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium block mb-1">Tipo</label>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value as "TABLE" | "VIEW")}
              >
                <option value="TABLE">TABLE</option>
                <option value="VIEW">VIEW</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium block mb-1">Nome técnico *</label>
              <Input
                value={technicalName}
                onChange={(e) => setTechnicalName(e.target.value)}
                placeholder="cliente"
                autoFocus
              />
            </div>
            <div>
              <label className="text-xs font-medium block mb-1">Nome lógico</label>
              <Input
                value={logicalName}
                onChange={(e) => setLogicalName(e.target.value)}
                placeholder="Cliente"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium">Colunas</label>
              <Button variant="outline" size="sm" onClick={addRow}>
                <Plus className="mr-1 h-3 w-3" /> Adicionar coluna
              </Button>
            </div>
            <div className="border rounded-md overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-muted-foreground">
                  <tr>
                    <th className="text-left p-2 font-medium">Nome</th>
                    <th className="text-left p-2 font-medium">Tipo</th>
                    <th className="text-center p-2 font-medium w-12">Nulo</th>
                    <th className="text-center p-2 font-medium w-12">PK</th>
                    <th className="text-left p-2 font-medium">FK → Tabela</th>
                    <th className="text-left p-2 font-medium">FK → Coluna</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const targetEnt = fkCandidates.find((e) => e.entity_id === r.fkTargetEntityId);
                    return (
                      <tr key={r.uid} className="border-t">
                        <td className="p-1">
                          <Input
                            value={r.name}
                            onChange={(e) => updateRow(r.uid, { name: e.target.value })}
                            placeholder="nome_coluna"
                            className="h-7 text-xs font-mono"
                          />
                        </td>
                        <td className="p-1">
                          <TypePicker
                            value={r.type}
                            onChange={(next) => updateRow(r.uid, { type: next })}
                            technology={systemTechnology}
                            size="compact"
                          />
                        </td>
                        <td className="p-1 text-center">
                          <input
                            type="checkbox"
                            checked={r.nullable}
                            onChange={(e) => updateRow(r.uid, { nullable: e.target.checked })}
                          />
                        </td>
                        <td className="p-1 text-center">
                          <input
                            type="checkbox"
                            checked={r.pk}
                            onChange={(e) => updateRow(r.uid, { pk: e.target.checked, nullable: e.target.checked ? false : r.nullable })}
                          />
                        </td>
                        <td className="p-1">
                          <select
                            value={r.fkTargetEntityId}
                            onChange={(e) =>
                              updateRow(r.uid, {
                                fkTargetEntityId: e.target.value,
                                fkTargetAttrId: "",
                              })
                            }
                            className="h-7 text-xs rounded border bg-background px-1.5 w-full"
                          >
                            <option value="">— nenhuma —</option>
                            {fkCandidates.map((e) => (
                              <option key={e.entity_id} value={e.entity_id}>
                                {e.schema_name}.{e.technical_name}
                                {(e as { is_shared?: boolean }).is_shared ? " (compartilhada)" : ""}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="p-1">
                          <select
                            value={r.fkTargetAttrId}
                            onChange={(e) => updateRow(r.uid, { fkTargetAttrId: e.target.value })}
                            disabled={!targetEnt}
                            className="h-7 text-xs rounded border bg-background px-1.5 font-mono w-full disabled:opacity-50"
                          >
                            <option value="">— coluna —</option>
                            {(targetEnt?.attributes ?? []).map((a) => (
                              <option key={a.attribute_id} value={a.attribute_id}>
                                {a.technical_name}{a.is_primary_key ? " 🔑" : ""}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="p-1">
                          <button
                            onClick={() => removeRow(r.uid)}
                            className="text-muted-foreground hover:text-destructive"
                            disabled={rows.length === 1}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Marque PK pra chave primária. Pra FK, escolha tabela alvo e a coluna —
              o relacionamento entra na sessão automaticamente quando você criar a tabela.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting || !technicalName || !schemaName}
            >
              {submitting ? "Salvando..." : "Criar"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ValidationDialog({
  result,
  sandboxes,
  currentSandboxId,
  onSandboxChange,
  onClose,
  onRerun,
  rerunning,
}: {
  result: SourceValidationOut;
  sandboxes: Array<{ sandbox_id: string; name: string; instance_name: string }>;
  currentSandboxId: string;
  onSandboxChange: (v: string) => void;
  onClose: () => void;
  onRerun: () => void;
  rerunning: boolean;
}) {
  const isLakebase = result.source_kind === "LAKEBASE";
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <Card className="w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <CardHeader className="shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-nuclea-primary" />
                Validação na fonte
              </CardTitle>
              <CardDescription>
                Fonte: <Badge variant="outline">{result.source_kind}</Badge>{" "}
                {result.target_catalog && (
                  <code className="text-xs">{result.target_catalog}</code>
                )}
              </CardDescription>
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          {isLakebase && sandboxes.length > 0 && (
            <div className="flex items-end gap-2 pt-2">
              <div className="flex-1">
                <label className="text-xs font-medium block mb-1">Sandbox Lakebase</label>
                <select
                  value={currentSandboxId}
                  onChange={(e) => onSandboxChange(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {sandboxes.map((s) => (
                    <option key={s.sandbox_id} value={s.sandbox_id}>
                      {s.name} ({s.instance_name})
                    </option>
                  ))}
                </select>
              </div>
              <Button onClick={onRerun} disabled={rerunning} size="sm">
                <RefreshCw className={`mr-2 h-4 w-4 ${rerunning ? "animate-spin" : ""}`} />
                Revalidar
              </Button>
            </div>
          )}
          <div className="flex flex-wrap gap-3 pt-2 text-xs">
            <Badge variant="outline">
              {result.total_entities} entidades
            </Badge>
            <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {result.found_count} encontradas
            </span>
            {result.missing_count > 0 && (
              <span className="inline-flex items-center gap-1 text-destructive">
                <XCircle className="h-3.5 w-3.5" />
                {result.missing_count} ausentes
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-1">
          <div className="space-y-2">
            {result.results.map((r: SourceCheckResult) => (
              <div
                key={r.entity_id}
                className={`rounded-md border p-3 ${
                  r.exists_in_source
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-destructive/30 bg-destructive/5"
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    {r.exists_in_source ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <XCircle className="h-4 w-4 text-destructive" />
                    )}
                    <strong className="font-mono text-sm">
                      {r.schema_name}.{r.technical_name}
                    </strong>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {r.columns_in_catalog} cols catálogo
                    {r.columns_in_source != null && ` · ${r.columns_in_source} cols fonte`}
                  </span>
                </div>
                {r.error && (
                  <p className="text-xs text-destructive font-mono">{r.error}</p>
                )}
                {r.missing_in_source.length > 0 && (
                  <div className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                    <span className="mr-1">Colunas no catálogo, ausentes na fonte:</span>
                    <span className="inline-flex flex-wrap gap-1">
                      {r.missing_in_source.map((c) => (
                        <code key={c} className="px-1.5 py-0.5 bg-amber-500/10 rounded font-mono">{c}</code>
                      ))}
                    </span>
                  </div>
                )}
                {r.extra_in_source.length > 0 && (
                  <div className="text-xs text-blue-700 dark:text-blue-300 mt-1">
                    <span className="mr-1">Colunas na fonte, ausentes do catálogo:</span>
                    <span className="inline-flex flex-wrap gap-1">
                      {r.extra_in_source.map((c) => (
                        <code key={c} className="px-1.5 py-0.5 bg-blue-500/10 rounded font-mono">{c}</code>
                      ))}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CreateRelationshipDialog({
  systemId,
  source,
  target,
  entities,
  onClose,
  onCreated,
}: {
  systemId: string;
  source: string;
  target: string;
  entities: DiagramEntity[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [relType, setRelType] = useState<RelType>("1:N");
  const [sourceCard, setSourceCard] = useState<Cardinality>("OPTIONAL");
  const [targetCard, setTargetCard] = useState<Cardinality>("MANDATORY");
  const [description, setDescription] = useState("");
  const [sourceAttrIds, setSourceAttrIds] = useState<string[]>([]);
  const [targetAttrIds, setTargetAttrIds] = useState<string[]>([]);

  const { mutate: create, isPending, error } = useCreateRelationship({
    mutation: { onSuccess: () => onCreated() },
  });

  const srcEnt = entities.find((e) => e.entity_id === source);
  const tgtEnt = entities.find((e) => e.entity_id === target);
  const label = (e?: DiagramEntity) =>
    e ? `${e.schema_name}.${e.technical_name}` : "?";

  const toggleAttr = (which: "src" | "tgt", attrId: string) => {
    const setter = which === "src" ? setSourceAttrIds : setTargetAttrIds;
    setter((prev) =>
      prev.includes(attrId) ? prev.filter((x) => x !== attrId) : [...prev, attrId],
    );
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        system_id: systemId,
        source_entity_id: source,
        target_entity_id: target,
        source_attr_ids: sourceAttrIds,
        target_attr_ids: targetAttrIds,
        rel_type: relType,
        source_cardinality: sourceCard,
        target_cardinality: targetCard,
        description: description || null,
      },
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg border shadow-xl max-w-lg w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-base font-semibold">Novo relacionamento</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <form onSubmit={submit} className="p-4 space-y-4">
          <div className="rounded-md bg-muted/40 border p-3 text-xs font-mono">
            <span className="text-nuclea-primary">{label(srcEnt)}</span>
            <span className="mx-2 text-muted-foreground">→</span>
            <span className="text-nuclea-accent">{label(tgtEnt)}</span>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1.5">Tipo</label>
            <div className="flex flex-wrap gap-2">
              {(["1:1", "1:N", "N:M", "INHERIT"] as RelType[]).map((rt) => (
                <label
                  key={rt}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs font-mono ${
                    relType === rt
                      ? "bg-nuclea-primary text-primary-foreground border-nuclea-primary"
                      : "hover:bg-muted"
                  }`}
                >
                  <input
                    type="radio"
                    name="dl_rel_type"
                    value={rt}
                    checked={relType === rt}
                    onChange={() => setRelType(rt)}
                    className="sr-only"
                  />
                  {rt}
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium block mb-1.5">
                Cardinalidade origem
              </label>
              <div className="flex gap-2">
                {(["OPTIONAL", "MANDATORY"] as Cardinality[]).map((c) => (
                  <label
                    key={c}
                    className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs ${
                      sourceCard === c
                        ? "bg-nuclea-primary text-primary-foreground border-nuclea-primary"
                        : "hover:bg-muted"
                    }`}
                  >
                    <input
                      type="radio"
                      name="dl_src_card"
                      value={c}
                      checked={sourceCard === c}
                      onChange={() => setSourceCard(c)}
                      className="sr-only"
                    />
                    {c === "OPTIONAL" ? "Opcional" : "Obrig."}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium block mb-1.5">
                Cardinalidade destino
              </label>
              <div className="flex gap-2">
                {(["OPTIONAL", "MANDATORY"] as Cardinality[]).map((c) => (
                  <label
                    key={c}
                    className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs ${
                      targetCard === c
                        ? "bg-nuclea-primary text-primary-foreground border-nuclea-primary"
                        : "hover:bg-muted"
                    }`}
                  >
                    <input
                      type="radio"
                      name="dl_tgt_card"
                      value={c}
                      checked={targetCard === c}
                      onChange={() => setTargetCard(c)}
                      className="sr-only"
                    />
                    {c === "OPTIONAL" ? "Opcional" : "Obrig."}
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Picker de colunas (FK explícita coluna-a-coluna). Opcional. */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium block mb-1.5">
                Colunas origem ({sourceAttrIds.length})
              </label>
              <div className="max-h-32 overflow-y-auto border rounded-md p-2 space-y-1 text-xs">
                {srcEnt?.attributes?.length ? (
                  srcEnt.attributes.map((a) => (
                    <label key={a.attribute_id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 px-1 rounded">
                      <input
                        type="checkbox"
                        checked={sourceAttrIds.includes(a.attribute_id)}
                        onChange={() => toggleAttr("src", a.attribute_id)}
                      />
                      <code className="font-mono">{a.technical_name}</code>
                      {a.is_primary_key && <span className="text-amber-600">🔑</span>}
                    </label>
                  ))
                ) : (
                  <span className="text-muted-foreground italic">sem colunas</span>
                )}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium block mb-1.5">
                Colunas destino ({targetAttrIds.length})
              </label>
              <div className="max-h-32 overflow-y-auto border rounded-md p-2 space-y-1 text-xs">
                {tgtEnt?.attributes?.length ? (
                  tgtEnt.attributes.map((a) => (
                    <label key={a.attribute_id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 px-1 rounded">
                      <input
                        type="checkbox"
                        checked={targetAttrIds.includes(a.attribute_id)}
                        onChange={() => toggleAttr("tgt", a.attribute_id)}
                      />
                      <code className="font-mono">{a.technical_name}</code>
                      {a.is_primary_key && <span className="text-amber-600">🔑</span>}
                    </label>
                  ))
                ) : (
                  <span className="text-muted-foreground italic">sem colunas</span>
                )}
              </div>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1.5">Descrição</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Opcional"
            />
          </div>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-xs text-destructive">
              <pre className="whitespace-pre-wrap">{String(error)}</pre>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Criando..." : "Criar"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Converte um relacionamento do backend (FK, constraints) em uma edge do React Flow.
 *
 * FIX (v1.0027): Arestas não se perdiam na navegação.
 * - Agora usa sourceHandle/targetHandle explícitos apontando para handles ID'd.
 * - Source sempre sai por "source-right"; target chega por "target-right".
 * - Isso garante que a linha sempre toca uma borda real, não flutua pro vazio
 *   mesmo durante navegação, filtro, refetch ou mudança de layout.
 *
 * Por que funciona:
 * - Sem handles ID'd, o RF ambiguamente selecionava o handle mais próximo,
 *   causando overlay quando posições mudavam.
 * - Com handles explícitos nos dois lados, sabemos exatamente qual usar.
 * - smoothstep curva a linha elegantemente entre os pontos de entrada/saída.
 */
function relationshipToEdge(r: DiagramRelationship): Edge {
  const label = r.rel_type
    ? r.rel_type
    : r.source_cardinality || r.target_cardinality
      ? `${r.source_cardinality || "?"} ↔ ${r.target_cardinality || "?"}`
      : undefined;
  return {
    id: r.relationship_id,
    source: r.source_entity_id,
    target: r.target_entity_id,
    // Handles explícitos: garantem que a aresta sempre conecta nos pontos certos
    sourceHandle: "source-right",
    targetHandle: "target-right",
    label,
    labelStyle: { fontSize: 10, fill: "#6b7280" },
    labelBgPadding: [4, 2],
    labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9, stroke: "#e5e7eb" },
    style: { stroke: "#832ED9", strokeWidth: 1.5 },
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, color: "#832ED9" },
  };
}

// ───────────────────────────────────────────────────────────────────────────
// EditEntityDialog: side dialog to edit an entity's metadata + attributes.
// ───────────────────────────────────────────────────────────────────────────

function EditEntityDialog({
  entity,
  candidateEntities,
  relationships,
  systemTechnology,
  onClose,
  onSaved,
}: {
  entity: DiagramEntity;
  candidateEntities: DiagramEntity[];
  relationships: DiagramRelationship[];
  systemTechnology?: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [techName, setTechName] = useState(entity.technical_name);
  const [logName, setLogName] = useState(entity.logical_name || "");
  const [schema, setSchema] = useState(entity.schema_name);
  const [domain, setDomain] = useState(entity.domain || "");
  const [criticality, setCriticality] = useState(entity.criticality || "");
  const [isShared, setIsShared] = useState(
    Boolean((entity as { is_shared?: boolean }).is_shared),
  );

  const updateEntity = useUpdateEntity({
    mutation: {
      onSuccess: () => {
        toast.success("Entidade atualizada");
        onSaved();
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  const onSave = () => {
    updateEntity.mutate({
      entityId: entity.entity_id,
      data: {
        system_id: entity.system_id,
        schema_name: schema,
        technical_name: techName,
        logical_name: logName || null,
        domain: domain || null,
        criticality: (criticality || null) as any,
        entity_type: entity.entity_type as any,
        tags: [],
        is_shared: isShared,
      },
    });
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-end p-4"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-2xl h-full max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="shrink-0 border-b">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="font-mono">
                {entity.schema_name}.{entity.technical_name}
              </CardTitle>
              <CardDescription>
                <Badge variant="outline" className="mr-2">{entity.entity_type}</Badge>
                Editar metadados e atributos
              </CardDescription>
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-1 space-y-4">
          {/* Metadata form */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Metadados</h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Schema">
                <Input value={schema} onChange={(e) => setSchema(e.target.value)} />
              </Field>
              <Field label="Nome técnico">
                <Input value={techName} onChange={(e) => setTechName(e.target.value)} />
              </Field>
              <Field label="Nome lógico">
                <Input value={logName} onChange={(e) => setLogName(e.target.value)} />
              </Field>
              <Field label="Domínio">
                <Input value={domain} onChange={(e) => setDomain(e.target.value)} />
              </Field>
              <Field label="Criticidade">
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={criticality}
                  onChange={(e) => setCriticality(e.target.value)}
                >
                  <option value="">—</option>
                  <option value="HIGH">Alta</option>
                  <option value="MEDIUM">Média</option>
                  <option value="LOW">Baixa</option>
                </select>
              </Field>
            </div>
            <div className="rounded-md border bg-muted/30 p-3">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isShared}
                  onChange={(e) => setIsShared(e.target.checked)}
                  className="mt-0.5"
                />
                <div className="text-xs">
                  <div className="font-medium">Entidade compartilhada</div>
                  <div className="text-muted-foreground">
                    Permite que esta entidade seja referenciada como destino
                    de relacionamentos em <strong>outros sistemas/modelos</strong>.
                    Útil pra entities canônicas (Cliente, Conta, etc) que
                    múltiplos domínios consomem.
                  </div>
                </div>
              </label>
            </div>
            <div className="flex justify-end">
              <Button onClick={onSave} disabled={updateEntity.isPending} size="sm">
                <Save className="mr-2 h-4 w-4" />
                {updateEntity.isPending ? "Salvando..." : "Salvar metadados"}
              </Button>
            </div>
          </div>

          {/* Attributes editor */}
          <div className="space-y-3 pt-4 border-t">
            <h3 className="text-sm font-semibold">Atributos</h3>
            <AttributesEditor
              entityId={entity.entity_id}
              systemId={entity.system_id}
              systemTechnology={systemTechnology}
              candidateEntities={candidateEntities}
              relationships={relationships}
              onChanged={() => qc.invalidateQueries({ queryKey: ["getDiagram"] })}
            />
          </div>

          <div className="pt-4 border-t text-xs text-muted-foreground">
            Para editar descrição, owners, tags, flags LGPD e mais, abra a página completa em{" "}
            <Link
              to="/entities/$id"
              params={{ id: entity.entity_id }}
              className="text-nuclea-primary underline"
            >
              /entities/{entity.entity_id.slice(0, 12)}…
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AttributesEditor({
  entityId,
  systemId,
  systemTechnology,
  candidateEntities,
  relationships,
  onChanged,
}: {
  entityId: string;
  systemId: string;
  systemTechnology?: string | null;
  candidateEntities: DiagramEntity[];
  relationships: DiagramRelationship[];
  onChanged: () => void;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  const { data: entityFlags } = useListEntityFlagsSuspense(entityId, selector());
  const qc = useQueryClient();

  // FKs desta entity → avisa (não bloqueia) ao marcar como PK.
  const fkAttrIds = new Set<string>();
  for (const rel of relationships) {
    if (rel.source_entity_id === entityId)
      for (const id of rel.source_attrs) fkAttrIds.add(id);
    if (rel.target_entity_id === entityId)
      for (const id of rel.target_attrs) fkAttrIds.add(id);
  }
  // Numeração PK1, PK2… na ordem de definição (ordinal_position).
  const pkOrdinals = computePkOrdinals(attrs);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("STRING");
  const [newPk, setNewPk] = useState(false);
  // FK opcional na criação: marca tabela alvo + coluna alvo
  const [newFkEntity, setNewFkEntity] = useState("");
  const [newFkAttr, setNewFkAttr] = useState("");

  const createAttr = useCreateAttribute();
  const createFkRel = useCreateRelationship();
  const updateAttr = useUpdateAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        // Mantém o badge de "mudanças pendentes" (SessionBanner) em dia.
        qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
        onChanged();
        // Toast específico é disparado pelo caller (ex.: PkToggle) para dar
        // feedback contextual (PK marcada/desmarcada).
      },
    },
  });
  const deleteAttr = useDeleteAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        onChanged();
      },
    },
  });

  // Flags: entity-level
  const { mutate: applyEntityFlagBatch, isPending: applyingEntityFlags } = useBatchApplyEntityFlags({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
      onError: (e) => {
        toast.error("Erro ao aplicar flags na entidade: " + String(e));
      },
    },
  });
  const { mutate: removeEntityFlag } = useRemoveEntityFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
    },
  });

  return (
    <div className="space-y-4">
      {/* Entity-level flags section */}
      <div className="border rounded-lg p-3 bg-muted/30">
        <div className="text-xs font-semibold mb-2 flex items-center gap-1">
          <ShieldCheck className="h-3 w-3" />
          Flags da tabela
        </div>
        <FlagPicker
          applied={entityFlags.map((ef) => ({
            applied_flag_id: ef.entity_flag_id,
            flag: ef.flag,
            justification: ef.justification,
            is_propagated: ef.is_propagated,
          }))}
          applying={applyingEntityFlags}
          onApply={(specs) =>
            applyEntityFlagBatch({ data: { target_ids: [entityId], flags: specs } })
          }
          onRemove={(efid) =>
            removeEntityFlag({ entityId, entityFlagId: efid })
          }
          size="small"
          label="+ Flags"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-1 pr-2 font-medium">Nome</th>
              <th className="py-1 pr-2 font-medium">Tipo</th>
              <th className="py-1 pr-2 font-medium w-20">PK</th>
              <th className="py-1 pr-2 font-medium">Flags</th>
              <th className="py-1 pr-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {attrs.map((a) => {
              const warnings = getPkWarnings({
                isNullable: a.is_nullable,
                isForeignKey: fkAttrIds.has(a.attribute_id),
              });
              return (
                <tr key={a.attribute_id} className="border-b">
                  <td className="py-1 pr-2 font-mono">{a.technical_name}</td>
                  <td className="py-1 pr-2 font-mono text-muted-foreground">{a.native_data_type || "—"}</td>
                  <td className="py-1 pr-2">
                    <PkToggle
                      checked={a.is_primary_key}
                      ordinal={pkOrdinals.get(a.attribute_id)}
                      warnings={warnings}
                      // STAGE via PUT (fluxo editorial → ticket). Ao marcar PK,
                      // força NOT NULL (PK não pode ser nullable).
                      onCheckedChange={(checked) => {
                        updateAttr.mutate({
                          entityId,
                          attributeId: a.attribute_id,
                          data: {
                            entity_id: entityId,
                            technical_name: a.technical_name,
                            native_data_type: a.native_data_type || null,
                            ordinal_position: a.ordinal_position ?? null,
                            is_nullable: checked ? false : a.is_nullable,
                            is_primary_key: checked,
                          },
                        });
                        toast.success(
                          checked
                            ? `"${a.technical_name}" marcada como PK (pendente)`
                            : `"${a.technical_name}" deixou de ser PK (pendente)`,
                        );
                      }}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <Suspense fallback={<span className="text-[10px] text-muted-foreground">…</span>}>
                      <AttributeFlagsCell
                        attributeId={a.attribute_id}
                        entityId={entityId}
                      />
                    </Suspense>
                  </td>
                  <td className="py-1 pr-2">
                    <button
                      onClick={() => {
                        if (confirm(`Remover ${a.technical_name}?`))
                          deleteAttr.mutate({ entityId, attributeId: a.attribute_id });
                      }}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!newName.trim()) return;
          try {
            await createAttr.mutateAsync({
              entityId,
              data: {
                entity_id: entityId,
                technical_name: newName.trim(),
                native_data_type: newType.trim() || "STRING",
                is_primary_key: newPk,
                is_nullable: !newPk,
              },
            });
            // Se FK marcada, cria relationship na mesma sessão
            if (newFkEntity && newFkAttr) {
              try {
                await createFkRel.mutateAsync({
                  data: {
                    system_id: systemId,
                    source_entity_id: entityId,
                    target_entity_id: newFkEntity,
                    source_attr_ids: [],
                    target_attr_ids: [newFkAttr],
                    rel_type: "1:N",
                    source_cardinality: "MANDATORY",
                    target_cardinality: "OPTIONAL",
                    description: `FK logica coluna ${newName.trim()} alvo`,
                  },
                });
                qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
                qc.invalidateQueries({ queryKey: ["getSessionStatus", systemId] });
              } catch (err) {
                toast.error("Atributo criado, mas FK falhou", {
                  description: err instanceof Error ? err.message : String(err),
                });
              }
            }
            qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
            onChanged();
            setNewName("");
            setNewFkEntity("");
            setNewFkAttr("");
            toast.success(
              newFkEntity && newFkAttr
                ? "Atributo + FK adicionados"
                : "Atributo adicionado",
            );
          } catch (err) {
            toast.error(String(err));
          }
        }}
        className="space-y-2 pt-2"
      >
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[140px]">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">Nome</label>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="nova_coluna"
              className="h-8 text-xs"
            />
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">Tipo</label>
            <TypePicker
              value={newType}
              onChange={setNewType}
              technology={systemTechnology}
            />
          </div>
          <PkToggle checked={newPk} onCheckedChange={setNewPk} />
          <Button type="submit" size="sm" disabled={!newName.trim() || createAttr.isPending || createFkRel.isPending}>
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        <div className="flex flex-wrap gap-2 items-end pl-3 border-l-2 border-nuclea-primary/30">
          <div className="flex-1 min-w-[140px]">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">FK → tabela</label>
            <select
              value={newFkEntity}
              onChange={(e) => { setNewFkEntity(e.target.value); setNewFkAttr(""); }}
              className="w-full h-8 text-xs rounded border bg-background px-1.5"
            >
              <option value="">— sem FK —</option>
              {candidateEntities
                .filter((e) => e.entity_id !== entityId)
                .map((e) => (
                  <option key={e.entity_id} value={e.entity_id}>
                    {e.schema_name}.{e.technical_name}
                  </option>
                ))}
            </select>
          </div>
          <div className="flex-1 min-w-[100px]">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">FK → coluna</label>
            <select
              value={newFkAttr}
              onChange={(e) => setNewFkAttr(e.target.value)}
              disabled={!newFkEntity}
              className="w-full h-8 text-xs rounded border bg-background px-1.5 disabled:opacity-50"
            >
              <option value="">— coluna —</option>
              {(candidateEntities.find((e) => e.entity_id === newFkEntity)?.attributes ?? []).map((a) => (
                <option key={a.attribute_id} value={a.attribute_id}>
                  {a.technical_name}{a.is_primary_key ? " 🔑" : ""}
                </option>
              ))}
            </select>
          </div>
          <span className="text-[11px] text-muted-foreground italic flex-1">
            opcional — vira aresta no DER
          </span>
        </div>
      </form>
    </div>
  );
}

/**
 * AttributeFlagsCell — Componente para aplicar flags a atributos dentro do editor do DER.
 * Reusa FlagPicker com suspense para carregar flags do atributo.
 * Integrado à tabela de atributos do AttributesEditor.
 */
function AttributeFlagsCell({
  attributeId,
  entityId,
}: {
  attributeId: string;
  entityId: string;
}) {
  const qc = useQueryClient();
  const { data: appliedFlags } = useListAttributeFlagsSuspense(
    attributeId,
    selector(),
  );

  const { mutate: applyBatch, isPending: applying } = useBatchApplyAttributeFlags({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributeFlags", attributeId] });
        qc.invalidateQueries({ queryKey: ["listEntityFlags", entityId] });
      },
      onError: (e) => {
        toast.error("Erro ao aplicar flags: " + String(e));
      },
    },
  });

  const { mutate: remove } = useRemoveAttributeFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributeFlags", attributeId] });
      },
    },
  });

  const applied = appliedFlags.map((af) => ({
    applied_flag_id: af.attribute_flag_id,
    flag: af.flag,
    justification: af.justification,
  }));

  return (
    <FlagPicker
      applied={applied}
      applying={applying}
      onApply={(specs) =>
        applyBatch({ data: { target_ids: [attributeId], flags: specs } })
      }
      onRemove={(afid) =>
        remove({ attributeId, attributeFlagId: afid })
      }
      size="small"
      label="+ Flag"
    />
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

