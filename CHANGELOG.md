# Changelog

Convenção: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Fixed 🐛
- **Import de DDL não extraía coluna nenhuma** — o parser lia `stmt.expressions`
  (sempre vazio no sqlglot) em vez de `stmt.this.expressions`. CREATE TABLE via
  DDL gerava entidades sem atributos no diagrama. Corrigido em
  `extractions/service.py:run_ddl_import()`, com teste de regressão.
- **Relacionamentos (FKs) perdidos no import** — Embarcadero (.DM1) e DDL agora
  extraem FKs estruturalmente e as persistem na tabela `relationships` via
  entries sintéticas `__relationship__` no diff, resolvidas por nome no apply do
  ticket (depois das entities materializadas). Antes eram apenas warnings.
- **Alteração manual "não refletia" após aprovação** — `approve` só mudava o
  status; a materialização exigia um `apply` separado (restrito a Architect/Admin),
  então um Steward que aprovava deixava o ticket preso e a mudança nunca chegava
  ao catálogo. Novo `POST /tickets/{id}/approve-apply` aprova e materializa numa
  única ação.

### Added
- **Aprovação/aplicação em lote de tickets** — `POST /tickets/batch`
  (`approve` / `reject` / `apply` / `approve_and_apply`) processa N tickets sem
  abortar o lote por erro de um item.
- **Extração de FK no DDL** — constraints inline (`col REFERENCES …`) e
  table-level (`CONSTRAINT … FOREIGN KEY … REFERENCES …`), incluindo FKs
  cross-schema.
- **Log de falha de import estruturado** — o resultado e o detalhe da extração
  passam a separar **problemas** (perda de dados: entity/atributo sem nome
  ignorado, FK órfã, tipo desconhecido, erro de parse) de **avisos
  informativos**, formatados em markdown no `summary_md`. O `error_summary`
  persistido deixa de ser truncado em 500 chars (até 4000). Import de Embarcadero
  com perda de dados agora marca status **PARTIAL** (antes sempre SUCCESS),
  sinalizando que o log deve ser revisado.
- **UI: botão "Aprovar e aplicar"** no detalhe do ticket (resolve OPEN numa ação
  só, para quem tem papel de applier) e **seleção múltipla + ações em lote** na
  lista de tickets (aprovar/aplicar/aprovar-e-aplicar/rejeitar N de uma vez).
- **UI: checklist de pré-requisitos** nos formulários de import (DDL e
  Embarcadero) — mostra o que falta (sistema-alvo, DDL/arquivo, dialeto) antes de
  liberar a importação.
- **Segregação por schema + múltiplos diagramas (M6, fatia 1+2)** — schema vira
  entidade de 1ª classe (tabela `schemas`) e cada schema pode ter vários
  diagramas (tabelas `diagrams` + `diagram_entities`). Migration `014` é
  **aditiva e não-destrutiva** (não toca em `entities` — relação derivada por
  JOIN na chave natural `(system_id, schema_name)`; validada contra a warehouse:
  zero perda de dados, idempotente). Backend CRUD: `/api/schemas` e
  `/api/diagrams` (+ membership e layout), com RBAC nas mutações. Sidebar em
  árvore e multi-diagrama no canvas vêm nas próximas fatias.

### Security 🔒
- **RBAC em sistemas** — `createSystem`/`updateSystem` exigem
  DATA_ARCHITECT/DATA_STEWARD/ADMIN; `deleteSystem` exige DATA_ARCHITECT/ADMIN e
  bloqueia exclusão de sistema que ainda tem entidades. Antes qualquer usuário
  autenticado podia renomear/excluir sistemas via API.

### Changed
- **Engenharia reversa do Embarcadero migrou de `.erx` (XML) para `.DM1` (CSV nativo)** —
  formato `.DM1` é o export padrão do ER/Studio na Núclea. Novo parser em
  `extractions/embarcadero.py:parse_dm1()` extrai entities, atributos (com
  tipo derivado de `DatatypeId` + Length/Scale), PKs e FKs (agora persistidas,
  ver Fixed). UI: `accept=".dm1,.DM1"`, cap de upload 50 MB.
- Dependência `defusedxml` removida — sem parser XML em ingestion, vetor XXE
  elimina-se por construção. Tests de segurança XXE substituídos por tests
  de robustez do parser DM1.

## [0.2.1] — 2026-05-28

**Security patch release.** Atualização recomendada imediatamente — corrige
vulnerabilidade XXE no parser de upload `.erx`.

### Security 🔒
- **XXE / XML External Entity (CWE-20, bandit B314) — corrigido** — parser `.erx`
  do Embarcadero (`extractions/embarcadero.py`) agora usa
  `defusedxml.ElementTree.fromstring` ao invés de `xml.etree.ElementTree.fromstring`,
  proibindo entities externas, billion-laughs DoS e DTD recursion.
  Severity Medium, Confidence High — detectado pelo bandit hard-gate em CI.
  Payload malicioso poderia ler arquivos do servidor via `file://`, exaurir memória,
  ou bater o processo. **Recomendação:** atualizar para v0.2.1 imediatamente se
  o app aceita uploads de `.erx`.
- Tests novos em `tests/test_embarcadero_security.py` validam rejeição de 3 payloads
  maliciosos (XXE, billion laughs, DTD com entities) + sanity test.

### Added
- 11 tests novos para `audit/service.py` (list_audit + count_audit filtros/clamps/offset)
- Tests de migrations runner agora passam (mock state usa enum `StatementState`)
- Dependency `defusedxml>=0.7.1`

### Changed
- **Bandit é hard-gate** no CI (removido `continue-on-error`). B608 (low-confidence SQL)
  adicionado a skips com justificativa em `pyproject.toml` (vide ADR-0003).
- **OpenAPI snapshot drift check** é hard-gate condicional — stub é tolerado, mismatch real bloqueia.
- **Node.js 24** forçado em todos os 4 workflows via `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  (preempt da deprecação Junho/2026).

### Removed
- `.github/workflows/codeql.yml` renomeado para `.disabled` — repo privado requer
  GitHub Advanced Security (pago). Reativar via `git mv` quando GHAS for habilitado.

## [0.2.0] — 2026-05-28

Sprint de produção (`production-hardening`). App deixa de ser MVP — todas as
capacidades necessárias para uso pelo cliente estão em produção.

### Added
- **Migrations runner** (`core/migrations.py`) — auto-apply de `databricks/sql/*.sql` no startup com tracking SHA-256 em `schema_migrations`. CLI: `python -m nuclea_modeler.backend.core.migrations`.
- **Security middleware** (`core/security.py`) — `SecurityHeadersMiddleware` (X-Frame DENY, Referrer-Policy, HSTS condicional) e `RateLimitMiddleware` sliding window por (IP, rota).
- **Request correlation** (`core/logging.py`) — `RequestIdMiddleware` gera/honra `X-Request-ID`, propaga via contextvar, reusado pelo audit middleware.
- **JSON logging opt-in** — `NUCLEA_LOG_JSON=true` ativa `JsonFormatter` single-line para log aggregators.
- **Health probes separadas** — `/api/livez` (sem deps) e `/api/readyz` (warehouse probe, cache 5s).
- **Exception handler global** (`core/exceptions.py`) — captura uncaught, gera `error_id`, retorna 500 sanitizado com `X-Error-ID` header, loga ERROR estruturado com traceback. Mensagem do exception nunca vaza.
- **Metrics in-process** (`core/metrics.py`) — `MetricsMiddleware` agrega counts por (route_pattern, status_class) + latency ring p50/p95/max. `/api/metrics` admin-only.
- **Feature flags env-driven** (`core/features.py`) — 8 flags declaradas, `NUCLEA_FEATURE_*`. `/api/features` endpoint + hook `useFeatures` no frontend.
- **CORS middleware opt-in** — `NUCLEA_CORS_ALLOW_ORIGINS` env (CSV), default same-origin no-op.
- **ODBC + REST testers reais** (`connections/testers.py`) — `pyodbc.connect()` + `httpx.GET`, secrets via Databricks Secrets API. ImportError gracioso.
- **Paginação** — `GET /api/entities/page` e `GET /api/audit/page` com `PaginatedX` model.
- **404 customizada** — `components/apx/not-found.tsx` com layout Núclea, 3 CTAs.
- **Welcome tour** — `components/apx/welcome-tour.tsx`, 5 passos guiados, persistência localStorage. Refazer via Help.
- **EmptyState component** — `components/apx/empty-state.tsx` reutilizável; 10 rotas refatoradas.
- **Admin metrics dashboard** — `/admin/metrics` (ADMIN-only) com cards de resumo + tabela de tráfego, refresh 10s.
- **Bundle splitting** — `vite.config.ts` manualChunks (monaco/diagram/tanstack/react/ui/misc). Monaco também via React.lazy em SqlEditor.
- **OpenAPI customizado** — `/docs` e `/redoc` com 15 tags 1-por-módulo, version, contact, license.
- **A11y pass** — skip-to-content link, role landmarks, aria-labels, focus-visible com outline, `prefers-reduced-motion`.
- **CI/CD** — `.github/workflows/ci.yml` (Python + Frontend + Secret scan), `e2e.yml` opt-in via label, `dependabot.yml`.
- **E2E Playwright** — `tests/e2e/smoke.spec.ts` com 5 testes (home, 404, tour, Cmd+K, skip-link).
- **Backup CLI** — `scripts/backup.py` copia 25 tabelas para Volume UC em Parquet.
- **CONTRIBUTING.md** — onboarding completo para time Núclea + parceiros.
- **ADR-0003** — `docs/adr/0003-production-hardening.md` documentando 8 decisões do sprint.

### Changed
- **SQL parametrizado 100%** — eliminadas 100+ ocorrências de `_q()` / f-string com input do usuário. Helpers `delta.param()` + `delta.run_params()`. `_quote_lit` agora tz-aware (normaliza datetime para UTC).
- **/api/health** — probe barata (`SELECT 1`) + counts cacheadas TTL 30s.
- **README** — tabela de endpoints operacionais + runbook (app não sobe, performance, restauração, secrets, error_id) + env vars + feature flags.

### Fixed
- Pre-push secret scanning passa em Sprint 0 (TruffleHog modo diff para PR, full para push).
- `ruff` config em pyproject.toml com `per-file-ignores` para `tests/` (E402, F401 — pytest.importorskip pattern).
- Vite build precede `tsc` no CI (TanStack Router gera `routeTree.gen.ts` no build).
- Test recursion: `httpx.Client` capturado antes de patch para evitar recursão infinita.

### Security
- Defense in depth: rate limit + security headers + sanitização de exception response + parametrização universal de SQL + ODBC/REST timeouts duros.
- `X-Error-ID` para correlation sem leak de stack.
- `.claude/` agent state gitignored.

## [0.1.0] — 2026-05-23

MVP funcional. Spec 100% + extras.

### Added
- 10 módulos da spec funcional implementados (M1-M10).
- Tickets de Reconciliação (cross-cutting).
- Lakebase Sandbox para validação round-trip.
- Code Objects (Views, Procedures, Triggers, Sequences) com Monaco editor.
- Audit log com middleware Starlette.
- Busca global cross-cutting (Cmd+K) em 7 dimensões.
- Importer Embarcadero ER/Studio `.erx`.
- Home page rica + Centro de Ajuda in-app.
- Stack: FastAPI + React 19 + TanStack Router + shadcn/ui + Tailwind 4 + Delta Lake + Unity Catalog.
- Deploy: Databricks Apps (svc @ fevm-stable-classic-pg4xe1).
- Persistência: 100% Delta/UC, sem Postgres operacional.
- Lakebase: usado apenas como sandbox de validação.

[Unreleased]: https://github.com/lfmed/nuclea-modeler/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/lfmed/nuclea-modeler/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/lfmed/nuclea-modeler/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lfmed/nuclea-modeler/releases/tag/v0.1.0
