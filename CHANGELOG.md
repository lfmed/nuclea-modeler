# Changelog

Convenção: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Changed
- **"Sistema atual" compartilhado entre as telas de modelagem (v1.0033)** — ao
  escolher um sistema em qualquer tela (DER, Entidades, Atributos, Índices,
  Relacionamentos), a seleção passa a **acompanhar o usuário** ao abrir as demais —
  só muda quando ele trocar em alguma delas. Antes, o DER lembrava o último sistema
  (sessionStorage), mas as listas só liam o `?system=` da URL e **zeravam para
  "Todos os sistemas"** quando abertas pela sidebar. Agora todas inicializam com
  `?system=` → último sistema compartilhado (`getLastSystemId`) → 1º da lista, e
  todas gravam a escolha (`saveLastSystemId`) — o estado é bidirecional entre as
  telas. (Navegador e Canvas Exploratório não têm filtro de sistema único —
  mostram todos por natureza — então não entram nessa regra.)

### Fixed 🐛
- **Edições sequenciais na mesma coluna não se perdem mais (v1.0032)** — correção
  de code-review sobre o v1.0030. `list_attributes` devolvia a linha CRUA do
  catálogo para entities existentes (sem overlay das edições pendentes), então a UI
  reconstruía o payload de update com dados desatualizados; como o staging faz merge
  "última intenção vence" por field-key, editar a descrição e depois togglar a PK da
  MESMA coluna no mesmo ticket **apagava a descrição** (e vice-versa). Fix: novo
  `_overlay_existing_attrs` espelha o estado staged sobre o catálogo (análogo ao
  `_overlay_entity_out` de entity-level), com teste. Além disso:
  (a) **descrição de coluna agora pode ser limpa** — a UI envia texto cru (`""`
  limpa) em vez de `null`, que o apply de atributo filtrava;
  (b) payloads de update de atributo ficaram **consistentes** entre DER e tela do
  objeto (todos carregam logical_name/default_value/description_md/business_rule),
  eliminando perda cruzada de edições;
  (c) a seção "Campos em aprovação" atualiza na hora (invalida `getSessionState`);
  (d) o guardrail de lote limpa a seleção ao trocar de filtro (evitava o aviso
  escapar quando a seleção saía da lista visível).
- **Guardrail de aprovação em lote — mesmo autor + mesmo sistema (v1.0031)** —
  feedback do cliente: aprovar mudanças em lote só deveria valer para tickets do
  mesmo schema e do mesmo usuário. Como um ticket já é por **(autor, sistema)**, o
  guardrail valida autor + sistema direto pelos campos do ticket (não precisa
  varrer o schema das entidades do diff). Decisão de produto: **avisar, não
  bloquear** — quando a seleção mistura autores e/ou sistemas diferentes, a barra
  de ações em lote mostra um aviso âmbar e a ação pede confirmação antes de
  prosseguir; o usuário ainda pode aprovar um lote heterogêneo se quiser. Só
  frontend (`tickets.index.tsx`), sem mudança de backend nem de contrato.
- **Editar descrições em todo lugar + exportar no CSV (v1.0030)** — fecha o tema
  "descrições" do feedback do cliente (round 3, itens A2/A3/A5). O v1.0029 só
  **exibia** descrição no DER; agora dá pra **editar** e **exportar**:
  - **Editar por coluna no modal do DER (A2)** — o editor de atributos do diagrama
    ganhou uma coluna **Descrição** editável inline (clique → textarea → Salvar;
    Ctrl/Cmd+Enter salva, Esc cancela). Staged via ticket como os demais campos.
  - **Editar na tela do objeto (A3)** — o card "Descrição de negócio" da entidade
    virou **editável** (botão Editar → textarea → Salvar) e cada coluna da tabela
    de atributos tem descrição **editável inline** (mesma célula do DER). Tudo via
    fluxo editorial → ticket.
  - **Export com descritivos (A5)** — os CSVs de **Entidades** (Descrição +
    Comentário nativo), **Atributos** (Descrição + Regra de negócio) e **Índices**
    (Descrição) agora carregam os campos de descrição. Os endpoints paginados
    passaram a trazer esses campos no SELECT (mapeamento posicional documentado).
  - **Backend (gotcha corrigido):** o allowlist de apply de `attribute:NAME.update`
    **não incluía** `description_md`/`business_rule` — a descrição staged era
    **descartada** no apply e nunca chegava ao catálogo. Adicionados ao allowlist
    (update + create). Célula sempre reenvia o payload COMPLETO do atributo porque
    o staging faz merge por field-key com "última intenção vence" (parcial apagaria
    PK/tipo). O `PkToggle` também passou a reenviar descrição/regra pelo mesmo motivo.
- **Descrições de tabela/coluna no DER (v1.0029)** — as descrições (`description_md`),
  comentários nativos (`native_comment`) e regra de negócio (`business_rule`) já
  existiam no catálogo mas **não chegavam ao diagrama**. Agora o endpoint do DER carrega
  esses campos (entities e attributes) e o `EntityNode` os exibe via **tooltip no hover**
  (ícone info no header da tabela; hover na coluna) — canvas continua limpo. Base para
  editar descrição por coluna no modal e exportar no CSV (próximos incrementos).
  Mapeamento posicional coberto por teste (`test_diagram_router_descriptions.py`) para
  não repetir o bug de índice do v1.0025.
- **Estado das telas persiste na navegação (v1.0028)** — antes, ao sair do DER (ou
  das listagens) e voltar, o modelo/filtros zeravam (tudo era `useState` local). Agora
  o sistema selecionado e os filtros/ordenação/página vivem na **URL** (search params
  do TanStack Router) — a seleção sobrevive a sair-e-voltar, ao back/forward do
  navegador e vira **link compartilhável**. Além disso, o **último sistema** usado é
  lembrado (sessionStorage) e vira o default ao abrir uma tela sem `?system=`. Cobre
  DER + Entidades + Atributos + Índices + Relacionamentos.

### Fixed 🐛
- **Linhas de relacionamento se perdiam na navegação do DER (v1.0027)** — as arestas
  (FK) ficavam desconectadas das tabelas, com setas apontando pro vazio, ao dar
  pan/zoom/filtrar. Causa: o nó do DER tinha handles do React Flow **sem id** (um
  `target` à esquerda, um `source` à direita); sem id, o RF não ancorava a linha de
  forma estável quando as posições relativas mudavam. Fix: 4 handles com id
  (`source-left/right`, `target-left/right`) no `EntityNode` e edges com
  `sourceHandle="source-right"` + `targetHandle="target-left"` (Esq→Dir, sem contornar
  o nó). As linhas passam a tocar sempre a borda real da tabela.
- **Todas as colunas apareciam como PK após aprovação (v1.0026)** — bug sistêmico de
  coerção de booleano. A Databricks SQL Statement Execution API devolve as células do
  `data_array` como **string**, então colunas BOOLEAN voltam como `"true"`/`"false"`.
  O código fazia `bool(r[n])` direto e, como `bool("false")` é `True` em Python
  (string não-vazia é truthy), **todo booleano lido de query virava `True`** — daí
  todas as colunas viravam PK no DER (só após aprovação, quando o dado passa a vir da
  query e não do diff JSON). Corrigido com o helper `delta.as_bool()` aplicado a
  **todos** os campos booleanos lidos de resultado de query (is_primary_key,
  is_nullable, is_unique, is_active, is_default, is_shared, flags, etc.). Teste de
  regressão `test_delta_as_bool.py` fixa `as_bool("false") is False`.
- **Tela de Relacionamentos dava "Erro ao carregar" (500) (v1.0025)** — regressão da
  v1.0023: ao adicionar `relationship_name` em `_REL_COLS`, os índices posicionais de
  `list_relationships` não foram atualizados, fazendo `system_name`/`updated_at` lerem
  colunas erradas (`GET /api/relationships` estourava `datetime_from_date_parsing` →
  500). Índices corrigidos, `relationship_name` agora aparece na listagem, e um teste
  de regressão (`test_relationships_list_mapping.py`) fixa o contrato posicional
  linha→modelo (que o CI não pegava por ser só índice, não tipo estático).

### Added
- **Seletor de formato de layout no DER (v1.0024)** — inspirado no menu "Layout" do
  ER/Studio (Embarcadero), o diagrama ganhou um dropdown para escolher a
  autodistribuição: **Hierárquico**, **Árvore**, **Circular**, **Ortogonal** e
  **Força/Simétrico**. Cada modo é aplicado ao clicar "Auto-layout"/"Auto-organizar
  tudo" (que continua salvando as posições). Sem dependências novas — algoritmos
  circular e de força implementados à mão em TS; os demais via Dagre.
- **Listas navegáveis, busca ampla e nomear relacionamento (v1.0023)** — o nome do
  modelo/sistema nas listagens (entidades, atributos, índices, relacionamentos) vira
  **link para o DER** daquele sistema (rota `/diagram?system=<id>`). A **busca global**
  (Cmd/Ctrl+K) passa a cobrir também **índices** e **relacionamentos** (além de
  entidades, atributos, termos, flags…). Relacionamentos ganham um campo de **nome/
  rótulo** editável (`relationship_name`, migration 019). Edição de objetos das
  listagens segue o fluxo de aprovação por ticket já existente.
- **Flags no editor do DER + flags de relacionamento (v1.0022)** — no editor de
  atributos do diagrama agora dá para aplicar flags **na tabela** (entidade) e **em
  cada coluna**, reusando o multi-select do catálogo existente (a chave/PK é uma
  coluna, então já é coberta). Relacionamentos passam a ter flags também: nova tabela
  `relationship_flags` (migration 018), rotas single + batch (`applyRelationshipFlag`,
  `batchApplyRelationshipFlags`, remove/list correspondentes) e coluna de Flags na
  tela de relacionamentos. Múltiplas tags por objeto.

### Fixed 🐛
- **Edições do mesmo modelo se sobrescreviam na aprovação (v1.0021)** — ao editar
  2+ campos/colunas do mesmo modelo antes de aprovar, a 2ª edição **apagava** a 1ª do
  ticket (o staging deduplicava por `schema.tech.op` substituindo a entry inteira).
  Agora o staging **acumula (merge) os `field_changes`** no mesmo ticket: campos
  diferentes coexistem, o mesmo campo editado 2x mantém a última intenção, e o apply
  aplica todas as mudanças. Novo painel **"Campos em aprovação"** na tela da entidade
  mostra, em seção separada, o que já está pendente de aprovação.
- **Import DDL Postgres não subia (streaming.sql) (v1.0020)** — DDL Postgres puro
  (`SERIAL`, `SET search_path`, `CHECK`, `DEFAULT CURRENT_TIMESTAMP`, PK composta)
  extraía **0 objetos** e **não gerava ticket** de aprovação, porque o dialeto
  default do front era `ANSI`. Correções: dialeto default do seletor de import passa
  a **POSTGRES**; o backend **auto-detecta o dialeto** pelo conteúdo do DDL quando
  vier vazio/ANSI; e o parser ficou **resiliente** — `CREATE SCHEMA`/`SET` são
  ignorados sem abortar o lote, e um statement problemático não derruba a extração
  inteira. Agora o `streaming.sql` sobe ~40 tabelas + FKs + PKs e gera ticket.
- **Reimportar o mesmo arquivo duplicava entidades (v1.0020)** — a resolução
  inconsistente de `schema_name` (via `search_path`) fazia a mesma tabela cair em
  schema diferente na 2ª importação → virava "add" duplicado (Delta não enforça
  UNIQUE). Agora o schema não-qualificado é resolvido de forma **determinística** e
  o apply tem **guard de dedup por nome** (case-insensitive, dentro do sistema): a
  reimportação vira no-op em vez de duplicar.

### Changed
- **Manipulação de PK unificada e intuitiva (v1.0019)** — a edição de chave
  primária agora usa **o mesmo controle rotulado** (checkbox + ícone chave + "PK")
  na tabela de atributos da entidade e no editor do DER (antes: read-only numa tela,
  checkbox "nu" noutra). **PK composta é numerada** (PK1, PK2… por `ordinal_position`)
  em todas as visões, com **reordenação por drag**. Avisos não bloqueantes quando a
  coluna marcada como PK é nullable ou também é FK. Banner de **mudanças pendentes**
  na tela da entidade (a edição de PK segue o fluxo editorial → ticket). Backend:
  `ordinal_position` entrou na allowlist do apply de `attribute:*.update` para a
  reordenação sobreviver à aplicação do ticket.

### Added
- **Flagueamento em lote de entidades e atributos (v1.0018)** — aplicar/remover
  **várias flags a vários alvos numa única ação**, matando os ~250 cliques do
  fluxo antigo (um modal por flag/atributo). O `FlagPicker` virou **multi-select**
  (justificativa por flag quando exigida); as listas de entidades e a tabela de
  atributos ganharam **seleção múltipla + barra flutuante** ("Aplicar flags"/
  "Remover flags"), no mesmo padrão do batch de tickets. Backend: `POST
  /entities/batch/flags` (`batchApplyEntityFlags`), `POST /entities/batch/flags/remove`
  (`batchRemoveEntityFlags`) e os equivalentes de atributo — idempotentes, com erro
  parcial por item e propagação LGPD atributo→entidade preservada.
- **Listas de entidades, atributos e índices (v1.0017)** — a lista de entidades
  passou a **consumir a paginação** do backend (antes carregava tudo) com busca,
  filtros (sistema, tipo, criticidade, flag), ordenação por coluna, coluna de
  flags e export CSV. Novas telas globais **Atributos** (`/attributes`) e
  **Índices** (`/indexes`) com filtros próprios (PK, tipo de índice, UNIQUE, flag)
  e export. Backend: rotas `GET /attributes/page` (`listAttributesPaginated`) e
  `GET /indexes/page` (`listIndexesPaginated`); `GET /entities/page` estendido com
  filtros/ordenação (whitelist anti-injeção) e coluna de flags.

### Fixed 🐛
- **Autodistribuição do layout do DER (v1.0016)** — entidades novas importadas
  (via DDL/DM1) num diagrama já organizado deixavam de empilhar invisíveis na
  origem `(0,0)`. A causa era o sentinel `{x:0,y:0}` + detecção binária de
  "tem layout"; agora distingue-se **"sem posição"** de **"(0,0)"** e roda-se um
  **layout incremental** que posiciona só os nós novos ao lado do bloco já
  organizado (preservando os arrastados manualmente), com reenquadre automático.
  Novo botão **"Auto-organizar tudo"** reroda o layout do diagrama inteiro (com
  confirmação) e **salva** as posições.

### Added
- **Paridade do import DDL com o DM1 (v1.0015)** — o parser DDL agora extrai
  `CREATE [UNIQUE] INDEX` (colunas ordenadas, `INCLUDE`, `WHERE` parcial),
  resolve FKs em **2 passes** (FK declarada antes da tabela-alvo passa a
  funcionar), infere `parent_columns` a partir da(s) PK(s) da tabela referenciada
  quando `REFERENCES` vem sem coluna, lê PK composta table-level e respeita
  `SET search_path` com **múltiplos schemas**. FK/índice apontando para tabela
  ausente vira **warning** (status `PARTIAL`) em vez de descarte silencioso —
  igual ao fluxo Embarcadero (.DM1).

### Fixed 🐛
- **Import DDL sem objetos falha explicitamente (#8)** — DDL sem nenhum
  `CREATE TABLE/VIEW` reconhecido devolvia `SUCCESS` com 0 objetos (falha
  silenciosa). Agora devolve `FAILED` com mensagem acionável ("confirme o
  dialeto"), **antes** do diff — evitando que um snapshot vazio marcasse todo o
  catálogo como removido (ticket destrutivo).
- **Import "sucesso" sem ticket agora é explicado** — quando uma extração não
  reconhece objetos (`0 encontrados` — dialeto errado ou sem CREATE TABLE) ou
  não detecta mudanças vs o catálogo (`+0 novos`), o painel de resultado mostra
  um aviso âmbar explícito ("Nenhum objeto reconhecido…" / "Nenhuma mudança
  detectada — nada a aprovar") em vez de um "sucesso" verde ambíguo.
- **Apply de ticket auto-curável (atributos)** — se um apply criava a entity mas
  falhava nos atributos por erro transitório de warehouse, a entity ficava
  **presa sem colunas** (o skip por idempotência impedia o conserto num re-apply).
  Agora `_apply_op_add` reconcilia: quando a entity já existe, insere apenas os
  atributos que faltam; e cada atributo é inserido de forma resiliente (uma falha
  pontual não aborta os demais e é curada num re-apply via "Reabrir").
- **Import de DDL não extraía coluna nenhuma** — o parser lia `stmt.expressions`
  (sempre vazio no sqlglot) em vez de `stmt.this.expressions`. CREATE TABLE via
  DDL gerava entidades sem atributos no diagrama. Corrigido em
  `extractions/service.py:run_ddl_import()`, com teste de regressão.
- **Relacionamentos (FKs) perdidos no import** — Embarcadero (.DM1) e DDL agora
  extraem FKs estruturalmente e as persistem na tabela `relationships` via
  entries sintéticas `__relationship__` no diff, resolvidas por nome no apply do
  ticket (depois das entities materializadas). Antes eram apenas warnings.
- **Alteração manual "não refletia" após aprovação** — `approve` só mudava o
  status; a materialização exigia um `apply` separado (restrito a Architect/Admin),
  então um Steward que aprovava deixava o ticket preso e a mudança nunca chegava
  ao catálogo. Novo `POST /tickets/{id}/approve-apply` aprova e materializa numa
  única ação.

### Added
- **Materializar modelo em Delta (#9)** — o sync (M9) ganha a flag `materialize`:
  quando a tabela destino não existe no catálogo escolhido pelo cliente, ela é
  **criada** (Delta, tipos mapeados p/ Spark, com COMMENTs) e a entidade é
  marcada como materializada (`is_materialized` / `materialized_at` /
  `materialized_catalog` — migration 015). Sem a flag, tabela inexistente segue
  `SKIPPED`. Exige grant `CREATE TABLE` ao SP no catálogo destino.
- **Anexar documentos a tabelas e modelos (#7)** — upload/list/download/delete de
  documentos (≤ 25 MB) numa entidade, diagrama ou sistema. Bytes num Volume
  gerenciado do Unity Catalog (migration 016), metadados em Delta. UI:
  `AttachmentsPanel` na tabela e no modelo. Exige `WRITE VOLUME` ao SP.
- **DDL captura comentários (#2)** — `COMMENT` inline de coluna/tabela e
  `COMMENT ON TABLE/COLUMN` no import DDL passam a ser gravados em
  `native_comment` (antes eram descartados).
- **Exportar objeto único do DER como imagem (#4)** — botão "PNG objeto" exporta
  só a tabela selecionada no canvas (além do PNG do diagrama inteiro).
- **Diagrama sempre visível (#5)** — `fitView` imperativo ao trocar
  schema/diagrama/filtro + botão "Encaixar na tela".
- **Aprovação/aplicação em lote de tickets** — `POST /tickets/batch`
  (`approve` / `reject` / `apply` / `approve_and_apply`) processa N tickets sem
  abortar o lote por erro de um item.
- **Extração de FK no DDL** — constraints inline (`col REFERENCES …`) e
  table-level (`CONSTRAINT … FOREIGN KEY … REFERENCES …`), incluindo FKs
  cross-schema.
- **Log de falha de import estruturado** — o resultado e o detalhe da extração
  passam a separar **problemas** (perda de dados: entity/atributo sem nome
  ignorado, FK órfã, tipo desconhecido, erro de parse) de **avisos
  informativos**, formatados em markdown no `summary_md`. O `error_summary`
  persistido deixa de ser truncado em 500 chars (até 4000). Import de Embarcadero
  com perda de dados agora marca status **PARTIAL** (antes sempre SUCCESS),
  sinalizando que o log deve ser revisado.
- **UI: botão "Aprovar e aplicar"** no detalhe do ticket (resolve OPEN numa ação
  só, para quem tem papel de applier) e **seleção múltipla + ações em lote** na
  lista de tickets (aprovar/aplicar/aprovar-e-aplicar/rejeitar N de uma vez).
- **UI: checklist de pré-requisitos** nos formulários de import (DDL e
  Embarcadero) — mostra o que falta (sistema-alvo, DDL/arquivo, dialeto) antes de
  liberar a importação.
- **UI: criar/editar diagramas no canvas (M6, fatia 4b+4c)** — botão "Novo
  diagrama" cria um recorte no schema selecionado; "Editar tabelas" abre um
  diálogo pra escolher quais tabelas entram no diagrama; "Salvar layout" passa a
  gravar as posições NO diagrama quando há um selecionado (e carrega-as ao abrir).
  Auto-layout com mais espaçamento (nodesep/ranksep) para melhor legibilidade.
- **UI: seletor de schema + diagrama no canvas (M6, fatia 4a)** — o DER ganha
  dropdowns de schema e de diagrama; selecionar um schema restringe o canvas às
  suas tabelas, e selecionar um diagrama mostra só a membership daquele recorte
  (read-only nesta fatia). Re-aplica auto-layout ao trocar.
- **UI: Navegador em árvore (M6, fatia 3)** — nova tela `/explorer` com árvore
  Sistema → Schema → Diagramas/Tabelas, com lazy-load por nó e contagens.
  Clicar numa tabela abre seus atributos; clicar num diagrama abre o DER.
- **Segregação por schema + múltiplos diagramas (M6, fatia 1+2)** — schema vira
  entidade de 1ª classe (tabela `schemas`) e cada schema pode ter vários
  diagramas (tabelas `diagrams` + `diagram_entities`). Migration `014` é
  **aditiva e não-destrutiva** (não toca em `entities` — relação derivada por
  JOIN na chave natural `(system_id, schema_name)`; validada contra a warehouse:
  zero perda de dados, idempotente). Backend CRUD: `/api/schemas` e
  `/api/diagrams` (+ membership e layout), com RBAC nas mutações. Sidebar em
  árvore e multi-diagrama no canvas vêm nas próximas fatias.

### Security 🔒
- **RBAC em sistemas** — `createSystem`/`updateSystem` exigem
  DATA_ARCHITECT/DATA_STEWARD/ADMIN; `deleteSystem` exige DATA_ARCHITECT/ADMIN e
  bloqueia exclusão de sistema que ainda tem entidades. Antes qualquer usuário
  autenticado podia renomear/excluir sistemas via API.

### Changed
- **Engenharia reversa do Embarcadero migrou de `.erx` (XML) para `.DM1` (CSV nativo)** —
  formato `.DM1` é o export padrão do ER/Studio na Núclea. Novo parser em
  `extractions/embarcadero.py:parse_dm1()` extrai entities, atributos (com
  tipo derivado de `DatatypeId` + Length/Scale), PKs e FKs (agora persistidas,
  ver Fixed). UI: `accept=".dm1,.DM1"`, cap de upload 50 MB.
- Dependência `defusedxml` removida — sem parser XML em ingestion, vetor XXE
  elimina-se por construção. Tests de segurança XXE substituídos por tests
  de robustez do parser DM1.

## [0.2.1] — 2026-05-28

**Security patch release.** Atualização recomendada imediatamente — corrige
vulnerabilidade XXE no parser de upload `.erx`.

### Security 🔒
- **XXE / XML External Entity (CWE-20, bandit B314) — corrigido** — parser `.erx`
  do Embarcadero (`extractions/embarcadero.py`) agora usa
  `defusedxml.ElementTree.fromstring` ao invés de `xml.etree.ElementTree.fromstring`,
  proibindo entities externas, billion-laughs DoS e DTD recursion.
  Severity Medium, Confidence High — detectado pelo bandit hard-gate em CI.
  Payload malicioso poderia ler arquivos do servidor via `file://`, exaurir memória,
  ou bater o processo. **Recomendação:** atualizar para v0.2.1 imediatamente se
  o app aceita uploads de `.erx`.
- Tests novos em `tests/test_embarcadero_security.py` validam rejeição de 3 payloads
  maliciosos (XXE, billion laughs, DTD com entities) + sanity test.

### Added
- 11 tests novos para `audit/service.py` (list_audit + count_audit filtros/clamps/offset)
- Tests de migrations runner agora passam (mock state usa enum `StatementState`)
- Dependency `defusedxml>=0.7.1`

### Changed
- **Bandit é hard-gate** no CI (removido `continue-on-error`). B608 (low-confidence SQL)
  adicionado a skips com justificativa em `pyproject.toml` (vide ADR-0003).
- **OpenAPI snapshot drift check** é hard-gate condicional — stub é tolerado, mismatch real bloqueia.
- **Node.js 24** forçado em todos os 4 workflows via `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  (preempt da deprecação Junho/2026).

### Removed
- `.github/workflows/codeql.yml` renomeado para `.disabled` — repo privado requer
  GitHub Advanced Security (pago). Reativar via `git mv` quando GHAS for habilitado.

## [0.2.0] — 2026-05-28

Sprint de produção (`production-hardening`). App deixa de ser MVP — todas as
capacidades necessárias para uso pelo cliente estão em produção.

### Added
- **Migrations runner** (`core/migrations.py`) — auto-apply de `databricks/sql/*.sql` no startup com tracking SHA-256 em `schema_migrations`. CLI: `python -m nuclea_modeler.backend.core.migrations`.
- **Security middleware** (`core/security.py`) — `SecurityHeadersMiddleware` (X-Frame DENY, Referrer-Policy, HSTS condicional) e `RateLimitMiddleware` sliding window por (IP, rota).
- **Request correlation** (`core/logging.py`) — `RequestIdMiddleware` gera/honra `X-Request-ID`, propaga via contextvar, reusado pelo audit middleware.
- **JSON logging opt-in** — `NUCLEA_LOG_JSON=true` ativa `JsonFormatter` single-line para log aggregators.
- **Health probes separadas** — `/api/livez` (sem deps) e `/api/readyz` (warehouse probe, cache 5s).
- **Exception handler global** (`core/exceptions.py`) — captura uncaught, gera `error_id`, retorna 500 sanitizado com `X-Error-ID` header, loga ERROR estruturado com traceback. Mensagem do exception nunca vaza.
- **Metrics in-process** (`core/metrics.py`) — `MetricsMiddleware` agrega counts por (route_pattern, status_class) + latency ring p50/p95/max. `/api/metrics` admin-only.
- **Feature flags env-driven** (`core/features.py`) — 8 flags declaradas, `NUCLEA_FEATURE_*`. `/api/features` endpoint + hook `useFeatures` no frontend.
- **CORS middleware opt-in** — `NUCLEA_CORS_ALLOW_ORIGINS` env (CSV), default same-origin no-op.
- **ODBC + REST testers reais** (`connections/testers.py`) — `pyodbc.connect()` + `httpx.GET`, secrets via Databricks Secrets API. ImportError gracioso.
- **Paginação** — `GET /api/entities/page` e `GET /api/audit/page` com `PaginatedX` model.
- **404 customizada** — `components/apx/not-found.tsx` com layout Núclea, 3 CTAs.
- **Welcome tour** — `components/apx/welcome-tour.tsx`, 5 passos guiados, persistência localStorage. Refazer via Help.
- **EmptyState component** — `components/apx/empty-state.tsx` reutilizável; 10 rotas refatoradas.
- **Admin metrics dashboard** — `/admin/metrics` (ADMIN-only) com cards de resumo + tabela de tráfego, refresh 10s.
- **Bundle splitting** — `vite.config.ts` manualChunks (monaco/diagram/tanstack/react/ui/misc). Monaco também via React.lazy em SqlEditor.
- **OpenAPI customizado** — `/docs` e `/redoc` com 15 tags 1-por-módulo, version, contact, license.
- **A11y pass** — skip-to-content link, role landmarks, aria-labels, focus-visible com outline, `prefers-reduced-motion`.
- **CI/CD** — `.github/workflows/ci.yml` (Python + Frontend + Secret scan), `e2e.yml` opt-in via label, `dependabot.yml`.
- **E2E Playwright** — `tests/e2e/smoke.spec.ts` com 5 testes (home, 404, tour, Cmd+K, skip-link).
- **Backup CLI** — `scripts/backup.py` copia 25 tabelas para Volume UC em Parquet.
- **CONTRIBUTING.md** — onboarding completo para time Núclea + parceiros.
- **ADR-0003** — `docs/adr/0003-production-hardening.md` documentando 8 decisões do sprint.

### Changed
- **SQL parametrizado 100%** — eliminadas 100+ ocorrências de `_q()` / f-string com input do usuário. Helpers `delta.param()` + `delta.run_params()`. `_quote_lit` agora tz-aware (normaliza datetime para UTC).
- **/api/health** — probe barata (`SELECT 1`) + counts cacheadas TTL 30s.
- **README** — tabela de endpoints operacionais + runbook (app não sobe, performance, restauração, secrets, error_id) + env vars + feature flags.

### Fixed
- Pre-push secret scanning passa em Sprint 0 (TruffleHog modo diff para PR, full para push).
- `ruff` config em pyproject.toml com `per-file-ignores` para `tests/` (E402, F401 — pytest.importorskip pattern).
- Vite build precede `tsc` no CI (TanStack Router gera `routeTree.gen.ts` no build).
- Test recursion: `httpx.Client` capturado antes de patch para evitar recursão infinita.

### Security
- Defense in depth: rate limit + security headers + sanitização de exception response + parametrização universal de SQL + ODBC/REST timeouts duros.
- `X-Error-ID` para correlation sem leak de stack.
- `.claude/` agent state gitignored.

## [0.1.0] — 2026-05-23

MVP funcional. Spec 100% + extras.

### Added
- 10 módulos da spec funcional implementados (M1-M10).
- Tickets de Reconciliação (cross-cutting).
- Lakebase Sandbox para validação round-trip.
- Code Objects (Views, Procedures, Triggers, Sequences) com Monaco editor.
- Audit log com middleware Starlette.
- Busca global cross-cutting (Cmd+K) em 7 dimensões.
- Importer Embarcadero ER/Studio `.erx`.
- Home page rica + Centro de Ajuda in-app.
- Stack: FastAPI + React 19 + TanStack Router + shadcn/ui + Tailwind 4 + Delta Lake + Unity Catalog.
- Deploy: Databricks Apps (svc @ fevm-stable-classic-pg4xe1).
- Persistência: 100% Delta/UC, sem Postgres operacional.
- Lakebase: usado apenas como sandbox de validação.

[Unreleased]: https://github.com/lfmed/nuclea-modeler/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/lfmed/nuclea-modeler/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/lfmed/nuclea-modeler/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lfmed/nuclea-modeler/releases/tag/v0.1.0
