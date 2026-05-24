import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";

import {
  useCreateTerm,
  type ConceptualType,
} from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, AlertCircle } from "lucide-react";

export const Route = createFileRoute("/_sidebar/glossary/new")({
  component: NewTermPage,
});

const CONCEPTUAL_TYPES: { value: ConceptualType; label: string }[] = [
  { value: "IDENTIFIER", label: "Identificador" },
  { value: "MONETARY", label: "Valor monetário" },
  { value: "DATE", label: "Data" },
  { value: "BOOLEAN", label: "Booleano" },
  { value: "TEXT", label: "Texto livre" },
  { value: "NUMERIC", label: "Numérico" },
  { value: "CATEGORICAL", label: "Categórico" },
  { value: "OTHER", label: "Outro" },
];

function NewTermPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/glossary">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Dicionário
        </Link>
      </Button>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Novo termo</h1>
        <p className="text-muted-foreground">
          Cadastre um termo do glossário corporativo. O status inicial é Rascunho.
        </p>
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
              <TermForm />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function TermForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { mutate: create, isPending, error } = useCreateTerm({
    mutation: {
      onSuccess: (data) => {
        qc.invalidateQueries({ queryKey: ["listTerms"] });
        navigate({ to: "/glossary/$id", params: { id: data.term_id } });
      },
    },
  });

  const [canonicalName, setCanonicalName] = useState("");
  const [definition, setDefinition] = useState("");
  const [synonymsRaw, setSynonymsRaw] = useState("");
  const [domain, setDomain] = useState("");
  const [conceptualType, setConceptualType] = useState<ConceptualType | "">("");
  const [examplesRaw, setExamplesRaw] = useState("");
  const [ownerPerson, setOwnerPerson] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create({
      data: {
        canonical_name: canonicalName,
        definition,
        synonyms: synonymsRaw.split(",").map((s) => s.trim()).filter(Boolean),
        domain: domain || null,
        conceptual_type: (conceptualType || null) as ConceptualType | null,
        valid_examples: examplesRaw.split(",").map((s) => s.trim()).filter(Boolean),
        owner_person: ownerPerson || null,
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
            <Field label="Nome canônico" required>
              <Input
                value={canonicalName}
                onChange={(e) => setCanonicalName(e.target.value)}
                placeholder="CPF do Cliente"
                required
              />
            </Field>
            <Field label="Domínio">
              <Input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="Comercial"
              />
            </Field>
            <Field label="Tipo conceitual">
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={conceptualType}
                onChange={(e) => setConceptualType(e.target.value as ConceptualType | "")}
              >
                <option value="">—</option>
                {CONCEPTUAL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Owner do conceito">
              <Input
                value={ownerPerson}
                onChange={(e) => setOwnerPerson(e.target.value)}
                placeholder="usuario@nuclea.com.br"
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Definição de negócio</CardTitle>
          <CardDescription>Markdown suportado</CardDescription>
        </CardHeader>
        <CardContent>
          <textarea
            value={definition}
            onChange={(e) => setDefinition(e.target.value)}
            rows={6}
            required
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
            placeholder="Documento de identificação fiscal do cliente pessoa física..."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sinônimos & exemplos</CardTitle>
          <CardDescription>Separados por vírgula</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Sinônimos">
            <Input
              value={synonymsRaw}
              onChange={(e) => setSynonymsRaw(e.target.value)}
              placeholder="cliente_cpf, documento_cliente, doc_cpf"
            />
          </Field>
          <Field label="Exemplos de valores válidos">
            <Input
              value={examplesRaw}
              onChange={(e) => setExamplesRaw(e.target.value)}
              placeholder="123.456.789-00, 11122233344"
            />
          </Field>
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
          <Link to="/glossary">Cancelar</Link>
        </Button>
        <Button
          type="submit"
          disabled={isPending || !canonicalName || !definition}
        >
          {isPending ? "Salvando..." : "Salvar termo"}
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
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
