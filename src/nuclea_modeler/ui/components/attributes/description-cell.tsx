/**
 * Célula de descrição de coluna EDITÁVEL inline (v1.0030, plano round 3 A2/A3).
 *
 * Compartilhada entre a tela do objeto (`entities.$id.tsx`) e o editor de
 * atributos do DER (`diagram.tsx` → AttributesEditor), para o cliente editar a
 * descrição de uma coluna nos dois lugares com a MESMA UX.
 *
 * Comportamento: mostra o texto truncado (ou um "+ descrição" discreto quando
 * vazio); clicar abre um textarea com Salvar/Cancelar. Ctrl/Cmd+Enter salva,
 * Esc cancela — atalhos pra edição rápida em massa. O `onSave` é quem faz o
 * stage via ticket (o caller reenvia o payload COMPLETO do atributo — ver nota
 * em saveAttrDesc, pois o staging faz merge por field-key com "última vence").
 */
import { useState } from "react";
import { Pencil } from "lucide-react";

export function AttrDescriptionCell({
  value,
  onSave,
}: {
  value?: string | null;
  onSave: (description: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value || "");

  if (editing) {
    return (
      <div className="space-y-1">
        <textarea
          className="w-full min-w-[180px] min-h-[56px] rounded-md border bg-background px-2 py-1 text-xs leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              onSave(text);
              setEditing(false);
            }
          }}
          placeholder="Descrição da coluna…"
          autoFocus
        />
        <div className="flex justify-end gap-1">
          <button
            type="button"
            className="text-[11px] text-muted-foreground hover:text-foreground px-1"
            onClick={() => {
              setText(value || "");
              setEditing(false);
            }}
          >
            Cancelar
          </button>
          <button
            type="button"
            className="text-[11px] text-nuclea-primary hover:underline px-1 font-medium"
            onClick={() => {
              onSave(text);
              setEditing(false);
            }}
          >
            Salvar
          </button>
        </div>
      </div>
    );
  }

  const preview = value
    ? value.length > 80
      ? value.slice(0, 80) + "…"
      : value
    : null;

  return (
    <button
      type="button"
      className="text-left hover:text-foreground group flex items-start gap-1"
      onClick={() => {
        setText(value || "");
        setEditing(true);
      }}
      title="Clique para editar a descrição"
    >
      {preview ? (
        <span>{preview}</span>
      ) : (
        <span className="italic text-muted-foreground/70 group-hover:text-nuclea-primary">
          + descrição
        </span>
      )}
      <Pencil className="h-3 w-3 opacity-0 group-hover:opacity-60 shrink-0 mt-0.5" />
    </button>
  );
}
