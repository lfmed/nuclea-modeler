import { createFileRoute, Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import Navbar from "@/components/apx/navbar";
import {
  ArrowRight,
  Database,
  ScanSearch,
  FileText,
  CloudCog,
  Tags,
  BookOpenText,
} from "lucide-react";
import { BubbleBackground } from "@/components/backgrounds/bubble";

export const Route = createFileRoute("/")({
  component: () => <Index />,
});

function Index() {
  return (
    <div className="relative min-h-screen w-screen overflow-x-hidden flex flex-col">
      <Navbar />

      <main className="flex-1 grid lg:grid-cols-2 relative">
        <div className="relative hidden lg:block">
          <BubbleBackground interactive />
        </div>

        <div className="relative flex flex-col items-start justify-center px-8 md:px-14 py-12 lg:border-l">
          <div className="max-w-xl space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
              <span className="size-1.5 rounded-full bg-nuclea-primary" />
              Núclea · Tribo de Dados
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight">
              Catálogo e modelagem de dados,{" "}
              <span className="text-nuclea-primary">unificados</span>.
            </h1>

            <p className="text-lg text-muted-foreground leading-relaxed">
              Do reverso dos ambientes HINT / HEXT / PROD ao espelhamento no
              Unity Catalog — um único lugar para descobrir, documentar,
              flaguear e governar os dados corporativos da Núclea.
            </p>

            <div className="flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link to="/dashboard" className="flex items-center gap-2">
                  Ir para o Dashboard
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/connections">Cadastrar conexão</Link>
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-6">
              <ModuleHint icon={<Database className="h-4 w-4" />} title="Conexões" desc="ODBC, REST, DDL" />
              <ModuleHint icon={<ScanSearch className="h-4 w-4" />} title="Engenharia Reversa" desc="Schemas, FKs, SPs" />
              <ModuleHint icon={<FileText className="h-4 w-4" />} title="Documentação" desc="Entidades & atributos" />
              <ModuleHint icon={<Tags className="h-4 w-4" />} title="Flags LGPD" desc="Auditável & rastreável" />
              <ModuleHint icon={<BookOpenText className="h-4 w-4" />} title="Dicionário" desc="Glossário corporativo" />
              <ModuleHint icon={<CloudCog className="h-4 w-4" />} title="Sync UC" desc="Espelha modelo ativo" />
            </div>
          </div>
        </div>
      </main>

      <div className="absolute inset-0 -z-10 h-full w-full bg-background" />
    </div>
  );
}

function ModuleHint({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border bg-card/50 px-3 py-2">
      <div className="mt-0.5 text-nuclea-primary">{icon}</div>
      <div className="flex flex-col">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">{desc}</span>
      </div>
    </div>
  );
}
