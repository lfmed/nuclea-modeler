/**
 * Célula de "CHECK constraint" de coluna EDITÁVEL inline (round 7, item 21).
 *
 * Compartilhada entre a tela do objeto (`entities.$id.tsx`) e o editor de atributos
 * do DER (`diagram.tsx` → AttributesEditor), para o cliente definir/editar o CHECK de
 * uma coluna nos DOIS lugares com a MESMA UX — irmã da `AttrDefaultCell`.
 *
 * PORQUÊ desta célula (feedback do cliente, round 7): antes o CHECK só podia ser
 * preenchido no form de "novo atributo". Numa tabela IMPORTADA (colunas já existentes)
 * não havia como preencher/testar o CHECK — o cliente "não localizou" o recurso.
 * Tornando o CHECK editável na própria linha da coluna, ele fica descoberto e
 * testável no modelo real (preencher aqui → exportar DDL → sai `CHECK (...)`).
 *
 * O valor é exportado no DDL (backend `ddl/generators._build_columns_block`) na aba
 * "Exportar DDL": ex. `situacao INT NOT NULL CHECK (situacao IN (0,1))`. Guarda-se
 * SÓ a expressão (sem os parênteses externos) — o gerador envelopa em `CHECK (...)`.
 *
 * Por que <input> (e não textarea): a expressão é curta (ex.: `situacao IN (0,1)`,
 * `valor >= 0`). Enter salva, Esc cancela.
 *
 * O `onSave` faz o stage via ticket; o caller reenvia o payload COMPLETO do atributo
 * (o merge do staging é "última intenção vence" por field-key — ver saveAttrCheck).
 * String vazia "" limpa o CHECK (o apply de atributo filtra None, então null nunca
 * limparia; "" passa no filtro e zera) — mesma disciplina do DEFAULT/descrição.
 */
import { useState } from "react";
import { Pencil } from "lucide-react";

/**
 * Normaliza a expressão de CHECK digitada (round 7 — achados do Isaac Review).
 * - Espaços nas pontas removidos; um valor SÓ de espaços vira "" (limpa de fato —
 *   senão a coluna mostraria "CHECK definido" mas o export, que dá `.strip()`, não
 *   emitiria nada → indicação enganosa).
 * - Desembrulha uma CLÁUSULA colada por engano: o rótulo diz "CHECK", então é natural
 *   o usuário colar `CHECK (situacao IN (0,1))`. Guardamos SÓ a expressão porque o
 *   export já envelopa em `CHECK (...)`; sem isso sairia `CHECK (CHECK (...))` inválido.
 *   Só desembrulha quando os parênteses externos formam UM par que casa (não toca em
 *   `(a > 0) AND (b < 10)`).
 */
export function normalizeCheckExpr(raw: string): string {
  let s = raw.trim();
  if (!s) return "";
  // Remove um "CHECK" líder (com/sem espaço), case-insensitive.
  const lead = s.match(/^check\b\s*/i);
  if (lead) s = s.slice(lead[0].length).trim();
  // Desembrulha UM par externo de parênteses que casa do início ao fim.
  if (s.startsWith("(") && s.endsWith(")")) {
    let depth = 0;
    let wrapsWhole = true;
    for (let i = 0; i < s.length; i++) {
      if (s[i] === "(") depth++;
      else if (s[i] === ")") {
        depth--;
        // Fechou o par do 1º "(" antes do fim → o par externo NÃO envolve tudo.
        if (depth === 0 && i < s.length - 1) {
          wrapsWhole = false;
          break;
        }
      }
    }
    if (wrapsWhole && depth === 0) s = s.slice(1, -1).trim();
  }
  return s;
}

export function AttrCheckCell({
  value,
  onSave,
}: {
  value?: string | null;
  onSave: (checkExpr: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value || "");

  if (editing) {
    const cancel = () => {
      setText(value || "");
      setEditing(false);
    };
    const save = () => {
      // Normaliza antes de encenar: desembrulha `CHECK (...)` colado e zera só-espaços.
      onSave(normalizeCheckExpr(text));
      setEditing(false);
    };
    return (
      <div className="flex items-center gap-1">
        <input
          className="w-full min-w-[140px] rounded-md border bg-background px-2 py-1 text-xs font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") cancel();
            if (e.key === "Enter") save();
          }}
          placeholder="situacao IN (0,1)"
          autoFocus
        />
        <button
          type="button"
          className="text-[11px] text-muted-foreground hover:text-foreground px-1"
          onClick={cancel}
        >
          Cancelar
        </button>
        <button
          type="button"
          className="text-[11px] text-nuclea-primary hover:underline px-1 font-medium"
          onClick={save}
        >
          Salvar
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="text-left hover:text-foreground group flex items-center gap-1 font-mono text-xs"
      onClick={() => {
        setText(value || "");
        setEditing(true);
      }}
      title="Clique para editar a CHECK constraint (exportada no DDL)"
    >
      {value && value.trim() ? (
        <span>{value}</span>
      ) : (
        <span className="italic font-sans text-muted-foreground/70 group-hover:text-nuclea-primary">
          + CHECK
        </span>
      )}
      <Pencil className="h-3 w-3 opacity-0 group-hover:opacity-60 shrink-0" />
    </button>
  );
}
