import { createFileRoute } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Database, ScanSearch, FileText, CloudCog, AlertCircle, Activity } from "lucide-react";

export const Route = createFileRoute("/_sidebar/dashboard")({
  component: Dashboard,
});

function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Visão geral do catálogo de dados Núclea — status de ambientes, modelos publicados, sync UC e atividade recente.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard icon={<Database className="h-4 w-4" />} label="Conexões" value="—" hint="HINT · HEXT · PROD" />
        <KpiCard icon={<FileText className="h-4 w-4" />} label="Entidades" value="—" hint="catalogadas" />
        <KpiCard icon={<ScanSearch className="h-4 w-4" />} label="Última extração" value="—" hint="por sistema" />
        <KpiCard icon={<CloudCog className="h-4 w-4" />} label="Sync UC" value="—" hint="objetos em sincronia" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                Saúde dos ambientes
              </CardTitle>
              <Badge variant="outline">Status</Badge>
            </div>
            <CardDescription>Latência e disponibilidade das conexões cadastradas</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <EnvStatus name="HINT — Homologação Interna" status="placeholder" />
            <EnvStatus name="HEXT — Homologação Externa" status="placeholder" />
            <EnvStatus name="PROD — Produção" status="placeholder" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Conformidade LGPD
            </CardTitle>
            <CardDescription>Cobertura de flags em colunas com dados pessoais</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Dados aparecem aqui quando o Módulo 5 (Flagueamento) estiver ativo na Fase 2.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
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
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-2 text-xs uppercase tracking-wider">
          <span className="text-nuclea-primary">{icon}</span>
          {label}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  );
}

function EnvStatus({ name, status }: { name: string; status: "placeholder" | "ok" | "down" }) {
  const color =
    status === "ok"
      ? "bg-emerald-500"
      : status === "down"
        ? "bg-destructive"
        : "bg-muted-foreground/40";
  const label =
    status === "ok" ? "Operacional" : status === "down" ? "Indisponível" : "Sem conexão cadastrada";
  return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2">
      <div className="flex items-center gap-3">
        <span className={`size-2 rounded-full ${color}`} />
        <span className="text-sm">{name}</span>
      </div>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}
