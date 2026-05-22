# Nuclea Modeler

> Catálogo e modelagem de dados corporativa — Databricks App nativo para a **Núclea**.

Aplicação full-stack (FastAPI + React, via [APX](https://github.com/databricks-solutions/apx)) que centraliza o ciclo de vida dos modelos de dados da Núclea — da engenharia reversa dos ambientes HINT/HEXT/PROD até o espelhamento automático no **Unity Catalog**.

## Visão geral

| | |
|---|---|
| **Cliente** | Núclea S.A. (ex-CIP) |
| **Audiência** | Tribo de Dados, CdE de Dados, Data Stewards, Architects, Engineers |
| **Plataforma** | Databricks Apps + Unity Catalog + Delta Lake |
| **Stack** | Python 3.12 · FastAPI · React 18 · TanStack Router · shadcn/ui · Tailwind |
| **Status** | 🟡 Fase 0 — Bootstrap |

## Módulos funcionais

1. **Conexões de Ambiente** — ODBC, REST, import de DDL (HINT/HEXT/PROD)
2. **Engenharia Reversa** — extração automatizada de metadados
3. **Documentação** — entidades, atributos, views, procedures, triggers, relacionamentos
4. **DER Interativo** *(não-mandatório)* — diagrama entidade-relacionamento navegável
5. **Flagueamento** — LGPD, uso, qualidade, custom
6. **Dicionário Corporativo** — glossário com vínculos a atributos
7. **Linhagem** — upstream/downstream com integração ao UC Lineage
8. **Versionamento** — snapshots imutáveis e diff entre versões
9. **Sincronização Unity Catalog** — espelhamento de descrições + tags
10. **Exportação DDL** — multi-dialect (ANSI/T-SQL/PL-SQL/Postgres/MySQL/SparkSQL)

## Estrutura do repositório

```
.
├── docs/
│   ├── spec/                 # Especificação funcional autoritativa
│   ├── prompts/              # Prompt Registry — histórico de prompts por fase
│   └── adr/                  # Architecture Decision Records
├── src/
│   └── nuclea_modeler/
│       ├── backend/          # FastAPI app, models, routers
│       └── ui/               # React app, routes, components
├── databricks/
│   ├── app.yaml              # Manifesto do Databricks App
│   ├── bundles/              # Databricks Asset Bundles
│   └── sql/                  # DDL para schemas Delta no UC
└── README.md
```

## Início rápido (dev)

```bash
# Pré-requisitos: uv, bun, node 22+, apx 0.3+
apx dev
```

A app sobe localmente, gera tipos OpenAPI automaticamente, e a UI fica em `http://localhost:5173`.

## Roadmap

Ver [`docs/prompts/01-plano-militar.md`](docs/prompts/01-plano-militar.md) para o plano de execução por fase.

## Licença

Privado · Núclea S.A. · Todos os direitos reservados.
