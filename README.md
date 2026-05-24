# Núclea Modeler

> Catálogo e modelagem de dados corporativa — Databricks App nativo para a **Núclea**.

Aplicação full-stack (FastAPI + React, via [APX](https://github.com/databricks-solutions/apx)) que centraliza o ciclo de vida dos modelos de dados — da engenharia reversa dos ambientes **HINT/HEXT/PROD** até o espelhamento automático no **Unity Catalog**.

| | |
|---|---|
| **Cliente** | Núclea S.A. (ex-CIP) |
| **Audiência** | Tribo de Dados, CdE de Dados, Stewards, Architects, Engineers |
| **Plataforma** | Databricks Apps + Unity Catalog + Delta Lake |
| **Stack** | Python 3.11+ · FastAPI · React 19 · TanStack Router · shadcn/ui · Tailwind 4 |
| **Persistência** | 100% Delta Lake no Unity Catalog (sem Postgres operacional) |
| **Status** | 🟢 9 dos 10 módulos prontos · só M4 DER (não-mandatório) falta |
| **URL live** | https://nuclea-modeler-7474646973581105.aws.databricksapps.com |

## Módulos funcionais

| # | Módulo | Fase | Status |
|---|--------|------|--------|
| M1 | Conexões de Ambiente (ODBC/REST/DDL) | 1 | ✅ |
| M2 | Engenharia Reversa (Lakebase + DDL) | 1 | ✅ |
| M3 | Documentação de Componentes | 1 | ✅ |
| M4 | Diagrama Entidade-Relacionamento *(não-mandatório)* | 3 | ⏳ |
| M5 | Flagueamento (LGPD/uso/qualidade) | 2 | ✅ |
| M6 | Dicionário Corporativo | 2 | ✅ |
| M7 | Linhagem (upstream/downstream + UC Lineage) | 3 | ✅ |
| M8 | Versionamento de Modelos + Diff | 2 | ✅ |
| M9 | Sincronização Unity Catalog (COMMENT+TAGS) | 1 | ✅ |
| M10 | Exportação DDL multi-dialect | 2 | ✅ |
| M-LB | Lakebase Sandbox (validação round-trip) | 2 | ✅ |
| Cross | Tickets de Reconciliação + RBAC | 1 | ✅ |

## Estrutura do repositório

```
.
├── docs/
│   ├── spec/                 # Especificação funcional autoritativa
│   ├── prompts/              # Prompt Registry — histórico por fase
│   └── adr/                  # Architecture Decision Records
├── src/
│   └── nuclea_modeler/
│       ├── backend/          # FastAPI: models, router, core
│       └── ui/               # React: rotas, components, hooks
├── databricks/
│   └── sql/                  # DDL Delta para schema do app
├── app.yml                   # Manifesto do Databricks App
├── databricks.yml            # Databricks Asset Bundle (DAB)
└── pyproject.toml
```

## Desenvolvimento

Pré-requisitos: `uv`, `bun`, `node 22+`, `apx 0.3+`, acesso de rede a npm/pypi (corporativo bloqueia esses registries — usar VPN apropriado para dev local).

```bash
# Subir backend + frontend + watcher OpenAPI
apx dev start

# Status / logs / parar
apx dev status
apx dev logs -f
apx dev stop

# Type check (TS + Python)
apx dev check
```

## Build & Deploy

```bash
# Build de produção (UI compilada, backend empacotado)
apx build

# Deploy no workspace Databricks via DAB
databricks bundle deploy -p svc
databricks bundle run nuclea-modeler-app -p svc
```

## Branding

Paleta Núclea (placeholder, validar visualmente após primeiro deploy):
- Primário: magenta/violeta `oklch(0.45 0.21 330)` (~#7B2D8E)
- Acento: amarelo `oklch(0.83 0.17 90)` (~#FFC72C)
- Tipografia: stack do sistema com features OpenType (`cv11`, `ss01`, `ss03`)

## Documentação

- 📋 Spec funcional: [`docs/spec/`](docs/spec/)
- 🛠️ Plano de execução: [`docs/prompts/01-plano-militar.md`](docs/prompts/01-plano-militar.md)
- 🗒️ Prompt registry: [`docs/prompts/`](docs/prompts/)
- 🏛️ Decisões: [`docs/adr/`](docs/adr/)

## Licença

Privado · Núclea S.A. · Todos os direitos reservados.

---

<sub>Construído com [apx](https://github.com/databricks-solutions/apx) · Stack: FastAPI + React + shadcn/ui</sub>
