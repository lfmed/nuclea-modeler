# 10 — Fase 0 · Bootstrap

**Objetivo:** Pôr os trilhos para o desenvolvimento — repo, scaffold APX, schema Delta no UC, manifesto do Databricks App.
**Status:** 🟡 em curso
**Início:** 2026-05-22

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

## Aprendizados desta fase

(preencher conforme avança)
