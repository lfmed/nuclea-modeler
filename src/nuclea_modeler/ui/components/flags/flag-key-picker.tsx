/**
 * FlagKeyPicker (round 6 pt 16) — seleção de flags por `flag_key` para o ato de
 * CRIAÇÃO manual de tabela/coluna.
 *
 * Diferente do FlagPicker/FlagPickerModal existentes (que APLICAM flags via API a
 * um alvo que já existe), este componente é puramente CONTROLADO: devolve a lista
 * de `flag_keys` escolhidos para ir no payload de criação (QuickEntityIn / AttributeIn).
 * As flags só são materializadas quando o ticket editorial é aprovado — por isso
 * aqui não há mutation, só seleção.
 */
import { Suspense } from "react";

import { useListFlagsSuspense } from "@/lib/api";
import selector from "@/lib/selector";

function FlagChips({
  value,
  onChange,
}: {
  value: string[];
  onChange: (keys: string[]) => void;
}) {
  const { data: flags } = useListFlagsSuspense({ isActive: true }, selector());
  const toggle = (key: string) =>
    onChange(value.includes(key) ? value.filter((k) => k !== key) : [...value, key]);

  return (
    <div className="flex flex-wrap gap-1.5">
      {flags.map((f) => {
        const on = value.includes(f.flag_key);
        return (
          <button
            key={f.flag_id}
            type="button"
            onClick={() => toggle(f.flag_key)}
            title={f.description ?? f.display_name}
            className={
              "rounded-full border px-2 py-0.5 text-xs transition-colors " +
              (on
                ? "border-transparent bg-nuclea-primary text-white"
                : "bg-background text-muted-foreground hover:bg-muted")
            }
          >
            {f.display_name}
          </button>
        );
      })}
    </div>
  );
}

export function FlagKeyPicker(props: {
  value: string[];
  onChange: (keys: string[]) => void;
}) {
  return (
    <Suspense
      fallback={<p className="text-xs text-muted-foreground">Carregando flags…</p>}
    >
      <FlagChips {...props} />
    </Suspense>
  );
}
