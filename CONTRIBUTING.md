# Contribuindo com o Núclea Modeler

Este guia é para quem vai estender, manter ou corrigir o app. Voltado para o time
da Tribo de Dados Núclea e parceiros aprovados.

## Setup local

> O sandbox corporativo da Núclea bloqueia pypi/npm. Build local não é o caminho
> recomendado — use deploy direto para Databricks Apps (vide README). Esta seção
> é para quem **precisa** de ambiente local fora da rede corp.

```bash
# Python
uv venv
uv pip install -e ".[dev]"
uv pip install "psycopg[binary]>=3.1" pyodbc

# Frontend
bun install

# Variáveis de ambiente (.env)
NUCLEA_CATALOG=stable_classic_pg4xe1_catalog
NUCLEA_SCHEMA=data_catalog_app
NUCLEA_WAREHOUSE_ID=b8e52268d9828bdd
NUCLEA_SECRETS_SCOPE=nuclea-modeler
DATABRICKS_HOST=https://fevm-stable-classic-pg4xe1.cloud.databricks.com
DATABRICKS_TOKEN=...   # PAT só para dev, NÃO commitar

# Rodar
bun run dev     # frontend Vite na 5173, proxy /api → 8000
uvicorn nuclea_modeler.backend.app:app --reload --app-dir src
```

## Estrutura de um módulo backend

Cada módulo funcional vive em `src/nuclea_modeler/backend/<modulo>/`:

```
<modulo>/
├── __init__.py
├── models.py     ← Pydantic In/Out/List/Patch
├── router.py     ← FastAPI APIRouter, /api/<modulo>/*
└── service.py    ← lógica de negócio (quando ≥30 linhas)
```

**Convenções:**
- `response_model=` e `operation_id=` obrigatórios em toda rota.
- Input do usuário → `delta.param()`, NUNCA f-string.
- IDs gerados internamente (entity_id, etc.) → ok como `_quote_id()` em IN lists.
- Identifiers (nomes de tabela/coluna) → validar com `_require_ident()` em `core/security.py`.
- Mutations criam entry no audit log automaticamente (middleware).
- Errors → `raise HTTPException(...)` para 4xx; deixe exceções subirem para 5xx (handler global trata).

## Estrutura de uma rota frontend

`src/nuclea_modeler/ui/routes/_sidebar/<rota>.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { useListXSuspense } from "@/lib/api";
import selector from "@/lib/selector";

export const Route = createFileRoute("/_sidebar/x")({
  component: XPage,
});

function XPage() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary onReset={reset} fallbackRender={...}>
          <Suspense fallback={<Skeleton />}>
            <XContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

function XContent() {
  const { data } = useListXSuspense(selector());
  if (data.length === 0) {
    return <EmptyState ... />;
  }
  return ...;
}
```

**Convenções:**
- `useXSuspense(selector())` em vez de `useX()` — sempre Suspense.
- Empty states usam `EmptyState` de `@/components/apx/empty-state`.
- Mutations usam `useMutation` + `toast.success/error` do sonner.
- Listas grandes consomem o endpoint `/page` (paginado).
- Feature flags: `const { isEnabled } = useFeatures();`.

## Pre-commit hooks

Recomendado: instale os hooks locais que rodam ruff + TruffleHog + tsc antes de cada commit. Evita push de algo que o CI vai rejeitar.

```bash
uv tool install pre-commit
pre-commit install

# Rodar manualmente em tudo
pre-commit run --all-files
```

Config: [`.pre-commit-config.yaml`](.pre-commit-config.yaml).

## Fluxo de PR

1. **Branch:** `feat/<slug>`, `fix/<slug>`, `refactor/<slug>`, `docs/<slug>`, `chore/<slug>`.
2. **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).
3. **PR template:** preenchido (vide `.github/pull_request_template.md`).
4. **CI verde:** ruff + pytest + tsc + bundle size + secret scan (vide `.github/workflows/ci.yml`).
5. **Review:** code owner em `.github/CODEOWNERS` (hoje `@lfmed`).
6. **Merge:** squash & merge para `main`. Deploy automático via Databricks Bundle (futuro CD).

## Adicionar um módulo novo

1. **Migration:** crie `databricks/sql/0NN_<nome>.sql` (numerada, idempotente, usa `CREATE TABLE IF NOT EXISTS`).
2. **Backend module:** `src/nuclea_modeler/backend/<nome>/` (models + router + service).
3. **Registrar router:** `src/nuclea_modeler/backend/app.py` adiciona o router à lista de `create_app(routers=[...])`.
4. **OpenAPI tag:** adicione em `core/_factory.py` `openapi_tags=[...]` com descrição.
5. **Frontend rota:** `src/nuclea_modeler/ui/routes/_sidebar/<nome>.tsx`.
6. **Sidebar:** adicione item em `src/nuclea_modeler/ui/routes/_sidebar/route.tsx` (`NavItem`).
7. **Tests:** `tests/test_<nome>.py` para a service layer (sem rede).
8. **ADR:** se a decisão tem trade-off relevante, crie `docs/adr/000N-<nome>.md`.

## Adicionar uma feature flag

1. Edite `KNOWN_FLAGS` em `src/nuclea_modeler/backend/core/features.py`.
2. Adicione tipo correspondente em `FeatureFlag` em `src/nuclea_modeler/ui/lib/features.ts`.
3. Use `isEnabled("flag_name")` no frontend ou `is_enabled("flag_name")` no backend.
4. Documente em `README.md` (seção Feature flags) com módulo e descrição.

## Como debuggar produção

1. **Bug do usuário:** peça o `error_id` (sai no header `X-Error-ID` em todo 500).
2. `databricks apps logs nuclea-modeler` → procure o `error_id`.
3. Se logs em JSON (`NUCLEA_LOG_JSON=true`): use `jq` para filtrar:
   ```bash
   databricks apps logs nuclea-modeler | jq 'select(.request_id == "abc123")'
   ```
4. `/api/metrics` (admin) → ver p95 por rota se for performance.
5. `/api/readyz` → ver se warehouse responde.
6. `/admin/audit` → histórico de quem fez o quê.

## Como NÃO contribuir

- 🚫 Não rode `apx build` localmente — o sandbox corp bloqueia pypi/npm. Deploy direto.
- 🚫 Não commite `.env`, `.databricks/`, `.claude/` (gitignore cobre).
- 🚫 Não use `print()` em código novo — use `logger.info(..., extra={...})`.
- 🚫 Não use f-string para SQL com input do usuário — use `delta.param()`.
- 🚫 Não amplie funcionalidade sem teste correspondente (ver `tests/`).
- 🚫 Não force-push em `main`.
