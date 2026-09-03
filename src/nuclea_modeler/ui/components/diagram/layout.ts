import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_WIDTH = 280;
const NODE_HEIGHT_COMPACT = 80;
// Altura por atributo: 24 → 30. Medido AO VIVO (offsetHeight, imune ao zoom): cada
// linha de atributo ocupa ~29px, não 24. Com 24, a estimativa SUBESTIMAVA a altura
// de 13/34 nós (até 19px cada) → o resolveOverlaps achava que tinha desempilhado,
// mas sobrava sobreposição vertical REAL (~40px) no layout força. Com 30 a
// estimativa fica ≥ real para TODOS os nós (super-estima ~1-2 linhas), então o
// resolvedor deixa folga garantida e não sobra overlap. (A largura 280 já
// super-estima a real ~240, então o eixo X nunca foi o problema.)
const NODE_HEIGHT_EXPANDED = (attrs: number) => 80 + attrs * 30;

export type LayoutDirection = "LR" | "TB" | "RL" | "BT";

/**
 * Modo de layout automático do DER.
 * - hierarchical: disposição hierárquica por níveis (Dagre rankdir TB/LR)
 * - tree: variante de hierárquico com ranker "tight-tree" (para árvores reais)
 * - circular: nós dispostos num círculo, ordem estável por ID
 * - orthogonal: arestas em ângulos retos (Dagre com configuração ortogonal)
 * - force: algoritmo simples de forças (repulsão + atração por arestas)
 */
export type LayoutMode = "hierarchical" | "tree" | "circular" | "orthogonal" | "force";

/**
 * Altura de um node do DER, para o anti-sobreposição e o bounding box.
 *
 * PREFERE a altura REAL medida pelo React Flow (`node.measured.height`), que já
 * está disponível quando o usuário dispara o Auto-layout (os nós estão na tela).
 * Isso é crucial: a ESTIMATIVA `80 + attrs*30` não cobre linhas extras que o
 * EntityNode às vezes renderiza (índices, descrição) — nós com 5 atributos podiam
 * medir como 7 linhas. Com a estimativa curta, o resolveOverlaps operava num
 * espaço MENOR que o real e deixava sobreposição vertical (bug da força). Usando a
 * medida real, o de-overlap acontece no espaço real → zero sobreposição.
 *
 * Fallback para a estimativa só quando não há medida (ex.: layout incremental de
 * import, com nós ainda não renderizados).
 */
function nodeHeight(node: Node, expanded: boolean): number {
  const measured = (node as any).measured?.height as number | undefined;
  if (measured && measured > 0) return measured;
  const attrs = ((node.data as any)?.entity?.attributes?.length as number) ?? 0;
  return expanded ? NODE_HEIGHT_EXPANDED(attrs) : NODE_HEIGHT_COMPACT;
}

/** Largura de um node — real medida (React Flow) quando disponível; senão a
 * constante (que já super-estima a real ~240, folga segura no eixo X). */
function nodeWidth(node: Node): number {
  const measured = (node as any).measured?.width as number | undefined;
  return measured && measured > 0 ? measured : NODE_WIDTH;
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
    maxX = Math.max(maxX, x + nodeWidth(n));
    maxY = Math.max(maxY, y + nodeHeight(n, expanded));
  }
  return { minX, minY, maxX, maxY };
}

/**
 * Anti-sobreposição (round 5, pt 13): garante que NENHUM par de tabelas fique
 * sobreposto após um layout automático. O Dagre normalmente já separa os nós, mas
 * a altura estimada (`nodeHeight`) depende do nº de atributos — se um nó vier mais
 * alto do que o estimado, dava sobreposição vertical. Os layouts circular/força/
 * ortogonal também podem colidir. Esta passagem empurra pares que se sobrepõem no
 * eixo de MENOR penetração (movimento mínimo → layout estável), com uma folga.
 *
 * Só mexe em nós REALMENTE sobrepostos (interseção de área > 0); nós que apenas se
 * encostam ficam parados. Aplicada apenas em layouts AUTOMÁTICOS — nunca sobre as
 * posições salvas/arrastadas manualmente (essas passam pelo caminho "positioned"
 * do layout incremental, que não chama esta função).
 */
function resolveOverlaps(
  nodes: Node[],
  expanded: boolean,
  gap = 28,
  // maxIter 10 → 400. Medido AO VIVO (v1.0051 ainda deixava ~7 sobreposições na
  // força com 34 nós): a força nasce MUITO aglomerada e o empurra-pares precisa de
  // ~174 iterações para convergir a partir do pior caso (60 deixava 27 pares; 150
  // deixava 12; 300 zerava em 174). 400 dá margem. Como o laço PARA assim que
  // converge (nenhum par sobreposto), o custo extra só existe enquanto ainda há
  // colisão — trivial para os diagramas típicos e garante zero sobreposição.
  maxIter = 400,
): Node[] {
  if (nodes.length < 2) return nodes;
  const out = nodes.map((n) => ({ ...n, position: { ...n.position } }));
  for (let iter = 0; iter < maxIter; iter++) {
    let moved = false;
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const a = out[i];
        const b = out[j];
        const ah = nodeHeight(a, expanded);
        const bh = nodeHeight(b, expanded);
        const aw = nodeWidth(a);
        const bw = nodeWidth(b);
        // Penetração (positiva = sobrepõe) em cada eixo. Usa a largura REAL de
        // cada nó (medida) — antes assumia NODE_WIDTH fixo p/ ambos.
        const penX =
          Math.min(a.position.x + aw, b.position.x + bw) -
          Math.max(a.position.x, b.position.x);
        const penY =
          Math.min(a.position.y + ah, b.position.y + bh) -
          Math.max(a.position.y, b.position.y);
        if (penX > 0 && penY > 0) {
          moved = true;
          if (penX < penY) {
            const push = (penX + gap) / 2;
            if (a.position.x <= b.position.x) {
              a.position.x -= push;
              b.position.x += push;
            } else {
              a.position.x += push;
              b.position.x -= push;
            }
          } else {
            const push = (penY + gap) / 2;
            if (a.position.y <= b.position.y) {
              a.position.y -= push;
              b.position.y += push;
            } else {
              a.position.y += push;
              b.position.y -= push;
            }
          }
        }
      }
    }
    if (!moved) break; // convergiu — nenhum par sobreposto restante
  }
  return out;
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
    g.setNode(node.id, { width: nodeWidth(node), height });
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

  const laid = nodes.map((node) => {
    const meta = g.node(node.id);
    if (!meta) return node;
    return {
      ...node,
      position: { x: meta.x - meta.width / 2, y: meta.y - meta.height / 2 },
    };
  });
  // Rede de segurança anti-sobreposição (round 5, pt 13). Como o incremental chama
  // applyDagreLayout só nos nós NOVOS, isto nunca move posições salvas.
  return resolveOverlaps(laid, expanded);
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

// ───────────────────────────────────────────────────────────────────────────
// Algoritmos de layout alternativos para suporte a múltiplos formatos.
// ───────────────────────────────────────────────────────────────────────────

/**
 * Layout circular — posiciona nós em círculo com ordem estável por ID.
 *
 * Algoritmo:
 * 1. Ordena nós por ID para garantir determinismo
 * 2. Calcula raio do círculo proporcional ao sqrt(N) para evitar aglomeração
 * 3. Distribui nós uniformemente em ângulos (2π / N) ao redor do centro
 * 4. Centraliza o layout na origem para padronização
 *
 * Decisões:
 * - Raio base = 100 + (N-1) * 40 para acomodar mais nós sem sobreposição
 * - Ordem por ID garante layout determinístico entre rerenders
 */
export function applyCircularLayout(nodes: Node[], expanded: boolean = true): Node[] {
  if (nodes.length === 0) return nodes;

  // Ordena por ID para determinismo
  const sorted = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const n = sorted.length;

  // Raio adaptativo. ANTES era só função de N (100 + (N-1)*40), ignorando a
  // LARGURA/ALTURA real das tabelas — com nós largos (280px) ou altos (modo
  // expandido) o círculo ficava apertado e as tabelas encavalavam (bug relatado).
  // A corda entre dois nós vizinhos no círculo é 2*R*sin(π/N); para não
  // sobreporem, ela precisa ser ≥ maior dimensão do nó + folga. Resolvemos R por
  // aí e usamos o MAIOR entre o raio adaptativo e esse mínimo geométrico.
  const gap = 64;
  const maxExtent = Math.max(
    ...sorted.map((node) => Math.max(nodeWidth(node), nodeHeight(node, expanded))),
  );
  const minRadiusNoOverlap =
    n > 1 ? (maxExtent + gap) / (2 * Math.sin(Math.PI / n)) : 0;
  const radius = Math.max(140, 100 + (n - 1) * 40, minRadiusNoOverlap);

  // Calcula posições ao longo do círculo
  const positioned = sorted.map((node, i) => {
    // Ângulo uniforme: começa no topo (3π/2 = -90°) e gira em sentido horário
    const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
    const x = radius * Math.cos(angle);
    const y = radius * Math.sin(angle);

    return {
      ...node,
      position: {
        x: x - NODE_WIDTH / 2,
        y: y - NODE_HEIGHT_COMPACT / 2,
      },
    };
  });

  // Centraliza: calcula bbox e desloca para origem
  const bbox = boundingBox(positioned, false);
  if (!bbox) return positioned;

  const offsetX = -bbox.minX + 50;
  const offsetY = -bbox.minY + 50;

  return positioned.map((n) => ({
    ...n,
    position: {
      x: n.position.x + offsetX,
      y: n.position.y + offsetY,
    },
  }));
}

/**
 * Layout com ranker "tight-tree" do Dagre — variante de hierárquico para árvores.
 *
 * Diferença vs hierarchical: usa ranker "tight-tree" que produz layouts
 * mais compactos e alinhados à estrutura de árvore, reduzindo espaço vazio
 * desnecessário em grafos com alta conectividade hierárquica.
 */
export function applyTreeLayout(
  nodes: Node[],
  edges: Edge[],
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: direction,
    ranker: "tight-tree", // Ranker específico para árvores
    nodesep: 80,
    ranksep: 150,
    edgesep: 20,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    const height = nodeHeight(node, expanded);
    g.setNode(node.id, { width: NODE_WIDTH, height });
  }

  for (const edge of edges) {
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

/**
 * Layout ortogonal — similiar a hierárquico mas com espaçamento adaptado
 * para arestas em ângulos retos (0°, 90°, 180°, 270°).
 *
 * Usa Dagre com rankdir TB (vertical) + espaçamento aumentado para dar
 * espaço às arestas ortogonais se dobrarem. Não há ranker específico;
 * a configuração de spacing é o que diferencia.
 */
export function applyOrthogonalLayout(
  nodes: Node[],
  edges: Edge[],
  expanded: boolean = true,
): Node[] {
  const g = new dagre.graphlib.Graph();
  // rankdir TB força layout vertical (mais comum em ER). Espaçamento aumentado
  // para acomodar curvas das arestas ortogonais.
  g.setGraph({
    rankdir: "TB",
    nodesep: 120,    // Maior afastamento horizontal
    ranksep: 200,    // Maior afastamento vertical
    edgesep: 50,     // Mais espaço entre arestas para evitar sobreposição
    marginx: 60,
    marginy: 60,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    const height = nodeHeight(node, expanded);
    g.setNode(node.id, { width: NODE_WIDTH, height });
  }

  for (const edge of edges) {
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

/**
 * Layout com forças simples — algoritmo iterativo de repulsão + atração.
 *
 * Algoritmo (n iterações):
 * 1. Cada nó repele outros nós (força proporcional ao inverso da distância)
 * 2. Nós conectados por arestas se atraem (força proporcional à distância atual)
 * 3. Força de amortecimento reduz movimento a cada iteração
 * 4. Todas as forças são acumuladas e aplicadas em paralelo
 *
 * Decisões de implementação:
 * - N = 100 iterações (balanço entre qualidade e performance)
 * - K_rep = 50000 (constante de repulsão — aumentar afasta mais)
 * - K_attr = 0.1 (constante de atração — reduzir enfraquece a ligação)
 * - Damping = 0.95 (amortecimento — valores próximos a 1 suavizam mais)
 * - Distância mínima = 100px para evitar divisão por zero
 * - Ordem inicial aleatória para explorar o espaço
 */
export function applyForceLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  // Cópia mutável com posições iniciais aleatórias
  const positions: Map<string, { x: number; y: number; vx: number; vy: number }> = new Map();
  const random = (seed: string) => {
    // Hash simples do ID para pseudoaleatoriedade determinística
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = ((hash << 5) - hash) + seed.charCodeAt(i);
      hash = hash & hash; // Converte para 32-bit
    }
    return (Math.sin(hash) + 1) / 2; // Normaliza para [0,1]
  };

  for (const node of nodes) {
    const r1 = random(node.id + "_x");
    const r2 = random(node.id + "_y");
    positions.set(node.id, {
      x: r1 * 800 - 400,
      y: r2 * 600 - 300,
      vx: 0,
      vy: 0,
    });
  }

  // Parâmetros do algoritmo. K_REP e MIN_DIST foram AUMENTADOS: com repulsão
  // fraca (50000) e MIN_DIST=100 os nós assentavam a ~150px — MENOS que a largura
  // de uma tabela (280px) — e ficavam sobrepostos. Como o nó é uma CAIXA (não um
  // ponto), a distância de equilíbrio precisa superar a maior dimensão do nó.
  // Elevamos a repulsão e o piso de distância para o layout já nascer arejado; o
  // resolveOverlaps abaixo é a rede de segurança final.
  const K_REP = 250000;    // Constante de repulsão (mais forte → mais afastado)
  const K_ATTR = 0.1;      // Constante de atração
  const DAMPING = 0.9;     // Amortecimento de velocidade
  const MIN_DIST = 260;    // Piso de distância ~ largura de um nó (evita encavalar)
  const ITERATIONS = 160;  // Iterações de simulação

  // Simulação de forças
  for (let iter = 0; iter < ITERATIONS; iter++) {
    // Zera acumulador de forças
    const forces: Map<string, { fx: number; fy: number }> = new Map();
    for (const node of nodes) {
      forces.set(node.id, { fx: 0, fy: 0 });
    }

    // Repulsão: cada par de nós se repele
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const nodeA = nodes[i];
        const nodeB = nodes[j];
        const posA = positions.get(nodeA.id)!;
        const posB = positions.get(nodeB.id)!;

        const dx = posB.x - posA.x;
        const dy = posB.y - posA.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), MIN_DIST);

        // Força de repulsão (inverso da distância)
        const force = K_REP / (dist * dist);
        const fx = (force * dx) / dist;
        const fy = (force * dy) / dist;

        // Aplica força em sentidos opostos
        forces.get(nodeA.id)!.fx -= fx;
        forces.get(nodeA.id)!.fy -= fy;
        forces.get(nodeB.id)!.fx += fx;
        forces.get(nodeB.id)!.fy += fy;
      }
    }

    // Atração: nós conectados se atraem
    for (const edge of edges) {
      const posA = positions.get(edge.source);
      const posB = positions.get(edge.target);
      if (!posA || !posB) continue;

      const dx = posB.x - posA.x;
      const dy = posB.y - posA.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // Força de atração (proporcional à distância)
      const force = K_ATTR * dist;
      const fx = (force * dx) / Math.max(dist, 1);
      const fy = (force * dy) / Math.max(dist, 1);

      forces.get(edge.source)!.fx += fx;
      forces.get(edge.source)!.fy += fy;
      forces.get(edge.target)!.fx -= fx;
      forces.get(edge.target)!.fy -= fy;
    }

    // Atualiza velocidades e posições
    for (const node of nodes) {
      const pos = positions.get(node.id)!;
      const force = forces.get(node.id)!;

      pos.vx = (pos.vx + force.fx) * DAMPING;
      pos.vy = (pos.vy + force.fy) * DAMPING;
      pos.x += pos.vx;
      pos.y += pos.vy;
    }
  }

  // Centraliza e normaliza posições para o canvas
  const bbox = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const pos of positions.values()) {
    bbox.minX = Math.min(bbox.minX, pos.x);
    bbox.minY = Math.min(bbox.minY, pos.y);
    bbox.maxX = Math.max(bbox.maxX, pos.x);
    bbox.maxY = Math.max(bbox.maxY, pos.y);
  }

  const offsetX = -bbox.minX + 50;
  const offsetY = -bbox.minY + 50;

  return nodes.map((node) => {
    const pos = positions.get(node.id)!;
    return {
      ...node,
      position: {
        x: pos.x + offsetX - NODE_WIDTH / 2,
        y: pos.y + offsetY - NODE_HEIGHT_COMPACT / 2,
      },
    };
  });
}

/**
 * Aplica um layout de acordo com o modo escolhido.
 *
 * Esta é a função pública principal para aplicar diferentes formatos.
 * Centraliza a lógica de seleção de algoritmo.
 */
export function applyLayoutByMode(
  nodes: Node[],
  edges: Edge[],
  mode: LayoutMode,
  direction: LayoutDirection = "LR",
  expanded: boolean = true,
): Node[] {
  let laid: Node[];
  switch (mode) {
    case "hierarchical":
      laid = applyDagreLayout(nodes, edges, direction, expanded);
      break;
    case "tree":
      laid = applyTreeLayout(nodes, edges, direction, expanded);
      break;
    case "circular":
      laid = applyCircularLayout(nodes, expanded);
      break;
    case "orthogonal":
      laid = applyOrthogonalLayout(nodes, edges, expanded);
      break;
    case "force":
      laid = applyForceLayout(nodes, edges);
      break;
    default:
      laid = applyDagreLayout(nodes, edges, direction, expanded);
  }
  // Anti-sobreposição em TODOS os modos (round 5, pt 13) — circular/força/ortogonal
  // podem colidir; dagre já é resolvido internamente, aqui é idempotente.
  return resolveOverlaps(laid, expanded);
}
