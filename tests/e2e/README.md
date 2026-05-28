# Playwright E2E tests

Smoke tests para o frontend do Núclea Modeler. Cobrem o que renderiza
**sem autenticação**: home, 404, welcome tour, busca global, skip-to-content.

## Como rodar localmente

```bash
# 1. Instalar Playwright na primeira vez
bun add -D @playwright/test
bunx playwright install chromium

# 2. Build do app (vite preview precisa do dist)
bun run build

# 3. Rodar tests (sobe vite preview automaticamente)
bunx playwright test --config tests/e2e/playwright.config.ts
```

## Rodar contra uma URL externa

```bash
E2E_BASE_URL=https://nuclea-modeler-7474646973581105.aws.databricksapps.com \
  bunx playwright test --config tests/e2e/playwright.config.ts
```

> Nota: a URL live exige SSO Databricks. Os smoke tests não autenticam — eles
> esperam que `/` renderize sem auth (vite preview local), então só funcionam
> em ambientes desautenticados.

## CI

Roda no workflow `.github/workflows/e2e.yml`, separado do CI principal,
opcional via label `e2e` no PR ou manual via `workflow_dispatch`.
