import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useMemo, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListFlagsSuspense,
  useCreateCustomFlag,
  useToggleFlag,
  useMyRolesSuspense,
  type FlagCategory,
  type FlagOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  AlertCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Tag,
  Sparkles,
  CheckCircle2,
  XCircle,
  X,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/flags")({
  component: FlagsPage,
});

const CATEGORY_META: Record<
  FlagCategory,
  { title: string; description: string; icon: React.ReactNode }
> = {
  LGPD: {
    title: "LGPD / Privacidade",
    description:
      "Sinalização de dados pessoais, sensíveis e bases legais. Requer justificativa.",
    icon: <ShieldCheck className="h-4 w-4 text-nuclea-primary" />,
  },
  USE: {
    title: "Uso do dado",
    description: "Categorização funcional do dado (master, transacional, depreciado, etc).",
    icon: <Tag className="h-4 w-4 text-nuclea-accent" />,
  },
  QUALITY: {
    title: "Qualidade",
    description: "Indicadores de validação, criticidade e inconsistências conhecidas.",
    icon: <CheckCircle2 className="h-4 w-4 text-emerald-600" />,
  },
  CUSTOM: {
    title: "Personalizadas",
    description: "Flags criadas por arquitetos/admins para necessidades específicas.",
    icon: <Sparkles className="h-4 w-4 text-amber-600" />,
  },
};

const CATEGORY_ORDER: FlagCategory[] = ["LGPD", "USE", "QUALITY", "CUSTOM"];

function FlagsPage() {
  return (
    <div className="space-y-6">
      <Header />
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar flags
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Tentar novamente
                  </Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<PageSkeleton />}>
              <FlagsBody />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function Header() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <h1 className="text-3xl font-bold tracking-tight">Flags &amp; LGPD</h1>
        <Badge variant="outline" className="font-mono">
          M5
        </Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Marcação categórica de tabelas e colunas para controle de uso,
        privacidade e conformidade. Flags <strong>LGPD</strong> aplicadas a
        colunas propagam automaticamente uma sinalização para a entidade-pai.
      </p>
    </div>
  );
}

function FlagsBody() {
  const [tab, setTab] = useState<"catalog" | "lgpd">("catalog");
  return (
    <div className="space-y-4">
      <Tabs
        current={tab}
        onChange={setTab}
        tabs={[
          { key: "catalog", label: "Catálogo de Flags" },
          { key: "lgpd", label: "Cobertura LGPD" },
        ]}
      />
      {tab === "catalog" ? <CatalogTab /> : <LgpdCoverageTab />}
    </div>
  );
}

function Tabs<T extends string>({
  current,
  onChange,
  tabs,
}: {
  current: T;
  onChange: (v: T) => void;
  tabs: { key: T; label: string }[];
}) {
  return (
    <div className="inline-flex rounded-md border bg-muted/40 p-1">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={
            "px-3 py-1.5 text-sm rounded transition-colors " +
            (current === t.key
              ? "bg-background shadow-sm font-medium"
              : "text-muted-foreground hover:text-foreground")
          }
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function CatalogTab() {
  const { data: flags } = useListFlagsSuspense({}, selector());
  const { data: roles } = useMyRolesSuspense(selector());
  const [showNew, setShowNew] = useState(false);

  const canManage = roles.is_admin || roles.roles.includes("DATA_ARCHITECT");

  const grouped = useMemo(() => {
    const g: Record<FlagCategory, FlagOut[]> = {
      LGPD: [],
      USE: [],
      QUALITY: [],
      CUSTOM: [],
    };
    for (const f of flags) g[f.category]?.push(f);
    return g;
  }, [flags]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {flags.length} flags catalogadas — sistema:{" "}
          <strong>{flags.filter((f) => f.is_system).length}</strong>, customizadas:{" "}
          <strong>{flags.filter((f) => !f.is_system).length}</strong>.
        </p>
        {canManage && (
          <Button size="sm" onClick={() => setShowNew(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Nova flag custom
          </Button>
        )}
      </div>

      {showNew && (
        <NewCustomFlagForm onClose={() => setShowNew(false)} />
      )}

      <div className="space-y-6">
        {CATEGORY_ORDER.map((cat) => {
          const list = grouped[cat];
          if (!list || list.length === 0) return null;
          const meta = CATEGORY_META[cat];
          return (
            <Card key={cat}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {meta.icon}
                  {meta.title}
                  <Badge variant="outline" className="ml-1">
                    {list.length}
                  </Badge>
                </CardTitle>
                <CardDescription>{meta.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2">
                  {list.map((f) => (
                    <FlagCard key={f.flag_id} flag={f} canManage={canManage} />
                  ))}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function FlagCard({ flag, canManage }: { flag: FlagOut; canManage: boolean }) {
  const qc = useQueryClient();
  const { mutate: toggle, isPending } = useToggleFlag({
    mutation: {
      onSuccess: () => qc.invalidateQueries({ queryKey: ["listFlags"] }),
    },
  });

  return (
    <div
      className={
        "rounded-lg border p-3 flex flex-col gap-2 " +
        (flag.is_active ? "bg-background" : "bg-muted/30 opacity-70")
      }
    >
      <div className="flex items-start gap-2">
        <FlagChip flag={flag} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-sm">{flag.display_name}</span>
            {flag.is_system ? (
              <Badge variant="secondary" className="text-[10px]">
                sistema
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">
                custom
              </Badge>
            )}
            {flag.requires_justification && (
              <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-700">
                justificativa
              </Badge>
            )}
            {!flag.is_active && (
              <Badge variant="outline" className="text-[10px] border-destructive/40 text-destructive">
                inativa
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground font-mono mt-0.5">
            {flag.flag_key}
          </p>
        </div>
      </div>
      {flag.description && (
        <p className="text-xs text-muted-foreground leading-snug">
          {flag.description}
        </p>
      )}
      {canManage && (
        <div className="flex justify-end">
          <button
            disabled={isPending}
            onClick={() =>
              toggle({ flagId: flag.flag_id, data: { is_active: !flag.is_active } })
            }
            className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            title={flag.is_active ? "Desativar" : "Reativar"}
          >
            {flag.is_active ? (
              <>
                <XCircle className="h-3.5 w-3.5" /> Desativar
              </>
            ) : (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" /> Reativar
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

export function FlagChip({
  flag,
  onRemove,
  small,
}: {
  flag: FlagOut;
  onRemove?: () => void;
  small?: boolean;
}) {
  const bg = flag.color_hex || "#6C757D";
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded-full border border-black/10 text-white " +
        (small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs")
      }
      style={{ backgroundColor: bg }}
      title={flag.description || flag.display_name}
    >
      <span className="font-medium">{flag.display_name}</span>
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="hover:bg-black/20 rounded-full p-0.5"
          aria-label="Remover flag"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}

function NewCustomFlagForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [color, setColor] = useState("#6C757D");
  const [requires, setRequires] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useCreateCustomFlag({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listFlags"] });
        onClose();
      },
      onError: (e) => setError(String((e as Error).message || e)),
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mutate({
      data: {
        flag_key: key.trim(),
        display_name: name.trim(),
        description: desc.trim() || null,
        color_hex: color,
        requires_justification: requires,
      },
    });
  };

  return (
    <Card className="border-nuclea-primary/40">
      <CardHeader>
        <CardTitle className="text-lg">Nova flag personalizada</CardTitle>
        <CardDescription>
          Flags personalizadas ficam em <code>CUSTOM</code>. Use uma chave única
          em <code>kebab-case</code>.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid md:grid-cols-2 gap-3">
            <Input
              placeholder="flag_key (ex: equipe-risco)*"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              required
            />
            <Input
              placeholder="Nome de exibição*"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <Input
            placeholder="Descrição"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
          <div className="flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <span className="text-muted-foreground">Cor:</span>
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-8 w-12 rounded border cursor-pointer"
              />
              <code className="text-xs text-muted-foreground">{color}</code>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={requires}
                onChange={(e) => setRequires(e.target.checked)}
              />
              Requer justificativa
            </label>
          </div>
          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
          <Separator />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending || !key || !name}>
              {isPending ? "Criando..." : "Criar flag"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function LgpdCoverageTab() {
  const { data: flags } = useListFlagsSuspense({ category: "LGPD" }, selector());
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-nuclea-primary" />
          Cobertura LGPD
        </CardTitle>
        <CardDescription>
          Visão consolidada das flags de privacidade catalogadas. Relatórios
          agregados por sistema/domínio entrarão em fase posterior.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-3">
          {flags.map((f) => (
            <div key={f.flag_id} className="rounded-lg border p-3 flex flex-col gap-1.5">
              <FlagChip flag={f} />
              <p className="text-xs text-muted-foreground">
                {f.description}
              </p>
              {f.requires_justification && (
                <span className="text-[10px] text-amber-700">
                  Justificativa obrigatória
                </span>
              )}
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-6 italic">
          Em construção: relatório agregado por sistema / domínio / entidade.
        </p>
      </CardContent>
    </Card>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
