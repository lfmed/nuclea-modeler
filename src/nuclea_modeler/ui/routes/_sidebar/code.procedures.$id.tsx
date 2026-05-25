import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useEffect, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useGetProcedureSuspense,
  useUpdateProcedure,
  useDeleteProcedure,
  type ProcedureParam,
  type RiskLevel,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft, AlertCircle, Code2, Save, Trash2, Plus, X,
} from "lucide-react";
import { SqlEditor } from "@/components/code/sql-editor";

export const Route = createFileRoute("/_sidebar/code/procedures/$id")({
  component: ProcedureDetailPage,
});

function ProcedureDetailPage() {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/code">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Voltar
        </Link>
      </Button>
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar procedure
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-96 w-full" />}>
              <ProcedureDetail />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ProcedureDetail() {
  const { id } = Route.useParams();
  const { data: proc } = useGetProcedureSuspense(id, selector());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { mutate: save, isPending: saving } = useUpdateProcedure({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["getProcedure", id] });
        qc.invalidateQueries({ queryKey: ["listProcedures"] });
      },
    },
  });
  const { mutate: del, isPending: deleting } = useDeleteProcedure({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["listProcedures"] });
        navigate({ to: "/code" });
      },
    },
  });

  const [logicalName, setLogicalName] = useState(proc.logical_name || "");
  const [behaviorDesc, setBehaviorDesc] = useState(proc.behavior_desc || "");
  const [sourceCode, setSourceCode] = useState(proc.source_code || "");
  const [risk, setRisk] = useState<RiskLevel | "">(proc.change_risk_level || "");
  const [params, setParams] = useState<ProcedureParam[]>(proc.parameters);
  const [dependentSystems, setDependentSystems] = useState(proc.dependent_systems.join(", "));

  useEffect(() => {
    setLogicalName(proc.logical_name || "");
    setBehaviorDesc(proc.behavior_desc || "");
    setSourceCode(proc.source_code || "");
    setRisk(proc.change_risk_level || "");
    setParams(proc.parameters);
    setDependentSystems(proc.dependent_systems.join(", "));
  }, [proc.procedure_id]);

  const submit = () => {
    save({
      procedureId: id,
      data: {
        system_id: proc.system_id,
        schema_name: proc.schema_name,
        technical_name: proc.technical_name,
        logical_name: logicalName || null,
        behavior_desc: behaviorDesc || null,
        parameters: params,
        source_code: sourceCode || null,
        dependent_systems: dependentSystems.split(",").map((x) => x.trim()).filter(Boolean),
        change_risk_level: (risk || null) as RiskLevel | null,
      },
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Code2 className="h-5 w-5 text-nuclea-primary" />
            <Badge variant="outline">PROCEDURE</Badge>
          </div>
          <h1 className="text-3xl font-bold tracking-tight font-mono">
            {proc.schema_name}.{proc.technical_name}
          </h1>
          <p className="text-sm text-muted-foreground">{proc.system_name || proc.system_id}</p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            if (confirm(`Excluir procedure "${proc.technical_name}"?`))
              del({ procedureId: id });
          }}
          disabled={deleting}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Excluir
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Metadados</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Nome lógico (negócio)">
              <Input value={logicalName} onChange={(e) => setLogicalName(e.target.value)} />
            </Field>
            <Field label="Nível de risco de alteração">
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={risk}
                onChange={(e) => setRisk(e.target.value as RiskLevel | "")}
              >
                <option value="">—</option>
                <option value="CRITICAL">Crítico</option>
                <option value="MODERATE">Moderado</option>
                <option value="LOW">Baixo</option>
              </select>
            </Field>
          </div>
          <Field label="Comportamento (em linguagem de negócio)">
            <textarea
              value={behaviorDesc}
              onChange={(e) => setBehaviorDesc(e.target.value)}
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Sistemas dependentes (CSV)">
            <Input value={dependentSystems} onChange={(e) => setDependentSystems(e.target.value)} placeholder="DW, Reporting, ML" />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Parâmetros ({params.length})</CardTitle>
              <CardDescription>Entradas / saídas da procedure</CardDescription>
            </div>
            <Button size="sm" onClick={() => setParams([...params, { name: "", type: "", direction: "IN" }])}>
              <Plus className="mr-2 h-4 w-4" />
              Adicionar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {params.length === 0 && (
            <p className="text-sm text-muted-foreground italic">Sem parâmetros.</p>
          )}
          {params.map((p, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <Input
                className="col-span-3"
                placeholder="nome"
                value={p.name}
                onChange={(e) =>
                  setParams(params.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                }
              />
              <Input
                className="col-span-3"
                placeholder="tipo (INT, VARCHAR, ...)"
                value={p.type}
                onChange={(e) =>
                  setParams(params.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))
                }
              />
              <select
                className="col-span-2 rounded-md border bg-background px-2 py-1.5 text-sm"
                value={p.direction || "IN"}
                onChange={(e) =>
                  setParams(params.map((x, j) => (j === i ? { ...x, direction: e.target.value as any } : x)))
                }
              >
                <option value="IN">IN</option>
                <option value="OUT">OUT</option>
                <option value="INOUT">INOUT</option>
              </select>
              <Input
                className="col-span-3"
                placeholder="descrição"
                value={p.description || ""}
                onChange={(e) =>
                  setParams(params.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))
                }
              />
              <button
                className="col-span-1 text-muted-foreground hover:text-destructive"
                onClick={() => setParams(params.filter((_, j) => j !== i))}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Código-fonte</CardTitle>
          <CardDescription>Referência (não executa)</CardDescription>
        </CardHeader>
        <CardContent>
          <SqlEditor value={sourceCode} onChange={setSourceCode} height={420} language="sql" />
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
