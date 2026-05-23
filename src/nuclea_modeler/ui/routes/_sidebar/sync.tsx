import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/sync")({
  component: () => (
    <PlaceholderPage
      title="Sincronização Unity Catalog"
      moduleNumber="M9"
      phase="Fase 1"
      description="Espelhamento automático do modelo publicado no Unity Catalog — descrições viram COMMENTs e flags viram TAGs."
      features={[
        "Disparado pela publicação de uma versão Ativa",
        "ALTER TABLE / COLUMN COMMENT + ALTER TABLE SET TAGS",
        "Tipagens não são sobrescritas (preserva tipos nativos do UC)",
        "Job em background com log em sync_log; status na app",
        "Detecção de conflitos (alteração externa no UC) com override/ignorar",
        "Sincronização incremental e métrica de SLA < 2 min para 200 objetos",
      ]}
    />
  ),
});
