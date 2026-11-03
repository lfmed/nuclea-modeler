/**
 * Qualidade do export PNG do DER (rodada 9, item 8 — "aumentar a resolução das
 * imagens exportadas").
 *
 * O PNG é raster: a nitidez ao ampliar depende dos pixels REAIS (largura CSS do
 * modelo × pixelRatio). O limite real é o canvas do browser: lados acima de
 * ~16k px ou áreas acima de algumas centenas de MP fazem o `toPng` rejeitar ou
 * devolver imagem vazia (Chrome ~16384 px/lado de forma confiável; Safari é mais
 * restrito). Por isso cada preset tem um ALVO e TETOS; o ratio efetivo é o
 * maior que respeita os tetos, nunca abaixo de 1x — o modelo sai SEMPRE completo.
 *
 * Para nitidez em qualquer zoom, o caminho certo é o SVG (vetorial, v1.0067); o
 * PNG "Máxima" é para quem precisa de raster (ex.: colar em documento/slide).
 */

export type PngQuality = "standard" | "high" | "max";

export interface PngQualityPreset {
  label: string;
  /** pixelRatio alvo (pixels reais por px CSS). */
  ratio: number;
  /** teto por lado em px reais. */
  maxSide: number;
  /** teto de área em px reais (memória do canvas ≈ área × 4 bytes). */
  maxArea: number;
}

export const PNG_QUALITY_PRESETS: Record<PngQuality, PngQualityPreset> = {
  // O "padrão" é o comportamento da v1.0066 (3x, 12k px, 50 MP).
  standard: { label: "Qualidade: padrão", ratio: 3, maxSide: 12_000, maxArea: 50_000_000 },
  high: { label: "Qualidade: alta", ratio: 4, maxSide: 16_384, maxArea: 100_000_000 },
  // ~150 MP ≈ 600 MB de canvas: funciona em desktop com memória folgada; se falhar,
  // o export cai em degraus (ver exportPng no diagram.tsx).
  max: { label: "Qualidade: máxima", ratio: 6, maxSide: 16_384, maxArea: 150_000_000 },
};

export const PNG_QUALITY_KEY = "nuclea.der.pngQuality";

export function loadPngQuality(): PngQuality {
  try {
    const v = localStorage.getItem(PNG_QUALITY_KEY);
    if (v === "standard" || v === "high" || v === "max") return v;
  } catch {
    /* storage indisponível */
  }
  return "high";
}

/** Maior pixelRatio ≤ alvo que respeita os tetos de lado e de área (mínimo 1). */
export function pngPixelRatio(width: number, height: number, preset: PngQualityPreset): number {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  let r = preset.ratio;
  r = Math.min(r, preset.maxSide / w, preset.maxSide / h);
  r = Math.min(r, Math.sqrt(preset.maxArea / (w * h)));
  return Math.max(1, r);
}
