import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/entities")({
  component: () => (
    <PlaceholderPage
      title="Documentação de Componentes"
      moduleNumber="M3"
      phase="Fase 1"
      description="Documente entidades, atributos, views, procedures, triggers e relacionamentos com forms ricos e Markdown."
      features={[
        "Entidades: nome lógico, descrição (Markdown), domínio, owners, tags, criticidade",
        "Atributos: nome lógico, exemplo, regra de negócio, vínculo ao dicionário, flags",
        "Views: propósito, SQL com syntax highlight, tabelas base relacionadas",
        "Procedures/Triggers: descrição, parâmetros, sistemas dependentes, nível de risco",
        "Relacionamentos: 1:1, 1:N, N:M, herança — colunas participantes, regras",
        "Auto-save de rascunho a cada 30s; busca global < 1s",
      ]}
    />
  ),
});
