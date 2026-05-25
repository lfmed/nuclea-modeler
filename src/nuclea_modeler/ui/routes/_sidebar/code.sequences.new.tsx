import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useCreateSequence, useListSystemsSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle, Hash, Save } from "lucide-react";

export const Route = createFileRoute("/_sidebar/code/sequences/new")({
  component: NewSequencePage,
});

function NewSequencePage() {
  return (
    <div className="space-y-6 max-w-3xl">
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
              <SequenceForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function SequenceForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { mutate: create, isPending } = useCreateSequence({
    mutation: {
      onSuccess: (s) => {
        qc.invalidateQueries({ queryKey: ["listSequences"] });
        navigate({ to: "/code/sequences/$id", params: { id: s.sequence_id } });
      },
    },
  });

  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [schemaName, setSchemaName] = useState("public");
  const [technicalName, setTechnicalName] = useState("");
  const [logicalName, setLogicalName] = useState("");
  const [descMd, setDescMd] = useState("");
  const [startValue, setStartValue] = useState("1");
  const [incrementBy, setIncrementBy] = useState("1");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [cacheSize, setCacheSize] = useState("");
  const [isCycle, setIsCycle] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1"><Hash className="h-5 w-5 text-nuclea-primary" /></div>
        <h1 className="text-3xl font-bold tracking-tight">Nova Sequence</h1>
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
              <Input value={technicalName} onChange={(e) => setTechnicalName(e.target.value)} placeholder="seq_cliente_id" required />
            </Field>
            <Field label="Nome lógico">
              <Input value={logicalName} onChange={(e) => setLogicalName(e.target.value)} />
            </Field>
          </div>
          <Field label="Descrição">
            <textarea value={descMd} onChange={(e) => setDescMd(e.target.value)} rows={2} className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Parâmetros</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Field label="Valor inicial">
              <Input type="number" value={startValue} onChange={(e) => setStartValue(e.target.value)} />
            </Field>
            <Field label="Incremento">
              <Input type="number" value={incrementBy} onChange={(e) => setIncrementBy(e.target.value)} />
            </Field>
            <Field label="Cache">
              <Input type="number" value={cacheSize} onChange={(e) => setCacheSize(e.target.value)} placeholder="20" />
            </Field>
            <Field label="Mínimo">
              <Input type="number" value={minValue} onChange={(e) => setMinValue(e.target.value)} />
            </Field>
            <Field label="Máximo">
              <Input type="number" value={maxValue} onChange={(e) => setMaxValue(e.target.value)} />
            </Field>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Cycle</label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isCycle} onChange={(e) => setIsCycle(e.target.checked)} />
                Reinicia ao chegar no máximo
              </label>
            </div>
          </div>
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
              logical_name: logicalName || null,
              description_md: descMd || null,
              start_value: startValue ? parseInt(startValue) : null,
              increment_by: incrementBy ? parseInt(incrementBy) : null,
              min_value: minValue ? parseInt(minValue) : null,
              max_value: maxValue ? parseInt(maxValue) : null,
              cache_size: cacheSize ? parseInt(cacheSize) : null,
              is_cycle: isCycle,
            },
          })}
          disabled={isPending || !systemId || !schemaName || !technicalName}
        >
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Salvando..." : "Criar sequence"}
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
