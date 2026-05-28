import { useEffect, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Database,
  ScanSearch,
  Network,
  Tags,
  History,
  ArrowRight,
  ArrowLeft,
  Check,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "nuclea-modeler:welcome-tour:dismissed";

interface Step {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  cta: { label: string; to: string };
  badge: string;
}

const STEPS: Step[] = [
  {
    icon: <Database className="h-6 w-6" />,
    title: "Cadastre uma conexão",
    description: (
      <>
        Conexões representam os ambientes <strong>HINT</strong>, <strong>HEXT</strong> e{" "}
        <strong>PROD</strong>. Cadastre uma conexão ODBC, REST ou de import de DDL — credenciais
        ficam em Databricks Secrets.
      </>
    ),
    cta: { label: "Ir para Conexões", to: "/connections" },
    badge: "Passo 1 · M1",
  },
  {
    icon: <ScanSearch className="h-6 w-6" />,
    title: "Faça engenharia reversa",
    description: (
      <>
        Rode uma extração a partir do <strong>Lakebase</strong>, <strong>DDL file</strong> ou{" "}
        <strong>.erx do Embarcadero</strong>. O app compara com o catálogo e abre tickets
        automaticamente se houver divergências.
      </>
    ),
    cta: { label: "Ir para Extrações", to: "/extractions" },
    badge: "Passo 2 · M2",
  },
  {
    icon: <Network className="h-6 w-6" />,
    title: "Explore o DER",
    description: (
      <>
        Visualize entidades e relacionamentos em um <strong>diagrama interativo</strong>. Layout
        automático via Dagre, drag-edge para criar relacionamentos, exporte como PNG/SVG.
      </>
    ),
    cta: { label: "Ir para Diagrama", to: "/diagram" },
    badge: "Passo 3 · M4",
  },
  {
    icon: <Tags className="h-6 w-6" />,
    title: "Aplique flags LGPD",
    description: (
      <>
        Marque atributos sensíveis com flags LGPD. A flag <strong>propaga automaticamente</strong>{" "}
        para a tabela pai (regra spec §4.5.2), garantindo cobertura total do compliance.
      </>
    ),
    cta: { label: "Ir para Flags", to: "/flags" },
    badge: "Passo 4 · M5",
  },
  {
    icon: <History className="h-6 w-6" />,
    title: "Publique e sincronize",
    description: (
      <>
        Publique versões do modelo com changelog e approval trail. Sincronize{" "}
        <strong>COMMENT + TAGS</strong> para o Unity Catalog em um clique — metadados aparecem no
        Catalog Explorer nativo.
      </>
    ),
    cta: { label: "Ir para Versões", to: "/versions" },
    badge: "Passo 5 · M8 + M9",
  },
];

interface WelcomeTourProps {
  /** Se true, força a abertura (usado pelo botão "Refazer tour" no Help). */
  forceOpen?: boolean;
  onClose?: () => void;
}

/**
 * Onboarding sheet de 5 passos. Auto-abre na primeira visita do usuário
 * (persiste flag em localStorage). Pode ser reaberto manualmente via prop.
 */
export function WelcomeTour({ forceOpen = false, onClose }: WelcomeTourProps) {
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (forceOpen) {
      setOpen(true);
      setIndex(0);
      return;
    }
    try {
      const dismissed = localStorage.getItem(STORAGE_KEY);
      if (!dismissed) {
        // Pequeno delay para o app montar antes do tour aparecer.
        const t = setTimeout(() => setOpen(true), 800);
        return () => clearTimeout(t);
      }
    } catch {
      /* localStorage indisponível em modos privados — apenas não abre */
    }
  }, [forceOpen]);

  function dismiss(persist: boolean) {
    setOpen(false);
    setIndex(0);
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, new Date().toISOString());
      } catch {
        /* ignore */
      }
    }
    onClose?.();
  }

  const step = STEPS[index];
  const isLast = index === STEPS.length - 1;
  const isFirst = index === 0;

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o) dismiss(true);
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-md flex flex-col"
        aria-describedby="welcome-tour-desc"
      >
        <SheetHeader className="text-left">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
            <Badge variant="outline" className="font-mono text-xs">
              {step.badge}
            </Badge>
          </div>
          <SheetTitle className="text-2xl">{step.title}</SheetTitle>
          <SheetDescription id="welcome-tour-desc" className="text-base leading-relaxed pt-2">
            {step.description}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 flex flex-col items-center justify-center px-6">
          <div
            aria-hidden="true"
            className="flex h-24 w-24 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 text-primary mb-6"
          >
            {step.icon}
          </div>
          <Button asChild size="lg" onClick={() => dismiss(true)}>
            <Link to={step.cta.to}>
              {step.cta.label}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>

        <SheetFooter className="border-t pt-4 mt-4">
          <div className="flex w-full items-center justify-between gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
              disabled={isFirst}
              aria-label="Passo anterior"
            >
              <ArrowLeft className="mr-1 h-4 w-4" />
              Voltar
            </Button>

            <div className="flex items-center gap-1.5" role="tablist" aria-label="Progresso do tour">
              {STEPS.map((_, i) => (
                <button
                  key={i}
                  role="tab"
                  aria-selected={i === index}
                  aria-label={`Ir para passo ${i + 1}`}
                  onClick={() => setIndex(i)}
                  className={cn(
                    "h-2 rounded-full transition-all cursor-pointer",
                    i === index ? "w-6 bg-primary" : "w-2 bg-muted hover:bg-muted-foreground/40",
                  )}
                />
              ))}
            </div>

            {isLast ? (
              <Button size="sm" onClick={() => dismiss(true)}>
                Concluir
                <Check className="ml-1 h-4 w-4" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => setIndex((i) => Math.min(STEPS.length - 1, i + 1))}>
                Próximo
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            )}
          </div>
          <button
            onClick={() => dismiss(true)}
            className="mt-3 w-full text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Pular tour
          </button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/** Public helper: resets the dismissed flag and reopens the tour next visit. */
export function resetWelcomeTour() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export default WelcomeTour;
