# Roadmap

Documento vivo. Atualize com PRs.

## Em andamento (v0.3.0 — em planejamento)

Pendentes da auditoria de produção que **não entraram no v0.2.0**:

- **Mobile QA visual** — DER + Audit + Diff em iPad/iPhone. Requer device real ou BrowserStack.
- **k6 / Locust load test** — perf_smoke é só baseline; falta cenário realista (50 usuários simultâneos, 1h ramp).
- **Sentry / Datadog APM** — exception handler local + /metrics in-process cobrem 80% do que importa, mas correlation cross-service exige APM.
- **OpenAPI snapshot enforcement** — `docs/openapi.json` está committed mas o check no CI é warn-only. Tornar hard-gate quando snapshot estiver estável.
- **i18n EN/ES** — todo PT-BR hardcoded. Extrair strings para `i18next`.

## Backlog técnico

| Item | Esforço | Valor |
|---|---|---|
| Multi-tenant (várias instâncias da Núclea) | XL | Baixo (não é caso de uso) |
| Distributed rate limit (Redis) | M | Médio (multi-pod) |
| Glossary search com embeddings (semantic) | M | Alto se modelo grande crescer |
| Column lineage (não só table) no Sync UC | L | Alto |
| Diff visual no DER (visualizar v1.0 vs v1.1 lado-a-lado) | M | Alto |
| Bulk operations no UI (apply flag em 50 atributos) | M | Médio |
| Export para Power BI / Tableau lineage formats | M | Médio |
| Slack/Teams notification em ticket OPEN | S | Alto |
| MFA enforcement | S | Médio (SSO Databricks já cobre maioria) |
| API rate limit per-user (não per-IP) | S | Médio |
| Soft-delete em entities (vs hard delete) | S | Alto |
| Mermaid export do DER | S | Médio |
| Profiling endpoint (slow queries) | M | Alto |
| Backup automático recorrente via Databricks Job | S | Alto |
| GitHub Pages pra documentação navegável | M | Médio |

## Fora de escopo (decididamente NÃO)

- **Hosted SaaS multi-tenant** — Núclea Modeler é single-tenant por design.
- **Mobile app nativo** — web responsive é suficiente.
- **GraphQL** — REST + paginação cobrem todos os casos atuais.
- **WYSIWYG entity editor** — formulário simples + Monaco para SQL é melhor UX para data architects.
- **Real-time collaboration** (cursor sharing) — overkill, ticket workflow já resolve conflitos.

## Features de produto pedidas (não-priorizadas)

> Vire issue com label `enhancement` para entrar na fila.

- (vazio — popular conforme demandas chegam)

## Versionamento

- **v0.1.0** — MVP (spec 100% + extras Tickets/Lakebase/Code/Audit/Busca/Embarcadero).
- **v0.2.0** — Production hardening (migrations runner, security headers, rate-limit,
  /livez+/readyz, JSON logs, request_id, exception handler, /metrics, feature flags,
  CORS, ODBC/REST real, paginação, 404 custom, welcome tour, EmptyState, lazy Monaco,
  bundle splitting, A11y pass, CI/CD, E2E Playwright, Dependabot, backup CLI,
  docs completos).
- **v0.3.0** — TBD após validação com cliente.

## Como contribuir para o roadmap

Veja [CONTRIBUTING.md](CONTRIBUTING.md). Abra issue com label `enhancement` ou
edite este arquivo via PR.
