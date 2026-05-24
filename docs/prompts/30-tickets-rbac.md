# 30 — Tickets de Reconciliação + RBAC

**Objetivo:** Adicionar fluxo de aprovação humana para todas as alterações no catálogo. Reconciliação não escreve automaticamente — gera ticket.
**Status:** ✅ entregue · branch `feature/tickets-rbac`
**Data:** 2026-05-24

## Origem do requisito

> "sempre que houve uma diferença capturada na reconciliaçao, deve ser abert um ticket tratado na propria aplicacao para alguem aceitar e tratar essa nove versao"
> — usuário, durante a Fase 1

## Tabelas Delta novas

- `user_roles` — RBAC por email (DATA_ARCHITECT, DATA_STEWARD, DATA_ENGINEER, CDE, ADMIN)
- `reconciliation_tickets` — diff + status (OPEN → APPROVED → APPLIED | REJECTED)

## Fluxo

```
[eng. reversa / ddl import / lakebase roundtrip / manual]
            │
            ▼
       OPEN ──── reject ──► REJECTED  (qualquer architect/steward/admin)
        │
        │ approve (architect/steward/admin)
        ▼
     APPROVED ──── apply (architect/admin) ──► APPLIED
                                                  │
                                                  ▼
                              [escreve entities/attributes no catálogo]
```

## Endpoints

| Método | Path | Descrição | Permissão |
|--------|------|-----------|-----------|
| GET | `/api/rbac/me` | Papéis do usuário corrente | qualquer |
| GET | `/api/rbac` | Lista todos os papéis | ADMIN |
| POST | `/api/rbac` | Conceder papel | ADMIN |
| DELETE | `/api/rbac/{id}` | Revogar papel (soft) | ADMIN |
| GET | `/api/tickets` | Inbox de tickets (filtro por status) | qualquer |
| GET | `/api/tickets/{id}` | Detalhe + diff | qualquer |
| POST | `/api/tickets` | Abrir ticket manual | qualquer |
| POST | `/api/tickets/{id}/approve` | Aprovar | ARCHITECT/STEWARD/ADMIN |
| POST | `/api/tickets/{id}/reject` | Rejeitar com motivo | ARCHITECT/STEWARD/ADMIN |
| POST | `/api/tickets/{id}/apply` | Aplicar diff no catálogo | ARCHITECT/ADMIN |

## UI

- `/tickets` — inbox com tabs (OPEN, APPROVED, APPLIED, REJECTED, ALL) e contadores de diff
- `/tickets/:id` — detalhe com diff visual + ações condicionais (botões aparecem só se o usuário tem o papel necessário) + timeline
- `/admin/roles` — gestão de papéis (apenas ADMIN vê)

## Bootstrap de papéis

Inserido via SQL na criação do schema:
- `leandro.medeiros@databricks.com` → DATA_ARCHITECT + ADMIN
- `svc_app_novo` (service principal) → ADMIN

## Validação

- Apply é idempotente em `add` ops (checa existência de entidade pela tupla system_id+schema+technical_name)
- `change` aplica apenas campos whitelisted: logical_name, description_md, native_comment, row_count_approx, domain
- `remove` ops geram aviso (não auto-aplica — soft-delete não implementado nesta fase)
