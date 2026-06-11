# Núclea Modeler

> Catálogo e modelagem de dados corporativa — Databricks App nativo para a **Núclea**.

[![CI](https://github.com/lfmed/nuclea-modeler/actions/workflows/ci.yml/badge.svg)](https://github.com/lfmed/nuclea-modeler/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lfmed/nuclea-modeler?include_prereleases&label=release&color=7B2D8E)](https://github.com/lfmed/nuclea-modeler/releases)
[![Coverage](https://img.shields.io/badge/coverage-81%25-green)](https://github.com/lfmed/nuclea-modeler/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![Security](https://img.shields.io/badge/security-bandit-blue)](SECURITY.md)
[![License](https://img.shields.io/badge/license-Privado-lightgrey)](#)

Aplicação full-stack (FastAPI + React, via [APX](https://github.com/databricks-solutions/apx)) que centraliza o ciclo de vida dos modelos de dados — da engenharia reversa dos ambientes **HINT/HEXT/PROD** até o espelhamento automático no **Unity Catalog**.

> **🚀 Novo aqui?** Comece pelo [tutorial de 20 minutos](docs/tutorial/getting-started.md) para fazer o primeiro ciclo completo (sistema → conexão → reversa → ticket → versão → sync).
>
> **📦 Vai instalar em outro workspace Databricks?** Siga o [DEPLOY.md](DEPLOY.md) — pré-requisitos, parametrização (`app.yml.example`) e troubleshooting.

## Índice

- [Módulos funcionais](#módulos-funcionais)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Desenvolvimento](#desenvolvimento)
- [Build & Deploy](#build--deploy)
- [Branding](#branding)
- [Endpoints operacionais](#endpoints-operacionais)
- [Migrations](#migrations)
- [Runbook](#runbook)
- [Feature flags](#feature-flags)
- [Documentação](#documentação)
- [Licença](#licença)

| | |
|---|---|
| **Cliente** | Núclea S.A. (ex-CIP) |
| **Audiência** | Tribo de Dados, CdE de Dados, Stewards, Architects, Engineers |
| **Plataforma** | Databricks Apps + Unity Catalog + Delta Lake |
| **Stack** | Python 3.11+ · FastAPI · React 19 · TanStack Router · shadcn/ui · Tailwind 4 |
| **Persistência** | 100% Delta Lake no Unity Catalog (sem Postgres operacional) |
| **Status** | 🟢 Spec 100% + extras (Tickets, Lakebase, Code Objects, Audit, Busca, Embarcadero, Home, Help) + Production hardening (migrations, security, rate-limit, paginação, ODBC/REST real, livez/readyz, JSON logs, bundle splitting) |
| **URL live** | https://nuclea-modeler-7474646973581105.aws.databricksapps.com |

## Módulos funcionais

| # | Módulo | Fase | Status |
|---|--------|------|--------|
| M1 | Conexões de Ambiente (ODBC/REST/DDL) | 1 | ✅ |
| M2 | Engenharia Reversa (Lakebase + DDL) | 1 | ✅ |
| M3 | Documentação de Componentes | 1 | ✅ |
| M4 | Diagrama Entidade-Relacionamento (React Flow + Dagre) | 3 | ✅ |
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

## Endpoints operacionais

| Endpoint | Quem usa | O que retorna |
|---|---|---|
| `GET /api/livez` | k8s/Apps probe de restart | 200 imediato, sem deps · uptime + version |
| `GET /api/readyz` | k8s/Apps probe de tráfego | Verifica `SELECT 1` no warehouse (cache 5s) |
| `GET /api/health` | UI + monitoramento | Reachability + counts (cache 30s) |
| `GET /api/version` | Build pipeline | Versão semântica do package |
| `GET /api/entities/page?page=1&page_size=50` | UI listas grandes | `PaginatedEntities` |
| `GET /api/audit/page?page=1&page_size=50` | Admin audit | `PaginatedAudit` |
| `GET /api/features` | UI + scripts | Flags ativas no processo (env-driven) |
| `GET /api/metrics` | Admin / dashboards | Contadores per route + p50/p95 (in-memory) |
| `GET /docs` · `GET /redoc` | Devs / integração | OpenAPI navegável (Swagger + ReDoc) |
| `X-Request-ID` (header) | Toda response | Correlation id curto (12 chars) ou inbound sanitizado (64) |
| `X-Error-ID` (header) | Quando 500 | UUID curto quotável para reportar bugs (sem leak de stack) |
| `Retry-After` (header) | Quando 429 | Segundos até retry (rate limit por rota/IP) |

## Migrations

Schema do app vive em `databricks/sql/*.sql` (numeradas, idempotentes).

```bash
# Aplicar manualmente (workspace novo, debug):
python -m nuclea_modeler.backend.core.migrations

# Auto-aplicação no startup (default):
# Controlada por NUCLEA_MIGRATIONS_AUTO_APPLY=true (false desabilita)
```

Tracking via `schema_migrations` Delta com SHA-256. Drift detectado mas não re-aplicado — investigação manual.

## Runbook

### Cenários comuns

**App não sobe**
1. `databricks apps logs nuclea-modeler` → procure `[migrations]` no log de startup
2. Se "DRIFT detected": migração foi editada após aplicar. Reverter o arquivo OU criar nova migration corrigindo
3. Se falha em statement específico: rodar o SQL manual no SQL Editor para entender. Migrations runner é fail-fast — fix e re-deploy

**Performance degradada**
1. Verificar `/api/readyz` → latência do warehouse
2. Verificar `/api/metrics` (admin) → p95 por rota + counts 5xx
3. Verificar `/api/health` → `delta_tables_count` cresceu muito? Trocar listagem por `/page`
4. Logs com `NUCLEA_LOG_JSON=true` permitem filtrar por `request_id` para rastrear request lento

**Bug reportado pelo usuário**
- Pedir o `error_id` (sai no header `X-Error-ID` em qualquer 500 ou no Toast da UI)
- Buscar no log: `grep <error_id> logs.json` → request_id, path, traceback completo
- Logs JSON têm `request_id`, `method`, `path`, `exception_type` como campos top-level

**Restauração**
- Delta Time Travel: `SELECT * FROM table TIMESTAMP AS OF '2026-05-01'`
- Versões publicadas: aba `/versions` → "Restaurar" cria DRAFT a partir do snapshot
- Tickets: histórico permanente em `reconciliation_tickets`

**Secrets rotacionados**
- Atualizar valor em Databricks Secrets (scope = `NUCLEA_SECRETS_SCOPE`)
- Re-testar conexão em `/connections/{id}/test`
- App lê secret a cada teste (sem cache) — efeito imediato

### Variáveis de ambiente

| Var | Default | Descrição |
|---|---|---|
| `NUCLEA_CATALOG` | `stable_classic_pg4xe1_catalog` | UC catalog do app state |
| `NUCLEA_SCHEMA` | `data_catalog_app` | Schema do app |
| `NUCLEA_WAREHOUSE_ID` | (config) | SQL Warehouse para queries |
| `NUCLEA_SECRETS_SCOPE` | `nuclea-modeler` | Secrets default das conexões |
| `NUCLEA_MIGRATIONS_AUTO_APPLY` | `true` | Aplica migrations no startup |
| `NUCLEA_MIGRATIONS_DIR` | (auto) | Override do path de `databricks/sql/` |
| `NUCLEA_LOG_JSON` | `false` | Emite logs em JSON single-line |
| `NUCLEA_LOG_LEVEL` | `INFO` | Nível raiz de logging |
| `NUCLEA_CORS_ALLOW_ORIGINS` | (vazio) | CSV de origens permitidas pelo CORS (opt-in, default same-origin) |
| `NUCLEA_FEATURE_*` | `false` | Feature flags individuais — vide `core/features.py` para a lista |

### Feature flags

Flags são booleanas e default-off. Ative com `NUCLEA_FEATURE_<NOME>=true`:

| Flag | Módulo | O que ativa |
|---|---|---|
| `der_minimap` | M4 | Minimap no canvas do diagrama |
| `der_auto_layout_v2` | M4 | Tweaks experimentais no auto-layout Dagre |
| `embarcadero_v2` | M2 | Parser .erx de nova geração com heurísticas de namespace |
| `ddl_import_dry_run` | M2 | Preview de DDL antes de persistir |
| `versions_signed` | M8 | Assinatura criptográfica em versões publicadas |
| `sync_column_lineage` | M9 | Tentativa de escrever lineage column-level no UC |
| `global_search_v2` | Cross | UI de busca de nova geração (placeholder) |
| `structured_logs` | Ops | Alias legado — use `NUCLEA_LOG_JSON` |

Frontend consome via `useFeatures()` em `ui/lib/features.ts`.

## Documentação

- 🚀 **Comece aqui:** [`docs/tutorial/getting-started.md`](docs/tutorial/getting-started.md) — primeiro dia em 20min
- 🏗️ Arquitetura (Mermaid): [`docs/architecture/system.md`](docs/architecture/system.md)
- 📋 Spec funcional: [`docs/spec/`](docs/spec/)
- 🏛️ Decisões: [`docs/adr/`](docs/adr/)
- 🎯 Roteiro de demo para arquiteto: [`docs/demo/jornada-arquiteto-de-dados.html`](docs/demo/jornada-arquiteto-de-dados.html)
- 🔧 Receitas curl da API: [`docs/api/RECIPES.md`](docs/api/RECIPES.md)
- 📜 Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- 🗺️ Roadmap: [`ROADMAP.md`](ROADMAP.md)
- 🔒 Segurança: [`SECURITY.md`](SECURITY.md)
- 🤝 Como contribuir: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 🛠 Scripts operacionais: [`scripts/README.md`](scripts/README.md)
- ⚙️ Deploy & runbook detalhado: [`docs/operations/deploy-runbook.md`](docs/operations/deploy-runbook.md)
- 🔐 Branch protection: [`docs/operations/branch-protection.md`](docs/operations/branch-protection.md)

## Licença

Privado · Núclea S.A. · Todos os direitos reservados.

---

<sub>Construído com [apx](https://github.com/databricks-solutions/apx) · Stack: FastAPI + React + shadcn/ui</sub>
