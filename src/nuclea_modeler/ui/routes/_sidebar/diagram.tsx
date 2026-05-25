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
  useSaveLayout,
  type Cardinality,
  type DiagramEntity,
  type DiagramRelationship,
  type DiagramView,
  type RelType,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  Download,
  Eye,
  EyeOff,
  LayoutGrid,
  Network,
  RefreshCw,
  Save,
  Search,
  FileJson,
  ShieldAlert,
  X,
} from "lucide-react";

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
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <Network className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            Cadastre sistemas e entidades primeiro para gerar um diagrama.
          </p>
          <Button asChild>
            <Link to="/entities">Ir para Entidades</Link>
          </Button>
        </CardContent>
      </Card>
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
          <p className="text-sm text-muted-foreground">
            Este sistema ainda não tem entidades catalogadas.
          </p>
        </CardContent>
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
    </Card>
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
