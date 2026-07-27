/**
 * Peças reutilizáveis das listagens de sistema (entidades, atributos, índices).
 *
 * Contexto (ponto 5 do plano feedback-cliente-jul2026): as três listagens
 * compartilham os mesmos controles — busca textual, selects de filtro,
 * barra de paginação, chip de flag e export CSV. Centralizar aqui evita
 * duplicação e mantém o visual consistente. Os projetos não têm o componente
 * shadcn <Select>, então usamos <select> nativo estilizado.
 */
import { Search, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { FlagBadge } from "@/lib/api";

// ─── Busca textual ──────────────────────────────────────────────────────────

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative w-full sm:w-64">
      <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || "Buscar…"}
        className="pl-8"
      />
    </div>
  );
}

// ─── Select de filtro nativo ──────────────────────────────────────────────────

export type SelectOption = { value: string; label: string };

export function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder: string;
  ariaLabel?: string;
}) {
  return (
    <select
      aria-label={ariaLabel || placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

// ─── Barra de paginação ───────────────────────────────────────────────────────

export function PaginationBar({
  page,
  pageSize,
  total,
  count,
  hasMore,
  onPrev,
  onNext,
}: {
  page: number;
  pageSize: number;
  total: number;
  count: number; // itens na página atual
  hasMore: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = (page - 1) * pageSize + count;
  return (
    <div className="flex items-center justify-between gap-3 pt-3 text-sm text-muted-foreground">
      <span className="tabular-nums">
        {from}–{to} de {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onPrev}
          disabled={page <= 1}
          aria-label="Página anterior"
        >
          <ChevronLeft className="h-4 w-4" />
          Anterior
        </Button>
        <span className="tabular-nums">Página {page}</span>
        <Button
          variant="outline"
          size="sm"
          onClick={onNext}
          disabled={!hasMore}
          aria-label="Próxima página"
        >
          Próxima
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ─── Chip de flag (a partir do resumo FlagBadge) ──────────────────────────────

export function FlagBadgeChip({ flag }: { flag: FlagBadge }) {
  const bg = flag.color_hex || "#6C757D";
  return (
    <span
      className="inline-flex items-center rounded-full border border-black/10 px-1.5 py-0.5 text-[10px] text-white"
      style={{ backgroundColor: bg }}
      title={flag.display_name}
    >
      {flag.display_name}
    </span>
  );
}

export function FlagBadges({ flags }: { flags?: FlagBadge[] | null }) {
  if (!flags || flags.length === 0)
    return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <FlagBadgeChip key={f.flag_id} flag={f} />
      ))}
    </div>
  );
}

// ─── Cabeçalho de coluna ordenável ────────────────────────────────────────────

export function SortableTh({
  label,
  col,
  sortBy,
  sortDir,
  onSort,
  className,
}: {
  label: string;
  col: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
  className?: string;
}) {
  const active = sortBy === col;
  return (
    <th className={"py-2 pr-3 font-medium " + (className || "")}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        {label}
        {active && <span className="text-xs">{sortDir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}

// ─── Export CSV ───────────────────────────────────────────────────────────────

/**
 * Gera e baixa um CSV a partir de linhas já mapeadas (headers + matriz de
 * strings). Escapa aspas/;/quebra de linha conforme RFC 4180. Client-side:
 * exporta apenas o que está carregado na página atual (documentado na UI).
 */
export function downloadCsv(filename: string, headers: string[], rows: (string | number | null | undefined)[][]) {
  const escape = (v: string | number | null | undefined) => {
    const s = v === null || v === undefined ? "" : String(v);
    if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  };
  const lines = [headers.map(escape).join(",")];
  for (const r of rows) lines.push(r.map(escape).join(","));
  // BOM para o Excel reconhecer UTF-8 (acentos do PT-BR).
  const blob = new Blob(["﻿" + lines.join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function ExportCsvButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick}>
      <Download className="mr-2 h-4 w-4" />
      Exportar CSV
    </Button>
  );
}
