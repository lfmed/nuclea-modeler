# 20 — Fase 1 · MVP usável (parcial)

**Objetivo:** Entregar valor real ao usuário com M1 (Conexões) + M3 (Documentação) — primeiro deploy + smoke test. M2 (Eng. Reversa) e M9 (Sync UC) ficam para o próximo ciclo após validação visual.
**Status:** 🟡 parcial — aguardando deploy/validação para seguir M2/M9
**Início:** 2026-05-23

---

## Decisão de escopo (checkpoint do plano militar)

O usuário optou por **parar na metade da Fase 1 para deploy intermediário**. Justificativa: ver UI + branding rodando antes de implementar engenharia reversa e sync UC, que dependem de drivers ODBC + Lineage API e podem demorar para validar.

> Ordem revisada: M1 + M3 → deploy → feedback visual + branding → M2 + M9 → segundo deploy.

---

## Etapa 1.M1 — Conexões ✅

### Entregas

- **Backend:** `connections/{models,router}.py` + `systems/{models,router}.py`
  - 7 endpoints: `listSystems`, `getSystem`, `createSystem`, `updateSystem`, `deleteSystem`, `listConnections`, `getConnection`, `createConnection`, `updateConnection`, `deleteConnection`, `testConnection`
  - DAO leve (`core/delta.py`) com `fetch_all`, `fetch_one`, `insert`, `update_by_id`, `delete_by_id`
  - `testConnection` é **placeholder** nesta fase (simula success/latency). Logic real ODBC/REST entra junto com M2.
- **Frontend:** `_sidebar/connections.tsx` (lista), `connections.new.tsx` (form 3-tipos), `connections.$id.tsx` (detalhe + teste + delete)
  - Component-types: ODBC vs REST vs DDL_IMPORT com fields condicionais
  - Credenciais como **chaves do secret** (nunca senhas em texto)
- **Seed:** `004_seed_systems.sql` com 3 sistemas exemplo (DW Principal, Core Bancário, CRM Comercial)

### Decisões

- **Sem upload de DDL no MVP**: tipo `DDL_IMPORT` só persiste a conexão; upload real é integrado em M2.
- **Sem RBAC ainda**: qualquer usuário cria/edita. Locked-down vem no F-Cross #17.
- **`DEFAULT current_timestamp()` não usado**: app preenche `created_at` / `updated_at` no INSERT (Delta sem feature `defaults` habilitada).

---

## Etapa 1.M3 — Documentação ✅

### Entregas

- **Backend:** `entities/{models,router}.py`
  - `EntityIn / EntityOut / EntityListOut` + `AttributeIn / AttributeOut`
  - CRUD para entidades + sub-resource `/{entity_id}/attributes` para colunas
  - DELETE em cascata (atributos primeiro, depois a entidade)
- **Frontend:** `_sidebar/entities.tsx` (lista), `entities.new.tsx` (form), `entities.$id.tsx` (detalhe + inline-add de atributos)
  - Markdown como textarea (Monaco virá na Fase 2)
  - Tags via input separado por vírgula
  - Criticality badge colorido (HIGH=destructive, MEDIUM=amber, LOW=emerald)
  - Atributos inline: tabela + form rápido (nome técnico/lógico, tipo, nullable, PK, descrição)

### Decisões

- **Views/Procedures/Triggers ficam para depois**: a spec lista 4 tipos. Implementei só TABLE no MVP — outros tipos viram após M2 (eng. reversa que pode extraí-los).
- **Relacionamentos não no MVP**: precisam de UI de seleção dual (source attrs / target attrs). Vão na Fase 2 quando der pra integrar com DER (M4).
- **Sem edição da entidade ainda**: por enquanto só criar/excluir. PUT existe no backend, formulário de edição entra junto com expansão dos forms na Fase 2.

---

## Pendências (para a 2ª metade da Fase 1)

- M2 — Engenharia Reversa: extrator ODBC + parser DDL (sqlglot) + reconciliação
- M9 — Sync UC: COMMENT + TAGS via Databricks SDK
- Edit pages para connections e entities
- Upload de DDL para conexões tipo DDL_IMPORT

---

## Aprendizados

- `create_router()` da APX é singleton com prefix global (`/api`). Sub-routers usam `APIRouter(prefix=f"{api_prefix}/connections", tags=[...])` direto.
- A API auto-gerada (`@/lib/api`) só fica disponível em build time (após `apx build`) — durante edição local sem `apx dev` rodando, as importações ficam vermelhas no editor, mas é esperado.
- `dependencies.UserClient` autentica via X-Forwarded-Access-Token (OBO). Em dev local sem header, cai no service principal — `_actor()` tem fallback `"unknown"`.
