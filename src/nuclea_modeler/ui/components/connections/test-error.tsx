/**
 * Exibição do erro de teste de conexão + diagnóstico (rodada 9, item 3).
 *
 * O backend (`connections/testers.py::classify_db_error`) classifica a falha
 * (DNS, rede, porta recusada, autenticação, SSL, banco inexistente, driver) e
 * PERSISTE em `last_test_error` o texto cru do driver seguido de
 * "\nDiagnóstico: <o que fazer>" — sem coluna nova no schema. Aqui separamos as
 * duas partes: o erro técnico fica no bloco vermelho (para o DBA/infra) e o
 * diagnóstico vira um aviso legível para quem cadastrou a conexão.
 */
import { Lightbulb } from "lucide-react";

export const DIAGNOSIS_SEP = "\nDiagnóstico: ";

export function splitDiagnosis(error: string): { raw: string; hint: string | null } {
  const i = error.indexOf(DIAGNOSIS_SEP);
  if (i < 0) return { raw: error, hint: null };
  return { raw: error.slice(0, i), hint: error.slice(i + DIAGNOSIS_SEP.length) };
}

export function ConnectionTestError({ error }: { error: string }) {
  const { raw, hint } = splitDiagnosis(error);
  return (
    <div className="mt-2 space-y-2">
      {hint && (
        <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-200">
          <Lightbulb className="h-4 w-4 shrink-0" />
          <p>
            <strong>Diagnóstico:</strong> {hint}
          </p>
        </div>
      )}
      <pre className="rounded-md bg-destructive/10 p-3 text-xs whitespace-pre-wrap text-destructive">
        {raw}
      </pre>
    </div>
  );
}
