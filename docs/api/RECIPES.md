# API Recipes — Núclea Modeler

Receitas com `curl` para os fluxos mais comuns da API. Para exploração
interativa, use `/docs` (Swagger UI) ou `/redoc`.

## Autenticação

Todos os endpoints sob `/api/*` (exceto `/livez`, `/version`) exigem
autenticação Databricks SSO. Em chamadas server-to-server, use um Personal
Access Token (PAT) ou OAuth M2M.

```bash
export BASE="https://nuclea-modeler-7474646973581105.aws.databricksapps.com"
export TOKEN="dapi..."  # PAT do workspace
export AUTH="-H 'Authorization: Bearer $TOKEN'"
```

> Para uso em produção, prefira **OAuth M2M** com service principal +
> resource declarado em `app.yml`. PATs são para desenvolvimento.

## Health & status

```bash
# Liveness (sem auth, sem deps — para probe de restart k8s)
curl -s "$BASE/api/livez" | jq

# Readiness (sem auth, mas faz SELECT 1 no warehouse)
curl -s "$BASE/api/readyz" | jq
# {
#   "ready": true,
#   "version": "0.2.0",
#   "warehouse_reachable": true,
#   "warehouse_latency_ms": 245
# }

# Health rico (counts + reachability)
curl -s "$BASE/api/health" | jq

# Version
curl -s "$BASE/api/version" | jq

# Feature flags ativas
curl -s $AUTH "$BASE/api/features" | jq
```

## Engenharia reversa (Módulo 2)

### Importar `.erx` do ER/Studio

```bash
# Lê o XML e envia em payload JSON
XML=$(jq -Rs . < meu_modelo.erx)

curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/extractions/embarcadero/run" \
  -d "{
    \"system_id\": \"sys-crm-001\",
    \"xml_text\": $XML,
    \"open_ticket\": true
  }" | jq
```

### Round-trip Lakebase

```bash
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/extractions/lakebase/run" \
  -d '{
    "sandbox_id": "sb-lakebase-jdbctest",
    "system_id": "sys-crm-001",
    "schemas": ["public", "comum"],
    "object_kinds": ["TABLE", "VIEW"],
    "open_ticket": true
  }' | jq
```

### Import DDL string

```bash
DDL=$(cat ./create_tables.sql | jq -Rs .)

curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/extractions/ddl/run" \
  -d "{
    \"system_id\": \"sys-crm-001\",
    \"dialect\": \"POSTGRES\",
    \"ddl_text\": $DDL,
    \"open_ticket\": true
  }" | jq
```

## Tickets de Reconciliação

```bash
# Listar tickets abertos
curl -s $AUTH "$BASE/api/tickets?status=OPEN" | jq

# Detalhe de um ticket
curl -s $AUTH "$BASE/api/tickets/tk-abc123" | jq

# Aprovar e aplicar
curl -X POST $AUTH \
  "$BASE/api/tickets/tk-abc123/approve" | jq
curl -X POST $AUTH \
  "$BASE/api/tickets/tk-abc123/apply" | jq

# Rejeitar
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/tickets/tk-abc123/reject" \
  -d '{"reason": "duplicado com tk-xyz789"}'
```

## Entidades & atributos

```bash
# Listar com paginação (PREFERIDO para sistemas grandes)
curl -s $AUTH "$BASE/api/entities/page?page=1&page_size=50&system_id=sys-crm-001" | jq
# {
#   "items": [...],
#   "total": 247,
#   "page": 1,
#   "page_size": 50,
#   "has_more": true
# }

# Detalhe + atributos
curl -s $AUTH "$BASE/api/entities/ent-xyz" | jq
curl -s $AUTH "$BASE/api/entities/ent-xyz/attributes" | jq

# Criar entidade
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/entities" \
  -d '{
    "system_id": "sys-crm-001",
    "schema_name": "comum",
    "technical_name": "cliente",
    "logical_name": "Cliente",
    "domain": "Cadastro",
    "criticality": "HIGH",
    "description_md": "Tabela mestre de clientes."
  }' | jq
```

## Glossário

```bash
# Busca por termo
curl -s $AUTH "$BASE/api/glossary/terms?q=cpf&status=APPROVED" | jq

# Aplicar mapeamento termo → atributo
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/glossary/terms/term-cpf-cliente/mappings" \
  -d '{
    "term_id": "term-cpf-cliente",
    "attribute_id": "attr-xyz",
    "inherit_description": true
  }'
```

## Flags LGPD

```bash
# Aplicar flag em atributo (propaga LGPD automaticamente para a entidade pai)
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/attributes/attr-cpf/flags" \
  -d '{
    "flag_id": "flag-lgpd-pessoal",
    "justification": "Documento de identificação (LGPD art. 5º, II)"
  }'

# Listar todos os atributos com flag LGPD
curl -s $AUTH "$BASE/api/flags?category=LGPD" | jq
```

## Sincronização com Unity Catalog (Módulo 9)

```bash
# Dry-run primeiro
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/sync/run" \
  -d '{
    "system_id": "sys-crm-001",
    "target_catalog": "nuclea_dw",
    "dry_run": true
  }' | jq '.objects'

# Aplicar para valer
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/sync/run" \
  -d '{
    "system_id": "sys-crm-001",
    "target_catalog": "nuclea_dw",
    "dry_run": false
  }' | jq
```

## Versionamento

```bash
# Listar versões de um sistema
curl -s $AUTH "$BASE/api/versions?system_id=sys-crm-001" | jq

# Publicar nova versão
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/versions/publish" \
  -d '{
    "system_id": "sys-crm-001",
    "title": "Q2 2026 — adição domínio Cartões",
    "changelog": "* +12 entidades de cartões\n* ~5 alterações de tipo\n* -2 tabelas legadas",
    "make_active": true
  }' | jq

# Diff entre versões
curl -s $AUTH "$BASE/api/versions/diff?from=ver-q1&to=ver-q2" | jq
```

## Exportação DDL

```bash
# Exportar para PostgreSQL
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/ddl/export" \
  -d '{
    "system_id": "sys-crm-001",
    "dialect": "POSTGRES",
    "include_comments": true,
    "include_drop_if_exists": false
  }' | jq -r '.combined_text'

# Mesmo modelo, dialeto Spark/Delta
curl -X POST $AUTH \
  -H "Content-Type: application/json" \
  "$BASE/api/ddl/export" \
  -d '{
    "system_id": "sys-crm-001",
    "dialect": "SPARKSQL",
    "include_comments": true
  }' | jq -r '.combined_text'
```

## Busca global

```bash
# Busca cross-cutting em 7 dimensões
curl -s $AUTH "$BASE/api/search?q=cliente&limit=20" | jq
# {
#   "q": "cliente",
#   "total": 12,
#   "results": [
#     { "kind": "entity", "id": "ent-...", "label": "...", "path": "..." },
#     { "kind": "term", "id": "term-...", "label": "Cliente", ... },
#     { "kind": "flag", "id": "flag-...", ... }
#   ]
# }
```

## Admin: audit + metrics

```bash
# Audit log paginado (ADMIN)
curl -s $AUTH "$BASE/api/audit/page?page=1&page_size=50&action=APPLY" | jq

# Metrics in-process (ADMIN)
curl -s $AUTH "$BASE/api/metrics" | jq
# {
#   "uptime_seconds": 3245.7,
#   "routes": {
#     "/api/entities/{entity_id}": {
#       "counts": {"2xx": 142, "4xx": 3},
#       "latency_ms": {"count": 145, "p50": 87.2, "p95": 412.1, "max": 1203.5}
#     }
#   }
# }
```

## Correlation IDs & error reporting

Toda response inclui `X-Request-ID`. Em 500s, inclui também `X-Error-ID`.
Use ambos ao reportar bugs:

```bash
curl -i $AUTH "$BASE/api/entities/ent-broken" 2>&1 | grep -E "^x-|^X-"
# x-request-id: a3f8c9d12345
# x-error-id: b7e1f2334455   (apenas em 5xx)
```

Para reportar: `"vi um 500 em GET /api/entities/ent-broken, error_id b7e1f2334455, request_id a3f8c9d12345"`.

## Rate limiting

Endpoints quentes têm rate limit por IP:

| Endpoint | Janela | Limite |
|---|---|---|
| `/api/search` | 60s | 60 req |
| `/api/extractions/*/run` | 5min | 20 req |
| `/api/sync/run` | 5min | 10 req |
| `/api/diagram/*` | 60s | 120 req |

Resposta 429 inclui `Retry-After` (segundos) e `X-RateLimit-Limit`/`X-RateLimit-Window`.
