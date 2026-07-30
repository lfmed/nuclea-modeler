# Plano — Feedback do cliente (round 2, jul/2026, sobre v1.0019 deployada)

> Documento vivo. Origem: 2º teste do cliente no app deployado (v1.0019).
> Diferente do round 1 (features faltando), este round tem **bugs concretos**
> reproduzíveis + refinamentos. Diagnóstico feito por leitura do código real
> (file:line abaixo). Cada bloco vira PR + `APP_VERSION` + CHANGELOG + testes.
>
> Artefato de teste do cliente: `streaming.sql` (raiz do repo) — DDL Postgres que
> "não subiu nem apareceu para aprovação". `streaming.DM1`/`novostreamingdm.DM1`
> são os equivalentes Embarcadero (que funcionam).

## Veredito do cliente (round 2)

| Ponto | Status | Natureza |
|---|---|---|
| Arquivamento de sistemas/modelos | ✅ OK | — |
| **Subida via DDL** | ❌ Não OK | **BUG**: `streaming.sql` não gerou ticket |
| **Representação entidades/relacionamentos via DDL** | ❌ Não OK | consequência do acima |
| Importação DM1 | ✅ OK | (validar reimport — ver dedup) |
| Representação relacionamentos DM1 | ✅ OK | — |
| **Autodistribuição/Layout** | ❌ Não OK | revalidar + print do cliente sobre Embarcadero |
| **Alterações/aprovações em lote** | ❌ Não OK | **BUG grave**: staging sobrescreve edição anterior |
| **Manipulação de PKs** | ⏸️ Em espera | cliente ainda vai validar — não mexer agora |
| **Lista de entidades/atributos/índices/componentes** | ❌ Não OK | refinamentos (link DER, editar, busca, nomear rel, dedup) |
| **Flagueamento** | ❌ Não OK | falta flag em tabela/coluna no editor + relacionamentos |

---

## BLOCO 1 — [BUG] Subida via DDL não gera ticket (`streaming.sql`)

**Sintoma:** importar `streaming.sql` → nada sobe, nenhum ticket de aprovação.

**Diagnóstico (código real):**
- Frontend envia **dialeto default `"ANSI"`** (`ui/routes/_sidebar/extractions.tsx:297`,
  `useState("ANSI")`). O backend mapeia `"ANSI"→None` no sqlglot
  (`extractions/service.py:868-872`).
- `streaming.sql` é **Postgres puro**: `SERIAL`, `TEXT`, `DEFAULT CURRENT_TIMESTAMP`,
  `CHECK (...)`, `SET search_path`, `CREATE SCHEMA`. Com dialeto ANSI/None o sqlglot
  não reconhece essas construções → **0 tabelas extraídas**.
- Guard `if not entities:` (`service.py:1051`) → status **FAILED** e ticket
  **não** é criado (`if has_changes and open_ticket_on_diff:` em `service.py:1159`).
- `CREATE SCHEMA` (1º statement, `streaming.sql:4`) é ignorado — só `TABLE/VIEW`
  são processados (`service.py:927`). Se o parse do lote inteiro falhar por causa
  dele + dialeto errado, cai tudo.

**Plano:**
1. **[P0] Default POSTGRES** no seletor de dialeto do frontend (`extractions.tsx:297`)
   — o cliente usa Postgres. Manter o seletor para outros dialetos.
2. **[P0] Auto-detecção de dialeto** no backend quando dialeto vier vazio/ANSI:
   heurística por conteúdo (`SERIAL`/`CURRENT_TIMESTAMP`/`SET search_path`→postgres;
   `CONVERT`/`NVARCHAR`→tsql; etc.). Não confiar só no default do front.
3. **[P0] Parse resiliente por statement**: em vez de um `sqlglot.parse(texto_inteiro)`
   que morre num statement, iterar statement-a-statement (split defensivo) e pular
   os não suportados (`CREATE SCHEMA`, `SET`, `CHECK` isolado) sem abortar o lote.
   Ignorar `CREATE SCHEMA`/`SET` de forma explícita e silenciosa (não é erro).
4. **[P0] Nunca falhar silencioso**: quando 0 objetos, a resposta já tem aviso, mas
   garantir que o front mostre claramente "0 reconhecidos — verifique o dialeto"
   e, na auto-detecção, reprocessar antes de desistir.
5. **[P1]** Suportar `SERIAL`/`BIGSERIAL` (mapear p/ INT/BIGINT + autoincrement note),
   `DEFAULT`, e `CHECK` (ao menos não quebrar; idealmente capturar como constraint).

**Testes (CI + deployado):**
- **CI:** `tests/test_import_ddl_streaming.py` — usar o próprio `streaming.sql` como
  fixture; assert: ≥ N tabelas extraídas, FKs resolvidas, PK composta lida, status
  SUCCESS/PARTIAL, e um ticket seria criado (`has_changes=True`). Casos de dialeto:
  ANSI-auto→postgres, postgres explícito. `pytest.importorskip("sqlglot")`.
- **Deployado:** importar `streaming.sql` no app → aparece ticket com ~40 tabelas +
  relacionamentos; aprovar → DER mostra as entidades e FKs.

---

## BLOCO 2 — [BUG] Staging sobrescreve edição anterior (mesma aprovação por modelo)

**Sintoma:** editar 2 campos/colunas do mesmo modelo → a 2ª edição **apaga** a 1ª
do ticket; "está deixando apenas uma por uma".

**Diagnóstico (código real):**
- `tickets/session.py:116-160` `stage_entity_change()`: dedup por chave
  `schema.tech.op` (`_entity_key`, `:105-106`) que **remove a entry inteira** e faz
  append da nova (`:134-136`) — perde os `field_changes` anteriores. Comentário no
  código confirma que é "última edição vence" (design incorreto p/ o requisito).
- `entities/router.py` (`update_entity` ~659-716, `_stage_attribute_change` ~859-893)
  monta `field_changes` só da edição atual e chama o staging que sobrescreve.

**Plano:**
1. **[P0] MERGE em vez de overwrite** em `stage_entity_change()`: quando já existe
   entry para (schema, tech, op), **mesclar os `field_changes`** (por `field`, última
   intenção do campo vence) e mesclar o `payload`, preservando campos não tocados.
   Idem para atributos (`attribute:NAME.update`, `attribute_add:NAME`).
2. **[P0] Acumular no mesmo ticket** do mesmo modelo+usuário (já usa
   `get_or_create_session_ticket`; garantir que o merge preserve N edições de N
   campos/colunas da entidade num único diff).
3. **[P1] UI — "campos em aprovação"**: no snippet de edição da entidade/atributo,
   mostrar numa **seção separada** os campos que já estão staged (pendentes) — ler do
   ticket OPEN da sessão (o banner de pendências v1.0019 já lê `getSessionStatus`;
   estender para listar os field_changes por entidade/campo).

**Testes (CI + deployado):**
- **CI:** `tests/test_stage_merge.py` — 2 edições de campos diferentes da mesma
  entidade acumulam (assert diff tem ambos os `field_changes`); 2 edições do MESMO
  campo → última vence; edições de 2 atributos diferentes coexistem; apply aplica
  TODOS. (Fecha a lacuna: hoje não há teste de `stage_entity_change`.)
- **Deployado:** editar nome lógico + domínio + marcar 2 colunas → 1 ticket com todas
  as mudanças; aprovar → todas aplicam.

---

## BLOCO 3 — [BUG] Reimportar mesmo arquivo duplica entidades

**Sintoma:** importar o mesmo DDL/DM1 2x cria entidades duplicadas; deveria detectar
nomes iguais e perguntar se substitui/atualiza.

**Diagnóstico (código real):**
- Match no diff é por `(schema_name, technical_name)` (`extractions/diff.py:158-164`).
- **Raiz compartilhada com o Bloco 1**: `search_path` interpretado de forma
  inconsistente → mesma tabela cai em `schema` diferente entre a 1ª e a 2ª importação
  (`service.py:925-937`) → match falha → vira "add" duplicado.
- Apply faz guard por `(system_id, schema_name, technical_name)`
  (`tickets/service.py:700-717`) mas se o schema divergiu, não acha e faz INSERT.
- **Delta NÃO enforça UNIQUE/PK** (confirmado: nenhuma constraint enforced nas
  migrations). Então **a barreira tem que ser na aplicação**, não no banco.

**Plano:**
1. **[P0] Normalizar `schema_name` deterministicamente** no import (corrige a causa
   raiz junto do Bloco 1): sempre resolver o schema da tabela não-qualificada pelo
   `search_path[0]` de forma consistente; documentar o default.
2. **[P0] Dedup por nome no diff/apply**: quando existir entidade com mesmo
   `technical_name` no mesmo `system_id` (mesmo que schema diferente), tratar como
   **"change"/match** em vez de "add" — ou sinalizar como provável duplicata.
3. **[P1] UI "arquivo já importado"**: ao reimportar e detectar N nomes já existentes,
   perguntar **substituir/atualizar vs criar novo** antes de gerar o ticket.
4. **[P1] Guard de idempotência reforçado** no `_apply_op_add`: match case-insensitive
   por nome dentro do sistema antes de INSERT (evita duplicata mesmo com schema
   divergente).

**Testes (CI + deployado):**
- **CI:** `tests/test_import_dedup.py` — importar snapshot 2x → 2ª vira change/no-op,
  não add; entidade com mesmo nome em schema diferente é reconhecida; apply não
  duplica.
- **Deployado:** importar `streaming.sql` 2x → 2ª vez avisa "já existe", não duplica.

---

## BLOCO 4 — Listas: link p/ DER, edição c/ aprovação, busca ampla, nomear relacionamento

**Diagnóstico (código real):**
- (A) Listagens (`entities.index.tsx`, `attributes.index.tsx`, `indexes.index.tsx`,
  `relationships.tsx`) mostram nome do sistema **sem link**. Rota `/diagram`
  (`diagram.tsx:107`) é **estática** (sem `?system=`/param).
- (B) Edição via listagem **não existe** (tabelas read-only; só relationships tem
  DELETE). Backend de staging **já existe** p/ atributo (`entities/router.py:951-993`),
  índice (`indexes_router.py:129-150`) e relacionamento (`relationships/router.py:343-376`).
- (C) Busca global (`search/router.py:20-28`) cobre entity/attribute/term/flag/ticket/
  connection/system — **falta index e relationship**. UI `global-search.tsx` tem
  dropdown/autocomplete pronto.
- (D) Relacionamento **não tem campo nome/label** (`relationships` migration
  `002:160-184`; `RelationshipIn/Out` sem `name`).

**Plano:**
1. **[P0] Rota do DER parametrizável** (`/diagram?system=<id>` ou `/diagrams/$id`) +
   **link do nome do modelo** em todas as 4 listagens.
2. **[P0] Busca ampla**: adicionar `index` e `relationship` ao `SearchKind` e ao
   service; incluir no dropdown do `global-search.tsx`. Busca "dentro do modelo"
   retorna tabelas, colunas (com PK/FK), índices, relacionamentos e flags conforme
   digitado.
3. **[P1] Edição via listagem com aprovação**: modal/sheet de edição inline nas
   listagens de atributos/índices/relacionamentos, reusando as rotas de staging que
   já existem (→ ticket editorial).
4. **[P1] Nomear relacionamento**: migration aditiva `018_relationship_name.sql`
   (`ALTER TABLE relationships ADD COLUMNS (relationship_name STRING)`); campo em
   `RelationshipIn/Out`; hook à mão em `api.ts`; UI para editar (via ticket).

**Testes (CI + deployado):**
- **CI:** busca por índice e relacionamento retorna resultados; update de
  relationship com `relationship_name` persiste; migration 018 aplica (aditiva).
- **Deployado:** clicar no nome do modelo abre o DER; buscar coluna/índice/rel no
  typeahead; editar um atributo da listagem gera ticket; nomear um relacionamento.

---

## BLOCO 5 — Flags em tabela/coluna/PK/relacionamento na edição

**Diagnóstico (código real):**
- Multi-tag **já funciona** (sem UNIQUE em `entity_flags`/`attribute_flags`; batch
  testado). Entidade e atributo têm UI completa em `/entities/$id`.
- **Falta:**
  - **Editor do DER** (`diagram.tsx` `AttributesEditor` ~2196+): tabela tem Nome/Tipo/
    PK/Delete, **sem coluna de Flags** (nem de entidade nem de coluna).
  - **Relacionamentos**: sem `relationship_flags` (tabela/rotas/UI). Nenhum hook em
    `api.ts`.
  - PK é atributo com `is_primary_key` → flag de coluna já cobre "chave"; só falta a UI
    estar acessível onde a chave é editada.

**Plano:**
1. **[P0] Flags no editor do DER**: expor `FlagPicker` (tabela + por coluna) dentro do
   `AttributesEditor`/painel de edição da entidade no diagrama — reusar o componente
   existente. Cobre "tabela, chaves, colunas" na edição.
2. **[P0] Flags em relacionamento**: migration `019_relationship_flags.sql`
   (`relationship_flags` espelhando `attribute_flags`), rotas (single + batch, padrão
   das de atributo, com `response_model`+`operation_id`), hooks à mão em `api.ts`, e
   `FlagPicker` na UI de relacionamentos (coluna + edição). Múltiplas tags do catálogo
   existente.
3. **[P1] Filtro/coluna de flags** na listagem de relacionamentos (consistência com
   entidades/atributos — cruza com Bloco 4).

**Testes (CI + deployado):**
- **CI:** `tests/test_relationship_flags.py` — aplicar/remover N flags a N
  relacionamentos, idempotência, erro parcial (espelha `test_flags_batch.py`);
  migration 019 aplica.
- **Deployado:** no DER, aplicar flag na tabela e numa coluna; na tela de
  relacionamentos, aplicar múltiplas flags num relacionamento.

---

## BLOCO 6 — Autodistribuição/Layout (revalidar)

O cliente marcou como Não OK e mandou o print (`printembarcadero.png`, raiz do repo):
é o **menu "Layout" do ER/Studio (Embarcadero)** com um SELETOR de formatos de
organização automática. O cliente quer poder **escolher o formato de layout** no DER
(hoje só há um auto-layout Dagre fixo). Opções do print:
- **Circular Layout** — nós em círculo.
- **Hierarchical** — hierárquico por dependência (≈ Dagre rankdir TB/LR atual).
- **Orthogonal Layout** — arestas em ângulos retos, grade.
- **Symmetrical Layout** — força/simetria (≈ d3-force).
- **Tree Layout** — árvore.
- **Global / Increment Layout** — global (reorganiza tudo) vs incremental (só novos —
  já temos o incremental do v1.0016).
- Layout Properties (config).

**Plano (Bloco 6, entra depois dos bugs):** adicionar um **seletor de layout** no toolbar
do DER (`diagram.tsx`) com, no mínimo: Hierárquico (Dagre TB/LR — já temos), Árvore,
Circular, Ortogonal e "Força/Simétrico". Implementar cada modo em `components/diagram/
layout.ts` (Dagre cobre hierárquico/árvore/ortogonal via `rankdir`+`ranker`; circular e
força podem ser calculados à mão ou com `d3-force`/`elkjs`). Manter "Auto-organizar
tudo" (global) e o incremental (v1.0016). Persistir a escolha por diagrama.

**Testes:** CI valida as funções puras de layout (cada modo devolve posições sem
sobreposição p/ um grafo pequeno); no app deployado, trocar entre formatos reorganiza o
DER e "encaixa na tela".

---

## Ordem de execução sugerida

P0 primeiro (bugs que travam o cliente), depois refinamentos:

1. **v1.0020 — [BUG] DDL streaming + dedup de reimport** (Blocos 1 e 3 — raiz comum: schema/search_path).
2. **v1.0021 — [BUG] staging acumula (não sobrescreve) + "campos em aprovação"** (Bloco 2).
3. **v1.0022 — Flags no editor + flags de relacionamento** (Bloco 5).
4. **v1.0023 — Listas: link DER + busca ampla + nomear relacionamento + edição via listagem** (Bloco 4).
5. **Bloco 6 (layout)** — após receber o print do cliente.

> Bugs (1,3,2) têm prioridade sobre features (5,4). PKs (round 1) ficam em espera a
> pedido do cliente.
