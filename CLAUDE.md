# apx Project

Full-stack Databricks App built with apx (React + Vite frontend, FastAPI backend).

## Do's and Don'ts
- OpenAPI client auto-regenerates on code changes when dev servers are running - don't manually regenerate.
- Prefer running apx related commands via MCP server if it's available.
- Use the apx MCP `search_registry_components` and `add_component` tools to find and add shadcn/ui components.
- When using the API calls on the frontend, use error boundaries to handle errors.
- Run `apx dev check` command (via CLI or MCP) to check for errors in the project code after making changes.
- If agent has access to native browser tool, use it to verify changes on the frontend. If such tool is not present or is not working, use playwright MCP to automate browser actions (e.g. screenshots, clicks, etc.).
- Avoid unnecessary restarts of the development servers
- **Databricks SDK:** Use the apx MCP `docs` tool to search Databricks SDK documentation instead of guessing or hallucinating API signatures.

## Documentação & manutenibilidade (INSTRUÇÃO PERMANENTE)

Este app é entregue a um cliente e evoluído em sessões separadas, por humanos e
por agentes de IA distintos. **Toda melhoria deve deixar o código muito bem
documentado para quem mantém depois.** Cumprir em todo PR:

- **Docstring de módulo** explicando propósito + fluxo; docstring em funções não-triviais.
- **Comentar o "porquê"** (decisões, gotchas, ordem que importa) — não o "o quê" óbvio.
  Ex.: "guard antes do diff para não marcar todo o catálogo como removido".
- **Migrations** com cabeçalho explicando o que muda e por quê (padrão `databricks/sql/001–016`).
- **Testes** como documentação viva do comportamento esperado (o CI é o loop de validação).
- **Decisões arquiteturais** relevantes vão para este `CLAUDE.md` (para outros
  agentes/humanos) e para a memória do agente quando aplicável.

### Versionamento visível (contador de build)
- `src/nuclea_modeler/ui/lib/build-info.ts` expõe `APP_VERSION` (exibido no rodapé
  da sidebar junto da data/hora do build). **Incremente `APP_VERSION` a cada
  melhoria entregue:** `1.0001 → 1.0002 → 1.0003…`. Serve para comparar o que está
  deployado no cliente vs. a última versão.

### Realidades deste repo que agentes precisam saber (corrigem o boilerplate acima)
- **NUNCA rode nada localmente (REGRA DURA).** npm **e** pypi estão bloqueados nesta
  máquina — `bun install`, `uv sync`, `uv pip install`, `apx dev start`, `pytest`,
  `ruff`, `tsc` e `vite build` **vão falhar** (connection refused). Não tente instalar
  deps nem executar/servir o app localmente. O máximo permitido é `python -m py_compile`
  para checar sintaxe. **Toda validação de teste é feita (1) pelo CI do GitHub
  (`.github/workflows/ci.yml`: ruff+bandit+pytest 3.11/3.12 + build + tsc) e (2)
  manualmente no app DEPLOYADO no Databricks Apps.** Escreva testes junto do código para
  o CI exercê-los; o teste funcional real acontece no app deployado após o merge.
  Ignore qualquer linha do boilerplate acima que mande rodar `apx dev check`, `bun`,
  `uv`, etc. localmente.
- **BOOLEANOS de query vêm como STRING (GOTCHA).** A Databricks SQL Statement
  Execution API devolve TODAS as células do `data_array` como string — colunas
  BOOLEAN voltam como `"true"`/`"false"`. **NUNCA** use `bool(r[n])` direto (em Python
  `bool("false")` é `True`!). Use `delta.as_bool(r[n])` para todo campo booleano lido
  de resultado de query. (Causou o bug "todas as colunas viram PK" — v1.0026 **e
  regrediu no export de DDL em v1.0041**, ver abaixo.)
- **ARRAYS de query vêm como STRING JSON (GOTCHA, v1.0042).** Pela mesma razão, uma
  coluna `ARRAY<STRING>` volta do `data_array` como **string JSON** (`'["a","b"]'`,
  ou `'[]'`). **NUNCA** faça `list(r[n])` direto — `list('["a"]')` itera a STRING e
  devolve uma lista de CARACTERES (`['[','"','a',...]`), corrompendo o array em
  silêncio. Use `delta.as_str_list(r[n])` para toda coluna ARRAY. Bugs que isso
  causou no app DEPLOYADO v1.0041 (achados ao validar o Round 5): (1) o export de DDL
  não emitia NENHUMA foreign key (pt 11) porque `source_attr_ids`/`target_attr_ids`
  viravam chars e não casavam com `attribute_id`; (2) o `bool()` cru em
  `ddl/service.py::_attr_row_to_dict` marcava TODA coluna como PK/NOT NULL no DDL.
  Fix v1.0042: helper `delta.as_str_list` + aplicado em ~10 sites de read (ddl,
  relationships, diagram, versions, glossary, entities, indexes, code_objects) +
  `as_bool` no ddl/service. **LIÇÃO:** teste que exercita o round-trip STRING→parse
  (não só listas Python) — `test_ddl_service_coercion.py`, `test_delta_as_str_list.py`.
  Foi por testar só com listas prontas que o CI ficou verde com a prod quebrada.
- **React Flow v12 Handles com IDs explícitos (v1.0027).** O DER usa `@xyflow/react`
  v12.10.2 + `@dagrejs/dagre`. Antes, o EntityNode tinha handles SEM id, causando
  ambiguidade — quando posições relativas mudavam (pan/zoom/refetch), as arestas
  "flutuavam" e apontavam pro vazio. FIX: renderize 4 handles (source-left, source-right,
  target-left, target-right) com IDs explícitos; em relationshipToEdge(), especifique
  sourceHandle="source-right" e targetHandle="target-left". Isso garante que as linhas
  sempre tocam uma borda real da tabela, independente da navegação. Veja entity-node.tsx
  linhas 265+ e relationshipToEdge() no diagram.tsx ~2040-2075.
- **DER: remontar o ReactFlow ao TROCAR de sistema/recorte (v1.0051, GOTCHA React
  Flow).** Ao trocar o `systemId`/`diagramId`, TODO o conjunto de nós é substituído
  (ids novos). O React Flow, mantido montado, às vezes NÃO re-media os nós novos →
  eles ficam `visibility:hidden` e, sem medição, NENHUMA aresta é desenhada
  ("as tabelas e as linhas somem"). FIX: `key={`rf-${systemId}-${diagramId}`}` no
  `<ReactFlow>` força remontagem (medição fresca + fitView) na troca de contexto —
  filtro/expandir NÃO entram na key (mudança incremental que o RF já mede sozinho).
  Além disso, o fit passou a esperar `useNodesInitialized()` (antes era um
  setTimeout(60ms) que disparava ANTES da medição). Reproduzido/validado ao vivo:
  DOM tinha 4 nós + handles mas 0 arestas e nós hidden só ao trocar de sistema.
- **DER: staging na sessão precisa invalidar o indicador de pendência (v1.0051).**
  Criar/editar/remover relacionamento OU entidade no DER é STAGED numa sessão/ticket
  (não aplicado na hora). Os callbacks (`onCreated` do CreateRelationshipDialog,
  `quickAdd`/`deleteEntity` onSuccess, path de FK do QuickAdd) DEVEM invalidar
  `["getSessionStatus", systemId]` E `["listTickets"]` — senão o banner "alteração
  pendente" e o aviso de ticket aberto não aparecem até um reload (o usuário via a
  linha nova mas "nenhuma sinalização de pendência").
- **Diff de RELACIONAMENTO no ticket carrega rótulos legíveis (v1.0051).** O payload
  do relacionamento (`__relationship__`) só tinha ids → o ticket mostrava
  `__relationship__.rel-xxx`, ilegível. `relationships/router` agora grava
  `source_label`/`target_label`/`source_columns`/`target_columns` no payload
  (helper `_enrich_rel_payload_labels`, best-effort) em create/update/delete; a tela
  de aprovação (`tickets.$id.tsx::relationshipSummary`) renderiza "pai → filho
  (colunas)". Teste: `tests/test_relationship_payload_labels.py`.
- **Auto-layout força/circular: anti-sobreposição robusta (v1.0051).** O circular
  calculava o raio só por N (ignorando a largura 280px / altura expandida do nó) e o
  força tinha repulsão fraca (K_REP=50000, MIN_DIST=100 < largura do nó) → tabelas
  encavalavam. FIX em `components/diagram/layout.ts`: raio circular usa o mínimo
  geométrico (corda ≥ maior dimensão + folga); força com K_REP=250000/MIN_DIST=260;
  e `resolveOverlaps` maxIter 10→**400** (para assim que converge) como rede de
  segurança. **Medido ao vivo:** a força nasce muito aglomerada e o empurra-pares
  precisa de ~174 iterações p/ convergir no pior caso (60 deixava 27 pares, 150
  deixava 12, 300 zerava) — por isso 400 (v1.0052, ajuste do v1.0051). Circular já
  zerava com o raio geométrico. **CAUSA RAIZ da força (v1.0053):** a altura por
  atributo estimada era 24px mas a REAL é ~29-30px (medido via `offsetHeight`,
  imune ao zoom) → `NODE_HEIGHT_EXPANDED` SUBESTIMAVA a altura e o resolvedor
  deixava sobreposição VERTICAL real (~40px) mesmo "convergindo". **FIX DEFINITIVO
  (v1.0054):** `nodeHeight`/`nodeWidth` agora PREFEREM a dimensão REAL medida pelo
  React Flow (`node.measured.height/width`), disponível quando o usuário dispara o
  Auto-layout (nós já na tela), caindo na estimativa (`80 + attrs*30`) só quando não
  há medida (layout incremental de import). Nenhuma estimativa cobre TODAS as linhas
  extras que o EntityNode renderiza (índices, descrição — um nó de 5 atributos
  media como 7 linhas); usar a medida real faz o de-overlap operar no espaço REAL →
  zero sobreposição garantida. Lição: quando a medição do React Flow existir,
  USE-a no layout em vez de estimar o tamanho do nó.
- **Dialeto DDL: vocabulário CANÔNICO único (GOTCHA, v1.0037).** O import de DDL usa
  `sqlglot`; o backend só entende as chaves canônicas `ANSI | POSTGRES | TSQL | PLSQL |
  MYSQL | SPARKSQL | DB2` (ver `extractions/service.py::_resolve_sqlglot_dialect`). Toda
  tela que manda dialeto (wizard, extractions, export) DEVE usar EXATAMENTE esses valores.
  O `new-system-wizard.tsx` mandava `POSTGRESQL/MSSQL/ORACLE/DATABRICKS` → o sqlglot recebia
  nome desconhecido, parseava 0 objetos e o import falhava (round 5, pt 12). O helper agora
  normaliza aliases e cai em `None` (auto) se não reconhecer — mas mantenha o vocabulário
  alinhado. Teste: `tests/test_dialect_resolution.py`.
- **DM1 (ER/Studio) cria índice de APOIO da FK (GOTCHA, v1.0039).** No `.DM1`, cada
  FK vira (1) um relacionamento na seção `ForeignKey` E (2) um índice de apoio na seção
  `Indexes` com `KeyType="F"`. O parser (`extractions/embarcadero.py`) pula `KeyType` em
  `("P","F")` — senão a FK "sumia" e reaparecia como um índice (IDX) no modelo (round 5,
  pt 14). Se um `.DM1` do cliente ainda mostrar FK virando índice, verifique o `KeyType`
  real das linhas de `Indexes`. Teste: `tests/test_embarcadero_security.py`.
- **FK: emissão no DDL + transporte com rolename (v1.0040).** O export de DDL agora
  emite `ALTER TABLE <filho> ADD CONSTRAINT … FOREIGN KEY … REFERENCES <pai> …` após os
  CREATE (ver `ddl/generators.render_foreign_keys` + `ddl/service.fetch_relationships`);
  Spark/Databricks = FK informativa (sem ON DELETE/UPDATE). Convenção do modelo:
  **source = PAI** (PK em `source_attr_ids`), **target = FILHO** (FK em `target_attr_ids`).
  O "transportar chaves" (criar colunas FK na filha) é orquestrado NO FRONTEND
  (`CreateRelationshipDialog`): cria os atributos-FK via `createAttribute` → pega os ids →
  cria o relacionamento — tudo no mesmo ticket (o apply ordena atributos antes de
  relacionamentos). Rolename (`id`→`id_<pai>`) só em colisão, editável (`transportedFkName`).
- **Versões × Tickets são conceitos SEPARADOS (v1.0041).** Versão = snapshot imutável
  publicado manualmente (`model_versions.snapshot_json`); Ticket = aprovação editorial de
  mudanças no modelo vivo. Não há vínculo populado entre eles (`reconciliation_tickets.
  target_version_id` existe mas nunca é gravado) — a tela de Versões linka para Tickets em
  vez de fingir um FK. Diff aceita `to="current"` (`compute_diff_vs_current` → `build_snapshot`
  ao vivo) para "o que mudou desde a versão X" sem publicar. Restore já é não-destrutivo
  (cria DRAFT). Export = download do `snapshot_json` (frontend, sem backend novo).
- **`ui/lib/api.ts` é ESCRITO À MÃO** — não há codegen no deploy (cliente sem npm/apx).
  Rota nova no backend ⇒ escreva o hook à mão em `api.ts` (padrão `use<Op>` /
  `use<Op>Suspense` / `selector()`). Ignore a linha do boilerplate que diz "auto-regenera".
- **UI só chega ao cliente após merge no `main`**, que dispara `build-dist.yml`
  (rebuild + commit de `src/nuclea_modeler/__dist__`, o bundle prebuilt servido em prod).
- **Deps sensíveis a versão são PINADAS em `==` (v1.0049).** `sqlglot==30.17.0` e
  `openpyxl==3.1.5` (em `pyproject.toml` E `requirements.txt` — `check_deps_sync`
  exige spec idêntico). O parse de DDL depende do AST interno do sqlglot, que muda
  entre releases: com `>=`, CI e deploy resolviam versões diferentes e o
  `COMMENT ON TABLE` passou no CI e falhou em produção (round 6). Para promover:
  suba a versão nos DOIS arquivos, rode o CI e revalide o import no app deployado.
- **INSERT em LOTE no apply de ticket (v1.0049).** `delta.insert_many()` junta N
  linhas num único `INSERT ... VALUES (…),(…),…` — cada INSERT é um round-trip
  completo pela Statement Execution API; aplicar ~10 entidades com dezenas de
  colunas cada estourava o timeout de 300s. `_apply_op_add` usa o lote e cai num
  fallback resiliente linha-a-linha se o lote falhar (isola a linha ruim, preserva
  a auto-cura de re-apply). Contrato do `insert_many`: todas as linhas com o MESMO
  conjunto de colunas (a 1ª define a ordem; cada linha é projetada por `.get`).
- **Dry-run / preview do import DDL (v1.0049).** `POST /extractions/ddl/preview`
  (`previewDDLImport`) = `run_ddl_import(..., dry_run=True)`: faz todo o parse+diff
  mas NÃO abre ticket NEM persiste (read-only) e devolve `ExtractionResult.preview`
  (lista por objeto do que mudaria). Hook `usePreviewDDLImport` + botão "Prever
  (dry-run)" no DDLTab de `extractions.tsx`. O `ddl.tsx` é o EXPORT (M10) — não
  confundir com o import.
- **Smoke test pós-deploy: `scripts/smoke_deployed.py` (v1.0049).** Roda LOCAL logo
  após o deploy manual (`python3 scripts/smoke_deployed.py "$TOKEN"`); cria um
  sistema descartável `SMOKE-<ts>`, exercita import DDL ponta-a-ponta e confere
  COMMENT ON→descrição / FK / CHECK / DEFAULT no app JÁ DEPLOYADO — pega justamente
  o gap "CI verde, prod quebrada" (drift de versão). Apaga o sistema no fim.
  Workflow opt-in `smoke-deployed.yml` (`workflow_dispatch`, pula sem o secret
  `SMOKE_DATABRICKS_TOKEN`).
- **DEFAULT no import de DDL COLADO (v1.0050).** O parse de DDL colado NUNCA
  extraía o `DEFAULT` da coluna (só o caminho Lakebase preenchia `default_value`);
  o valor sumia no import e o fix de aspas do export (v1.0048) nunca disparava para
  DDL colado. Fix: o loop de constraints em `extractions/service.py` agora captura
  `DefaultColumnConstraint` (checado por `type(kind).__name__`, robusto a versão do
  sqlglot) e guarda o `.sql()` da expressão. **Achado pelo próprio smoke test
  pós-deploy no 1º uso** — a prova de que o item vale (o Ck do v1.0048 estava verde
  e a prod dropava o DEFAULT). Teste que exercita o round-trip DDL→parse→export:
  `test_import_ddl_desc_check.py::test_default_*`.
- **Import CSV: match de tabela tolerante a SCHEMA (v1.0055).** O round-trip de
  metadados (`entities/roundtrip.py::parse_and_stage_csv`) casava as linhas por
  `schema.table` ESTRITO. O cliente exporta as descrições com schema `dbo` (default
  do Embarcadero), mas o DDL importado põe as tabelas em `social` (`SET search_path
  TO social`) → NENHUMA linha casava, tudo virava `unknown_tables` e o import "não
  carregava nada" (a mensagem ainda dizia enganosamente "Nenhuma mudança detectada").
  **Reproduzido ao vivo com os arquivos reais** (`ncleamodelerevoluo/programa_social.sql`
  + `descricoes_databricks_preenchido.csv`, via `scripts/reproduce_csv_import.py`):
  CSV `dbo` → 10 unknown_tables; mesmo CSV com schema `social` → 10 tabelas/40 colunas/
  19 flags. Fix: match em 3 níveis — (1) `schema.table` exato; (2) case-insensitive
  (DB2 grava `SOCIAL.PESSOA`); (3) fallback por NOME de tabela ÚNICO no modelo (nome
  ambíguo entre schemas fica desconhecido — não dá pra adivinhar). O diff usa o
  schema/nome REAIS do catálogo e chaveia por `entity_id`. Mensagem honesta quando há
  `unknown_tables` (`_unknown_note`). Export agora nomeia o arquivo com o NOME do
  sistema (`system_slug`, transliterando acentos), não o id. **Endurecido no Isaac
  Review:** (a) o match de COLUNA também é case-insensitive — senão uma coluna
  existente com caixa diferente viraria `attribute_add` e DUPLICARIA no apply; o
  update usa o nome REAL da coluna do catálogo; (b) o fallback por nome só dispara
  quando o schema do CSV NEM existe no modelo (schema presente + tabela ausente = ausência
  real, não remapeia para homônima de outro schema) e os remaps são reportados na
  mensagem (`_remap_note`); (c) o field-change de update carrega o snapshot `before`
  (catálogo) p/ o ticket mostrar "antes → depois". Testes: `test_csv_roundtrip.py`
  (fallback, case-insensitive de tabela E coluna, narrowing, ambiguidade, before, slug).
  **LIÇÃO:** teste o mismatch de schema/caixa real, não só o caminho feliz.
- **Ticket: valor de field-change nunca deve virar `[object Object]` (v1.0055).** A
  mudança/adição de COLUNA vinda do CSV/XLSX é encenada como PAYLOAD (objeto) no
  `field_changes.after`; `tickets.$id.tsx::humanizeValue` fazia `String(obj)` →
  `[object Object]` na tela de aprovação (bug pré-existente, commit 8007060). Fix:
  `humanizeValue` resume o objeto (tipo · PK · NOT NULL · "descrição" · lógico).
- **"Sistema atual" nas abas Versões/Sync/DDL (v1.0055).** Essas 3 abas inicializavam
  `systemId = systems[0]` e ignoravam o `nuclea.lastSystem` (sessionStorage) — o
  sistema escolhido em outra tela não era herdado. Fix: usam `selectDefaultSystemId`
  (valida contra a lista) + `saveLastSystemId` num `useEffect`, como as demais telas
  de modelagem. (O catálogo/schema de DESTINO do Sync seguem no próprio SYNC_PREFS_KEY.)
- **RODADA 7 — feedback do cliente sobre o DER/CHECK (v1.0056).** Ajustes na
  revalidação da rodada DER + CHECK:
  - **Item 9 (FK por cursor transporta chaves por DEFAULT).** O `CreateRelationshipDialog`
    (`diagram.tsx`) nascia com `transport = false` → clicar pai→filha desenhava a linha
    mas NÃO criava a coluna FK na filha ("a FK não reflete na filha"). Agora `transport`
    nasce **ligado**: o fluxo por cursor cria o relacionamento E transporta as chaves
    (coluna STAGED na filha, badge "adicionar"). Quem quer só MAPEAR colunas existentes
    (de-para) desmarca. Além disso, `transportedFkName` ganhou `alwaysQualify`: **sem
    de-para explícito** (transporta a PK do pai) a coluna já nasce **qualificada com a
    origem** (`id → id_<pai>`), não só em colisão — pedido do cliente.
  - **Item 14 (marcar FK no DER).** O nó do DER (`entity-node.tsx`) não tinha indicador
    de FK. `DiagramCanvas` calcula `fkAttrIds` e injeta no `data` do nó; o `EntityNode`
    renderiza o marcador **"FK"** por coluna + contador `N fk` no cabeçalho. É SÓ leitura
    visual. **GOTCHA (v1.0057, corrigido no 1º reteste):** NÃO dá pra keyar em
    `target_attrs` — a orientação source/target dos relacionamentos NÃO é consistente:
    o app cria `source=PAI(PK)/target=FILHO(FK)`, mas há dado seed/legado com o INVERSO
    (`source=FILHO(FK)/target=PAI(PK)`). Keyar em target_attrs pintava a **PK do PAI**
    como "FK" (o cliente pegou na hora). Fix: o lado FK é o que **NÃO é PK** (o
    referenciador); o lado referenciado é o conjunto todo-PK. Decidir pela PK
    (`is_primary_key`), não pelo rótulo source/target. **Correlato a investigar:** a
    emissão de FK no export DDL (v1.0040) assume `source=PAI` — com dado invertido, o
    `ALTER TABLE … FOREIGN KEY` pode sair trocado; validar quando o cliente exercitar.
  - **Item 21 (CHECK editável em coluna EXISTENTE + descoberta).** O CHECK só podia ser
    preenchido no form de "novo atributo" → o cliente "não localizou" para colunas
    importadas. Nova célula inline `AttrCheckCell` (`components/attributes/check-cell.tsx`,
    irmã da `AttrDefaultCell`) na tabela de atributos dos DOIS lugares (`entities.$id.tsx`
    e o `AttributesEditor` do `diagram.tsx`) → preencher/editar CHECK em qualquer coluna →
    exportar DDL sai `CHECK (...)`. **GOTCHA de staging:** TODO payload de update de
    atributo agora carrega `check_constraint: a.check_constraint ?? null` (saveAttrDesc,
    saveAttrDefault, toggle de PK, reorder de PK) pela disciplina "payload completo /
    última intenção vence por field-key" — omitir arriscava dropar o CHECK staged no mesmo
    ticket (mesma razão de description_md/default_value serem sempre reenviados). Backend
    já persistia/exportava CHECK desde o round 6 pt 21 (`entities/router`, `tickets/service`,
    `ddl/generators`) — a rodada 7 foi só UI/descoberta.
  - **Item 13 (distribuição das linhas do DER): NÃO mexido** por decisão (risco de
    regressão nas arestas > valor do polimento). A lógica de handles/`edgesToRender`
    (v1.0027/v1.0051) segue intocada.

## RODADA 8 — Conexões de banco NATIVAS (v1.0058, PR-1)
- **ODBC não roda no Databricks Apps (RCA confirmada ao vivo).** O teste de conexão
  ODBC (`pyodbc`) falhava em produção com `"pyodbc not installed…"` porque o wheel do
  pyodbc depende de `libodbc.so.2` (unixODBC), ausente no runtime do Apps, que roda
  sem `root`/`apt` — não dá pra instalar driver de sistema. Reproduzido no app
  deployado (`POST /api/connections/{id}/test`).
- **Decisão (aprovada pelo cliente): substituir ODBC por drivers Python EMBUTIDOS por
  engine** — nada a anexar. `connections/testers.py::test_database` despacha por
  `engine`: POSTGRES→`psycopg` (já comprovado no runtime, mesmo do Lakebase),
  ORACLE→`oracledb` thin, MYSQL→`PyMySQL`, SQLSERVER→`python-tds`, DB2→`ibm_db`.
  **Imports LAZY por engine** (`DriverUnavailable`): se um driver não carregar no
  runtime, só aquele engine falha com mensagem clara — o app não cai. ODBC vira LEGADO
  (o teste devolve msg de descontinuação; `connection_type` novo = `DATABASE`).
- **Credenciais self-service, senha CIFRADA EM REPOUSO.** O cliente digita
  URL/usuário/senha direto (fim do modelo "chave de secret por conexão + redeploy").
  A senha é cifrada com Fernet (`connections/crypto.py`) e guardada na coluna
  `enc_password` (migration 022); **nunca** volta na API (`ConnectionOut.has_password`
  só diz se existe). `username` não é sigiloso e fica no `config_json`. **Chave-mestra
  (v1.0059, corrigido ao vivo):** secret `nuclea-modeler/conn_enc_key`, LIDA EM RUNTIME
  via SDK pelo SP do app (`crypto.py::_read_from_secrets`, cacheada) — env
  `NUCLEA_CONN_ENC_KEY` continua como override p/ testes. NÃO usar `valueFrom` no
  app.yml: o recurso `secret` do app.yml **não é registrado** pelo `apps deploy` (a env
  não chega) e mexer nos recursos do app é arriscado (incidente do warehouse). O SP do
  app precisa de **READ no scope** (grant aditivo `secrets put-acl <sp> READ`). Falha
  FECHADO: sem a chave, criar conexão com senha dá 500 (nunca grava em claro). Rotação
  futura via `MultiFernet` sem mudar schema.
- **Deps novas** (pyproject + requirements, specs idênticas p/ `check_deps_sync`):
  `oracledb`, `PyMySQL`, `python-tds`, `ibm-db`, `cryptography` — TODAS com wheel no
  proxy interno `pypi-proxy.cloud.databricks.com/simple/` (cp311/cp312), que é o índice
  que o CI e o deploy usam (o PyPI público está bloqueado nesta máquina). ibm_db usa
  wheel manylinux_2_34 — validar o `import` no runtime após deploy (glibc); se não
  carregar, DB2 degrada com mensagem, sem derrubar o app.

## RODADA 8 — Flags OFP + marcador de particionamento (v1.0060, PR-2)
- **Item 7 (flags OFP):** nova categoria `OFP` (Operações Fora do Padrão) no catálogo.
  `FlagCategory` (backend `flags/models.py` + `api.ts`) ganhou `"OFP"` → **TODO
  `Record<FlagCategory,…>` da UI precisa da chave OFP** (senão o tsc reprova):
  `flags.tsx` (CATEGORY_META/ORDER/grouped), `flag-picker.tsx` (ORDER/LABEL/grouped),
  `flag-batch-bar.tsx` (ORDER/grouped). Seed em `023_seed_ofp_flags.sql` (MERGE por
  flag_key, como o 003). **É um conjunto-RASCUNHO** (operacao-manual, fora-de-janela,
  sem-aprovacao, reprocessamento, carga-emergencial) — nomes a validar com o cliente.
- **Item 2 (marcador de particionamento):** o DER JÁ mostrava o particionamento
  (`entity-node.tsx`: badge da estratégia no cabeçalho + estratégia/colunas no expandido,
  via `DiagramEntity.partition_strategy/columns` populados em `diagram/router.py`). O que
  faltava era ACHAR tabelas particionadas na LISTA: `list_entities_paginated` ganhou
  `partition_strategy` (subquery a `entity_partitioning` com `strategy<>'NONE'`) + filtro
  `partitioned` (EXISTS, no molde do filtro por flag); a lista de Entidades mostra badge
  "Particionada · <estratégia>" + FilterSelect "Só particionadas". Sem tocar no DER
  (evita regressão nas arestas). Sem schema novo.

## RODADA 8 — Flags custom por SISTEMA (v1.0061, PR-3, item 4)
- **Escopo por sistema no catálogo de flags.** `flags` ganhou coluna `system_id`
  (migration 024): NULL = global (comportamento atual); preenchido = flag CUSTOM válida
  só naquele sistema. `_FLAG_COLS` (flags/router.py) ganhou `system_id` NO FIM (os slices
  dos joins de entity/attribute/relationship flags se ajustam por `len()`) e
  `_flag_row_to_out` mapeia `r[10]`. `createCustomFlag` grava `system_id`; `listFlags`
  aceita `system_id` → `WHERE system_id IS NULL OR system_id = :sys` (globais + do sistema).
  ORDER BY do catálogo corrigido p/ incluir OFP (LGPD0/USE1/QUALITY2/OFP3/CUSTOM4).
- **UI:** form "Nova flag personalizada" (flags.tsx) ganhou seletor **Escopo** (Global /
  "Só o sistema: X"); o card do catálogo mostra badge **"só: <sistema>"**. Os PICKERS de
  aplicar/remover em lote (`FlagBatchBar`→`FlagPickerModal`/`FlagRemoveModal`) ganharam
  prop `systemId` (opcional) e listam globais + do sistema atual — wired nos 2 call sites
  (entities.index `params.systemId`; entities.$id/AttributesSection `systemId`).
  **Follow-up conhecido:** `FlagKeyPicker` (quick-add de tabela/coluna) ainda lista TODAS.

## RODADA 8 — Calendário de conformidade + pop-up (v1.0062, PR-4, item 3)
- **Novo módulo `backend/compliance/`** (models/service/router) + migration 025
  (`compliance_calendar`: 1 agendamento por sistema; `next_due_date` é STRING ISO p/
  evitar casting de DATE na Statement Execution API). Registrado no `app.py`
  (`compliance_router`). Endpoints: `listComplianceSchedules`, `listComplianceDue`
  (pop-up), `upsertComplianceSchedule`, `executeComplianceSchedule` (grava execução +
  AVANÇA next_due_date pela recorrência — a partir do max(prevista, hoje)),
  `deleteComplianceSchedule`, `importComplianceCalendar` (multipart CSV/XLSX, upsert por
  sistema). Recorrências: MONTHLY/QUARTERLY/SEMIANNUAL/ANNUAL (add_months com clamp de
  dia). Mutações exigem _MUTATORS (steward/architect/admin).
- **UI:** página `_sidebar/compliance.tsx` (lista + import de planilha + cadastro manual +
  "Registrar execução"); item "Conformidade" no menu Governança. Pop-up
  `components/apx/compliance-reminder.tsx` (molde WelcomeTour, query NÃO-suspense) montado
  no `_sidebar/route.tsx` — avisa vencidas/hoje, "Registrar execução" por sistema,
  dispensável na sessão (sessionStorage). Hooks à mão em api.ts.
- **Decisões do cliente:** recorrência mensal/trimestral/semestral/anual; pop-up avisa +
  registra execução (sem exigir anexo); 1ª carga via planilha. **Anexar o checklist ao
  sistema já funcionava** (módulo de anexos, owner_kind='system') — não refeito aqui.
- **Fixes do /code-review (v1.0063):** (a) o pop-up só aparece para quem PODE registrar
  (curadoria) — `useMyRoles` não-suspense + gate `is_admin||DATA_ARCHITECT||DATA_STEWARD`
  (evita modal bloqueante cuja ação daria 403 p/ viewer); (b) "hoje" é calculado em BRT
  (UTC-3 fixo, `service.today_br()`), não no UTC do runtime — senão o pop-up dispara 1 dia
  adiantado à noite; (c) `executeComplianceSchedule` devolve a linha pelo `calendar_id`
  (não por system_id, que podia devolver linha errada); (d) `wb.active` guardado (xlsx sem
  aba → 400, não 500); (e) delimitador do CSV decidido pela 1ª linha; (f) testes do módulo
  (`test_compliance_service.py`: normalize_date, advance_iso c/ clamp, parse_recurrence,
  due_fields, parse_import CSV/XLSX). a11y do pop-up: role=dialog/aria-modal + Esc + backdrop.

## RODADA 9 — Avaliação do cliente (v1.0069)
Itens aprovados: 1 (Lakebase, opção A), 3, 5, 6, 7, 8, 9, 10. Item 2 (datas na planilha de
conformidade) aguarda a planilha do cliente; itens 4 (ODBC), 11, 12 e 13 dependem de alinhamento.
- **Item 1 — Lakebase Sandbox (RCA ao vivo):** `GET /api/lakebase/instances` dava 403 "Invalid
  scope, required scopes: postgres": o app não declara `postgres` em `user_api_scopes` (o token
  OBO do usuário só tinha `iam.*`). Fix de verdade = declarar o scope no app (`apps update` com
  `user_api_scopes` + os MESMOS `resources` — conferir depois que warehouse/lakebase continuam;
  usuários re-consentem no próximo login). No código, `list_instances` cai no SP do app SÓ em erro
  de scope (`_is_scope_error`, por MENSAGEM — o SDK não tipa esse 403). test/schemas já usavam o SP.
- **Item 3 — Diagnóstico de conexão:** `connections/testers.py::classify_db_error` mapeia o texto
  do driver → DNS|NETWORK|REFUSED|AUTH|SSL|DATABASE|DRIVER|UNKNOWN + orientação. ORDEM das regras
  importa (DNS antes de NETWORK; AUTH antes de SSL por causa do pg_hba "SSL off"; `role "x" does not
  exist` é AUTH). Classifica também a cadeia `__cause__` (oracledb embrulha em DPY-6005). A
  orientação é PERSISTIDA em `last_test_error` como `"<erro>\nDiagnóstico: <hint>"` (sem coluna
  nova); a UI separa pelo marcador (`components/connections/test-error.tsx`). O toast de teste
  dizia "Conexão testada" (verde) até em FALHA — agora reflete o status. ODBC ganha selo
  "descontinuada".
- **Item 5 — Export enriquecido:** CSV ganha `fk_references` (fim; `CSV_EXPORT_HEADERS`); XLSX ganha
  schema/data_type/is_nullable/is_pk/fk_references DEPOIS das 4 colunas Embarcadero. FK é SÓ de
  export (o import ignora — relacionamento não se cria por texto de planilha). `CSV_HEADERS` NÃO
  mudou (é também o CSV canônico interno do import XLSX). Lado da FK decidido pela PK
  (`fk_references_by_attr`), não por source/target — mesmo gotcha do marcador FK do DER (v1.0057).
- **Item 6 — Exclusão em lote:** só UI (Navegador): "Selecionar vários" → arquivar em lote; nos
  arquivados → restaurar / solicitar exclusão em lote (1 ticket SYSTEM_DELETE por sistema, mesmo
  endpoint). Execução SEQUENCIAL (rate limit). Atalho "Sistemas de teste" = `SMOKE-*`, `tmp-*`,
  palavra test/teste/testes.
- **Item 7 — Dialeto:** a TECNOLOGIA do sistema É o dialeto. `ui/lib/dialects.ts` =
  vocabulário único (rótulo gravado ↔ chave canônica do backend). Editável no Navegador via
  `PATCH /systems/{id}/technology` (`setSystemTechnology`) — rota própria porque o PUT regrava todos
  os campos e o Navegador só tem `SystemListOut` (apagaria description/owner_team). Import de DDL
  pré-seleciona o dialeto do sistema a cada troca de sistema; export só SUGERE (destino é outro banco).
- **Item 8 — Resolução do PNG:** presets padrão/alta/máxima (`components/diagram/export-quality.ts`,
  persistido em localStorage). Fallback em degraus (alvo → metade → … → 1x); toast mostra a
  resolução REAL e sugere SVG quando o teto do browser limitou.
- **Item 9 — Seleção visual no DER:** modo "Selecionar" = laço (`selectionOnDrag`, pan no botão
  meio/direito); Shift+arrastar e Ctrl/⌘+clique em qualquer modo. Barra (≥2 selecionadas): criar
  diagrama com elas (exige 1 schema — diagrama pertence a um schema; leva as posições), "só as
  selecionadas" (foco LOCAL via `focusIds` no `filteredEntities` — nós e arestas seguem o mesmo
  `visibleIds`, sem tocar em handles/arestas), tirar do diagrama. A confirmação de exclusão foi
  para `onBeforeDelete` (antes, no `onNodesDelete`, cancelar não trazia o nó de volta e a seleção
  múltipla daria N confirms). MembersDialog virou grade de cartões com filtro/Todas/Nenhuma.
- **Item 10 — Guias:** seção "Guias práticos" na Ajuda (`components/apx/help-guides.tsx`): Código DB
  com exemplos copiáveis + DDL de exemplo para download (gerado no browser), Canvas, Linhagem e
  dialeto. Os campos citados batem com os formulários — atualizar junto se mudarem.

## RODADA 9 consolidada — pontos novos do cliente (v1.0070 → v1.0073)
- **v1.0070 — Lakebase: enum do SDK chega como `str`.** Com o scope `postgres` ativo, a
  listagem de instâncias saiu do 403 e quebrou em `inst.state.value`. `_enum_str` aceita
  Enum OU str. GOTCHA: `user_api_scopes` NÃO aceita `iam.*` (implícitos) — mande só os extras.
- **v1.0071 — DER alto contraste (item 3d):** `components/diagram/contrast.ts`. Modo "alto"
  (padrão) = canvas cinza, cartão branco com borda 2px, cabeçalho em faixa, aresta 2,5px
  roxo-escuro, rótulo 12px com fundo opaco. Seta com `markerUnits: "userSpaceOnUse"` — o
  default do React Flow ESCALA a seta com a espessura. Só estilo, aplicado por cima da aresta
  em `edgesToRender`; a escolha de handles não muda.
- **v1.0072 — Datas na planilha de conformidade (item 12):** `compliance/service.normalize_date`
  aceita data com hora, serial do Excel, `.`, ano-primeiro, mês PT/EN abreviado, AAAAMMDD;
  DD/MM por padrão (BR). **GOTCHA:** CSV do Excel BR é **Windows-1252** — decodificar como
  UTF-8 com `replace` quebrava o cabeçalho "Próxima" e nomes acentuados; agora UTF-8 estrito
  → fallback cp1252. Cabeçalho normalizado (sem acento/caixa/espaço) e procurado nas 10
  primeiras linhas (título antes). `.xls` recusado com mensagem. Botão "Baixar modelo".
- **v1.0073 — DDL extenso (item 10). RCA MEDIDA no app deployado** com
  `scripts/repro_large_ddl.py` (DDL sintético de 12 mil linhas / 358 tabelas):
  - preview (dry-run) OK em ~14 s — o TAMANHO não era o problema;
  - com 1 instrução não-parseável (`\connect`, `CREATE TABLESPACE`), o parse global caía
    num split por `;` CRU → 2.207 erros, `COMMENT ON … 'a; b'` picotado. FIX:
    `extractions/ddl_split.py` divide respeitando aspas/`$$`/comentários/`/`/`GO`/meta-
    comando psql (termina na linha), pré-filtra (só CREATE TABLE/VIEW/INDEX, ALTER TABLE,
    COMMENT ON, SET search_path) e o service parseia instrução a instrução (erro com nº da
    linha). Ignoradas aparecem no resumo ("Ignoradas: 710 INSERT, 35 CREATE FUNCTION").
  - `ALTER TABLE … ADD CONSTRAINT PRIMARY KEY/FOREIGN KEY` (formato do pg_dump) era
    IGNORADO → tabelas sem PK/FK. Agora extraído por REGEX (`parse_alter_constraints`,
    robusto à versão do sqlglot) e aplicado na ordem do script.
  - **a falha real era o APPLY:** 502 do proxy aos **300 s** com só 43/358 tabelas
    (~7 s/tabela: várias idas ao warehouse por item). FIX: `tickets/bulk_apply.py` — para
    tickets com ≥ `BULK_MIN_ADDS` (20) adds, carrega o existente UMA vez e insere entities/
    índices/atributos/FKs com `insert_many` por grupo; grupo que falha cai no caminho
    unitário (idempotente). Abaixo do limiar NADA muda. Builders de linha compartilhados
    (`_entity_row`, `_attribute_row`, `_relationship_row`, `build_index_row`).
  - UI: "Carregar arquivo .sql" + contador de linhas/KB no Importar DDL.
  - Ainda síncrono: se um modelo MUITO maior voltar a passar de 300 s, o próximo passo é
    apply em background (job + polling), não mais otimização.
- **v1.0074 — DynamoDB via JSON (item 17).** Import: `extractions/dynamodb.py` (puro)
  detecta 3 formatos — `describe-table` (1, lista ou `{"Tables"}`), NoSQL Workbench
  (`DataModel`; único com atributos não-chave + itens de exemplo → tipos inferidos) e
  CloudFormation (`AWS::DynamoDB::Table`). Mapeamento: schema lógico `dynamodb`; HASH+RANGE
  → PK composta (HASH primeiro); GSI/LSI → índices `index_type` GSI/LSI; sem FKs. Rota
  `POST /extractions/dynamodb/run` (`runDynamoDBImport`), `SourceKind` += DYNAMODB (sem
  migration: coluna STRING). Export: dialeto `DYNAMODB` em `ddl/dynamodb_gen.py` → JSON de
  `create-table --cli-input-json` (valida 1–2 PKs, chaves só S/N/B, AttributeDefinitions só
  com chaves, LSI usa a partition key da tabela; FKs puladas; combinado = lista JSON; download
  `.json`). **GOTCHA:** `IndexType` (backend `entities/models.py` + `api.ts`) é Literal
  FECHADO — sem "GSI"/"LSI", LER um índice importado daria 500. UI: tecnologia "DynamoDB"
  (`TECHNOLOGY_OPTIONS.dialect = null` = não relacional), tipos/índices/particionamento
  próprios em `types-by-tech`/`index-types-by-tech` (`techKey` checa "dynamo" ANTES das
  regras relacionais). "Outros não relacionais" (MongoDB/Cassandra/Cosmos) = mesmo molde,
  a fazer quando o cliente disser quais usa.
  **Validado no app deployado** com `scripts/smoke_dynamodb.py` (cria/arquiva
  `SMOKE-DYNAMO-*`: import Workbench → apply → PK composta → atributo inferido → leitura do
  GSI → export JSON). Rode-o após mexer em extractions/ddl/IndexType.

- **v1.0075 — Erros de import VISÍVEIS depois do import.** Pergunta do cliente: o
  ticket dizia "Erros de parse: 61" mas não havia onde ver QUAIS. Antes os erros só
  apareciam no card de resultado logo após importar; o ticket tinha só a contagem, o
  Histórico só o status PARTIAL, e `extractions.error_summary` era cortado em 4000
  chars no MEIO da linha. Agora (`extractions/service.py`): `format_ticket_errors`
  põe os 30 primeiros no resumo do ticket (+ "e mais N" + onde ver tudo);
  `join_error_summary` grava 1 msg/linha com limite de 100 mil chars, corte em
  fronteira de linha e marcador "+N não gravada(s)"; `GET /extractions/{id}/errors`
  (`getExtractionErrors`, rota LEVE — `getExtraction` traz o snapshot de MBs) alimenta
  o "Ver erros" do Histórico (linha expansível) com botão "Copiar". Extrações antigas
  continuam com o log truncado em 4000 (não dá para recuperar). **Lembrete:** os erros
  de parse do DDL são de instruções que o import USA (CREATE TABLE/VIEW/INDEX, ALTER,
  COMMENT ON — o resto é filtrado antes), então um erro pode significar uma tabela
  que NÃO entrou no modelo. Teste: `tests/test_extraction_error_log.py`.

## Package Management
- **Frontend:** Use `apx bun install` or `apx bun add <dependency>` for frontend package management.
- **Python:** Always use `uv` (never `pip`)

## Component Management
- **Check configured registries first:** Before building custom components, check `[tool.apx.ui.registries]` in `pyproject.toml` for domain-specific registries (e.g. `@ai-elements` for chat/AI, `@animate-ui` for animations). Use `list_registry_components` with the registry name to browse available components.
- **Finding components:** Use MCP `search_registry_components` to search across all configured registries. Results from project-configured registries are boosted.
- **Adding components:** Use MCP `add_component` or CLI `apx components add <component> --yes` to add components
- **Component location:** If component was added to a wrong location (e.g. stored into `src/components` instead of `src/nuclea-modeler/ui/components`), move it to the proper folder
- **Component organization:** Prefer grouping components by functionality rather than by file type (e.g. `src/nuclea-modeler/ui/components/chat/`)

## Project Structure
Full-stack app: `src/nuclea-modeler/ui/` (React + Vite) and `src/nuclea-modeler/backend/` (FastAPI). Backend serves frontend at `/` and API at `/api`. API client auto-generated from OpenAPI schema.

## Dependencies & Dependency Injection

The `Dependency` class in `src/nuclea-modeler/backend/core.py` provides typed FastAPI dependencies. **Always use these instead of manually creating clients or accessing `request.app.state`.**

| Dependency | Type | Description |
|---|---|---|
| `Dependencies.Client` | `WorkspaceClient` | Databricks client using app-level service principal credentials |
| `Dependencies.UserClient` | `WorkspaceClient` | Databricks client authenticated on behalf of the current user (requires OBO token) |
| `Dependencies.Config` | `AppConfig` | Application configuration loaded from environment variables |
| `Dependencies.Session` | `Session` | SQLModel database session, scoped to request (requires lakebase addon) |

## Models & API
- **3-model pattern:** `Entity` (DB), `EntityIn` (input), `EntityOut` (output)
- **API routes must have:** `response_model` and `operation_id` for client generation

## Frontend Rules
- **Routing:** `@tanstack/react-router` (routes in `src/nuclea-modeler/ui/routes/`)
- **Data fetching:** Always use `useXSuspense` hooks with `Suspense` and `Skeleton` components
- **Pattern:** Render static elements immediately, fetch API data with suspense
- **Components:** Use shadcn/ui, add to `src/nuclea-modeler/ui/components/`
- **Data access:** Use `selector()` function for clean destructuring (e.g., `const {data: profile} = useProfileSuspense(selector())`)

## MCP Tools Reference

This project is configured with the **apx MCP server** (see `.mcp.json`). Always prefer MCP tools over CLI commands — they are faster and provide structured output.

| Tool | Description |
|------|-------------|
| `start` | Start development server and return the URL |
| `stop` | Stop the development server |
| `restart` | Restart the development server (preserves port if possible) |
| `logs` | Fetch recent dev server logs |
| `check` | Check project code for errors (runs tsc and ty checks in parallel) |
| `refresh_openapi` | Regenerate OpenAPI schema and API client |
| `search_registry_components` | Search shadcn registry components using semantic search |
| `list_registry_components` | List all available components in a specific registry |
| `add_component` | Add a component to the project |
| `routes` | List all API routes with parameters, schemas, and generated hook names |
| `docs` | Search Databricks SDK documentation for code examples and API references |
| `databricks_apps_logs` | Fetch logs from deployed Databricks app using Databricks CLI |
| `get_route_info` | Get code example for using a specific API route |
| `feedback_prepare` | Prepare a feedback issue for review. Returns formatted title, body, and browser URL |
| `feedback_submit` | Submit a prepared feedback issue as a public GitHub issue |

## Development Commands

CLI equivalents (use MCP tools above when available):

| Command | Description |
|---------|-------------|
| `apx dev start` | Start all dev servers (backend + frontend + OpenAPI watcher) |
| `apx dev stop` | Stop all dev servers |
| `apx dev status` | Check running server status and ports |
| `apx dev check` | Check for TypeScript/Python errors |
| `apx dev logs` | View recent logs (default: last 10m) |
| `apx dev logs -f` | Follow/stream logs live |
| `apx build` | Build for production |

## Detailed Patterns

For backend patterns (DI, CRUD routers, AppConfig, lifespan) and frontend patterns (Suspense, mutations, selector, components), see `.claude/skills/apx/`.
