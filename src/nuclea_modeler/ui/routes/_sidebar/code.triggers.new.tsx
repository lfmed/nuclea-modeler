import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useCreateTrigger,
  useListSystemsSuspense,
  useListEntitiesSuspense,
  type EventType,
  type TriggerTiming,
  type RiskLevel,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle, Zap, Save } from "lucide-react";
import { SqlEditor } from "@/components/code/sql-editor";

export const Route = createFileRoute("/_sidebar/code/triggers/new")({
  component: NewTriggerPage,
});

function NewTriggerPage() {
  return (
    <div className="space-y-6 max-w-4xl">
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
              <TriggerForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function TriggerForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const { data: entities } = useListEntitiesSuspense({ systemId }, selector());

  const { mutate: create, isPending } = useCreateTrigger({
    mutation: {
      onSuccess: (t) => {
        qc.invalidateQueries({ queryKey: ["listTriggers"] });
        navigate({ to: "/code/triggers/$id", params: { id: t.trigger_id } });
      },
    },
  });

  const [schemaName, setSchemaName] = useState("dbo");
  const [technicalName, setTechnicalName] = useState("");
  const [entityId, setEntityId] = useState("");
  const [eventType, setEventType] = useState<EventType | "">("INSERT");
  const [timing, setTiming] = useState<TriggerTiming | "">("AFTER");
  const [body, setBody] = useState("");
  const [behaviorDesc, setBehaviorDesc] = useState("");
  const [risk, setRisk] = useState<RiskLevel | "">("");

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1"><Zap className="h-5 w-5 text-nuclea-primary" /></div>
        <h1 className="text-3xl font-bold tracking-tight">Novo Trigger</h1>
      </div>

      <Card>
        <CardHeader><CardTitle>Identificação</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Sistema" required>
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={systemId} onChange={(e) => setSystemId(e.target.value)} required>
                {systems.map((s) => <option key={s.system_id} value={s.system_id}>{s.system_name}</option>)}
              </select>
            </Field>
            <Field label="Schema" required>
              <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)} required />
            </Field>
            <Field label="Nome técnico" required>
              <Input value={technicalName} onChange={(e) => setTechnicalName(e.target.value)} placeholder="trg_auditoria_cliente" required />
            </Field>
            <Field label="Entidade associada">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={entityId} onChange={(e) => setEntityId(e.target.value)}>
                <option value="">—</option>
                {entities.map((e) => <option key={e.entity_id} value={e.entity_id}>{e.schema_name}.{e.technical_name}</option>)}
              </select>
            </Field>
            <Field label="Evento">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={eventType} onChange={(e) => setEventType(e.target.value as any)}>
                <option value="INSERT">INSERT</option>
                <option value="UPDATE">UPDATE</option>
                <option value="DELETE">DELETE</option>
              </select>
            </Field>
            <Field label="Timing">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={timing} onChange={(e) => setTiming(e.target.value as any)}>
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
        <CardHeader><CardTitle>Corpo do trigger</CardTitle><CardDescription>SQL — exibição apenas</CardDescription></CardHeader>
        <CardContent>
          <SqlEditor value={body} onChange={setBody} height={360} language="sql" />
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" asChild><Link to="/code">Cancelar</Link></Button>
        <Button
          onClick={() => create({
            data: {
              system_id: systemId,
              schema_name: schemaName,
              technical_name: technicalName,
              associated_entity_id: entityId || null,
              event_type: (eventType || null) as EventType | null,
              timing: (timing || null) as TriggerTiming | null,
              body: body || null,
              behavior_desc: behaviorDesc || null,
              change_risk_level: (risk || null) as RiskLevel | null,
            },
          })}
          disabled={isPending || !systemId || !schemaName || !technicalName}
        >
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Salvando..." : "Criar trigger"}
        </Button>
      </div>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium flex items-center gap-1">{label}{required && <span className="text-destructive">*</span>}</label>
      {children}
    </div>
  );
}
