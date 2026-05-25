import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useEffect, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetTriggerSuspense,
  useUpdateTrigger,
  useDeleteTrigger,
  type EventType,
  type TriggerTiming,
  type RiskLevel,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, AlertCircle, Zap, Save, Trash2 } from "lucide-react";
import { SqlEditor } from "@/components/code/sql-editor";

export const Route = createFileRoute("/_sidebar/code/triggers/$id")({
  component: TriggerDetailPage,
});

function TriggerDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/code"><ArrowLeft className="mr-1 h-4 w-4" />Voltar</Link>
      </Button>
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary onReset={reset} fallbackRender={({ resetErrorBoundary }) => (
            <Card className="border-destructive/50">
              <CardHeader><CardTitle className="text-destructive flex items-center gap-2"><AlertCircle className="h-5 w-5" />Erro</CardTitle></CardHeader>
              <CardContent><Button onClick={resetErrorBoundary}>Tentar novamente</Button></CardContent>
            </Card>
          )}>
            <Suspense fallback={<Skeleton className="h-96 w-full" />}>
              <TriggerDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function TriggerDetail() {
  const { id } = Route.useParams();
  const { data: t } = useGetTriggerSuspense(id, selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { mutate: save, isPending: saving } = useUpdateTrigger({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getTrigger", id] });
        qc.invalidateQueries({ queryKey: ["listTriggers"] });
      },
    },
  });
  const { mutate: del } = useDeleteTrigger({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listTriggers"] });
        navigate({ to: "/code" });
      },
    },
  });

  const [eventType, setEventType] = useState<EventType | "">(t.event_type || "");
  const [timing, setTiming] = useState<TriggerTiming | "">(t.timing || "");
  const [body, setBody] = useState(t.body || "");
  const [behaviorDesc, setBehaviorDesc] = useState(t.behavior_desc || "");
  const [risk, setRisk] = useState<RiskLevel | "">(t.change_risk_level || "");

  useEffect(() => {
    setEventType(t.event_type || "");
    setTiming(t.timing || "");
    setBody(t.body || "");
    setBehaviorDesc(t.behavior_desc || "");
    setRisk(t.change_risk_level || "");
  }, [t.trigger_id]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Zap className="h-5 w-5 text-nuclea-primary" />
            <Badge variant="outline">TRIGGER</Badge>
          </div>
          <h1 className="text-3xl font-bold tracking-tight font-mono">{t.schema_name}.{t.technical_name}</h1>
          {t.associated_entity_label && (
            <p className="text-sm text-muted-foreground font-mono">→ {t.associated_entity_label}</p>
          )}
        </div>
        <Button variant="outline" onClick={() => { if (confirm("Excluir trigger?")) del({ triggerId: id }); }}>
          <Trash2 className="mr-2 h-4 w-4" />Excluir
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Configuração</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-4">
            <Field label="Evento">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={eventType} onChange={(e) => setEventType(e.target.value as any)}>
                <option value="">—</option>
                <option value="INSERT">INSERT</option>
                <option value="UPDATE">UPDATE</option>
                <option value="DELETE">DELETE</option>
              </select>
            </Field>
            <Field label="Timing">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={timing} onChange={(e) => setTiming(e.target.value as any)}>
                <option value="">—</option>
                <option value="BEFORE">BEFORE</option>
                <option value="AFTER">AFTER</option>
                <option value="INSTEAD_OF">INSTEAD OF</option>
              </select>
            </Field>
            <Field label="Risco">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={risk} onChange={(e) => setRisk(e.target.value as any)}>
                <option value="">—</option>
                <option value="CRITICAL">Crítico</option>
                <option value="MODERATE">Moderado</option>
                <option value="LOW">Baixo</option>
              </select>
            </Field>
          </div>
          <Field label="Comportamento">
            <textarea value={behaviorDesc} onChange={(e) => setBehaviorDesc(e.target.value)} rows={3} className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Corpo</CardTitle><CardDescription>SQL — referência</CardDescription></CardHeader>
        <CardContent>
          <SqlEditor value={body} onChange={setBody} height={420} language="sql" />
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button
          onClick={() => save({
            triggerId: id,
            data: {
              system_id: t.system_id,
              schema_name: t.schema_name,
              technical_name: t.technical_name,
              associated_entity_id: t.associated_entity_id || null,
              event_type: (eventType || null) as EventType | null,
              timing: (timing || null) as TriggerTiming | null,
              body: body || null,
              behavior_desc: behaviorDesc || null,
              change_risk_level: (risk || null) as RiskLevel | null,
            },
          })}
          disabled={saving}
        >
          <Save className="mr-2 h-4 w-4" />
          {saving ? "Salvando..." : "Salvar"}
        </Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}
