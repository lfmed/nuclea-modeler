import { useEffect, useMemo, useRef, useState } from "react";
import {
  composeType,
  getTypeFamiliesForTechnology,
  parseType,
  type TypeFamily,
} from "@/components/diagram/types-by-tech";

/**
 * Picker de tipo de coluna com família + parâmetros (length / precision+scale).
 * Exemplo: o user escolhe "VARCHAR" no dropdown e aparece um input pra tamanho.
 * onChange recebe a string final composta — ex: "VARCHAR(80)" ou "NUMERIC(18,2)".
 *
 * Aceita `value` legacy (string como "VARCHAR(50)") e inicializa o picker
 * com a família + params parseados.
 */
export function TypePicker({
  value,
  onChange,
  technology,
  size = "default",
  className,
}: {
  value: string;
  onChange: (next: string) => void;
  technology?: string | null;
  size?: "default" | "compact";
  className?: string;
}) {
  const families = useMemo(
    () => getTypeFamiliesForTechnology(technology),
    [technology],
  );

  // State interno = derivado de value (parseado uma vez no mount, depois
  // gerenciado localmente). Sincroniza pra fora via onChange a cada mudança.
  const parsed = useMemo(() => parseType(value, families), [value, families]);
  const [familyName, setFamilyName] = useState<string>(
    parsed.family?.name || families[0]?.name || "",
  );
  const [length, setLength] = useState<string>(
    parsed.length != null
      ? String(parsed.length)
      : String(parsed.family?.defaultLength ?? ""),
  );
  const [precision, setPrecision] = useState<string>(
    parsed.precision != null
      ? String(parsed.precision)
      : String(parsed.family?.defaultPrecision ?? ""),
  );
  const [scale, setScale] = useState<string>(
    parsed.scale != null
      ? String(parsed.scale)
      : String(parsed.family?.defaultScale ?? ""),
  );

  const family =
    families.find((f) => f.name === familyName) || families[0] || null;

  // Quando a família muda, popula defaults dela nos inputs (se ainda vazios)
  function changeFamily(name: string) {
    setFamilyName(name);
    const f = families.find((x) => x.name === name);
    if (f?.defaultLength != null) setLength(String(f.defaultLength));
    if (f?.defaultPrecision != null) setPrecision(String(f.defaultPrecision));
    if (f?.defaultScale != null) setScale(String(f.defaultScale));
  }

  // Notifica pai sempre que a composição muda. Skip 1ª render se value já
  // estiver coerente, pra evitar overwriting do que veio de props.
  const initialized = useRef(false);
  useEffect(() => {
    if (!family) return;
    const composed = composeType(
      family,
      parseInt(length, 10) || undefined,
      parseInt(precision, 10) || undefined,
      parseInt(scale, 10) || undefined,
    );
    // Evita loop quando value externo já bate com a composição interna
    if (!initialized.current) {
      initialized.current = true;
      if (composed === value) return;
    }
    if (composed !== value) onChange(composed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyName, length, precision, scale]);

  const sel =
    "rounded border bg-background " +
    (size === "compact" ? "h-7 text-xs px-1.5" : "h-8 text-xs px-2");
  const inp =
    "rounded border bg-background " +
    (size === "compact" ? "h-7 text-xs px-1.5 w-14" : "h-8 text-xs px-2 w-16");

  return (
    <div className={`flex items-center gap-1 ${className || ""}`}>
      <select
        value={familyName}
        onChange={(e) => changeFamily(e.target.value)}
        className={`${sel} flex-1 font-mono`}
      >
        {families.map((f) => (
          <option key={f.name} value={f.name}>
            {f.name}
          </option>
        ))}
      </select>
      {family?.param === "length" && (
        <input
          type="number"
          min={1}
          max={family.maxLength ?? undefined}
          value={length}
          onChange={(e) => setLength(e.target.value)}
          className={`${inp} font-mono`}
          title="tamanho"
        />
      )}
      {family?.param === "precision_scale" && (
        <>
          <input
            type="number"
            min={1}
            value={precision}
            onChange={(e) => setPrecision(e.target.value)}
            className={`${inp} font-mono`}
            title="precision"
          />
          <span className="text-muted-foreground text-xs">,</span>
          <input
            type="number"
            min={0}
            value={scale}
            onChange={(e) => setScale(e.target.value)}
            className={`${inp} font-mono`}
            title="scale"
          />
        </>
      )}
    </div>
  );
}
