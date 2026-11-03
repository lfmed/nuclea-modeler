/**
 * Contraste visual do DER (rodada 9 consolidada, item 3d).
 *
 * Feedback do cliente: "deixar linhas mais espessas e visíveis, tais como os nomes
 * e linhas de relacionamento. Alterar a cor de fundo das tabelas a fim de
 * diferi-las do fundo." Causa no código: o cartão da tabela era `bg-card` sobre um
 * canvas `bg-background` — ambos ~branco — e as arestas tinham 1,5 px com rótulo
 * de 10 px cinza-claro.
 *
 * Decisão: um modo "alto" (NOVO PADRÃO) e o "padrão" anterior, alternável na
 * barra do DER e persistido no localStorage. É SÓ estilo: nada aqui toca em
 * handles/orientação das arestas (lógica sensível — v1.0027/v1.0051). Os estilos
 * de aresta são aplicados sobre o objeto devolvido por `relationshipToEdge`.
 */
import type { Edge } from "@xyflow/react";
import { MarkerType } from "@xyflow/react";

export type DerContrast = "standard" | "high";

export const DER_CONTRAST_KEY = "nuclea.der.contrast";

export function loadDerContrast(): DerContrast {
  try {
    const v = localStorage.getItem(DER_CONTRAST_KEY);
    if (v === "standard" || v === "high") return v;
  } catch {
    /* storage indisponível */
  }
  return "high";
}

export function saveDerContrast(v: DerContrast) {
  try {
    localStorage.setItem(DER_CONTRAST_KEY, v);
  } catch {
    /* modo privado — só não persiste */
  }
}

/** Fundo do canvas: no alto contraste, cinza-claro para o cartão branco destacar. */
export const CANVAS_BG_CLASS: Record<DerContrast, string> = {
  standard: "bg-background",
  high: "bg-slate-100 dark:bg-slate-900",
};

/** Cor dos pontos do grid de fundo (React Flow <Background color>). */
export const GRID_COLOR: Record<DerContrast, string> = {
  standard: "rgba(123, 45, 142, 0.08)",
  high: "rgba(71, 85, 105, 0.18)",
};

const EDGE = {
  standard: { stroke: "#832ED9", width: 1.5, label: 10, labelFill: "#6b7280", labelWeight: 400, arrow: 18 },
  // Roxo mais escuro (#6B21A8) lê melhor sobre o cinza e em impressão.
  high: { stroke: "#6B21A8", width: 2.5, label: 12, labelFill: "#111827", labelWeight: 600, arrow: 22 },
} as const;

/** Aplica o estilo do contraste a uma aresta. `selected` engrossa e realça a linha. */
export function styleEdge(e: Edge, contrast: DerContrast, selected = false): Edge {
  const c = EDGE[contrast];
  const stroke = selected ? "#C026D3" : c.stroke;
  return {
    ...e,
    style: { ...e.style, stroke, strokeWidth: selected ? c.width + 1.5 : c.width },
    labelStyle: { ...e.labelStyle, fontSize: c.label, fill: c.labelFill, fontWeight: c.labelWeight },
    labelBgPadding: contrast === "high" ? [6, 3] : e.labelBgPadding,
    labelBgStyle:
      contrast === "high"
        ? { fill: "#ffffff", fillOpacity: 1, stroke: "#94a3b8" }
        : e.labelBgStyle,
    // markerUnits fixo em px: o padrão do React Flow ("strokeWidth") ESCALA a seta
    // com a espessura — com 2.5–4 px ela ficaria desproporcional.
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: stroke,
      width: c.arrow,
      height: c.arrow,
      markerUnits: "userSpaceOnUse",
    },
  };
}
