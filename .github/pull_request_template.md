## O que muda

<!-- Descrição em 1-3 linhas do que esta PR entrega. -->

## Por que

<!-- Motivação: bug, feature, refactor, performance. Link para spec/ticket se houver. -->

## Como testar

- [ ] Roteiro manual:
- [ ] Tests adicionados/atualizados:
- [ ] `apx dev check` passa (TS + Python)
- [ ] Mudanças de schema: nova migration em `databricks/sql/NNN_*.sql`?

## Checklist

- [ ] Queries com input do usuário usam `delta.param()` (não interpolação)
- [ ] Routes têm `response_model` e `operation_id`
- [ ] Frontend usa `useXSuspense` + `selector()`
- [ ] Sem secrets commitados
- [ ] Sem `console.log`/`print` de debug
