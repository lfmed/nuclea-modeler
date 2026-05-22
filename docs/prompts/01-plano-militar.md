# 01 — Plano Militar

**Data:** 2026-05-22
**Status:** ✅ aprovado pelo product owner

## Objetivo

Entregar o Nuclea Modeler em três fases incrementais, priorizando valor utilizável o quanto antes (Fase 1 = MVP navegável e deployado) e mantendo governança, branding e rastreabilidade desde o dia 1.

## Princípios

1. **Tudo no Databricks.** Nada roda só local — Delta no UC, Secrets para credenciais, Jobs para work assíncrono.
2. **Trunk-based + commits pequenos.** Cada item entregue vira commit referenciado no prompt registry.
3. **UX é requisito, não verniz.** Branding Núclea, PT-BR, busca global, auto-save, estados de loading.
4. **Auditável.** `audit_log` cobre toda mutação relevante; mudanças em flags LGPD têm justificativa obrigatória.
5. **Versionado.** Modelo de dados (`model_versions`) é imutável após publicação; sync UC só ocorre em versão ativa.

## Fases

### Fase 0 — Bootstrap (tasks #1-#4) — *em curso*

| # | Entrega | Saída |
|---|---------|-------|
| 1 | Repo `lfmed/nuclea-modeler` privado | URL GitHub, estrutura `docs/` populada |
| 2 | Scaffold APX com branding Núclea | App rodando local em `apx dev` |
| 3 | Schema Delta no UC com 18 tabelas | DDL aplicado em `stable_classic_pg4xe1_catalog.data_catalog_app` |
| 4 | `app.yaml` + secrets scope + warehouse | Manifesto pronto para deploy |

### Fase 1 — MVP usável (tasks #5-#9)

| # | Módulo | Critério de aceite |
|---|--------|-------------------|
| 5 | M1 Conexões | Teste de conexão ODBC/REST/DDL funciona e persiste em `connections` |
| 6 | M2 Engenharia Reversa | Extrai schema de banco de referência, gera relatório de extração |
| 7 | M3 Documentação | Forms ricos preenchidos persistem em `entities`/`attributes`/etc. |
| 8 | M9 Sincronização UC | Publicação de versão dispara sync, log em `sync_log` |
| 9 | Deploy + smoke | App publicada em `*.databricksapps.com`, smoke OK |

### Fase 2 — Governança (tasks #10-#13)

| # | Módulo | Critério de aceite |
|---|--------|-------------------|
| 10 | M5 Flagueamento | Flag LGPD em coluna propaga sinal visual à tabela, justificativa obrigatória |
| 11 | M6 Dicionário | Termo aprovado vinculado a atributos em 2+ sistemas, herança de descrição |
| 12 | M8 Versionamento | Snapshot imutável + diff visual + export PDF/CSV |
| 13 | M10 Export DDL | DDL multi-dialect com comentários, válido sintaticamente |

### Fase 3 — Visualização (tasks #14-#15)

| # | Módulo | Critério de aceite |
|---|--------|-------------------|
| 14 | M7 Linhagem | Grafo upstream/downstream + complemento via UC Lineage API |
| 15 | M4 DER | Canvas interativo, layout persistido, export PNG/SVG/JSON |

### Cross-cutting (tasks #16-#17) — *contínuo*

- **#16** Prompt Registry vivo + ADRs por decisão crítica
- **#17** RBAC, auditoria, logs estruturados, busca global

## Riscos identificados

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Branding oficial Núclea inacessível via web scraping | Médio | Paleta placeholder, ajuste após validação visual com o cliente |
| Permissão `CREATE CATALOG` indisponível no workspace svc | Baixo | Já decidido: usar schema dentro de catalog existente |
| Drivers ODBC para SGBDs proprietários (Oracle, SQL Server) | Alto | Validar disponibilidade dentro do compute do Databricks App; fallback via import DDL |
| Sync UC bidirecional gera conflitos | Médio | Detecção de conflito + opção de override/ignorar (spec 4.9.3) |
| Volume do catálogo (≥10k objetos) | Médio | Paginação server-side, indexação Delta por sistema/schema, busca em SQL Warehouse |

## Próximos passos imediatos

1. Criar repo `lfmed/nuclea-modeler` privado (gh repo create)
2. Primeiro commit com docs/ + README + .gitignore
3. Push, depois `apx init` na raiz
4. Aplicar branding placeholder
5. Provisionar UC schema + 18 tabelas
