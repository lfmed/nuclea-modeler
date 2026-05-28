import { useState } from "react";
import { useListSystemsSuspense } from "@/lib/api";
import selector from "@/lib/selector";
import { NewSystemWizard } from "@/components/apx/new-system-wizard";

/** Dropdown de sistemas + opção "+ Criar novo" que abre o wizard.
 *
 * Mantém a mesma callback do componente anterior (`onChange(system_id)`),
 * mas a criação inline foi substituída pelo wizard multi-step de Novo
 * Sistema com discovery opcional (Lakebase/Unity Catalog). */
export function SystemPicker({
  value,
  onChange,
  required,
}: {
  value: string;
  onChange: (systemId: string) => void;
  required?: boolean;
}) {
  const { data: systems } = useListSystemsSuspense(selector());
  const [wizardOpen, setWizardOpen] = useState(false);

  return (
    <div className="space-y-2">
      <select
        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        value={value}
        onChange={(e) => {
          if (e.target.value === "__new__") {
            setWizardOpen(true);
          } else {
            onChange(e.target.value);
          }
        }}
        required={required}
      >
        <option value="" disabled>
          — selecione —
        </option>
        {systems.map((s) => (
          <option key={s.system_id} value={s.system_id}>
            {s.system_name}
          </option>
        ))}
        <option value="__new__">+ Criar novo sistema…</option>
      </select>
      <NewSystemWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onCreated={(sys) => onChange(sys.system_id)}
      />
    </div>
  );
}
