import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import { useCreateEntity, useListSystemsSuspense } from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle } from "lucide-react";

type Crit = "HIGH" | "MEDIUM" | "LOW";
type EntType = "TABLE" | "VIEW" | "MATERIALIZED_VIEW" | "EXTERNAL";

export const Route = createFileRoute("/_sidebar/entities/new")({
  component: NewEntityPage,
});

function NewEntityPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/entities" search={{}}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Entidades
        </Link>
      </Button>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Nova entidade</h1>
        <p className="text-muted-foreground">Cadastre uma tabela, view ou outro objeto.</p>
      </div>

      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="text-destructive flex items-center gap-2">
                    <AlertCircle className="h-5 w-5" /> Erro
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<FormSkeleton />}>
              <EntityForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function EntityForm() {
  const { data: systems } = useListSystemsSuspense(selector());
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { mutate: create, isPending, error } = useCreateEntity({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["listEntities"] });
        navigate({ to: "/entities/$id", params: { id: data.entity_id } });
      },
    },
  });

  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [schemaName, setSchemaName] = useState("");
  const [technicalName, setTechnicalName] = useState("");
  const [logicalName, setLogicalName] = useState("");
  const [entityType, setEntityType] = useState<EntType>("TABLE");
  const [domain, setDomain] = useState("");
  const [businessOwner, setBusinessOwner] = useState("");
  const [technicalOwner, setTechnicalOwner] = useState("");
  const [criticality, setCriticality] = useState<Crit | "">("");
  const [descriptionMd, setDescriptionMd] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        system_id: systemId,
        schema_name: schemaName,
        technical_name: technicalName,
        logical_name: logicalName || null,
        description_md: descriptionMd || null,
        domain: domain || null,
        business_owner: businessOwner || null,
        technical_owner: technicalOwner || null,
        criticality: (criticality || null) as Crit | null,
        tags: tagsRaw.split(",").map((t) => t.trim()).filter(Boolean),
        entity_type: entityType,
      },
    });
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Identificação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Sistema" required>
              {systems.length === 0 ? (
                <p className="text-sm text-muted-foreground">Cadastre um sistema primeiro.</p>
              ) : (
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={systemId} onChange={(e) => setSystemId(e.target.value)} required>
                  {systems.map((s) => (
                    <option key={s.system_id} value={s.system_id}>{s.system_name}</option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Tipo">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={entityType} onChange={(e) => setEntityType(e.target.value as EntType)}>
                <option value="TABLE">TABLE</option>
                <option value="VIEW">VIEW</option>
                <option value="MATERIALIZED_VIEW">MATERIALIZED_VIEW</option>
                <option value="EXTERNAL">EXTERNAL</option>
              </select>
            </Field>
            <Field label="Schema/Owner" required>
              <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)} placeholder="dbo" required />
            </Field>
            <Field label="Nome técnico" required>
              <Input value={technicalName} onChange={(e) => setTechnicalName(e.target.value)} placeholder="cliente" required />
            </Field>
            <Field label="Nome lógico (negócio)">
              <Input value={logicalName} onChange={(e) => setLogicalName(e.target.value)} placeholder="Cliente" />
            </Field>
            <Field label="Domínio">
              <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="Comercial" />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Responsáveis & governança</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Owner de negócio">
              <Input value={businessOwner} onChange={(e) => setBusinessOwner(e.target.value)} placeholder="usuario@nuclea.com.br" />
            </Field>
            <Field label="Owner técnico">
              <Input value={technicalOwner} onChange={(e) => setTechnicalOwner(e.target.value)} placeholder="time-dados" />
            </Field>
            <Field label="Criticidade">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={criticality} onChange={(e) => setCriticality(e.target.value as Crit | "")}>
                <option value="">—</option>
                <option value="HIGH">Alta</option>
                <option value="MEDIUM">Média</option>
                <option value="LOW">Baixa</option>
              </select>
            </Field>
            <Field label="Tags (separadas por vírgula)">
              <Input value={tagsRaw} onChange={(e) => setTagsRaw(e.target.value)} placeholder="master-data, referência" />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Descrição de negócio</CardTitle>
          <CardDescription>Markdown suportado</CardDescription>
        </CardHeader>
        <CardContent>
          <textarea
            value={descriptionMd}
            onChange={(e) => setDescriptionMd(e.target.value)}
            rows={6}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
            placeholder="## Visão geral&#10;&#10;Descreva o propósito desta entidade no negócio..."
          />
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="pt-4 text-sm text-destructive">
            <pre className="text-xs whitespace-pre-wrap">{String(error)}</pre>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" asChild>
          <Link to="/entities" search={{}}>Cancelar</Link>
        </Button>
        <Button type="submit" disabled={isPending || !systemId || !schemaName || !technicalName}>
          {isPending ? "Salvando..." : "Salvar entidade"}
        </Button>
      </div>
    </form>
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

function FormSkeleton() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-48" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
