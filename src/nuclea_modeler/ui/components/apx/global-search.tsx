import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Search,
  FileText,
  Database,
  BookOpenText,
  Tags,
  Inbox,
  Network,
  ChevronRight,
  Loader2,
} from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useGlobalSearch, type SearchKind, type SearchResult } from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<SearchKind, string> = {
  entity: "Entidades",
  attribute: "Atributos",
  term: "Termos do Glossário",
  flag: "Flags",
  ticket: "Tickets",
  connection: "Conexões",
  system: "Sistemas",
};

const KIND_ORDER: SearchKind[] = [
  "entity",
  "attribute",
  "term",
  "flag",
  "ticket",
  "connection",
  "system",
];

function KindIcon({ kind }: { kind: SearchKind }) {
  const className = "h-4 w-4 shrink-0 text-muted-foreground";
  switch (kind) {
    case "entity":
      return <FileText className={className} />;
    case "attribute":
      return <ChevronRight className={className} />;
    case "term":
      return <BookOpenText className={className} />;
    case "flag":
      return <Tags className={className} />;
    case "ticket":
      return <Inbox className={className} />;
    case "connection":
      return <Database className={className} />;
    case "system":
      return <Network className={className} />;
  }
}

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const { data, isFetching } = useGlobalSearch(q, 30);

  // Cmd/Ctrl+K opens. Esc closes (Sheet handles Esc by default).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) {
      // small timeout to wait for the sheet to mount
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
    setQ("");
  }, [open]);

  const grouped = useMemo(() => {
    const map = new Map<SearchKind, SearchResult[]>();
    for (const r of data?.results ?? []) {
      const arr = map.get(r.kind) ?? [];
      arr.push(r);
      map.set(r.kind, arr);
    }
    return KIND_ORDER.filter((k) => map.has(k)).map((k) => ({
      kind: k,
      items: map.get(k) ?? [],
    }));
  }, [data]);

  const totalShown = data?.results.length ?? 0;
  const queryTooShort = q.trim().length > 0 && q.trim().length < 2;
  const showEmpty =
    !isFetching && q.trim().length >= 2 && totalShown === 0;

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        className="gap-2 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-nuclea-primary"
        aria-label="Abrir busca global"
        title="Buscar (Cmd/Ctrl+K)"
      >
        <Search className="h-4 w-4" />
        <span className="hidden md:inline">Buscar...</span>
        <kbd className="hidden md:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-80">
          <span className="text-xs">⌘</span>K
        </kbd>
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full sm:max-w-xl flex flex-col">
          <SheetHeader>
            <SheetTitle>Busca global</SheetTitle>
            <SheetDescription>
              Procure entidades, atributos, termos, flags, tickets, conexões e sistemas.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 flex items-center gap-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Input
              ref={inputRef}
              placeholder="Digite ao menos 2 caracteres..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="flex-1"
            />
            {isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>

          <div className="mt-4 flex-1 overflow-y-auto -mx-2 px-2">
            {queryTooShort && (
              <p className="text-sm text-muted-foreground py-6 text-center">
                Continue digitando...
              </p>
            )}
            {showEmpty && (
              <p className="text-sm text-muted-foreground py-6 text-center">
                Nada encontrado para "<span className="font-medium">{q}</span>".
              </p>
            )}
            {grouped.map((g) => (
              <div key={g.kind} className="mb-5">
                <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1.5 px-1">
                  {KIND_LABELS[g.kind]}{" "}
                  <Badge variant="outline" className="ml-1 px-1.5 py-0 text-[10px]">
                    {g.items.length}
                  </Badge>
                </div>
                <ul className="space-y-1">
                  {g.items.map((r) => (
                    <li key={`${r.kind}-${r.id}`}>
                      <Link
                        to={r.path}
                        onClick={() => setOpen(false)}
                        className={cn(
                          "flex items-start gap-2 rounded-md p-2 text-sm transition-colors",
                          "hover:bg-muted focus-visible:bg-muted",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-nuclea-primary",
                        )}
                      >
                        <KindIcon kind={r.kind} />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">{r.label}</div>
                          {r.sublabel && (
                            <div className="text-xs text-muted-foreground truncate">
                              {r.sublabel}
                            </div>
                          )}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

export default GlobalSearch;
