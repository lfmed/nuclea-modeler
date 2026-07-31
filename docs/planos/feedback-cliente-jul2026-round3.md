# Plano — Feedback do cliente (round 3, jul/2026, sobre v1.0027 deployada)

> Diagnóstico por leitura do código real. Dois temas: (A) DESCRIÇÕES de objetos
> não aparecem/editam/exportam; (B) ESTADO de tela não persiste ao navegar.

## Tema A — Descrições de objetos (tabelas, schemas, colunas, índices)

**Achado central:** o modelo de dados **já tem** os campos de descrição em todos os
níveis (`description_md`, `native_comment`, `business_rule`). O problema é que o
frontend **não os carrega/exibe/edita/exporta** em vários pontos. É "iceberg
invertido": o dado existe no catálogo, mas não chega à UI.

Campos existentes (confirmados):
- entities: `description_md`, `native_comment`
- attributes: `description_md`, `native_comment`, `business_rule`
- entity_indexes: `description_md`, `native_comment`
- entity_partitioning: `description_md`
- schemas: `description_md`
- relationships: `description`, `relationship_name` (v1.0023)

### Gaps e plano

**A1 [P0] DER não mostra descrição de tabela nem de coluna.**
Causa: `backend/diagram/router.py` — os SELECT de entities (~80-87) e attributes
(~102-111) **não trazem** `description_md`/`native_comment`; e `DiagramEntity`/
`DiagramAttribute` (`backend/diagram/models.py`) não têm esses campos.
- Adicionar os campos ao SELECT e aos models.
- No `entity-node.tsx`: mostrar a descrição da tabela (ex.: subtítulo/tooltip no
  header) e a da coluna (tooltip no atributo, ou linha secundária). Não poluir o
  canvas — usar tooltip/hover + truncamento.

**A2 [P0] Editar descrição no MODAL do DER.**
`EditEntityDialog` (diagram.tsx) já edita `description_md` da entidade. Falta:
- editar descrição **por coluna** no `AttributesEditor` (campo de descrição por linha,
  staged via ticket como os outros campos de atributo).

**A3 [P1] Editar descrição na TELA do objeto.**
`entities.$id.tsx` mostra `description_md` da entidade **read-only**. Tornar editável
(via ticket, como os demais campos). Descrição por atributo também editável ali
(a tabela de atributos já virou editável no v1.0019 — adicionar campo descrição).
Índices/schemas: expor edição de descrição onde já há UI (indexes-section; tela de
schema se houver).

**A4 [P1] Import DDL: comentários.**
O parser (`extractions/service.py`) já captura `COMMENT` de tabela/coluna em
`native_comment` (trabalho #2). Validar que chega ao catálogo no apply e passa a
aparecer no DER (depende de A1). `COMMENT ON SCHEMA`/índice: capturar se vier (P2).

**A5 [P1] Export — incluir descrição.**
- CSV de entidades/atributos/índices (`*.index.tsx`): adicionar coluna(s) de
  descrição (`description_md` e/ou `native_comment`) aos headers e às linhas.
- Export DDL (`backend/ddl/generators.py`): já gera `COMMENT ON` para Oracle/PG;
  estender p/ os demais dialetos quando aplicável (P2).

### Testes (A)
CI: diagram router traz description nos models (teste de mapeamento); CSV inclui a
coluna. Deployado: descrição aparece no DER (tooltip), edita no modal/tela, exporta no CSV.

---

## Tema B — Persistência de estado de tela (não zerar ao voltar)

**Achado central:** todo o estado de seleção/filtro é `useState` local (reseta ao
desmontar). Só o DER lê `?system=` da URL **na entrada**, mas o dropdown de sistema
**não atualiza a URL** — então ao sair e voltar (sem query) zera. Padrão de solução
já existe no projeto: TanStack Router `validateSearch` + `useSearch` + `navigate`
(o v1.0023 começou isso no DER) e `localStorage` (usado em `sync.index.tsx`).

### Plano

**B1 [P0] DER: persistir sistema selecionado.**
`diagram.tsx` — no `onChange` do dropdown de sistema, além de `setSystemId`, chamar
`navigate({ search: { system: novo } })`. Assim a URL reflete a seleção e ao voltar
(back/link/sessão) mantém. Inicializar `systemId` de `Route.useSearch()`.

**B2 [P1] DER: persistir filtros/layout.**
Estender `validateSearch` para `schema`, `diagram`, `filter`, `domain`, `direction`,
`layoutMode`, `expanded`; espelhar cada setter na URL. (Bônus: URLs compartilháveis.)

**B3 [P1] Listagens (entidades/atributos/índices/relacionamentos): persistir sistema+filtros.**
Mesmo padrão: `validateSearch` + espelhar filtros na URL (q, system, tipo,
criticidade, flag, sort, página). Ao voltar, restaura.

**Alternativa/complemento:** `sessionStorage` (padrão de `sync.index.tsx`) para o
"último sistema visto" global — assim ao abrir o DER sem query, cai no último sistema
usado em vez do primeiro da lista. Combinar: URL (compartilhável) + sessionStorage
(default sensato). **Decisão recomendada:** URL como fonte primária; sessionStorage só
para o "último sistema" default.

### Testes (B)
Deployado: selecionar sistema X no DER → navegar pra Entidades → voltar ao DER →
continua em X (URL reflete). Idem filtros. Nas listagens: filtrar, sair, voltar → mantém.

---

## Ordem de execução sugerida (PRs)

1. **v1.0028 — Descrições no DER (carregar + exibir + editar coluna no modal)** — A1+A2 (P0).
2. **v1.0029 — Persistência de estado (DER + listagens via URL search params)** — B1+B2+B3 (P0/P1).
3. **v1.0030 — Descrição: editar na tela do objeto + export CSV/DDL** — A3+A5 (P1).
4. **A4/P2 (comentários DDL schema/índice) e polish** — conforme demanda.

> Os dois temas são independentes (backend diagram + UI vs. roteamento) — podem ir
> em paralelo em worktrees separados. Descrições tocam diagram router/models +
> entity-node + listagens; persistência toca as rotas/telas. Sobreposição pequena
> em diagram.tsx (modal de descrição vs. dropdown de sistema) — resolvo na integração.
