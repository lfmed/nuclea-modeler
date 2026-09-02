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
