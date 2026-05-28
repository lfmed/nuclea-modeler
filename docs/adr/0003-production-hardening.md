# ADR-0003 — Production hardening (Sprint 0 + observability)

**Status:** Aceito
**Data:** 2026-05-28
**Decisor:** Leandro Medeiros
**Contexto:** Após entrega completa dos 10 módulos + extras, o app foi auditado para uso operacional pela Núclea. A spec funcional estava 100% — mas faltava infra para colocar isso na frente de um cliente real.

## Decisões

### 1. Migrations runner no startup (não CLI manual)

**Decisão:** `databricks/sql/*.sql` aplicam-se automaticamente no boot do app, controlado por `NUCLEA_MIGRATIONS_AUTO_APPLY=true` (default). Tracking via tabela `schema_migrations` Delta com SHA-256.

**Alternativas consideradas:**
- CLI manual (`databricks bundle deploy` + `python -m migrations`) — operador tem que lembrar de rodar
- Pre-deploy hook em CI — atrasa deploy, exige credenciais Databricks no GitHub
- Migrate library (Alembic) — peso extra, abstração desnecessária para 9 arquivos

**Por que esta:** Workspace novo sobe e funciona. Zero passos manuais. Fail-fast com log estruturado. CLI continua disponível para casos de drift detection ou re-deploy.

**Trade-off aceito:** Migration que quebra trava o boot. Compensado por:
1. Logs claros (`[migrations] FAILED ...`)
2. Boot continua mesmo com migrations failure (app sobe, /readyz reflete)
3. Drift detection avisa sem re-aplicar (não destrói estado humano)

### 2. Rate limit in-memory (não Redis/distributed)

**Decisão:** Sliding window por (IP, route_pattern) em dict + deque no processo. 6 regras default, não configurável via env (mudança = redeploy).

**Alternativas consideradas:**
- Redis com slowapi — mais correto em multi-instância, mas adiciona deps + infra
- Token bucket por user (não IP) — exige resolução do user no middleware

**Por que esta:** Databricks Apps já dá DDoS protection na borda. Essa camada é defense-in-depth contra cliente abusivo (script). 2 workers compartilhando o mesmo dict via worker-per-pod = aceitável. Quando rodar em multi-pod, plug em Redis vira refactor mecânico (interface igual).

### 3. Logging estruturado opt-in (não obrigatório)

**Decisão:** `NUCLEA_LOG_JSON=false` por default. Logs em formato texto humanamente legível. JSON ativado por env para envs que têm log aggregation.

**Por que:** Em dev/staging, JSON quebra `tail -f` legibilidade. Em prod com Lakehouse Monitoring, é o formato que o pipeline parseia. Operador escolhe.

### 4. Feature flags env-driven (não service externo)

**Decisão:** `KNOWN_FLAGS` é uma tupla declarada em código. Estado vem de `NUCLEA_FEATURE_*` env vars, lido uma vez no startup com `lru_cache`. Mudança = redeploy.

**Alternativas consideradas:**
- GrowthBook / LaunchDarkly — overkill, depende de SDK externa
- Tabela Delta com runtime toggle — race conditions, complexo, requer cache invalidation

**Por que esta:** Para o cenário "ship behind flag, ativar para 1 ambiente, observar, ativar para todos", env vars são suficientes. Não precisamos de per-user targeting. Stable per process = sem skew entre requests do mesmo worker.

### 5. /livez e /readyz separados (convenção k8s)

**Decisão:**
- `/livez` = 200 imediato, sem deps. Para probe de restart do container.
- `/readyz` = SELECT 1 no warehouse com cache 5s. Para gating de tráfego.
- `/health` continua com counts + reachability + cache 30s.

**Por que:** Convenção k8s/Databricks Apps. `/livez` deve sempre retornar 200 — se o processo está vivo, o probe nunca deve sugerir restart por dependency externa. `/readyz` é o sinal correto para "envie tráfego para mim".

### 6. ODBC + REST testers reais com ImportError gracioso

**Decisão:** `pyodbc` é dep do requirements.txt, mas o tester captura `ImportError` e retorna `failure` com mensagem clara. Mesmo padrão para `httpx` (sempre presente, mas o pattern é o mesmo).

**Por que:** Em ambientes onde o driver ODBC não está instalado (dev sem unixodbc), o app continua funcional — só os testes ODBC falham com mensagem útil. Não bloqueia features REST/Lakebase.

### 7. Exception handler com error_id (não traceback no response)

**Decisão:** Exception não-capturada gera `error_id` (12 chars uuid), retorna 500 com `{detail, error_id, request_id}` + header `X-Error-ID`. Traceback completo VAI para o log, NÃO para o response.

**Por que:** Vazar traceback em produção é attack vector (revela paths, libs, versões). User reporta `error_id` ao SA, SA faz `grep error_id logs.json` e tem todo o contexto.

### 8. Metrics in-process (não Prometheus)

**Decisão:** `MetricsMiddleware` agrega por (route_pattern, status_class) em memória + ring buffer 512 últimas latências por rota. `/api/metrics` admin-only.

**Por que:** Prometheus exige scraping endpoint estilo OpenMetrics, exige cleanup de stale series, exige histogram buckets configurados — toda complexidade que não compensa para o tamanho atual. In-process resolve "que rota está lenta agora?" sem deps externas. Quando ganhar escala, exportador para Lakehouse Monitoring vira drop-in.

## Consequências

**Boas:**
- App sobe sem intervenção manual em workspace novo
- Operador tem `error_id`, `request_id`, `/metrics`, `/livez`/`/readyz`, logs estruturados — tudo necessário pra debug em produção
- Security defaults (headers + rate limit + CORS opt-in) cobrem OWASP top 10 básico
- Feature flags permitem dark launches sem refactor de código
- CI verde gate em todo PR

**Aceitas:**
- Rate limit não distribuído (multi-pod precisa Redis no futuro)
- Migrations runner é fail-fast (broken migration = broken boot)
- Métricas resetam a cada restart (sem persistência)
- JSON logs precisam de log aggregator externo para virar dashboards

## Não-objetivos (deliberadamente fora de escopo)

- **APM / tracing distribuído** (OpenTelemetry) — adicionar quando integrar com Datadog/New Relic
- **Per-user feature targeting** — usar GrowthBook se virar necessidade
- **Backup automatizado** — Delta Time Travel já cobre (runbook documenta)
- **Multi-tenancy** — app é single-tenant Núclea por design

## Arquivos relevantes

- `src/nuclea_modeler/backend/core/migrations.py`
- `src/nuclea_modeler/backend/core/security.py`
- `src/nuclea_modeler/backend/core/logging.py`
- `src/nuclea_modeler/backend/core/features.py`
- `src/nuclea_modeler/backend/core/exceptions.py`
- `src/nuclea_modeler/backend/core/metrics.py`
- `src/nuclea_modeler/backend/connections/testers.py`
- `.github/workflows/ci.yml`
- `.github/workflows/e2e.yml`
- `.github/dependabot.yml`
