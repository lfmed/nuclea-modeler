# 10 — Fase 0 · Bootstrap

**Objetivo:** Pôr os trilhos para o desenvolvimento — repo, scaffold APX, schema Delta no UC, manifesto do Databricks App.
**Status:** ✅ concluída
**Início:** 2026-05-22 · **Fim:** 2026-05-23

---

## Etapa 0.1 — Repositório privado

### Decisões

- Nome: `nuclea-modeler` (casa com a pasta local)
- Visibilidade: **privada** (requisito do cliente)
- Conta GitHub: `lfmed` (pessoal)

### Comandos executados

```bash
git init -b main
git config user.name "lfmed"
git config user.email "leandro.medeiros@gmail.com"
mkdir -p docs/spec docs/prompts docs/adr
mv especificacao_funcional_databricks_app_catalogo_dados.md docs/spec/
# README, .gitignore, prompt registry inicial criados manualmente
gh repo create lfmed/nuclea-modeler --private --source=. --description "Núclea data catalog & modeling Databricks App"
git add .
git commit -m "chore: bootstrap repo + docs/prompts + spec"
git push -u origin main
```

### Artefatos

- `README.md`, `.gitignore`
- `docs/spec/especificacao_funcional_databricks_app_catalogo_dados.md`
- `docs/prompts/{README,00-spec,01-plano-militar,10-fase0-bootstrap}.md`
- `docs/adr/0001-stack-apx.md`

---

## Etapa 0.2 — Scaffold APX

### Decisões

- Framework: **APX 0.3.8** (FastAPI + React via Vite/Bun)
- App name interno: `nuclea_modeler`
- Branding: paleta placeholder (magenta/roxo + amarelo) — refinar após primeira validação visual

### Comandos previstos

```bash
apx init  # interativo — confirmar nome
apx dev   # smoke local
```

### Próximas decisões a tomar

- Aplicar tema Tailwind/shadcn customizado com cores Núclea
- Adicionar fonte (Inter ou similar) consistente com identidade financeira

---

## Etapa 0.3 — Provisionar schema Delta no UC

### Decisões

- Namespace: `stable_classic_pg4xe1_catalog.data_catalog_app`
- 18 tabelas conforme spec seção 6
- Todas com colunas de auditoria: `created_at`, `created_by`, `updated_at`, `updated_by`
- Chaves substitutas em `STRING` (UUID v7) para portabilidade

### Comandos previstos

```bash
databricks sql query --profile svc --warehouse-id b8e52268d9828bdd --file databricks/sql/001_create_schema.sql
databricks sql query --profile svc --warehouse-id b8e52268d9828bdd --file databricks/sql/002_create_tables.sql
```

---

## Etapa 0.4 — `app.yaml` + recursos

### Decisões

- Compute principal: SQL Warehouse `Serverless Starter` (já disponível, Small)
- Secrets scope: `nuclea-modeler-secrets`
- Permissões UC declaradas: `USE CATALOG` em `stable_classic_pg4xe1_catalog`, `MODIFY` no schema `data_catalog_app`

### Comandos previstos

```bash
databricks secrets create-scope nuclea-modeler-secrets --profile svc
# preencher segredos conforme conexões cadastradas no runtime
```

---

## Etapa 0.3 — Schema Delta no UC ✅

### O que foi feito

- Schema `stable_classic_pg4xe1_catalog.data_catalog_app` criado via Statement Execution API
- 18 tabelas Delta criadas (todas com `delta.enableChangeDataFeed = true`, exceto `audit_log` que é `appendOnly`)
- Seed das **21 flags do sistema** (9 LGPD + 8 USE + 4 QUALITY) com `MERGE` idempotente

### Decisão técnica

- `DEFAULT current_timestamp()` removido na aplicação (Delta requer feature `defaults` por tabela). App preenche timestamps no INSERT.
- `DEFAULT true/false` em booleanos removido por mesma razão.
- PKs como `STRING` (UUID v7 gerado em código) — não há autoincrement em Delta.
- FKs lógicas, não materializadas em UC (UC suporta `FOREIGN KEY` como informativo, mas não impõe).

### Comandos

```bash
# Criou schema
databricks api post /api/2.0/sql/statements --profile svc --json '{"warehouse_id":"b8e52268d9828bdd","statement":"CREATE SCHEMA IF NOT EXISTS ..."}'

# Aplicou 18 DDLs via /tmp/apply_ddl.py (split por tabela)
python3 /tmp/apply_ddl.py
# → 18/18 ✅

# Validou
SHOW TABLES IN stable_classic_pg4xe1_catalog.data_catalog_app  -- retornou 18 linhas
SELECT category, COUNT(*) FROM ...flags GROUP BY category      -- LGPD=9, USE=8, QUALITY=4
```

---

## Etapa 0.4 — App resources + Secrets ✅

### O que foi feito

- Secret scope `nuclea-modeler` criado
- `databricks.yml` populado com:
  - Variables: `catalog`, `schema`, `warehouse_id`, `secrets_scope`
  - Recursos da app: SQL Warehouse (`CAN_USE`) e Secret scope (`READ`)
  - Env vars NUCLEA_* + `DATABRICKS_SQL_WAREHOUSE_ID` (consumido pelo SqlDependency do APX)
  - Targets `dev` (default) e `prod`
- `NucleaSettings` (Pydantic) em `backend/core/_nuclea_config.py` lendo as envs
- Endpoint `/api/health` que conta tabelas Delta e flags — primeiro smoke da conectividade

### Comandos

```bash
databricks secrets create-scope nuclea-modeler --profile svc
```

---

## Aprendizados desta fase

- **Sandbox bloqueia npm/pypi públicos**: rede corporativa Databricks bloqueia `registry.npmjs.org` e `pypi.org`. `databricks.jfrog.io` está acessível mas pede auth. Solução: scaffold local sem install + install/build server-side no deploy via DAB. Aliás, alinhado com o pedido "não rode nada local".
- **`apx init --no-addons` gerou UI completa**: o flag `--no-addons` afinal cria backend+UI mínimos (a interactive prompt seleciona addons OPCIONAIS como sidebar, lakebase, sql, cursor). Suficiente para nosso caso.
- **Identidade Núclea inacessível**: site oficial (Akamai 403), archive.org bloqueado, brand manual privado. Decisão: paleta placeholder magenta/violeta + amarelo, validar com cliente após primeiro deploy.
- **Delta DEFAULT requer feature**: `DEFAULT current_timestamp()` não funciona out-of-the-box; precisa `delta.feature.allowColumnDefaults`. Optei por preencher no app para evitar overhead de habilitar feature em todas as tabelas agora.
- **Lakebase tem papel específico**: NÃO é o backing store da app. É um sandbox de validação onde o usuário pode aplicar o DDL gerado e fazer round-trip. App = 100% Delta.

