/**
 * Helpers para persistência de estado de tela (URL search params + sessionStorage).
 *
 * Padrão de uso:
 * 1. URL search params como fonte primária (compartilhável, bookmarkável).
 * 2. sessionStorage como fallback: guarda o ÚLTIMO sistema visto para restaurar
 *    ao abrir uma tela sem query params (ex., DER sem ?system=).
 *
 * Inspirado no padrão de sync.index.tsx (SYNC_PREFS_KEY).
 */

const LAST_SYSTEM_KEY = "nuclea.lastSystem";

/**
 * Lê o último sistema visto de sessionStorage.
 * Retorna undefined se não houver ou se houver erro na desserialização.
 */
export function getLastSystemId(): string | undefined {
  try {
    const stored = sessionStorage.getItem(LAST_SYSTEM_KEY);
    if (stored) return stored;
  } catch {
    // best-effort: pode falhar em ambiente private-browsing
  }
  return undefined;
}

/**
 * Salva o sistema atual em sessionStorage para pré-preenchimento futuro.
 */
export function saveLastSystemId(systemId: string) {
  try {
    sessionStorage.setItem(LAST_SYSTEM_KEY, systemId);
  } catch {
    // best-effort
  }
}

/**
 * Remove o sistema salvo (ex., ao fazer logout ou reset).
 */
export function clearLastSystemId() {
  try {
    sessionStorage.removeItem(LAST_SYSTEM_KEY);
  } catch {
    // best-effort
  }
}

/**
 * Seleciona o "sistema padrão":
 * 1. Se systemFromUrl está definida (vem da query), a URL é a fonte da verdade.
 * 2. Senão, tenta usar o último sistema salvo em sessionStorage.
 * 3. Senão, usa o primeiro da lista (fallback).
 * 4. Se nenhuma destas, retorna string vazia.
 *
 * Uso típico no DER ou listagens:
 *   const systemId = selectDefaultSystemId(systemFromUrl, systems);
 */
export function selectDefaultSystemId(
  systemFromUrl: string | undefined,
  systemsList: Array<{ system_id: string }>,
): string {
  // URL é a fonte da verdade
  if (systemFromUrl && systemsList.some((s) => s.system_id === systemFromUrl)) {
    return systemFromUrl;
  }

  // Tenta o último sistema salvo
  const lastSystemId = getLastSystemId();
  if (lastSystemId && systemsList.some((s) => s.system_id === lastSystemId)) {
    return lastSystemId;
  }

  // Fallback: primeiro da lista ou string vazia
  return systemsList[0]?.system_id || "";
}

/**
 * Helper para coerce de string para boolean (para URL search params).
 * Retorna undefined se value for undefined/empty.
 */
export function coerceBool(value: string | undefined): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

/**
 * Helper para coerce de string para número (para URL search params).
 * Retorna undefined se value for undefined/empty, ou NaN.
 */
export function coerceNumber(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const n = Number(value);
  return Number.isNaN(n) ? undefined : n;
}
