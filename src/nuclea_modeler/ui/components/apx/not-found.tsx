import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Home, ArrowLeft, Search, BookOpen, Compass } from "lucide-react";

/**
 * Custom 404 — rendered by TanStack Router when no route matches.
 *
 * Branded layout with three escape hatches: back, home, help. Includes a
 * subtle "Cmd+K" hint to nudge users towards the global search.
 */
export function NotFoundPage() {
  return (
    <div
      id="main-content"
      role="main"
      className="min-h-screen flex items-center justify-center px-6 py-12 bg-background"
    >
      <Card className="w-full max-w-2xl border-dashed">
        <CardContent className="flex flex-col items-center text-center py-16 px-8">
          <div
            aria-hidden="true"
            className="mb-6 flex h-24 w-24 items-center justify-center rounded-2xl bg-gradient-to-br from-nuclea-primary/15 to-nuclea-accent/20 text-nuclea-primary"
          >
            <Compass className="h-12 w-12" />
          </div>

          <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground mb-2">
            Erro 404
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Não encontramos esta página
          </h1>
          <p className="text-muted-foreground max-w-md mb-8">
            A rota que você buscou não existe — ou foi renomeada. Use a busca global
            (<kbd className="px-1.5 py-0.5 rounded border bg-muted font-mono text-xs">⌘K</kbd>) ou
            volte para um destino conhecido.
          </p>

          <div className="flex flex-wrap gap-3 justify-center mb-6">
            <Button asChild size="lg">
              <Link to="/">
                <Home className="mr-2 h-4 w-4" aria-hidden="true" />
                Voltar ao início
              </Link>
            </Button>
            <Button
              variant="outline"
              size="lg"
              onClick={() => window.history.back()}
            >
              <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
              Página anterior
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link to="/help">
                <BookOpen className="mr-2 h-4 w-4" aria-hidden="true" />
                Centro de Ajuda
              </Link>
            </Button>
          </div>

          <div className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Search className="h-3 w-3" aria-hidden="true" />
            Dica: pressione <kbd className="px-1 py-0.5 rounded border bg-muted font-mono text-[10px]">⌘K</kbd> em qualquer página para buscar
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default NotFoundPage;
