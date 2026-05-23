import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/diagram")({
  component: () => (
    <PlaceholderPage
      title="Diagrama Entidade-Relacionamento"
      moduleNumber="M4"
      phase="Fase 3"
      description="Canvas interativo para visualização do modelo de dados — drag, zoom, layout automático, destaque de flags LGPD."
      features={[
        "Geração automática a partir do modelo catalogado",
        "Drag-and-drop com layout persistido por versão",
        "Zoom in/out e pan; modo compacto e expandido",
        "Filtros por domínio, tag, texto livre",
        "Destaque visual para entidades com flags LGPD ativas",
        "Agrupamento por domínio (swimlanes); export PNG/SVG/JSON",
      ]}
    />
  ),
});
