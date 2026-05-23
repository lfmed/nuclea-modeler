import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/glossary")({
  component: () => (
    <PlaceholderPage
      title="Dicionário Corporativo"
      moduleNumber="M6"
      phase="Fase 2"
      description="Glossário centralizado de conceitos de dados, com vínculos a atributos em múltiplos sistemas."
      features={[
        "Termos canônicos: definição, sinônimos, domínio, tipo conceitual, exemplos",
        "Status: rascunho → em revisão → aprovado → depreciado",
        "Vínculo N:N termo ↔ atributos em N sistemas",
        "Validação de compatibilidade de tipo nativo vs. conceitual",
        "Herança de descrição com opção de override no atributo",
        "Notificação no workspace Databricks ao responsável em revisões",
      ]}
    />
  ),
});
