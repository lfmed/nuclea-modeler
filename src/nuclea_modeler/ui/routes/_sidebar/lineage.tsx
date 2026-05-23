import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/lineage")({
  component: () => (
    <PlaceholderPage
      title="Linhagem"
      moduleNumber="M7"
      phase="Fase 3"
      description="Mapeamento de origem (upstream) e consumo (downstream) das entidades, complementado pela linhagem nativa do Unity Catalog."
      features={[
        "Upstream: sistema de origem, tipo de integração (CDC/batch/API), periodicidade",
        "Downstream: sistemas consumidores, tipo de consumo, equipe, SLA",
        "Integração com Unity Catalog Lineage API",
        "Grafo interativo com profundidade configurável",
        "Filtros por ambiente (HINT/HEXT/PROD)",
        "Exportação como imagem e JSON estruturado",
      ]}
    />
  ),
});
