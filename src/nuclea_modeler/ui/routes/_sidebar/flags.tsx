import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/flags")({
  component: () => (
    <PlaceholderPage
      title="Flags & LGPD"
      moduleNumber="M5"
      phase="Fase 2"
      description="Marcação categórica de tabelas e colunas para controle de uso, privacidade e conformidade LGPD."
      features={[
        "Flags LGPD: dados-pessoais, sensíveis, anonimizado, pseudonimizado, bases legais",
        "Flags de uso: master, transacional, histórico, calculado, depreciado",
        "Flags de qualidade: crítico, sem validação, validado, inconsistência conhecida",
        "Justificativa obrigatória para flags LGPD",
        "Propagação visual coluna → tabela (LGPD)",
        "Log imutável de aplicação/remoção; relatório por sistema/domínio",
      ]}
    />
  ),
});
