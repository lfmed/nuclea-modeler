import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/apx/placeholder-page";

export const Route = createFileRoute("/_sidebar/extractions")({
  component: () => (
    <PlaceholderPage
      title="Engenharia Reversa"
      moduleNumber="M2"
      phase="Fase 1"
      description="Extração automatizada de metadados a partir de conexões ativas ou scripts DDL importados."
      features={[
        "Extração ODBC: tabelas, colunas, PKs, FKs, índices, views, procedures, triggers, sequences",
        "Parser DDL multi-dialect: ANSI, T-SQL, PL/SQL, PostgreSQL, MySQL/MariaDB, SparkSQL/Hive",
        "Processo assíncrono com barra de progresso e estimativa de tempo",
        "Extração parcial — seleção de schemas e objetos específicos",
        "Relatório de extração: totais por tipo, erros de acesso, duração",
        "Reconciliação: diff visual entre extração e catálogo existente",
      ]}
    />
  ),
});
