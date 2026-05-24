import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_WIDTH = 280;
const NODE_HEIGHT_COMPACT = 80;
const NODE_HEIGHT_EXPANDED = (attrs: number) => 80 + attrs * 24;

export type LayoutDirection = "LR" | "TB" | "RL" | "BT";

export function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: direction,
    nodesep: 60,
    ranksep: 120,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    const attrs = ((node.data as any)?.entity?.attributes?.length as number) ?? 0;
    const height = expanded ? NODE_HEIGHT_EXPANDED(attrs) : NODE_HEIGHT_COMPACT;
    g.setNode(node.id, { width: NODE_WIDTH, height });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
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
