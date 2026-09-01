/**
 * Célula de "valor padrão" (DEFAULT) de coluna EDITÁVEL inline (round 5, pt 20).
 *
 * Compartilhada entre a tela do objeto (`entities.$id.tsx`) e o editor de atributos
 * do DER (`diagram.tsx` → AttributesEditor), para o cliente definir o DEFAULT de uma
 * coluna nos DOIS lugares com a MESMA UX — irmã da `AttrDescriptionCell`.
 *
 * O valor é exportado no DDL (backend `ddl/generators._col_default`) na aba
 * "Exportar DDL": ex. `status VARCHAR(50) DEFAULT 'ativo' NOT NULL`.
 *
 * Por que <input> (e não textarea como a descrição): o default é um token curto
 * (ex.: 'ativo', 0, CURRENT_TIMESTAMP). O backend emite o valor CRU, então strings
 * precisam vir COM aspas — o placeholder lembra disso. Enter salva, Esc cancela.
 *
 * O `onSave` faz o stage via ticket; o caller reenvia o payload COMPLETO do atributo
 * (o merge do staging é "última intenção vence" por field-key — ver saveAttrDefault).
 * String vazia "" limpa o default (o apply de atributo filtra None, então null nunca
 * limparia; "" passa no filtro e zera).
 */
import { useState } from "react";
import { Pencil } from "lucide-react";

export function AttrDefaultCell({
  value,
  onSave,
}: {
  value?: string | null;
  onSave: (defaultValue: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value || "");

  if (editing) {
    const cancel = () => {
      setText(value || "");
      setEditing(false);
    };
    const save = () => {
      onSave(text);
      setEditing(false);
    };
    return (
      <div className="flex items-center gap-1">
        <input
          className="w-full min-w-[120px] rounded-md border bg-background px-2 py-1 text-xs font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") cancel();
            if (e.key === "Enter") save();
          }}
          placeholder="'ativo', 0, CURRENT_TIMESTAMP…"
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
      title="Clique para editar o valor padrão (DEFAULT)"
    >
      {value ? (
        <span>{value}</span>
      ) : (
        <span className="italic font-sans text-muted-foreground/70 group-hover:text-nuclea-primary">
          + default
        </span>
      )}
      <Pencil className="h-3 w-3 opacity-0 group-hover:opacity-60 shrink-0" />
    </button>
  );
}
