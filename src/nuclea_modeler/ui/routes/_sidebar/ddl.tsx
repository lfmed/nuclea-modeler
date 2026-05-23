import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/ddl")({
  component: () => (
    <PlaceholderPage
      title="Exportar DDL"
      moduleNumber="M10"
      phase="Fase 2"
      description="Geração de scripts DDL a partir do catálogo, em múltiplos dialetos, para documentação e migração."
      features={[
        "Dialetos: ANSI, T-SQL, PL/SQL, PostgreSQL, MySQL, SparkSQL/Delta",
        "Inclui CREATE TABLE, PKs, FKs, índices, COMMENTs",
        "Opções: incluir/excluir comentários, qualificar schema, DROP IF EXISTS",
        "Arquivo único ou por objeto",
        "Preview com syntax highlight e copy-to-clipboard",
        "Critério: DDL gerado em SparkSQL/T-SQL é sintaticamente válido",
      ]}
    />
  ),
});
