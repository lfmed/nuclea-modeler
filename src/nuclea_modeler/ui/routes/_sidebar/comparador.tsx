/**
 * Comparador — canvas exploratório (pedido do cliente).
 *
 * Board livre (xyflow) onde o usuário traz "cartões de objeto" (tabelas) e os
 * coloca lado a lado para validar campos e similaridade — inclusive o MESMO
 * schema em versões diferentes (via snapshot do módulo de Versões M8). Serve
 * para mandar prints (export PNG do board ou de um cartão) e análise visual.
 *
 * Persistência: EFÊMERA por design — o board vive em localStorage (chave
 * STORAGE_KEY), sem backend. Se um dia precisar de boards salvos/compartilhados,
 * promover para uma tabela `explore_boards` + endpoints (ver design no PR).
 *
 * Reuso: xyflow (mesmo do DER), html-to-image (mesmo export do DER),
 * hooks não-suspense useEntityAttributes/useVersion, e a lógica pura em
 * components/compare/compare-utils.ts.
 */
import { createFileRoute } from "@tanstack/react-router";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
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
  type Node,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng } from "html-to-image";

import {
  useListEntitiesSuspense,
  useListVersionsSuspense,
  type EntityListOut,
} from "@/lib/api";
import selector from "@/lib/selector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FieldCardNode,
  CompareContext,
  type CompareCard,
  type FieldCardData,
} from "@/components/compare/field-card-node";
import {
  AlertCircle,
  Columns2,
  Download,
  GitCompare,
  ImageDown,
  Maximize2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/comparador")({
  component: ComparadorPage,
});

// nodeTypes precisa ser estável entre renders (senão xyflow re-monta os nodes).
const NODE_TYPES: NodeTypes = { fieldCard: FieldCardNode };
const STORAGE_KEY = "nuclea.comparador.v1";

type PersistShape = {
  nodes: { id: string; card: CompareCard; x: number; y: number }[];
  baseId: string | null;
  compareOn: boolean;
};

function loadPersisted(): PersistShape | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistShape) : null;
  } catch {
    return null;
  }
}

function ComparadorPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="mb-2 flex items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">Canvas Exploratório</h1>
          <Badge variant="outline" className="font-mono">
            <Columns2 className="mr-1 h-3 w-3" />
            comparar objetos
          </Badge>
        </div>
        <p className="max-w-3xl text-muted-foreground">
          Traga tabelas para o canvas e coloque-as lado a lado para validar campos
          e similaridade — inclusive o mesmo schema em versões diferentes. Ative
          <strong> Comparar</strong> para colorir as diferenças e exporte um PNG
          para prints. O board fica salvo neste navegador.
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
                    Erro ao carregar o comparador
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
            <ReactFlowProvider>
              <Board />
            </ReactFlowProvider>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function Board() {
  const persisted = useMemo(() => loadPersisted(), []);
  const { fitView } = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);

  const [nodes, setNodes] = useState<Node[]>(() =>
    (persisted?.nodes ?? []).map((n) => ({
      id: n.id,
      type: "fieldCard",
      position: { x: n.x, y: n.y },
      data: { card: n.card },
      draggable: true,
    })),
  );
  const [compareOn, setCompareOn] = useState<boolean>(persisted?.compareOn ?? false);
  const [baseId, setBaseId] = useState<string | null>(persisted?.baseId ?? null);
  const [showAdd, setShowAdd] = useState(false);

  // Persiste o board (metadados + posições) no localStorage a cada mudança.
  useEffect(() => {
    const shape: PersistShape = {
      nodes: nodes.map((n) => ({
        id: n.id,
        card: (n.data as unknown as FieldCardData).card,
        x: n.position.x,
        y: n.position.y,
      })),
      baseId,
      compareOn,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(shape));
    } catch {
      /* quota cheia / modo privado — persistência é best-effort */
    }
  }, [nodes, baseId, compareOn]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  const onRemove = useCallback((id: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== id));
    setBaseId((b) => (b === id ? null : b));
  }, []);

  const addCard = useCallback((card: Omit<CompareCard, "id">) => {
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `card-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setNodes((nds) => {
      const n = nds.length;
      return [
        ...nds,
        {
          id,
          type: "fieldCard",
          position: { x: 40 + (n % 4) * 300, y: 40 + Math.floor(n / 4) * 90 },
          data: { card: { ...card, id } },
          draggable: true,
        },
      ];
    });
  }, []);

  const cards = useMemo<CompareCard[]>(
    () => nodes.map((n) => (n.data as unknown as FieldCardData).card),
    [nodes],
  );
  const baseCard = useMemo(
    () => cards.find((c) => c.id === baseId) ?? null,
    [cards, baseId],
  );

  // Ao ligar o modo comparar sem base definida, usa o primeiro cartão como base.
  useEffect(() => {
    if (compareOn && !baseId && cards.length > 0) setBaseId(cards[0].id);
  }, [compareOn, baseId, cards]);

  const selectedNodeId = useMemo(
    () => nodes.find((n) => n.selected)?.id ?? null,
    [nodes],
  );

  const fitToScreen = useCallback(
    () => fitView({ padding: 0.15, duration: 300, maxZoom: 1.5 }),
    [fitView],
  );

  const exportPng = useCallback(async () => {
    if (!canvasRef.current) return;
    const url = await toPng(canvasRef.current, { backgroundColor: "#ffffff" });
    const a = document.createElement("a");
    a.href = url;
    a.download = "nuclea-comparador.png";
    a.click();
  }, []);

  const exportNodePng = useCallback(async () => {
    if (!canvasRef.current || !selectedNodeId) {
      toast.error("Selecione um cartão no canvas para exportar");
      return;
    }
    const el = canvasRef.current.querySelector(
      `.react-flow__node[data-id="${CSS.escape(selectedNodeId)}"]`,
    ) as HTMLElement | null;
    if (!el) return;
    const url = await toPng(el, { backgroundColor: "#ffffff", pixelRatio: 2 });
    const a = document.createElement("a");
    a.href = url;
    a.download = "nuclea-cartao.png";
    a.click();
  }, [selectedNodeId]);

  const clearAll = useCallback(() => {
    if (nodes.length === 0) return;
    if (confirm("Limpar todos os cartões do canvas?")) {
      setNodes([]);
      setBaseId(null);
    }
  }, [nodes.length]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setShowAdd((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          Adicionar objeto
        </Button>
        <Button
          size="sm"
          variant={compareOn ? "default" : "outline"}
          onClick={() => setCompareOn((v) => !v)}
          title="Colorir diferenças de campos em relação ao cartão-base"
        >
          <GitCompare className="mr-2 h-4 w-4" />
          {compareOn ? "Comparando" : "Comparar"}
        </Button>
        {compareOn && (
          <label className="flex items-center gap-1 text-xs text-muted-foreground">
            base:
            <select
              className="rounded-md border bg-background px-2 py-1 text-xs"
              value={baseId ?? ""}
              onChange={(e) => setBaseId(e.target.value || null)}
            >
              <option value="">—</option>
              {cards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="flex-1" />
        <Button size="sm" variant="outline" onClick={fitToScreen} title="Encaixar na tela">
          <Maximize2 className="mr-2 h-4 w-4" />
          Encaixar
        </Button>
        <Button size="sm" variant="outline" onClick={exportPng} title="Exportar o board inteiro">
          <Download className="mr-2 h-4 w-4" />
          PNG
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={exportNodePng}
          disabled={!selectedNodeId}
          title="Exportar só o cartão selecionado"
        >
          <ImageDown className="mr-2 h-4 w-4" />
          PNG cartão
        </Button>
        <Button size="sm" variant="outline" onClick={clearAll} disabled={nodes.length === 0}>
          <Trash2 className="mr-2 h-4 w-4" />
          Limpar
        </Button>
      </div>

      {showAdd && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Adicionar objeto ao canvas</CardTitle>
              <CardDescription>
                Escolha uma tabela; adicione a versão atual ou uma versão publicada.
              </CardDescription>
            </div>
            <Button size="icon" variant="ghost" onClick={() => setShowAdd(false)}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <Suspense fallback={<Skeleton className="h-56 w-full" />}>
              <EntityPicker
                onAdd={(card) => {
                  addCard(card);
                  toast.success("Cartão adicionado");
                }}
              />
            </Suspense>
          </CardContent>
        </Card>
      )}

      {nodes.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nenhum objeto no canvas. Clique em <strong>Adicionar objeto</strong> para começar.
        </p>
      )}

      <div
        ref={canvasRef}
        className="h-[calc(100vh-18rem)] min-h-[520px] w-full rounded-md border bg-background"
      >
        <CompareContext.Provider value={{ compareOn, baseCard, onRemove }}>
          <ReactFlow
            nodes={nodes}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.2}
            maxZoom={2}
          >
            <Background gap={20} size={1} color="rgba(123, 45, 142, 0.08)" />
            <Controls position="bottom-right" />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </CompareContext.Provider>
      </div>
    </div>
  );
}

/** Seletor de tabela + (opcional) versão para adicionar um cartão. */
function EntityPicker({ onAdd }: { onAdd: (card: Omit<CompareCard, "id">) => void }) {
  const { data: entities } = useListEntitiesSuspense({}, selector());
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<EntityListOut | null>(null);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return entities
      .filter(
        (e) =>
          !s ||
          `${e.schema_name}.${e.technical_name}`.toLowerCase().includes(s) ||
          (e.system_name ?? "").toLowerCase().includes(s),
      )
      .slice(0, 100);
  }, [entities, q]);

  const keyOf = (e: EntityListOut) => `${e.schema_name}.${e.technical_name}`;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar tabela ou sistema..."
            className="pl-9"
          />
        </div>
        <ul className="mt-2 max-h-64 divide-y overflow-auto rounded-md border">
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground italic">
              Nenhuma tabela encontrada.
            </li>
          ) : (
            filtered.map((e) => (
              <li key={e.entity_id}>
                <button
                  type="button"
                  onClick={() => setSel(e)}
                  className={`w-full px-3 py-1.5 text-left hover:bg-muted/40 ${
                    sel?.entity_id === e.entity_id ? "bg-muted/60" : ""
                  }`}
                >
                  <span className="font-mono text-sm">{keyOf(e)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {e.system_name ?? e.system_id}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>

      <div>
        {sel ? (
          <div className="space-y-3">
            <p className="text-sm">
              Selecionado:{" "}
              <strong className="font-mono">{keyOf(sel)}</strong>
            </p>
            <Button
              size="sm"
              onClick={() =>
                onAdd({
                  source: "live",
                  entityId: sel.entity_id,
                  entityKey: keyOf(sel),
                  label: keyOf(sel),
                })
              }
            >
              <Plus className="mr-2 h-4 w-4" />
              Adicionar (atual)
            </Button>
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                Ou adicionar de uma versão publicada:
              </p>
              <Suspense fallback={<Skeleton className="h-8 w-full" />}>
                <VersionChips
                  systemId={sel.system_id}
                  entityKey={keyOf(sel)}
                  onAdd={onAdd}
                />
              </Suspense>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Escolha uma tabela na lista à esquerda.
          </p>
        )}
      </div>
    </div>
  );
}

/** Chips das versões publicadas do sistema — cada uma adiciona um cartão daquela versão. */
function VersionChips({
  systemId,
  entityKey,
  onAdd,
}: {
  systemId: string;
  entityKey: string;
  onAdd: (card: Omit<CompareCard, "id">) => void;
}) {
  const { data: versions } = useListVersionsSuspense(systemId, selector());
  if (versions.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic">
        Sem versões publicadas neste sistema.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-1">
      {versions.map((v) => (
        <Button
          key={v.version_id}
          size="sm"
          variant="outline"
          onClick={() =>
            onAdd({
              source: "version",
              versionId: v.version_id,
              entityKey,
              label: `${entityKey} @ ${v.version_number}`,
            })
          }
        >
          {v.version_number}
        </Button>
      ))}
    </div>
  );
}
