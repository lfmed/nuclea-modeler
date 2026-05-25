import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useEffect, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetSequenceSuspense,
  useUpdateSequence,
  useDeleteSequence,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, AlertCircle, Hash, Save, Trash2 } from "lucide-react";

export const Route = createFileRoute("/_sidebar/code/sequences/$id")({
  component: SequenceDetailPage,
});

function SequenceDetailPage() {
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
              <SequenceDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function SequenceDetail() {
  const { id } = Route.useParams();
  const { data: s } = useGetSequenceSuspense(id, selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { mutate: save, isPending: saving } = useUpdateSequence({
    mutation: { onSuccess: () => { qc.invalidateQueries({ queryKey: ["getSequence", id] }); qc.invalidateQueries({ queryKey: ["listSequences"] }); } },
  });
  const { mutate: del } = useDeleteSequence({
    mutation: { onSuccess: () => { qc.invalidateQueries({ queryKey: ["listSequences"] }); navigate({ to: "/code" }); } },
  });

  const [logicalName, setLogicalName] = useState(s.logical_name || "");
  const [descMd, setDescMd] = useState(s.description_md || "");
  const [startValue, setStartValue] = useState(s.start_value?.toString() || "");
  const [incrementBy, setIncrementBy] = useState(s.increment_by?.toString() || "");
  const [minValue, setMinValue] = useState(s.min_value?.toString() || "");
  const [maxValue, setMaxValue] = useState(s.max_value?.toString() || "");
  const [cacheSize, setCacheSize] = useState(s.cache_size?.toString() || "");
  const [isCycle, setIsCycle] = useState(!!s.is_cycle);
  const [currentValue, setCurrentValue] = useState(s.current_value?.toString() || "");

  useEffect(() => {
    setLogicalName(s.logical_name || "");
    setDescMd(s.description_md || "");
    setStartValue(s.start_value?.toString() || "");
    setIncrementBy(s.increment_by?.toString() || "");
    setMinValue(s.min_value?.toString() || "");
    setMaxValue(s.max_value?.toString() || "");
    setCacheSize(s.cache_size?.toString() || "");
    setIsCycle(!!s.is_cycle);
    setCurrentValue(s.current_value?.toString() || "");
  }, [s.sequence_id]);

  const submit = () => save({
    sequenceId: id,
    data: {
      system_id: s.system_id,
      schema_name: s.schema_name,
      technical_name: s.technical_name,
      logical_name: logicalName || null,
      description_md: descMd || null,
      start_value: startValue ? parseInt(startValue) : null,
      increment_by: incrementBy ? parseInt(incrementBy) : null,
      min_value: minValue ? parseInt(minValue) : null,
      max_value: maxValue ? parseInt(maxValue) : null,
      cache_size: cacheSize ? parseInt(cacheSize) : null,
      is_cycle: isCycle,
      current_value: currentValue ? parseInt(currentValue) : null,
      used_by_entity_ids: s.used_by_entity_ids,
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Hash className="h-5 w-5 text-nuclea-primary" />
            <Badge variant="outline">SEQUENCE</Badge>
          </div>
          <h1 className="text-3xl font-bold tracking-tight font-mono">{s.schema_name}.{s.technical_name}</h1>
          <p className="text-sm text-muted-foreground">{s.system_name || s.system_id}</p>
        </div>
        <Button variant="outline" onClick={() => { if (confirm("Excluir sequence?")) del({ sequenceId: id }); }}>
          <Trash2 className="mr-2 h-4 w-4" />Excluir
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Documentação</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Field label="Nome lógico">
            <Input value={logicalName} onChange={(e) => setLogicalName(e.target.value)} />
          </Field>
          <Field label="Descrição">
            <textarea value={descMd} onChange={(e) => setDescMd(e.target.value)} rows={3} className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Parâmetros</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Field label="Valor inicial"><Input type="number" value={startValue} onChange={(e) => setStartValue(e.target.value)} /></Field>
            <Field label="Incremento"><Input type="number" value={incrementBy} onChange={(e) => setIncrementBy(e.target.value)} /></Field>
            <Field label="Cache"><Input type="number" value={cacheSize} onChange={(e) => setCacheSize(e.target.value)} /></Field>
            <Field label="Mínimo"><Input type="number" value={minValue} onChange={(e) => setMinValue(e.target.value)} /></Field>
            <Field label="Máximo"><Input type="number" value={maxValue} onChange={(e) => setMaxValue(e.target.value)} /></Field>
            <Field label="Valor atual"><Input type="number" value={currentValue} onChange={(e) => setCurrentValue(e.target.value)} /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm mt-4">
            <input type="checkbox" checked={isCycle} onChange={(e) => setIsCycle(e.target.checked)} />
            Cycle (reinicia ao chegar no máximo)
          </label>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={submit} disabled={saving}>
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
