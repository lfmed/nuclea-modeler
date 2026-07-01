import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { APP_VERSION } from "@/lib/build-info";
import {
  ArrowRight,
  Database,
  ScanSearch,
  FileText,
  CloudCog,
  Tags,
  BookOpenText,
  GitFork,
  History,
  FileCode,
  Network,
  TestTube2,
  Inbox,
  Github,
  BookOpen,
  Sparkles,
  ListChecks,
  Send,
} from "lucide-react";
import {
  useListSystemsSuspense,
  useListEntitiesSuspense,
  useListTicketsSuspense,
  useListExtractionsSuspense,
} from "@/lib/api";
import selector from "@/lib/selector";

// Renderizada DENTRO do layout _sidebar (arquivo em routes/_sidebar/index.tsx),
// então a tela inicial já traz o menu lateral. O header/navegação vêm do
// SidebarLayout — por isso não há Navbar próprio aqui.
export const Route = createFileRoute("/_sidebar/")({
  component: () => <Index />,
});

function Index() {
  return (
    <div className="relative w-full overflow-x-hidden flex flex-col">
      <div className="flex-1">
        <Hero />
        <section className="mx-auto w-full max-w-6xl px-6 md:px-10 -mt-10 md:-mt-14 relative z-10">
          <KpiRow />
        </section>
        <section className="mx-auto w-full max-w-6xl px-6 md:px-10 py-16">
          <JourneySection />
        </section>
        <section className="mx-auto w-full max-w-6xl px-6 md:px-10 pb-16">
          <CapabilitiesGrid />
        </section>
        <Footer />
      </div>
    </div>
  );
}

// ─── Hero ────────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="absolute inset-0 -z-10"
        style={{
          background:
            "linear-gradient(135deg, color-mix(in oklch, var(--nuclea-primary) 18%, transparent) 0%, var(--nuclea-surface) 55%, transparent 100%)",
        }}
      />
      <div
        aria-hidden
        className="absolute -top-32 -right-32 -z-10 size-[28rem] rounded-full blur-3xl opacity-30"
        style={{ background: "var(--nuclea-primary)" }}
      />
      <div
        aria-hidden
        className="absolute -bottom-40 -left-20 -z-10 size-[22rem] rounded-full blur-3xl opacity-20"
        style={{ background: "var(--nuclea-accent)" }}
      />

      <div className="mx-auto max-w-6xl px-6 md:px-10 py-20 md:py-28">
        <div className="max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border bg-card/80 backdrop-blur px-3 py-1 text-xs font-medium text-muted-foreground">
            <span className="size-1.5 rounded-full bg-nuclea-primary" />
            Núclea · Tribo de Dados · Plataforma de Catálogo
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.05]">
            Catálogo, modelagem e governança de dados,{" "}
            <span className="text-nuclea-primary">unificados</span>.
          </h1>

          <p className="text-lg md:text-xl text-muted-foreground leading-relaxed max-w-2xl">
            Do reverso dos ambientes HINT / HEXT / PROD ao espelhamento no
            Unity Catalog — um único lugar para descobrir, documentar,
            flaguear e governar os dados corporativos da Núclea.
          </p>

          <div className="flex flex-wrap gap-3 pt-2">
            <Button size="lg" asChild>
              <Link to="/dashboard" className="flex items-center gap-2">
                Entrar no Dashboard
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link to="/help" className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                Ver documentação
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── KPI row ─────────────────────────────────────────────────────────────────
function KpiRow() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={() => (
            <KpiGrid>
              <KpiCard icon={<Database className="h-4 w-4" />} label="Sistemas" value="—" hint="cadastrados" />
              <KpiCard icon={<FileText className="h-4 w-4" />} label="Entidades" value="—" hint="catalogadas" />
              <KpiCard icon={<ScanSearch className="h-4 w-4" />} label="Engenharias reversas" value="—" hint="executadas" />
              <KpiCard icon={<Inbox className="h-4 w-4" />} label="Tickets abertos" value="—" hint="aguardando ação" />
            </KpiGrid>
          )}
        >
          <Suspense fallback={<KpiSkeleton />}>
            <KpiData />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

function KpiData() {
  const { data: systems } = useListSystemsSuspense(selector());
  const { data: entities } = useListEntitiesSuspense({}, selector());
  const { data: tickets } = useListTicketsSuspense({}, selector());
  const { data: extractions } = useListExtractionsSuspense({}, selector());

  const openTickets = tickets.filter((t) => t.status === "OPEN").length;
  const successfulExtractions = extractions.filter(
    (e) => e.status === "SUCCESS" || e.status === "PARTIAL",
  ).length;

  return (
    <KpiGrid>
      <KpiCard
        icon={<Database className="h-4 w-4" />}
        label="Sistemas"
        value={String(systems.length)}
        hint="cadastrados"
      />
      <KpiCard
        icon={<FileText className="h-4 w-4" />}
        label="Entidades"
        value={String(entities.length)}
        hint="catalogadas"
      />
      <KpiCard
        icon={<ScanSearch className="h-4 w-4" />}
        label="Engenharias reversas"
        value={String(successfulExtractions)}
        hint={`${extractions.length} no total`}
      />
      <KpiCard
        icon={<Inbox className="h-4 w-4" />}
        label="Tickets abertos"
        value={String(openTickets)}
        hint="aguardando ação"
      />
    </KpiGrid>
  );
}

function KpiGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
  );
}

function KpiSkeleton() {
  return (
    <KpiGrid>
      {[0, 1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader className="pb-2">
            <Skeleton className="h-4 w-24" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-8 w-16 mb-2" />
            <Skeleton className="h-3 w-32" />
          </CardContent>
        </Card>
      ))}
    </KpiGrid>
  );
}

function KpiCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-2 text-xs uppercase tracking-wider">
          <span className="text-nuclea-primary">{icon}</span>
          {label}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold tabular-nums">{value}</div>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  );
}

// ─── Journey ────────────────────────────────────────────────────────────────
function JourneySection() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 text-sm text-nuclea-primary font-medium">
          <Sparkles className="h-4 w-4" />
          Por onde começar
        </div>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
          Quatro passos para colocar um sistema no ar
        </h2>
        <p className="text-muted-foreground max-w-2xl">
          Da primeira conexão à publicação no Unity Catalog. Cada passo gera
          rastreabilidade — quem cadastrou, quem aprovou, quem aplicou.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <JourneyStep
          step={1}
          to="/connections"
          icon={<Database className="h-5 w-5" />}
          title="Cadastrar conexão"
          desc="Conecte HINT/HEXT/PROD via ODBC, REST ou aponte um sandbox Lakebase."
        />
        <JourneyStep
          step={2}
          to="/extractions"
          icon={<ScanSearch className="h-5 w-5" />}
          title="Executar engenharia reversa"
          desc="Extraia o modelo atual da fonte ou importe um DDL multi-dialect."
        />
        <JourneyStep
          step={3}
          to="/tickets"
          icon={<ListChecks className="h-5 w-5" />}
          title="Revisar e aprovar tickets"
          desc="Cada extração gera um ticket de reconciliação para revisão."
        />
        <JourneyStep
          step={4}
          to="/sync"
          icon={<Send className="h-5 w-5" />}
          title="Publicar e sincronizar"
          desc="Publique a versão ativa e espelhe COMMENT + TAGS no Unity Catalog."
        />
      </div>
    </div>
  );
}

function JourneyStep({
  step,
  to,
  icon,
  title,
  desc,
}: {
  step: number;
  to: string;
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <Link to={to} className="group block focus:outline-none">
      <Card className="h-full transition-all border-border/60 hover:border-nuclea-primary/50 hover:shadow-md group-focus-visible:ring-2 group-focus-visible:ring-nuclea-primary">
        <CardHeader className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-5xl font-bold text-nuclea-primary/20 tabular-nums leading-none group-hover:text-nuclea-primary/40 transition-colors">
              0{step}
            </span>
            <div className="rounded-md bg-nuclea-primary/10 p-2 text-nuclea-primary">
              {icon}
            </div>
          </div>
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription className="text-sm leading-relaxed">
            {desc}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <span className="inline-flex items-center gap-1 text-xs font-medium text-nuclea-primary opacity-0 group-hover:opacity-100 transition-opacity">
            Abrir
            <ArrowRight className="h-3 w-3" />
          </span>
        </CardContent>
      </Card>
    </Link>
  );
}

// ─── Capabilities ───────────────────────────────────────────────────────────
function CapabilitiesGrid() {
  const caps: Array<{
    to: string;
    icon: React.ReactNode;
    title: string;
    desc: string;
  }> = [
    {
      to: "/connections",
      icon: <Database className="h-4 w-4" />,
      title: "M1 — Conexões",
      desc: "ODBC, REST e import DDL para HINT/HEXT/PROD.",
    },
    {
      to: "/extractions",
      icon: <ScanSearch className="h-4 w-4" />,
      title: "M2 — Engenharia reversa",
      desc: "Schemas, FKs e SPs de bancos heterogêneos.",
    },
    {
      to: "/entities",
      icon: <FileText className="h-4 w-4" />,
      title: "M3 — Documentação",
      desc: "Entidades, atributos, owners, criticidade.",
    },
    {
      to: "/diagram",
      icon: <Network className="h-4 w-4" />,
      title: "M4 — DER",
      desc: "Diagrama entidade-relacionamento navegável.",
    },
    {
      to: "/flags",
      icon: <Tags className="h-4 w-4" />,
      title: "M5 — Flags & LGPD",
      desc: "9 faixas LGPD com justificativa e auditoria.",
    },
    {
      to: "/glossary",
      icon: <BookOpenText className="h-4 w-4" />,
      title: "M6 — Dicionário",
      desc: "Glossário corporativo com aprovação.",
    },
    {
      to: "/lineage",
      icon: <GitFork className="h-4 w-4" />,
      title: "M7 — Linhagem",
      desc: "Upstream/downstream entre sistemas.",
    },
    {
      to: "/versions",
      icon: <History className="h-4 w-4" />,
      title: "M8 — Versões",
      desc: "Snapshots imutáveis e diff entre versões.",
    },
    {
      to: "/sync",
      icon: <CloudCog className="h-4 w-4" />,
      title: "M9 — Sync UC",
      desc: "Espelha COMMENT/TAGS no Unity Catalog.",
    },
    {
      to: "/ddl",
      icon: <FileCode className="h-4 w-4" />,
      title: "M10 — Export DDL",
      desc: "ANSI, T-SQL, PL/SQL, Postgres, MySQL, Spark.",
    },
    {
      to: "/lakebase",
      icon: <TestTube2 className="h-4 w-4" />,
      title: "M-LB — Lakebase",
      desc: "Sandboxes Postgres para validar modelos.",
    },
    {
      to: "/tickets",
      icon: <Inbox className="h-4 w-4" />,
      title: "Tickets",
      desc: "Workflow OPEN → APPROVED → APPLIED.",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 text-sm text-nuclea-primary font-medium">
          <Sparkles className="h-4 w-4" />
          Capacidades
        </div>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
          Tudo o que o Núclea Modeler entrega
        </h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {caps.map((c) => (
          <Link
            key={c.to}
            to={c.to}
            className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-nuclea-primary rounded-lg"
          >
            <div className="h-full rounded-lg border bg-card p-4 transition-all hover:border-nuclea-primary/50 hover:shadow-sm">
              <div className="flex items-start gap-3">
                <div className="rounded-md bg-nuclea-primary/10 p-2 text-nuclea-primary shrink-0">
                  {c.icon}
                </div>
                <div className="flex-1 space-y-1">
                  <div className="font-semibold text-sm">{c.title}</div>
                  <div className="text-xs text-muted-foreground leading-relaxed">
                    {c.desc}
                  </div>
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Footer ─────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t bg-muted/30 mt-8">
      <div className="mx-auto max-w-6xl px-6 md:px-10 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-nuclea-primary" />
            <span className="font-semibold">Núclea Modeler</span>
            <Badge variant="outline" className="ml-2 text-[10px]">
              v{APP_VERSION}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground max-w-md">
            Construído pela Tribo de Dados Núclea sobre a plataforma
            Databricks. 100% Delta no Unity Catalog.
          </p>
        </div>

        <div className="flex items-center gap-4 text-sm">
          <Link
            to="/help"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          >
            <BookOpen className="h-3.5 w-3.5" />
            Documentação
          </Link>
          <a
            href="https://github.com/lfmed/nuclea-modeler"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          >
            <Github className="h-3.5 w-3.5" />
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}

