import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";
import {
  ReactFlow,
  ReactFlowProvider,
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
  Download,
  Eye,
  EyeOff,
  LayoutGrid,
  Network,
  Plus,
  RefreshCw,
  Save,
  Search,
  FileJson,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { EmptyState } from "@/components/apx/empty-state";

import { EntityNode } from "@/components/diagram/entity-node";
import { applyDagreLayout, type LayoutDirection } from "@/components/diagram/layout";

const nodeTypes: NodeTypes = { entity: EntityNode };

export const Route = createFileRoute("/_sidebar/diagram")({
  component: DiagramPage,
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
  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");

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
                Sistema
              </label>
              <select
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>
                    {s.system_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

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
  const qc = useQueryClient();
  const canvasRef = useRef<HTMLDivElement>(null);

  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("");
  const [direction, setDirection] = useState<LayoutDirection>("LR");

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
      if (domainFilter && (e.domain || "") !== domainFilter) return false;
      if (!f) return true;
      return (
        e.technical_name.toLowerCase().includes(f) ||
        (e.logical_name || "").toLowerCase().includes(f) ||
        e.schema_name.toLowerCase().includes(f) ||
        (e.domain || "").toLowerCase().includes(f)
      );
    });
  }, [view.entities, filter, domainFilter]);

  const visibleIds = useMemo(
    () => new Set(filteredEntities.map((e) => e.entity_id)),
    [filteredEntities],
  );

  const baseNodes = useMemo<Node[]>(() => {
    return filteredEntities.map((e) => ({
      id: e.entity_id,
      type: "entity",
      position: view.layout[e.entity_id] ?? { x: 0, y: 0 },
      data: { entity: e, expanded } as any,
      draggable: true,
    }));
  }, [filteredEntities, view.layout, expanded]);

  const baseEdges = useMemo<Edge[]>(() => {
    return view.relationships
      .filter((r) => visibleIds.has(r.source_entity_id) && visibleIds.has(r.target_entity_id))
      .map((r) => relationshipToEdge(r));
  }, [view.relationships, visibleIds]);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Initialize nodes/edges. If no saved positions, run dagre once.
  useEffect(() => {
    const hasAnyPositions = baseNodes.some(
      (n) => n.position.x !== 0 || n.position.y !== 0,
    );
    if (hasAnyPositions) {
      setNodes(baseNodes);
    } else {
      setNodes(applyDagreLayout(baseNodes, baseEdges, direction, expanded));
    }
    setEdges(baseEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [systemId, expanded, filter, domainFilter]);

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

  const autoLayout = useCallback(() => {
    setNodes((nds) => applyDagreLayout(nds, edges, direction, expanded));
  }, [edges, direction, expanded]);

  const saveCurrentLayout = useCallback(() => {
    const positions: Record<string, { x: number; y: number }> = {};
    for (const n of nodes) {
      positions[n.id] = { x: n.position.x, y: n.position.y };
    }
    saveLayout({ systemId, data: { layout_name: "default", positions } });
  }, [nodes, saveLayout, systemId]);

  const exportPng = useCallback(async () => {
    if (!canvasRef.current) return;
    const dataUrl = await toPng(canvasRef.current, { backgroundColor: "#ffffff" });
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = `nuclea-der-${view.system_name || systemId}.png`;
    link.click();
  }, [view.system_name, systemId]);

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

  // Quick add entity
  const [showAddEntity, setShowAddEntity] = useState(false);
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
            onClose={() => setShowAddEntity(false)}
            onSubmit={(data) => quickAdd.mutate({ systemId, data })}
            submitting={quickAdd.isPending}
          />
        )}
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{view.system_name || view.system_id}</CardTitle>
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
            >
              <option value="LR">Esq → Dir</option>
              <option value="TB">Cima → Baixo</option>
              <option value="RL">Dir → Esq</option>
              <option value="BT">Baixo → Cima</option>
            </select>
            <Button variant="outline" size="sm" onClick={autoLayout}>
              <LayoutGrid className="mr-2 h-4 w-4" />
              Auto-layout
            </Button>
            <Button size="sm" onClick={saveCurrentLayout} disabled={saving}>
              <Save className="mr-2 h-4 w-4" />
              {saving ? "Salvando..." : "Salvar layout"}
            </Button>
            <Button variant="outline" size="sm" onClick={exportPng}>
              <Download className="mr-2 h-4 w-4" />
              PNG
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
        </div>
      </CardHeader>
      <CardContent>
        <div
          ref={canvasRef}
          className="h-[640px] w-full rounded-md border bg-background"
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
          onClose={() => setShowAddEntity(false)}
          onSubmit={(data) => quickAdd.mutate({ systemId, data })}
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
          onClose={() => setEditingEntity(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["getDiagram", systemId] });
            qc.invalidateQueries({ queryKey: ["listEntities"] });
            setEditingEntity(null);
          }}
        />
      )}
    </Card>
  );
}

// ───────────────────────────────────────────────────────────────────────────

function QuickAddEntityDialog({
  systemId,
  onClose,
  onSubmit,
  submitting,
}: {
  systemId: string;
  onClose: () => void;
  onSubmit: (data: import("@/lib/api").QuickEntityIn) => void;
  submitting: boolean;
}) {
  const [schemaName, setSchemaName] = useState("public");
  const [technicalName, setTechnicalName] = useState("");
  const [logicalName, setLogicalName] = useState("");
  const [entityType, setEntityType] = useState<"TABLE" | "VIEW">("TABLE");
  const [attrsText, setAttrsText] = useState(
    "id BIGINT PK\nnome VARCHAR(200)\ncriado_em TIMESTAMP",
  );

  const parseAttrs = () =>
    attrsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        // Format: "<name> <type> [PK] [NULL|NOT NULL]"
        const parts = line.split(/\s+/);
        const name = parts[0];
        const type = parts[1] || "STRING";
        const upper = parts.map((p) => p.toUpperCase());
        return {
          technical_name: name,
          native_data_type: type,
          is_primary_key: upper.includes("PK") || upper.includes("PRIMARY"),
          is_nullable: !upper.includes("NOT_NULL") && !(upper.includes("NOT") && upper.includes("NULL")),
        };
      });

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <Card className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <CardHeader>
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
            Atalho para criar uma entidade direto no canvas. Para edição completa use{" "}
            <Link to="/entities/$id" params={{ id: "x" }} className="underline text-nuclea-primary">
              /entities
            </Link>{" "}
            depois.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
                onChange={(e) => setEntityType(e.target.value as any)}
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
            <label className="text-xs font-medium block mb-1">
              Atributos (formato: <code>nome tipo [PK]</code> uma por linha)
            </label>
            <textarea
              value={attrsText}
              onChange={(e) => setAttrsText(e.target.value)}
              rows={6}
              className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button
              onClick={() =>
                onSubmit({
                  system_id: systemId,
                  schema_name: schemaName,
                  technical_name: technicalName,
                  logical_name: logicalName || null,
                  entity_type: entityType,
                  initial_attributes: parseAttrs(),
                })
              }
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

  const { mutate: create, isPending, error } = useCreateRelationship({
    mutation: { onSuccess: () => onCreated() },
  });

  const srcEnt = entities.find((e) => e.entity_id === source);
  const tgtEnt = entities.find((e) => e.entity_id === target);
  const label = (e?: DiagramEntity) =>
    e ? `${e.schema_name}.${e.technical_name}` : "?";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        system_id: systemId,
        source_entity_id: source,
        target_entity_id: target,
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
  onClose,
  onSaved,
}: {
  entity: DiagramEntity;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [techName, setTechName] = useState(entity.technical_name);
  const [logName, setLogName] = useState(entity.logical_name || "");
  const [schema, setSchema] = useState(entity.schema_name);
  const [domain, setDomain] = useState(entity.domain || "");
  const [criticality, setCriticality] = useState(entity.criticality || "");

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
            <AttributesEditor entityId={entity.entity_id} onChanged={() => qc.invalidateQueries({ queryKey: ["getDiagram"] })} />
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
  onChanged,
}: {
  entityId: string;
  onChanged: () => void;
}) {
  const { data: attrs } = useListAttributesSuspense(entityId, selector());
  const qc = useQueryClient();
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("STRING");
  const [newPk, setNewPk] = useState(false);

  const createAttr = useCreateAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        onChanged();
        setNewName("");
        toast.success("Atributo adicionado");
      },
      onError: (e) => toast.error(String(e)),
    },
  });
  const updateAttr = useUpdateAttribute({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listAttributes", entityId] });
        onChanged();
        toast.success("Atributo atualizado");
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

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-1 pr-2 font-medium w-6"></th>
              <th className="py-1 pr-2 font-medium">Nome</th>
              <th className="py-1 pr-2 font-medium">Tipo</th>
              <th className="py-1 pr-2 font-medium w-12">PK</th>
              <th className="py-1 pr-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {attrs.map((a) => (
              <tr key={a.attribute_id} className="border-b">
                <td className="py-1 pr-2">{a.is_primary_key && "🔑"}</td>
                <td className="py-1 pr-2 font-mono">{a.technical_name}</td>
                <td className="py-1 pr-2 font-mono text-muted-foreground">{a.native_data_type || "—"}</td>
                <td className="py-1 pr-2">
                  <input
                    type="checkbox"
                    checked={a.is_primary_key}
                    onChange={(e) =>
                      updateAttr.mutate({
                        entityId,
                        attributeId: a.attribute_id,
                        data: {
                          entity_id: entityId,
                          technical_name: a.technical_name,
                          native_data_type: a.native_data_type || null,
                          is_nullable: a.is_nullable,
                          is_primary_key: e.target.checked,
                        },
                      })
                    }
                  />
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
            ))}
          </tbody>
        </table>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!newName.trim()) return;
          createAttr.mutate({
            entityId,
            data: {
              entity_id: entityId,
              technical_name: newName.trim(),
              native_data_type: newType.trim() || "STRING",
              is_primary_key: newPk,
              is_nullable: !newPk,
            },
          });
        }}
        className="flex flex-wrap gap-2 items-end pt-2"
      >
        <div className="flex-1 min-w-[140px]">
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">Nome</label>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="nova_coluna"
            className="h-8 text-xs"
          />
        </div>
        <div className="flex-1 min-w-[100px]">
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground block">Tipo</label>
          <Input
            value={newType}
            onChange={(e) => setNewType(e.target.value)}
            placeholder="STRING"
            className="h-8 text-xs"
          />
        </div>
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={newPk} onChange={(e) => setNewPk(e.target.checked)} />
          PK
        </label>
        <Button type="submit" size="sm" disabled={!newName.trim() || createAttr.isPending}>
          <Plus className="h-3 w-3" />
        </Button>
      </form>
    </div>
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
