import { createFileRoute, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useListEntitiesSuspense,
  useListUpstreamSuspense,
  useListDownstreamSuspense,
  useLineageGraphSuspense,
  useCreateUpstream,
  useDeleteUpstream,
  useCreateDownstream,
  useDeleteDownstream,
  type IntegrationType,
  type Periodicity,
  type ConsumptionType,
  type SLALevel,
  type LineageGraph,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  GitFork,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";

export const Route = createFileRoute("/_sidebar/lineage")({
  component: LineagePage,
});

function LineagePage() {
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
                    Erro ao carregar linhagem
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
            <Suspense fallback={<Skeleton className="h-40 w-full" />}>
              <LineageBody />
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
        <h1 className="text-3xl font-bold tracking-tight">Linhagem</h1>
        <Badge variant="outline" className="font-mono">M7</Badge>
      </div>
      <p className="text-muted-foreground max-w-3xl">
        Origem (upstream) e consumo (downstream) das entidades catalogadas. Documente sistemas
        que alimentam os dados, tipos de integração, periodicidade e quem consome
        cada entidade.
      </p>
    </div>
  );
}

function LineageBody() {
  const { data: entities } = useListEntitiesSuspense({}, selector());
  const [entityId, setEntityId] = useState(entities[0]?.entity_id || "");
  const [depth, setDepth] = useState(1);

  if (entities.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-10 pb-10 text-center">
          <GitFork className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            Cadastre entidades primeiro para mapear sua linhagem.
          </p>
          <Button asChild>
            <Link to="/entities">Ir para Entidades</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[240px]">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Entidade
              </label>
              <select
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                {entities.map((e) => (
                  <option key={e.entity_id} value={e.entity_id}>
                    {e.schema_name}.{e.technical_name} · {e.system_name || e.system_id}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Profundidade
              </label>
              <select
                value={depth}
                onChange={(e) => setDepth(parseInt(e.target.value))}
                className="rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value={1}>1 nível</option>
                <option value={2}>2 níveis</option>
                <option value={3}>3 níveis</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {entityId && (
        <>
          <Suspense fallback={<Skeleton className="h-48 w-full" />}>
            <GraphCard entityId={entityId} depth={depth} />
          </Suspense>

          <div className="grid lg:grid-cols-2 gap-6">
            <Suspense fallback={<Skeleton className="h-64 w-full" />}>
              <UpstreamSection entityId={entityId} />
            </Suspense>
            <Suspense fallback={<Skeleton className="h-64 w-full" />}>
              <DownstreamSection entityId={entityId} />
            </Suspense>
          </div>
        </>
      )}
    </div>
  );
}

function GraphCard({ entityId, depth }: { entityId: string; depth: number }) {
  const { data: graph } = useLineageGraphSuspense(entityId, depth, selector());

  return (
    <Card>
      <CardHeader>
        <CardTitle>Grafo de linhagem</CardTitle>
        <CardDescription>
          {graph.nodes.length} nós, {graph.edges.length} ligações · profundidade {graph.depth}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <SimpleGraph graph={graph} />
      </CardContent>
    </Card>
  );
}

function SimpleGraph({ graph }: { graph: LineageGraph }) {
  const upstream = graph.edges.filter((e) => e.edge_kind === "upstream");
  const downstream = graph.edges.filter((e) => e.edge_kind === "downstream");
  const center = graph.nodes.find((n) => n.id === graph.center_entity_id);

  const findLabel = (id: string) => graph.nodes.find((n) => n.id === id)?.label || id;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center text-sm">
      <div className="space-y-2">
        <h4 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
          <ArrowUp className="h-3 w-3" />
          Upstream ({upstream.length})
        </h4>
        {upstream.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">sem origens documentadas</p>
        ) : (
          upstream.map((e, i) => (
            <div key={i} className="rounded-md border bg-muted/30 px-3 py-2">
              <p className="font-medium">{findLabel(e.source)}</p>
              {e.label && <p className="text-xs text-muted-foreground">{e.label}</p>}
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col items-center">
        <ArrowDown className="h-5 w-5 text-nuclea-primary mb-1 md:rotate-[-90deg]" />
        <div className="rounded-lg border-2 border-nuclea-primary bg-nuclea-primary/5 px-4 py-3 text-center">
          <p className="font-semibold text-nuclea-primary">{center?.label}</p>
          {center?.system_name && (
            <p className="text-xs text-muted-foreground mt-1">{center.system_name}</p>
          )}
          {center?.entity_type && (
            <Badge variant="outline" className="mt-2 text-xs">{center.entity_type}</Badge>
          )}
        </div>
        <ArrowDown className="h-5 w-5 text-nuclea-primary mt-1 md:rotate-[-90deg]" />
      </div>

      <div className="space-y-2">
        <h4 className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
          <ArrowDown className="h-3 w-3" />
          Downstream ({downstream.length})
        </h4>
        {downstream.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">sem consumidores documentados</p>
        ) : (
          downstream.map((e, i) => (
            <div key={i} className="rounded-md border bg-muted/30 px-3 py-2">
              <p className="font-medium">{findLabel(e.target)}</p>
              <div className="flex items-center gap-2 mt-1">
                {e.label && <p className="text-xs text-muted-foreground">{e.label}</p>}
                {e.sla_dependency && (
                  <Badge variant="outline" className="text-[10px]">SLA: {e.sla_dependency}</Badge>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function UpstreamSection({ entityId }: { entityId: string }) {
  const { data: items } = useListUpstreamSuspense(entityId, selector());
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { mutate: create, isPending } = useCreateUpstream({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listUpstream", entityId] });
        qc.invalidateQueries({ queryKey: ["lineageGraph", entityId] });
        setShowForm(false);
      },
    },
  });
  const { mutate: del } = useDeleteUpstream({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listUpstream", entityId] });
        qc.invalidateQueries({ queryKey: ["lineageGraph", entityId] });
      },
    },
  });

  const [sourceSystem, setSourceSystem] = useState("");
  const [sourceEntity, setSourceEntity] = useState("");
  const [integrationType, setIntegrationType] = useState<IntegrationType | "">("BATCH");
  const [periodicity, setPeriodicity] = useState<Periodicity | "">("DAILY");
  const [pipelineLink, setPipelineLink] = useState("");

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ArrowUp className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              Origem ({items.length})
            </CardTitle>
            <CardDescription>Sistemas que alimentam esta entidade</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus className="mr-2 h-4 w-4" />
            {showForm ? "Cancelar" : "Adicionar origem"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create({
                entityId,
                data: {
                  entity_id: entityId,
                  source_system: sourceSystem,
                  source_entity: sourceEntity || null,
                  integration_type: (integrationType || null) as IntegrationType | null,
                  periodicity: (periodicity || null) as Periodicity | null,
                  pipeline_link: pipelineLink || null,
                },
              });
              setSourceSystem("");
              setSourceEntity("");
              setPipelineLink("");
            }}
            className="rounded-lg border bg-muted/30 p-3 space-y-2"
          >
            <Input placeholder="Sistema de origem*" value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} required />
            <Input placeholder="Entidade/endpoint de origem (opcional)" value={sourceEntity} onChange={(e) => setSourceEntity(e.target.value)} />
            <div className="grid grid-cols-2 gap-2">
              <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={integrationType} onChange={(e) => setIntegrationType(e.target.value as any)}>
                <option value="CDC">CDC</option>
                <option value="BATCH">Batch</option>
                <option value="API_PULL">API Pull</option>
                <option value="API_PUSH">API Push</option>
                <option value="FILE">Arquivo</option>
              </select>
              <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={periodicity} onChange={(e) => setPeriodicity(e.target.value as any)}>
                <option value="REAL_TIME">Tempo real</option>
                <option value="DAILY">Diário</option>
                <option value="WEEKLY">Semanal</option>
                <option value="MONTHLY">Mensal</option>
                <option value="ON_DEMAND">Sob demanda</option>
              </select>
            </div>
            <Input placeholder="Link do pipeline (opcional)" value={pipelineLink} onChange={(e) => setPipelineLink(e.target.value)} />
            <Button type="submit" size="sm" disabled={isPending || !sourceSystem}>
              {isPending ? "Salvando..." : "Adicionar"}
            </Button>
          </form>
        )}

        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">Sem origens cadastradas.</p>
        ) : (
          items.map((u) => (
            <div key={u.lineage_id} className="rounded-md border px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <p className="font-medium text-sm">{u.source_system}</p>
                  {u.source_entity && (
                    <p className="text-xs text-muted-foreground font-mono">{u.source_entity}</p>
                  )}
                  <div className="flex flex-wrap gap-1 mt-1">
                    {u.integration_type && <Badge variant="outline" className="text-xs">{u.integration_type}</Badge>}
                    {u.periodicity && <Badge variant="secondary" className="text-xs">{u.periodicity}</Badge>}
                  </div>
                  {u.pipeline_link && (
                    <a href={u.pipeline_link} target="_blank" rel="noopener" className="text-xs text-nuclea-primary hover:underline">
                      Ver pipeline ↗
                    </a>
                  )}
                </div>
                <button onClick={() => del({ lineageId: u.lineage_id })} className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function DownstreamSection({ entityId }: { entityId: string }) {
  const { data: items } = useListDownstreamSuspense(entityId, selector());
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { mutate: create, isPending } = useCreateDownstream({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listDownstream", entityId] });
        qc.invalidateQueries({ queryKey: ["lineageGraph", entityId] });
        setShowForm(false);
      },
    },
  });
  const { mutate: del } = useDeleteDownstream({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listDownstream", entityId] });
        qc.invalidateQueries({ queryKey: ["lineageGraph", entityId] });
      },
    },
  });

  const [consumerSystem, setConsumerSystem] = useState("");
  const [consumptionType, setConsumptionType] = useState<ConsumptionType | "">("DIRECT_READ");
  const [team, setTeam] = useState("");
  const [sla, setSla] = useState<SLALevel | "">("MEDIUM");

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ArrowDown className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              Consumidores ({items.length})
            </CardTitle>
            <CardDescription>Sistemas/áreas que consomem esta entidade</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus className="mr-2 h-4 w-4" />
            {showForm ? "Cancelar" : "Adicionar consumidor"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showForm && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create({
                entityId,
                data: {
                  entity_id: entityId,
                  consumer_system: consumerSystem,
                  consumption_type: (consumptionType || null) as ConsumptionType | null,
                  responsible_team: team || null,
                  sla_dependency: (sla || null) as SLALevel | null,
                  detected_via: "MANUAL",
                },
              });
              setConsumerSystem("");
              setTeam("");
            }}
            className="rounded-lg border bg-muted/30 p-3 space-y-2"
          >
            <Input placeholder="Sistema consumidor*" value={consumerSystem} onChange={(e) => setConsumerSystem(e.target.value)} required />
            <div className="grid grid-cols-2 gap-2">
              <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={consumptionType} onChange={(e) => setConsumptionType(e.target.value as any)}>
                <option value="DIRECT_READ">Leitura direta</option>
                <option value="API">API</option>
                <option value="REPORT">Relatório</option>
                <option value="ML_MODEL">Modelo ML</option>
              </select>
              <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={sla} onChange={(e) => setSla(e.target.value as any)}>
                <option value="CRITICAL">Crítico</option>
                <option value="HIGH">Alto</option>
                <option value="MEDIUM">Médio</option>
                <option value="LOW">Baixo</option>
              </select>
            </div>
            <Input placeholder="Equipe responsável" value={team} onChange={(e) => setTeam(e.target.value)} />
            <Button type="submit" size="sm" disabled={isPending || !consumerSystem}>
              {isPending ? "Salvando..." : "Adicionar"}
            </Button>
          </form>
        )}

        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">Sem consumidores cadastrados.</p>
        ) : (
          items.map((d) => (
            <div key={d.consumer_id} className="rounded-md border px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <p className="font-medium text-sm">{d.consumer_system}</p>
                  {d.responsible_team && (
                    <p className="text-xs text-muted-foreground">{d.responsible_team}</p>
                  )}
                  <div className="flex flex-wrap gap-1 mt-1">
                    {d.consumption_type && <Badge variant="outline" className="text-xs">{d.consumption_type}</Badge>}
                    {d.sla_dependency && <Badge variant="secondary" className="text-xs">SLA: {d.sla_dependency}</Badge>}
                  </div>
                </div>
                <button onClick={() => del({ consumerId: d.consumer_id })} className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
