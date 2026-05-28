# Prompt Registry — Nuclea Modeler

> Histórico vivo dos prompts, decisões e comandos usados para construir o app, fase por fase.

## Por que isso existe

Este projeto está sendo construído em colaboração com um assistente de IA (Claude / Claude Code). Para garantir **reprodutibilidade, auditoria e onboarding rápido de novos colaboradores**, cada fase do trabalho é registrada aqui contendo:

1. **Prompt(s)** enviados ao assistente
2. **Decisões** tomadas em conjunto (e os trade-offs)
3. **Comandos** executados no ambiente Databricks / Git / local
4. **Diffs / artefatos** produzidos (referências aos commits)
5. **Aprendizados** e ajustes para iterações futuras

## Índice

### Fase 1 — Concepção e MVP (2026-05-22 → 2026-05-25)

| # | Arquivo | Fase | Status |
|---|---------|------|--------|
| 00 | [00-spec.md](00-spec.md) | Spec original recebida do cliente | ✅ |
| 01 | [01-plano-militar.md](01-plano-militar.md) | Plano de execução consolidado | ✅ |
| 10 | [10-fase0-bootstrap.md](10-fase0-bootstrap.md) | Bootstrap: repo, scaffold, UC, recursos | ✅ |
| 20 | [20-fase1-mvp.md](20-fase1-mvp.md) | MVP: M1 + M2 + M3 + M9 + deploy | ✅ |
| 30 | [30-tickets-rbac.md](30-tickets-rbac.md) | Tickets de reconciliação + RBAC | ✅ |
| 40 | [40-madrugada-multiagente.md](40-madrugada-multiagente.md) | Madrugada god-mode: 7 PRs paralelos | ✅ |

### Fase 2 — Visualização e cross-cutting (2026-05-25 → 2026-05-26)

| # | Arquivo | Fase | Status |
|---|---------|------|--------|
| 50 | [50-fase3-visualizacao.md](50-fase3-visualizacao.md) | M7 (Linhagem) + M4 (DER React Flow) | ✅ |
| 90 | [90-cross-rbac-audit.md](90-cross-rbac-audit.md) | RBAC global, auditoria, busca | ✅ |

### Fase 3 — Production hardening v0.2.0 (2026-05-26 → 2026-05-28)

Documentado em **commits Conventional Commits** + [**ADR-0003**](../adr/0003-production-hardening.md).

| Sprint | Entregas | Resultado |
|---|---|---|
| SQL parametrization | 100+ ocorrências `_q()` → `delta.param()` | 0 f-string SQL com input usuário |
| UX polish demo | Welcome tour, EmptyState shared, A11y pass | 25+ aria-labels, 7 rotas refatoradas |
| Sprint 0 produção | Migrations runner, security middleware, `/livez+/readyz`, JSON logs, request_id, exception handler, `/metrics`, feature flags, CORS, ODBC/REST real, paginação | App enterprise-ready |
| Quality gates | pytest-cov 60% hard, tsc enforcement, bandit, CodeQL, OpenAPI snapshot, Dependabot semanal | 5 workflows CI/CD ativos |
| Community ready | Issue templates, SECURITY.md, ROADMAP.md, CONTRIBUTING.md, pre-commit, welcome+stale bots, LICENSE | Onboarding completo |
| Docs | Getting Started, API Recipes, Architecture Mermaid, demo HTML, CHANGELOG, Makefile | 26 docs markdown |

### Fase 4 — Security patch + quality hardening v0.2.1 (2026-05-28)

Trigger inicial: usuário perguntou "vi vários errors de workflow, preciso me preocupar?".
Investigação levou a tornar bandit hard-gate, descobriu **vulnerabilidade XXE real**.
Documentado em [**ADR-0004**](../adr/0004-quality-gates-evolution.md).

| Sprint | Entregas | Resultado |
|---|---|---|
| Triage workflow errors | Classificar cancelled (concurrency) / CodeQL (GHAS) / CI fail (bug meu) | 3 categorias claras |
| 🔴 XXE security fix | bandit hard-gate descobriu B314 CWE-20 no parser .erx → defusedxml | **v0.2.1 security release** |
| Quality gates promotion | bandit, OpenAPI drift, pytest-cov 60→75% como hard-gates | 6 quality gates ativos |
| New gates | deps-sync (pyproject vs requirements), achou psycopg/pyodbc missing | 7º hard-gate ativo |
| Size caps | DDL 5MB, .erx 10MB (DoS defense em parsers) | 7 tests size-cap |
| DX | .editorconfig, .env.example, Makefile, pre-commit deps-sync hook | Onboarding < 5min |
| Docs | ADR-0004 quality gates lifecycle, tutorial 20min, architecture Mermaid | 28 docs markdown |

### Como contribuir prompts novos

Para um sprint novo significativo (>3h de trabalho, >5 commits, ou mudança arquitetural), crie um arquivo aqui com:
- Contexto: por que está fazendo
- Prompts principais que orientaram a IA
- Decisões + trade-offs aceitos
- Commits resultantes (referências)
- Aprendizados pro próximo sprint

## Convenções

- **Cada arquivo abre com um cabeçalho** contendo: fase, objetivo, status, autor primário, datas
- **Prompts citados literalmente** entre cercas tríplices ` ``` ` — preserva pontuação e nuances
- **Decisões críticas viram ADRs** em `docs/adr/` e são referenciadas aqui por número (ADR-NNNN)
- **Commits relevantes** são referenciados por hash curto
- **Linguagem:** português brasileiro (como o resto do produto)
