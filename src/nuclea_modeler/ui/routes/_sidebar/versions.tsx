import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/versions")({
  component: () => (
    <PlaceholderPage
      title="Versões"
      moduleNumber="M8"
      phase="Fase 2"
      description="Histórico de versões dos modelos com snapshots imutáveis, diff lado-a-lado e restauração."
      features={[
        "Rascunho de trabalho (WIP) editável + publicação como snapshot imutável",
        "Numeração automática (v1.0, v1.1, v2.0...) e changelog por versão",
        "Apenas uma versão Ativa por sistema; demais ficam Publicadas/Depreciadas",
        "Diff lado-a-lado: adições, remoções, alterações de estrutura e doc",
        "Indicadores visuais (verde/vermelho/amarelo) e export PDF/CSV",
        "Restauração não-destrutiva como novo rascunho",
      ]}
    />
  ),
});
