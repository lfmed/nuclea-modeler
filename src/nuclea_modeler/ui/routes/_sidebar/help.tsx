import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  BookOpen,
  HelpCircle,
  Compass,
  Layers,
  UserCog,
  Workflow,
  ShieldAlert,
  MessageCircleQuestion,
  Keyboard,
  Wrench,
  Github,
  Database,
  ScanSearch,
  FileText,
  Tags,
  BookOpenText,
  GitFork,
  History,
  CloudCog,
  TestTube2,
  Inbox,
  Network,
  CheckCircle2,
  XCircle,
  PlayCircle,
  Circle,
  ArrowRight,
  Shield,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/help")({
  component: Help,
});

const SECTIONS = [
  { id: "jornada", label: "Jornada do usuário", icon: <Compass className="h-3.5 w-3.5" /> },
  { id: "conceitos", label: "Conceitos-chave", icon: <Layers className="h-3.5 w-3.5" /> },
  { id: "papeis", label: "Por papel (RBAC)", icon: <UserCog className="h-3.5 w-3.5" /> },
  { id: "tickets", label: "Fluxo de Tickets", icon: <Workflow className="h-3.5 w-3.5" /> },
  { id: "lgpd", label: "Faixas LGPD", icon: <ShieldAlert className="h-3.5 w-3.5" /> },
  { id: "faq", label: "FAQ", icon: <MessageCircleQuestion className="h-3.5 w-3.5" /> },
  { id: "atalhos", label: "Atalhos", icon: <Keyboard className="h-3.5 w-3.5" /> },
  { id: "sobre", label: "Sobre", icon: <Wrench className="h-3.5 w-3.5" /> },
];

function Help() {
  return (
    <div className="space-y-10">
      <Header />
      <QuickLinks />
      <Journey />
      <Concepts />
      <Roles />
      <TicketFlow />
      <LgpdFlags />
      <Faq />
      <Shortcuts />
      <About />
    </div>
  );
}

// ─── Header ────────────────────────────────────────────────────────────────
function Header() {
  return (
    <div className="space-y-3">
      <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
        <BookOpen className="h-3.5 w-3.5 text-nuclea-primary" />
        Centro de Ajuda
      </div>
      <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
        Documentação do Núclea Modeler
      </h1>
      <p className="text-muted-foreground max-w-3xl">
        Guia in-app para quem precisa entender como cadastrar uma fonte,
        documentar entidades, aplicar flags LGPD, aprovar tickets e publicar
        modelos no Unity Catalog. Tudo em português, voltado para a Tribo de
        Dados Núclea.
      </p>
    </div>
  );
}

// ─── Quick links ───────────────────────────────────────────────────────────
function QuickLinks() {
  return (
    <div className="flex flex-wrap gap-2">
      {SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:border-nuclea-primary/50 transition-colors"
        >
          <span className="text-nuclea-primary">{s.icon}</span>
          {s.label}
        </a>
      ))}
    </div>
  );
}

// ─── Section wrapper ───────────────────────────────────────────────────────
function Section({
  id,
  icon,
  title,
  subtitle,
  children,
}: {
  id: string;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="space-y-4 scroll-mt-20">
      <div className="space-y-1">
        <div className="inline-flex items-center gap-2 text-sm text-nuclea-primary font-medium">
          {icon}
          {title}
        </div>
        {subtitle && (
          <p className="text-muted-foreground text-sm max-w-3xl">{subtitle}</p>
        )}
      </div>
      {children}
    </section>
  );
}

// ─── Jornada ────────────────────────────────────────────────────────────────
function Journey() {
  const steps = [
    {
      n: 1,
      to: "/connections",
      icon: <Database className="h-5 w-5" />,
      title: "Cadastrar conexão",
      desc: "Em /connections, crie uma conexão para HINT, HEXT ou PROD. Suporte a ODBC (SQL Server, Oracle, Postgres), REST e importação de DDL. Para Lakebase, cadastre um sandbox em /lakebase apontando para uma instância Postgres serverless.",
      tips: [
        "Use o botão 'Testar' para validar latência e versão do banco.",
        "Secrets podem ser armazenadas no Databricks Secret Scope.",
      ],
    },
    {
      n: 2,
      to: "/extractions",
      icon: <ScanSearch className="h-5 w-5" />,
      title: "Executar engenharia reversa",
      desc: "Em /extractions, escolha a conexão e dispare o reverso. Para fontes Lakebase, selecione schemas e tipos de objeto. Para arquivos, cole o DDL e escolha o dialeto.",
      tips: [
        "Toda extração bem-sucedida gera um ticket de reconciliação automaticamente.",
        "Multi-dialect via sqlglot: ANSI, T-SQL, PL/SQL, Postgres, MySQL, Spark SQL.",
      ],
    },
    {
      n: 3,
      to: "/tickets",
      icon: <Inbox className="h-5 w-5" />,
      title: "Revisar e aprovar tickets",
      desc: "Em /tickets, analise o diff entre o catálogo atual e o snapshot extraído. Aprove para sinalizar consenso (Data Architect) e depois Aplique para gravar as mudanças nas tabelas Delta do catálogo.",
      tips: [
        "Approve e Apply são dois passos separados, permitindo revisão entre eles.",
        "Tickets rejeitados ficam no histórico para auditoria.",
      ],
    },
    {
      n: 4,
      to: "/versions",
      icon: <History className="h-5 w-5" />,
      title: "Publicar versão",
      desc: "Em /versions, publique uma versão imutável do modelo. Use 'tornar ativa' para marcar a versão de referência. Versões antigas continuam acessíveis para diff e restauração como rascunho.",
      tips: [
        "Versões publicadas são imutáveis: restaure como rascunho para editar.",
        "O diff entre duas versões mostra adds, removes e changes a nível de atributo.",
      ],
    },
    {
      n: 5,
      to: "/sync",
      icon: <CloudCog className="h-5 w-5" />,
      title: "Sincronizar com Unity Catalog",
      desc: "Em /sync, espelhe COMMENT (descrição) e TAGS (flags) do modelo ativo para o catálogo destino no Unity Catalog. Os tipos nativos NÃO são sobrescritos: apenas metadados.",
      tips: [
        "Suporta dry-run para revisar mudanças antes de aplicar.",
        "Cada sync gera um log auditável em /sync com objetos OK / SKIPPED / ERROR.",
      ],
    },
  ];

  return (
    <Section
      id="jornada"
      icon={<Compass className="h-4 w-4" />}
      title="Jornada típica do usuário"
      subtitle="Da primeira conexão até o espelhamento no Unity Catalog. Cinco passos, cada um auditável."
    >
      <div className="space-y-3">
        {steps.map((s) => (
          <Card key={s.n}>
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex items-start gap-3 md:w-64 shrink-0">
                  <div className="text-3xl font-bold text-nuclea-primary/30 tabular-nums leading-none">
                    0{s.n}
                  </div>
                  <div className="rounded-md bg-nuclea-primary/10 p-2 text-nuclea-primary">
                    {s.icon}
                  </div>
                  <div className="flex-1">
                    <Link
                      to={s.to}
                      className="font-semibold hover:text-nuclea-primary"
                    >
                      {s.title}
                    </Link>
                    <p className="text-xs text-muted-foreground mt-0.5">{s.to}</p>
                  </div>
                </div>
                <div className="flex-1 space-y-2">
                  <p className="text-sm leading-relaxed">{s.desc}</p>
                  <ul className="space-y-1">
                    {s.tips.map((t) => (
                      <li
                        key={t}
                        className="text-xs text-muted-foreground flex items-start gap-2"
                      >
                        <ArrowRight className="h-3 w-3 mt-0.5 text-nuclea-primary shrink-0" />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}

// ─── Conceitos ──────────────────────────────────────────────────────────────
function Concepts() {
  const concepts: Array<{ icon: React.ReactNode; term: string; def: string }> = [
    {
      icon: <Database className="h-4 w-4" />,
      term: "Sistema",
      def: "Agrupador lógico que representa uma aplicação ou base fonte (ex.: ' Sistema de Pagamentos ', 'CRM'). Cada entidade pertence a um sistema.",
    },
    {
      icon: <Database className="h-4 w-4" />,
      term: "Conexão",
      def: "Configuração técnica para acessar uma fonte: tipo (ODBC/REST/DDL), ambiente (HINT/HEXT/PROD), credenciais via Databricks Secrets.",
    },
    {
      icon: <FileText className="h-4 w-4" />,
      term: "Entidade",
      def: "Uma tabela, view, materialized view ou external table. Carrega owners, criticidade, tags, descrição em markdown.",
    },
    {
      icon: <FileText className="h-4 w-4" />,
      term: "Atributo",
      def: "Uma coluna de uma entidade. Tem tipo nativo, posição, PK, descrição, regra de negócio e pode ser mapeada para um termo do glossário.",
    },
    {
      icon: <Tags className="h-4 w-4" />,
      term: "Flag",
      def: "Marcação aplicada a entidades ou atributos. Categorias: LGPD (9 faixas), USE (uso), QUALITY (qualidade) e CUSTOM. Algumas exigem justificativa.",
    },
    {
      icon: <Inbox className="h-4 w-4" />,
      term: "Ticket de reconciliação",
      def: "Diff entre o catálogo atual e um snapshot (extração ou import). Status: OPEN → APPROVED → APPLIED (ou REJECTED). Auditável.",
    },
    {
      icon: <History className="h-4 w-4" />,
      term: "Versão",
      def: "Snapshot imutável do modelo de um sistema. Status: DRAFT, PUBLISHED, ACTIVE, DEPRECATED. Permite diff e restauração como rascunho.",
    },
    {
      icon: <CloudCog className="h-4 w-4" />,
      term: "Sync UC",
      def: "Operação que espelha COMMENT + TAGS do modelo ativo para o Unity Catalog. Tipos nativos NÃO são sobrescritos.",
    },
    {
      icon: <TestTube2 className="h-4 w-4" />,
      term: "Lakebase Sandbox",
      def: "Instância Postgres serverless do Databricks usada como área de validação. NÃO é o backing store do app — é só ambiente de testes.",
    },
    {
      icon: <Network className="h-4 w-4" />,
      term: "DER",
      def: "Diagrama Entidade-Relacionamento. Visualização interativa do modelo com layout salvo por sistema (React Flow + Dagre).",
    },
    {
      icon: <BookOpenText className="h-4 w-4" />,
      term: "Glossário",
      def: "Dicionário corporativo de termos com workflow DRAFT → IN_REVIEW → APPROVED → DEPRECATED e mapeamento para atributos.",
    },
    {
      icon: <GitFork className="h-4 w-4" />,
      term: "Linhagem",
      def: "Upstream (de onde vêm os dados) e downstream (quem consome) de cada entidade, com SLA e tipo de integração.",
    },
  ];

  return (
    <Section
      id="conceitos"
      icon={<Layers className="h-4 w-4" />}
      title="Conceitos-chave"
      subtitle="Vocabulário mínimo para falar sobre o catálogo da Núclea."
    >
      <div className="grid gap-3 md:grid-cols-2">
        {concepts.map((c) => (
          <Card key={c.term}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <span className="text-nuclea-primary">{c.icon}</span>
                {c.term}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {c.def}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}

// ─── Papéis (RBAC) ──────────────────────────────────────────────────────────
function Roles() {
  const roles: Array<{
    code: string;
    label: string;
    color: string;
    desc: string;
    can: string[];
    routes: Array<{ to: string; label: string }>;
  }> = [
    {
      code: "DATA_ENGINEER",
      label: "Data Engineer",
      color: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
      desc: "Conecta o app às fontes e extrai a verdade do banco.",
      can: [
        "Cadastrar e testar conexões",
        "Executar engenharia reversa (Lakebase, ODBC, DDL)",
        "Exportar DDL em qualquer dialeto",
      ],
      routes: [
        { to: "/connections", label: "Conexões" },
        { to: "/extractions", label: "Engenharia Reversa" },
        { to: "/ddl", label: "Exportar DDL" },
      ],
    },
    {
      code: "DATA_STEWARD",
      label: "Data Steward",
      color: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
      desc: "Documenta o modelo e cuida do compliance.",
      can: [
        "Editar entidades e atributos",
        "Aplicar flags LGPD com justificativa",
        "Gerenciar termos do glossário e mapeamentos",
      ],
      routes: [
        { to: "/entities", label: "Entidades" },
        { to: "/flags", label: "Flags & LGPD" },
        { to: "/glossary", label: "Dicionário" },
      ],
    },
    {
      code: "DATA_ARCHITECT",
      label: "Data Architect",
      color: "bg-nuclea-primary/10 text-nuclea-primary",
      desc: "Decide o que entra no modelo e publica versões.",
      can: [
        "Aprovar e aplicar tickets de reconciliação",
        "Publicar versões e torná-las ativas",
        "Disparar sincronização com o Unity Catalog",
      ],
      routes: [
        { to: "/tickets", label: "Tickets" },
        { to: "/versions", label: "Versões" },
        { to: "/sync", label: "Sync UC" },
      ],
    },
    {
      code: "CDE",
      label: "CdE (Consumidor)",
      color: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
      desc: "Lê o catálogo, sem permissão de escrita.",
      can: [
        "Consultar entidades, atributos e glossário",
        "Visualizar DER, linhagem e versões",
        "Ver dashboards e métricas",
      ],
      routes: [
        { to: "/dashboard", label: "Dashboard" },
        { to: "/diagram", label: "Diagrama" },
        { to: "/lineage", label: "Linhagem" },
      ],
    },
    {
      code: "ADMIN",
      label: "Admin",
      color: "bg-red-500/10 text-red-700 dark:text-red-300",
      desc: "Governa o app: papéis e auditoria.",
      can: [
        "Conceder e revogar papéis (RBAC)",
        "Acessar logs e auditoria",
        "Todas as ações dos demais papéis",
      ],
      routes: [{ to: "/admin/roles", label: "Papéis (RBAC)" }],
    },
  ];

  return (
    <Section
      id="papeis"
      icon={<UserCog className="h-4 w-4" />}
      title="Por papel (RBAC)"
      subtitle="Quem faz o quê. Os papéis são concedidos pelo Admin em /admin/roles."
    >
      <div className="grid gap-4 md:grid-cols-2">
        {roles.map((r) => (
          <Card key={r.code}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{r.label}</CardTitle>
                <Badge className={r.color} variant="outline">
                  {r.code}
                </Badge>
              </div>
              <CardDescription>{r.desc}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1.5">
                {r.can.map((c) => (
                  <li key={c} className="text-sm flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 mt-0.5 text-nuclea-primary shrink-0" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
              <Separator />
              <div className="flex flex-wrap gap-1.5">
                {r.routes.map((rt) => (
                  <Link
                    key={rt.to}
                    to={rt.to}
                    className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 text-xs hover:border-nuclea-primary/50 hover:text-nuclea-primary"
                  >
                    {rt.label}
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}

// ─── Ticket flow ────────────────────────────────────────────────────────────
function TicketFlow() {
  const states: Array<{
    code: string;
    label: string;
    icon: React.ReactNode;
    actor: string;
    desc: string;
    color: string;
  }> = [
    {
      code: "OPEN",
      label: "OPEN",
      icon: <Circle className="h-4 w-4" />,
      actor: "auto (extração)",
      desc: "Ticket aberto automaticamente por uma extração ou import DDL. Aguarda revisão.",
      color: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
    },
    {
      code: "APPROVED",
      label: "APPROVED",
      icon: <CheckCircle2 className="h-4 w-4" />,
      actor: "Data Architect",
      desc: "Mudanças foram revisadas e aprovadas. Ainda não foram aplicadas ao catálogo.",
      color: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    },
    {
      code: "APPLIED",
      label: "APPLIED",
      icon: <PlayCircle className="h-4 w-4" />,
      actor: "Data Architect",
      desc: "Mudanças foram persistidas nas tabelas Delta. Estado terminal de sucesso.",
      color: "bg-nuclea-primary/10 text-nuclea-primary",
    },
    {
      code: "REJECTED",
      label: "REJECTED",
      icon: <XCircle className="h-4 w-4" />,
      actor: "Data Architect",
      desc: "Mudanças foram recusadas com justificativa. Estado terminal de descarte. Não bloqueia novas extrações.",
      color: "bg-red-500/10 text-red-700 dark:text-red-300",
    },
  ];

  return (
    <Section
      id="tickets"
      icon={<Workflow className="h-4 w-4" />}
      title="Fluxo do Ticket de Reconciliação"
      subtitle="Aprovar e aplicar são DOIS passos. Isso é proposital — permite revisão entre o consenso e a escrita."
    >
      <Card>
        <CardContent className="pt-6">
          <pre className="text-xs md:text-sm font-mono bg-muted/40 rounded-md p-4 overflow-x-auto">
            {`         (extração / import)
                  │
                  ▼
              ┌───────┐    approve     ┌──────────┐    apply    ┌──────────┐
              │ OPEN  │ ─────────────► │ APPROVED │ ──────────► │ APPLIED  │
              └───────┘                └──────────┘             └──────────┘
                  │
                  │  reject (motivo obrigatório)
                  ▼
              ┌──────────┐
              │ REJECTED │
              └──────────┘`}
          </pre>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {states.map((s) => (
          <Card key={s.code}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <Badge className={s.color} variant="outline">
                  <span className="inline-flex items-center gap-1">
                    {s.icon}
                    {s.label}
                  </span>
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Ator: <span className="font-medium text-foreground">{s.actor}</span>
              </p>
              <p className="text-sm leading-relaxed">{s.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  );
}

// ─── LGPD ───────────────────────────────────────────────────────────────────
function LgpdFlags() {
  const flags = [
    { key: "PII", desc: "Dado pessoal identificável (nome, CPF, e-mail)." },
    { key: "PII_SENSITIVE", desc: "Dado pessoal sensível (origem racial, religião, saúde, biometria, orientação sexual)." },
    { key: "FINANCIAL", desc: "Dado financeiro (saldo, transação, score)." },
    { key: "MINOR", desc: "Dado de criança ou adolescente — exige base legal específica." },
    { key: "ANONYMIZED", desc: "Dado anonimizado (irreversível). Fora do escopo LGPD." },
    { key: "PSEUDONYMIZED", desc: "Dado pseudonimizado (reversível via chave). Continua sob LGPD." },
    { key: "INTERNAL_ONLY", desc: "Uso restrito interno — não compartilhar externamente." },
    { key: "RETENTION_LIMITED", desc: "Retenção por tempo limitado — exige política de expurgo." },
    { key: "CROSS_BORDER", desc: "Pode trafegar entre países — atenção à transferência internacional (art. 33)." },
  ];

  const bases = [
    "Consentimento",
    "Cumprimento de obrigação legal",
    "Execução de contrato",
    "Legítimo interesse",
    "Proteção da vida",
    "Tutela da saúde",
    "Exercício regular de direitos",
    "Proteção ao crédito",
    "Políticas públicas",
    "Estudos por órgão de pesquisa",
  ];

  return (
    <Section
      id="lgpd"
      icon={<ShieldAlert className="h-4 w-4" />}
      title="Faixas LGPD"
      subtitle="9 faixas pré-cadastradas como flags de sistema. Algumas exigem justificativa explícita ao aplicar."
    >
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {flags.map((f) => (
          <div
            key={f.key}
            className="rounded-lg border bg-card p-3 space-y-1.5"
          >
            <div className="flex items-center gap-2">
              <Tags className="h-3.5 w-3.5 text-nuclea-primary" />
              <span className="font-mono text-xs font-semibold">{f.key}</span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {f.desc}
            </p>
          </div>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-4 w-4 text-nuclea-primary" />
            Bases legais (LGPD art. 7º e art. 11)
          </CardTitle>
          <CardDescription>
            Toda flag LGPD aplicada deve estar amparada por pelo menos uma base
            legal. A justificativa é obrigatória quando a flag a exige.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {bases.map((b) => (
              <Badge key={b} variant="outline" className="text-xs">
                {b}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
    </Section>
  );
}

// ─── FAQ ────────────────────────────────────────────────────────────────────
function Faq() {
  const items: Array<{ q: string; a: React.ReactNode }> = [
    {
      q: "Por que minha extração não criou nada no catálogo?",
      a: (
        <>
          A extração gera um <strong>ticket</strong> de reconciliação. As
          mudanças só aparecem no catálogo depois que o ticket é{" "}
          <strong>aprovado</strong> e <strong>aplicado</strong> por um Data
          Architect em <Link to="/tickets" className="text-nuclea-primary underline">/tickets</Link>.
        </>
      ),
    },
    {
      q: "Posso editar uma versão já publicada?",
      a: (
        <>
          Não. Versões publicadas são <strong>imutáveis</strong> por design
          (auditoria). Para iterar, use <strong>Restaurar como rascunho</strong>{" "}
          em <Link to="/versions" className="text-nuclea-primary underline">/versions</Link> — isso cria uma nova versão DRAFT a partir do snapshot.
        </>
      ),
    },
    {
      q: "Onde os dados do app são armazenados?",
      a: (
        <>
          100% em tabelas <strong>Delta</strong> no Unity Catalog, no schema{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">data_catalog_app</code>. Nada é gravado fora do UC.
        </>
      ),
    },
    {
      q: "Lakebase é o backing store do app?",
      a: (
        <>
          <strong>NÃO.</strong> Lakebase é um sandbox <em>opcional</em> de
          validação — uma instância Postgres serverless do Databricks usada
          como fonte para engenharia reversa ou para testar modelos. O catálogo
          em si vive em Delta no UC.
        </>
      ),
    },
    {
      q: "Como crio um modelo do zero, sem extração?",
      a: (
        <>
          Vá em <Link to="/entities" className="text-nuclea-primary underline">/entities</Link>{" "}
          → <strong>Nova entidade</strong>. Em seguida, cadastre os atributos e
          relacionamentos. O DER aparece automaticamente em{" "}
          <Link to="/diagram" className="text-nuclea-primary underline">/diagram</Link>.
        </>
      ),
    },
    {
      q: "Posso importar de outras ferramentas?",
      a: (
        <>
          Sim. Em <Link to="/extractions" className="text-nuclea-primary underline">/extractions</Link>{" "}
          → <strong>Importar DDL</strong>: cole o DDL e escolha o dialeto
          (T-SQL, PL/SQL, Postgres, MySQL, Spark SQL etc.). Importação de{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">.erx</code>{" "}
          (Embarcadero) também é suportada.
        </>
      ),
    },
    {
      q: "O que é sincronização com o Unity Catalog?",
      a: (
        <>
          A operação <strong>Sync UC</strong> espelha{" "}
          <strong>COMMENT</strong> (descrição) e <strong>TAGS</strong> (flags)
          do modelo ativo para tabelas reais no Unity Catalog. Os{" "}
          <strong>tipos nativos NÃO são sobrescritos</strong> — apenas
          metadados. Configure em{" "}
          <Link to="/sync" className="text-nuclea-primary underline">/sync</Link>.
        </>
      ),
    },
    {
      q: "Como atribuir um papel a um usuário?",
      a: (
        <>
          Apenas usuários com papel <strong>ADMIN</strong> conseguem. Vá em{" "}
          <Link to="/admin/roles" className="text-nuclea-primary underline">/admin/roles</Link>{" "}
          → conceder papel pelo e-mail corporativo. Revogação é soft-delete
          (auditável).
        </>
      ),
    },
    {
      q: "Posso reverter um ticket já aplicado?",
      a: (
        <>
          Não diretamente. Como o ticket altera o estado do catálogo, a forma
          correta é abrir um novo ticket (via nova extração ou edição manual)
          que represente o estado desejado. O histórico fica preservado.
        </>
      ),
    },
    {
      q: "Quem pode ver dados sensíveis (PII_SENSITIVE)?",
      a: (
        <>
          O app exibe apenas <strong>metadados</strong> — nunca valores. As
          flags LGPD são informativas e auditáveis: indicam que aquela coluna
          contém dado sensível. O acesso aos dados reais é controlado pelo
          Unity Catalog.
        </>
      ),
    },
  ];

  return (
    <Section
      id="faq"
      icon={<MessageCircleQuestion className="h-4 w-4" />}
      title="Perguntas frequentes"
      subtitle="Dúvidas comuns que recebemos durante o onboarding."
    >
      <div className="space-y-2">
        {items.map((it, i) => (
          <details
            key={i}
            className="group rounded-lg border bg-card open:bg-card/80"
          >
            <summary className="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3 text-sm font-medium hover:bg-muted/40 rounded-lg">
              <span className="flex items-center gap-2">
                <MessageCircleQuestion className="h-4 w-4 text-nuclea-primary shrink-0" />
                {it.q}
              </span>
              <span className="text-muted-foreground text-xs group-open:rotate-90 transition-transform">
                ▶
              </span>
            </summary>
            <div className="px-4 pb-4 pt-1 text-sm text-muted-foreground leading-relaxed border-t">
              <div className="pt-3">{it.a}</div>
            </div>
          </details>
        ))}
      </div>
    </Section>
  );
}

// ─── Atalhos ────────────────────────────────────────────────────────────────
function Shortcuts() {
  const items = [
    { keys: ["Cmd/Ctrl", "K"], desc: "Busca global (em breve)" },
    { keys: ["click no logo"], desc: "Voltar para a Home" },
    { keys: ["Esc"], desc: "Fechar diálogos e drawers" },
    { keys: ["Tab"], desc: "Navegar entre campos de formulários" },
  ];

  return (
    <Section
      id="atalhos"
      icon={<Keyboard className="h-4 w-4" />}
      title="Atalhos de teclado"
      subtitle="Pequenas otimizações de fluxo. Mais virão à medida que o app cresce."
    >
      <Card>
        <CardContent className="pt-6 divide-y">
          {items.map((it) => (
            <div
              key={it.desc}
              className="flex items-center justify-between py-2.5 text-sm"
            >
              <span className="text-muted-foreground">{it.desc}</span>
              <span className="flex items-center gap-1">
                {it.keys.map((k) => (
                  <kbd
                    key={k}
                    className="font-mono text-xs rounded border bg-muted px-1.5 py-0.5"
                  >
                    {k}
                  </kbd>
                ))}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </Section>
  );
}

// ─── Sobre ─────────────────────────────────────────────────────────────────
function About() {
  const stack = [
    { layer: "Backend", items: ["FastAPI", "psycopg", "sqlglot", "Databricks SDK"] },
    { layer: "Frontend", items: ["React 19", "TanStack Router", "TanStack Query", "shadcn/ui", "Tailwind 4"] },
    { layer: "Diagrama", items: ["React Flow", "Dagre"] },
    { layer: "Dados", items: ["Delta Lake", "Unity Catalog", "Lakebase (Postgres)"] },
  ];

  return (
    <Section
      id="sobre"
      icon={<Wrench className="h-4 w-4" />}
      title="Sobre / Construído com"
      subtitle="O que está debaixo do capô."
    >
      <Card>
        <CardContent className="pt-6 space-y-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <span className="size-2 rounded-full bg-nuclea-primary" />
              <span className="font-semibold">Núclea Modeler</span>
              <Badge variant="outline" className="text-[10px]">
                v0.1.0
              </Badge>
            </div>
            <a
              href="https://github.com/lfmed/nuclea-modeler"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
            >
              <Github className="h-4 w-4" />
              github.com/lfmed/nuclea-modeler
            </a>
          </div>

          <Separator />

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {stack.map((s) => (
              <div key={s.layer}>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                  {s.layer}
                </div>
                <ul className="space-y-1">
                  {s.items.map((i) => (
                    <li key={i} className="text-sm flex items-center gap-2">
                      <span className="size-1 rounded-full bg-nuclea-primary" />
                      {i}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Subtle "got more questions?" CTA */}
      <Card className="border-nuclea-primary/30">
        <CardContent className="pt-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="rounded-md bg-nuclea-primary/10 p-2 text-nuclea-primary">
              <HelpCircle className="h-5 w-5" />
            </div>
            <div>
              <p className="font-medium">Ainda com dúvidas?</p>
              <p className="text-sm text-muted-foreground">
                Abra uma issue no GitHub ou fale com o time da Tribo de Dados.
              </p>
            </div>
          </div>
          <a
            href="https://github.com/lfmed/nuclea-modeler/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm font-medium hover:border-nuclea-primary/50"
          >
            <Github className="h-4 w-4" />
            Abrir issue
          </a>
        </CardContent>
      </Card>
    </Section>
  );
}

