import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/connections")({
  component: () => (
    <PlaceholderPage
      title="Conexões de Ambiente"
      moduleNumber="M1"
      phase="Fase 1"
      description="Cadastro, teste e gerenciamento de conexões ODBC, REST e import de DDL para os ambientes HINT, HEXT e PROD."
      features={[
        "Cadastro de conexões ODBC (DSN, driver, host, porta, banco, usuário, senha)",
        "Cadastro de conexões REST (URL base, Basic/Bearer/OAuth, headers customizados)",
        "Import de scripts .sql / .ddl com parser multi-dialect",
        "Botão Testar Conexão com latência e versão detectada",
        "Credenciais armazenadas em Databricks Secrets (nunca em texto puro)",
        "Histórico de uso por conexão e RBAC (apenas Data Engineer/Admin criam)",
      ]}
    />
  ),
});
