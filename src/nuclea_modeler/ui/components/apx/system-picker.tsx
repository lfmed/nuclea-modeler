import { useState } from "react";
import { useCreateSystem, useListSystemsSuspense, type SystemListOut } from "@/lib/api";
import selector from "@/lib/selector";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { toast } from "sonner";

/** Dropdown de sistemas + opção "+ Criar novo" inline.
 *
 * Quando o user escolhe "+ Criar novo", o componente mostra inputs (nome,
 * domínio, tecnologia) e um botão "Criar e selecionar" que faz POST /systems
 * e seleciona o sistema novo. Útil pra fluxos de engenharia reversa onde
 * a extração pode iniciar um sistema do zero. */
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
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDomain, setNewDomain] = useState("");
  const [newTech, setNewTech] = useState("");

  const createSystem = useCreateSystem({
    mutation: {
      onSuccess: (sys: SystemListOut) => {
        onChange(sys.system_id);
        setCreating(false);
        setNewName("");
        setNewDomain("");
        setNewTech("");
        toast.success(`Sistema "${sys.system_name}" criado e selecionado`);
      },
      onError: (e) => toast.error(String(e)),
    },
  });

  return (
    <div className="space-y-2">
      <select
        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        value={creating ? "__new__" : value}
        onChange={(e) => {
          if (e.target.value === "__new__") {
            setCreating(true);
          } else {
            setCreating(false);
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
      {creating && (
        <div className="rounded-md border bg-muted/30 p-3 space-y-2">
          <p className="text-xs text-muted-foreground">
            Criando um novo modelo de dados. A extração popula este sistema com
            todas as entidades descobertas como adições (op=add).
          </p>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Nome do sistema *"
            className="h-8 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <Input
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              placeholder="Domínio (opcional)"
              className="h-8 text-sm"
            />
            <Input
              value={newTech}
              onChange={(e) => setNewTech(e.target.value)}
              placeholder="Tecnologia (PostgreSQL...)"
              className="h-8 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setCreating(false)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={createSystem.isPending || !newName.trim()}
              onClick={() =>
                createSystem.mutate({
                  data: {
                    system_name: newName.trim(),
                    domain: newDomain.trim() || null,
                    technology: newTech.trim() || null,
                  },
                })
              }
            >
              <Plus className="mr-1 h-3 w-3" />
              {createSystem.isPending ? "Criando..." : "Criar e selecionar"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
