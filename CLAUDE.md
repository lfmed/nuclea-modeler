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
  de resultado de query. (Causou o bug "todas as colunas viram PK" — v1.0026.)
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
- **`ui/lib/api.ts` é ESCRITO À MÃO** — não há codegen no deploy (cliente sem npm/apx).
  Rota nova no backend ⇒ escreva o hook à mão em `api.ts` (padrão `use<Op>` /
  `use<Op>Suspense` / `selector()`). Ignore a linha do boilerplate que diz "auto-regenera".
- **UI só chega ao cliente após merge no `main`**, que dispara `build-dist.yml`
  (rebuild + commit de `src/nuclea_modeler/__dist__`, o bundle prebuilt servido em prod).

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
