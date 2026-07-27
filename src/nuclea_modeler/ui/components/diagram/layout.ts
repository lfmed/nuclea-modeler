import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_WIDTH = 280;
const NODE_HEIGHT_COMPACT = 80;
const NODE_HEIGHT_EXPANDED = (attrs: number) => 80 + attrs * 24;

export type LayoutDirection = "LR" | "TB" | "RL" | "BT";

/**
 * Altura estimada de um node do DER. Precisa bater com a lógica usada no dagre
 * (nós expandidos crescem com o nº de atributos) para o bounding box do layout
 * incremental ficar correto — senão os nós novos poderiam sobrepor os já
 * organizados.
 */
function nodeHeight(node: Node, expanded: boolean): number {
  const attrs = ((node.data as any)?.entity?.attributes?.length as number) ?? 0;
  return expanded ? NODE_HEIGHT_EXPANDED(attrs) : NODE_HEIGHT_COMPACT;
}

/**
 * Bounding box (em coordenadas de canvas) de um conjunto de nós já posicionados.
 * `position` no React Flow é o canto superior-esquerdo do node.
 */
function boundingBox(
  nodes: Node[],
  expanded: boolean,
): { minX: number; minY: number; maxX: number; maxY: number } | null {
  if (nodes.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    const x = n.position.x;
    const y = n.position.y;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + NODE_WIDTH);
    maxY = Math.max(maxY, y + nodeHeight(n, expanded));
  }
  return { minX, minY, maxX, maxY };
}

/**
 * Layout Dagre "do zero" — reposiciona TODOS os nós recebidos. Usado quando o
 * diagrama ainda não tem nenhuma posição salva (tudo novo) ou pelo botão
 * "Auto-organizar tudo" (que sobrescreve posições manuais de propósito).
 */
export function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: direction,
    // Mais folga melhora a legibilidade — nós expandidos (com colunas) são
    // altos; nodesep maior evita sobreposição vertical e ranksep separa melhor
    // os níveis. edgesep reduz cruzamento de arestas próximas.
    nodesep: 90,
    ranksep: 170,
    edgesep: 30,
    marginx: 48,
    marginy: 48,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    const height = nodeHeight(node, expanded);
    g.setNode(node.id, { width: NODE_WIDTH, height });
  }
  for (const edge of edges) {
    // Dagre lança erro se a aresta referencia um node fora do grafo. Ao rodar
    // um layout PARCIAL (só nós novos) chegam arestas apontando pra nós fora do
    // subconjunto — filtramos essas para não quebrar o dagre.
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const meta = g.node(node.id);
    if (!meta) return node;
    return {
      ...node,
      position: { x: meta.x - meta.width / 2, y: meta.y - meta.height / 2 },
    };
  });
}

// Folga (px) entre o bloco de nós já organizados e o bloco de nós novos.
const INCREMENTAL_GAP = 160;

/**
 * Layout INCREMENTAL — o núcleo da correção do bug de auto-distribuição.
 *
 * Contexto do bug (v1.0014): ao importar entidades novas (DDL/DM1) para um
 * diagrama que já tinha layout, os nós novos vinham sem posição (pos NULL) e
 * caíam todos em (0,0), empilhados e invisíveis. A detecção antiga era binária
 * ("algum nó tem posição? então não roda dagre em NADA"), então nada os
 * distribuía.
 *
 * Estratégia (a ordem/decisão importa):
 *   1. Se não há nós novos → nada a fazer, devolve os já posicionados.
 *   2. Se NÃO há nós posicionados → é tudo novo: roda Dagre em todos (idêntico
 *      ao comportamento legado quando o diagrama é criado do zero).
 *   3. Caso misto (o cenário do bug): PRESERVA as posições dos nós já
 *      organizados e roda Dagre APENAS entre os nós novos (com as arestas
 *      internas ao subconjunto). Depois desloca esse sub-layout para a DIREITA
 *      do bounding box dos existentes (alinhando o topo), de modo que os novos
 *      apareçam agrupados e visíveis SEM re-embaralhar o que o usuário já
 *      posicionou manualmente.
 *
 * `positioned` carregam posições reais (salvas); `unpositioned` são os nós sem
 * posição salva — a posição atual deles é ignorada e recalculada aqui.
 */
export function applyIncrementalLayout(
  positioned: Node[],
  unpositioned: Node[],
  edges: Edge[],
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  if (unpositioned.length === 0) return positioned;
  if (positioned.length === 0) {
    // Tudo novo → layout completo (comportamento legado do diagrama vazio).
    return applyDagreLayout(unpositioned, edges, direction, expanded);
  }

  // Layout só entre os nós novos. Passamos todas as arestas; applyDagreLayout
  // já ignora as que apontam para fora do subconjunto.
  const laid = applyDagreLayout(unpositioned, edges, direction, expanded);

  const bbox = boundingBox(positioned, expanded);
  if (!bbox) return [...positioned, ...laid];

  // Origem do sub-layout dos novos (canto superior-esquerdo do bloco novo).
  const laidBox = boundingBox(laid, expanded);
  const laidMinX = laidBox ? laidBox.minX : 0;
  const laidMinY = laidBox ? laidBox.minY : 0;

  // Desloca os novos para a direita do bloco existente, alinhando os topos.
  const offsetX = bbox.maxX + INCREMENTAL_GAP - laidMinX;
  const offsetY = bbox.minY - laidMinY;

  const shifted = laid.map((n) => ({
    ...n,
    position: { x: n.position.x + offsetX, y: n.position.y + offsetY },
  }));

  return [...positioned, ...shifted];
}

/**
 * Helper de conveniência para o canvas. Recebe TODOS os nós (os posicionados já
 * com sua posição salva; os não-posicionados com posição qualquer/placeholder)
 * + o conjunto de ids que têm posição salva, e devolve o layout final aplicando
 * a estratégia incremental. Centraliza a decisão para os dois momentos em que o
 * canvas recalcula posições (troca de estrutura e refetch de membros).
 */
export function layoutWithSavedPositions(
  nodes: Node[],
  positionedIds: Set<string>,
  edges: Edge[],
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  const positioned = nodes.filter((n) => positionedIds.has(n.id));
  const unpositioned = nodes.filter((n) => !positionedIds.has(n.id));
  return applyIncrementalLayout(positioned, unpositioned, edges, direction, expanded);
}
