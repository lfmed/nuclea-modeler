import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useCreateProcedure,
  useListSystemsSuspense,
  type RiskLevel,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle, Code2, Save } from "lucide-react";
import { SqlEditor } from "@/components/code/sql-editor";

export const Route = createFileRoute("/_sidebar/code/procedures/new")({
  component: NewProcedurePage,
});

function NewProcedurePage() {
  return (
    <div className="space-y-6 max-w-4xl">
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
                    Erro
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-96 w-full" />}>
              <ProcedureForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ProcedureForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { mutate: create, isPending } = useCreateProcedure({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["listProcedures"] });
        navigate({ to: "/code/procedures/$id", params: { id: data.procedure_id } });
      },
    },
  });

  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [schemaName, setSchemaName] = useState("dbo");
  const [technicalName, setTechnicalName] = useState("");
  const [logicalName, setLogicalName] = useState("");
  const [behaviorDesc, setBehaviorDesc] = useState("");
  const [risk, setRisk] = useState<RiskLevel | "">("");
  const [sourceCode, setSourceCode] = useState("");

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Code2 className="h-5 w-5 text-nuclea-primary" />
        </div>
        <h1 className="text-3xl font-bold tracking-tight">Nova Procedure</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Identificação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Sistema" required>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={systemId}
                onChange={(e) => setSystemId(e.target.value)}
                required
              >
                {systems.map((s) => (
                  <option key={s.system_id} value={s.system_id}>{s.system_name}</option>
                ))}
              </select>
            </Field>
            <Field label="Schema" required>
              <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)} required />
            </Field>
            <Field label="Nome técnico" required>
              <Input value={technicalName} onChange={(e) => setTechnicalName(e.target.value)} placeholder="sp_processa_pagamento" required />
            </Field>
            <Field label="Nome lógico (negócio)">
              <Input value={logicalName} onChange={(e) => setLogicalName(e.target.value)} />
            </Field>
          </div>
          <Field label="Comportamento">
            <textarea
              value={behaviorDesc}
              onChange={(e) => setBehaviorDesc(e.target.value)}
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Descreve o que esta procedure faz em linguagem de negócio"
            />
          </Field>
          <Field label="Risco de alteração">
            <select
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={risk}
              onChange={(e) => setRisk(e.target.value as any)}
            >
              <option value="">—</option>
              <option value="CRITICAL">Crítico</option>
              <option value="MODERATE">Moderado</option>
              <option value="LOW">Baixo</option>
            </select>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Código-fonte</CardTitle>
          <CardDescription>Opcional. Adicione parâmetros depois de criar.</CardDescription>
        </CardHeader>
        <CardContent>
          <SqlEditor value={sourceCode} onChange={setSourceCode} height={360} language="sql" />
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" asChild>
          <Link to="/code">Cancelar</Link>
        </Button>
        <Button
          onClick={() =>
            create({
              data: {
                system_id: systemId,
                schema_name: schemaName,
                technical_name: technicalName,
                logical_name: logicalName || null,
                behavior_desc: behaviorDesc || null,
                source_code: sourceCode || null,
                change_risk_level: (risk || null) as RiskLevel | null,
                parameters: [],
                dependent_systems: [],
              },
            })
          }
          disabled={isPending || !systemId || !schemaName || !technicalName}
        >
          <Save className="mr-2 h-4 w-4" />
          {isPending ? "Salvando..." : "Criar procedure"}
        </Button>
      </div>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium flex items-center gap-1">
        {label}
        {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  );
}
