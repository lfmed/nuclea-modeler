# Deploy & Operations Runbook

Procedimentos para deploy, rollback, troubleshooting do Núclea Modeler em
produção.

## Deploy normal

### Pré-requisitos
- `databricks` CLI configurado (`databricks configure --token`)
- Acesso ao workspace `fevm-stable-classic-pg4xe1`
- Permissão CAN_MANAGE no app `nuclea-modeler`

### Steps

```bash
# 1. Sincronizar local com main
git checkout main && git pull --ff-only

# 2. Verificar CI verde
gh run list --limit 1 --repo lfmed/nuclea-modeler
# Esperar "success" no último

# 3. Deploy
make deploy
# Equivale a:
#   databricks bundle deploy -p svc
#   databricks bundle run nuclea-modeler-app -p svc

# 4. Verificar startup
make health   # GET /api/health da URL live
# Deve retornar 200 + delta_reachable: true

# 5. Sanity test rápido
curl -s "$LIVE_URL/api/livez" | jq .uptime_seconds
# Deve mostrar uptime baixo (segundos), confirma deploy novo
```

**Tempo médio:** 3-5 minutos do `make deploy` até `/livez` responder com uptime baixo.

## O que acontece no startup

Sequência observada nos logs (`databricks apps logs nuclea-modeler -p svc`):

```
1. [migrations] Discovered N migration(s) in /app/python/source_code/databricks/sql
2. [migrations] Applying 001_create_schema.sql...
3. [migrations] Applied 001_create_schema.sql in NN ms
   ... (uma linha por migration aplicada/skipped)
4. [migrations] Startup summary: {'applied': X, 'skipped': Y, 'drifted': 0, 'failed': 0}
5. INFO:     Started server process [PID]
6. INFO:     Uvicorn running on http://0.0.0.0:8000
```

Se você não vir até passo 4, **app não subiu** — vá pra seção [App não sobe](#app-não-sobe).

## Rollback

### Opção A — git revert (recomendado)

Se o commit problemático já está em `main`:

```bash
git revert <hash-do-commit-ruim>
git push origin main
# CI roda + auto-deploy via bundle (se configurado)
# OU manual: make deploy
```

### Opção B — Deploy de tag anterior

```bash
git checkout v0.2.0   # ou versão estável anterior
make deploy
# DEPOIS volta pra main para não ficar com working tree no detached HEAD
git checkout main
```

### Opção C — Time travel das tabelas

Para corrigir dados ruins introduzidos por migration buggy (não código):

```sql
-- No SQL Editor do workspace
RESTORE TABLE stable_classic_pg4xe1_catalog.data_catalog_app.entities
TO TIMESTAMP AS OF '2026-05-28 10:00:00';
```

Não desfaz mudanças de schema (CREATE TABLE etc) — só linhas.

## Troubleshooting

### App não sobe

1. `databricks apps logs nuclea-modeler -p svc | tail -200`
2. Procure por:
   - `[migrations] FAILED <arquivo>: ...` → migration buggy. Veja [migrations failure](#migrations-failure)
   - `ImportError: No module named X` → dep faltando em requirements.txt
   - `AttributeError` / `TypeError` no startup → bug de código novo

### Migrations failure

1. Identificar arquivo: `[migrations] FAILED 0XX_<nome>.sql: <erro>`
2. Rodar o SQL manualmente no SQL Editor pra ver o erro completo
3. Fix:
   - **Se for sintaxe:** corrigir o arquivo, deploy de novo
   - **Se for state real divergente:** criar nova migration que corrige (não editar o arquivo antigo — drift detection vai alertar)
4. Se urgência: temporariamente setar `NUCLEA_MIGRATIONS_AUTO_APPLY=false` no `app.yml` para boot sem aplicar, depois rodar `python -m nuclea_modeler.backend.core.migrations` no SQL Editor para diagnosticar

### Performance degradada

| Sintoma | Investigar primeiro |
|---|---|
| API lenta no geral | `/api/metrics` (admin) — qual rota tem p95 alto? |
| Listagem lenta | Trocar `/api/entities` → `/api/entities/page?page_size=50` |
| Warehouse lento | `/api/readyz` mostra latência. Verificar warehouse activity em workspace |
| /sync/run timeout | Aumentar `wait_timeout` no statement, ou paginar |

### Erro 5xx no UI

1. Pedir ao usuário o `error_id` (header `X-Error-ID` ou toast)
2. `databricks apps logs nuclea-modeler -p svc | grep <error_id>`
3. Log estruturado tem: `request_id`, `method`, `path`, `exception_type`, traceback completo
4. Para correlacionar com audit: `SELECT * FROM audit_log WHERE request_id = '<rid>'`

### Secrets rotacionados não funcionam

1. Atualizar valor: `databricks secrets put-secret nuclea-modeler <key>`
2. Re-testar conexão na UI: `/connections/{id}/test`
3. Se ainda falha: o app SP precisa ter `READ` permission no scope
4. Verificar permissões: `databricks secrets list-acls --scope nuclea-modeler`

## Manutenção planejada

### Backup pré-mudança de schema

```bash
make backup VOLUME=/Volumes/main/default/nuclea_backups
# Cria snapshot timestamp em /Volumes/.../<YYYYMMDDTHHMMSSZ>/
```

### Atualização de deps (Dependabot)

PRs do Dependabot são automáticas (semanal segunda 7am BRT):
- **Patch/minor agrupados** → mergear se CI verde, sem risco
- **Major individuais** → revisar breaking changes, testar local antes

### Adicionar nova migration

```bash
# 1. Criar arquivo numerado
echo "-- 010_new_table.sql" > databricks/sql/010_new_table.sql

# 2. Editar com CREATE TABLE IF NOT EXISTS (idempotente!)

# 3. Testar local
make migrate

# 4. Commit + push + deploy
git add databricks/sql/010_new_table.sql
git commit -m "feat(schema): nova tabela X"
git push  # CI roda
make deploy  # após CI verde
```

## Gotcha: SSO obrigatório em TODOS os endpoints

Validado em 2026-05-28: **Databricks Apps platform força autenticação SSO antes do request chegar ao app.** Isso inclui endpoints projetados como "públicos" sem auth como `/api/livez` e `/api/readyz` — todos retornam 401 sem token de SSO.

```bash
# Sem token, mesmo /livez retorna 401:
$ curl -i https://nuclea-modeler-7474646973581105.aws.databricksapps.com/api/livez
HTTP/1.1 401 Unauthorized
```

### Impactos

| O que NÃO funciona | O que funciona |
|---|---|
| ❌ UptimeRobot / Pingdom direto | ✅ Health check de Databricks Job (token M2M) |
| ❌ k8s probe externo | ✅ Probe interno do Databricks Apps (gerenciado pela plataforma) |
| ❌ Curl sem auth de qualquer endpoint | ✅ Browser com SSO logado |

### Como monitorar externamente (se preciso)

**Opção A — Databricks Job que faz curl com token M2M:**

```python
# Notebook ou Python job
from databricks.sdk import WorkspaceClient
import httpx

ws = WorkspaceClient()
token = ws.dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

r = httpx.get(
    "https://nuclea-modeler-7474646973581105.aws.databricksapps.com/api/health",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10.0,
)
assert r.status_code == 200, f"Health check falhou: {r.status_code}"
assert r.json()["delta_reachable"] is True
```

Agendar como Job recorrente (cron a cada 5 min) com email notification on failure.

**Opção B — Configurar unauthenticated access no app.yml** (se a Núclea aceitar):

```yaml
# app.yml
authentication:
  unauthenticated_paths:
    - /api/livez
    - /api/readyz
```

⚠️ Isso expõe esses endpoints publicamente. Use apenas se aceitável pela política de segurança.

**Opção C — Frontend polling com cookie SSO:**

UI já faz polling do `/api/health` usando o cookie SSO do usuário logado — visível em `/admin/metrics`. Não substitui monitor externo mas dá visibilidade pra quem está no app.

## SLA / SLO informais

| Métrica | Objetivo |
|---|---|
| Disponibilidade | ≥99.5% (vide Databricks Apps SLA) |
| `/api/livez` latência p95 | <100ms |
| `/api/readyz` latência p95 | <500ms |
| Listagem paginada (entities, audit) latência p95 | <1s |
| Sync UC com 100 entidades | <30s |

Tracking via `/api/metrics` (admin) — não há alerting automático ainda
(roadmap: Sentry/Datadog).

## Contatos

| Função | Pessoa |
|---|---|
| Owner / Tech Lead | @lfmed |
| Tribo de Dados Núclea | (TBD quando time crescer) |
| Vulnerabilidades | leandro.medeiros@databricks.com (vide SECURITY.md) |
