/**
 * Informações de versão/build exibidas no rodapé da sidebar.
 *
 * Objetivo: dar visibilidade rápida de "o que está deployado no cliente vs. a
 * última versão". A versão é um contador simples, independente do SemVer interno
 * do backend.
 *
 * ┌─ CONVENÇÃO DE VERSIONAMENTO (cumprir em TODA melhoria) ─────────────────────┐
 * │ Incremente APP_VERSION a cada melhoria entregue: 1.0001 → 1.0002 → 1.0003…  │
 * │ (registrado também no CLAUDE.md, seção "Documentação & manutenibilidade").   │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * BUILD_TIME é injetado pelo `vite build` (vite.config.ts `define`), que roda no
 * workflow build-dist.yml no merge para main — logo reflete quando o bundle
 * atualmente servido ao cliente foi gerado.
 */

/** Versão do app. INCREMENTE a cada melhoria (1.0001 → 1.0002 → …). */
export const APP_VERSION = "1.0012";

/** Instante do build da UI (ISO 8601), injetado no build. */
export const BUILD_TIME: string = __BUILD_TIME__;

/** BUILD_TIME formatado em pt-BR para exibição; cai no valor cru se inválido. */
export function formatBuildTime(): string {
  try {
    return new Date(BUILD_TIME).toLocaleString("pt-BR");
  } catch {
    return BUILD_TIME;
  }
}
