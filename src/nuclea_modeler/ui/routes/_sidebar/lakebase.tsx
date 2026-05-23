import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/lakebase")({
  component: () => (
    <PlaceholderPage
      title="Lakebase Sandbox"
      moduleNumber="M-LB"
      phase="Fase 2"
      description="Banco Postgres gerenciado (Lakebase) usado como sandbox de validação dos modelos catalogados — round-trip DDL ↔ catálogo."
      features={[
        "Provisionar instância Lakebase para testes",
        "Aplicar DDL gerado pelo M10 num schema de teste",
        "Rodar engenharia reversa (M2) de volta sobre o Lakebase",
        "Diff entre modelo catalogado e estrutura real no Lakebase",
        "Marcar entidades como 'validadas em Lakebase'",
        "App roda 100% em Delta; Lakebase é APENAS sandbox de teste",
      ]}
    />
  ),
});
