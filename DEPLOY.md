# Deploy do Núclea Modeler em um workspace do cliente

Guia passo-a-passo para o cliente subir o app no próprio workspace Databricks.
Os SQLs e o código backend são **workspace-agnostic** — você só edita
parâmetros no `app.yml`.

## Pré-requisitos

| Requisito | Mínimo | Como obter |
|---|---|---|
| **Databricks workspace** | qualquer tier com Unity Catalog ativado | já provisionado |
| **SQL Warehouse** | Serverless ou Pro, `2X-Small` é suficiente | SQL → SQL Warehouses → *Create* |
| **Unity Catalog** | 1 catalog + USAGE para o SP do app | Catalog → escolher um existente |
| **Permissões para o usuário deployer** | Workspace Admin **ou** ter `CAN_MANAGE` em apps + `CREATE SCHEMA` no catalog escolhido | acordar com admin |
| **Databricks CLI** | `>= 0.250.0` autenticado no workspace | `pip install databricks-cli` + `databricks auth login` |
| **(opcional) Lakebase Postgres** | Apenas se for usar engenharia reversa contra Lakebase | Compute → Lakebase → *Create* |

> **Não precisa Node/Python local.** O build da UI (Vite) e a instalação de
> deps Python (uv) rolam dentro do container do Databricks Apps no `command:`
> declarado em `app.yml`.

## 1. Clone

```bash
git clone https://github.com/lfmed/nuclea-modeler.git
cd nuclea-modeler
```

## 2. Parametrize `app.yml`

```bash
cp app.yml.example app.yml
```

Edite `app.yml` substituindo os placeholders `[ALTERAR]`:

| Placeholder | O que é | Onde achar |
|---|---|---|
| `<WAREHOUSE_ID>` | ID do SQL Warehouse | Final da URL ao abrir o warehouse (`/sql/warehouses/<ID>`) |
| `<CATALOG_NAME>` | Nome do Unity Catalog onde o app guarda estado | Catalog Explorer |
| `<LAKEBASE_INSTANCE_NAME>` | (opcional) Nome da instance Lakebase Postgres | Compute → Lakebase |

Se **não usar Lakebase**, remova ou comente o bloco `nuclea-lakebase` em
`resources:` — o resto do app continua funcionando.

Schema (`NUCLEA_SCHEMA`) é criado automaticamente na primeira run pelas
migrations. Sugestão: `nuclea_modeler` (default no `.example`).

## 3. Crie o secret scope (opcional, só se for conectar a ODBC/REST)

```bash
databricks secrets create-scope nuclea-modeler --profile <SEU_PROFILE>
```

Se mudou `NUCLEA_SECRETS_SCOPE`, use o nome correspondente.

## 4. Cria o app

```bash
databricks apps create nuclea-modeler --profile <SEU_PROFILE>
```

Pega o ID do service principal retornado — pode ser preciso pra grants
manuais em recursos extras (catálogos, lakebase, etc.).

## 5. Garanta permissões do SP do app

O SP precisa pelo menos:

```sql
-- No Unity Catalog do cliente
GRANT USAGE ON CATALOG <CATALOG_NAME> TO `<SP_APPLICATION_ID>`;
GRANT CREATE SCHEMA ON CATALOG <CATALOG_NAME> TO `<SP_APPLICATION_ID>`;

-- No schema (após primeira run que cria) — opcional, pode esperar
GRANT ALL PRIVILEGES ON SCHEMA <CATALOG_NAME>.nuclea_modeler TO `<SP_APPLICATION_ID>`;
```

O `<SP_APPLICATION_ID>` é o UUID que `databricks apps create` retornou.

## 6. Deploy

Faz o upload do source pra um workspace path e dispara o build:

```bash
# Sincroniza o repo pro workspace (qualquer path com permissão de escrita)
databricks sync . /Workspace/Users/<seu-user>/nuclea-modeler --profile <SEU_PROFILE> --full

# Deploya o app apontando pra esse path
databricks apps deploy nuclea-modeler \
  --source-code-path /Workspace/Users/<seu-user>/nuclea-modeler \
  --profile <SEU_PROFILE>
```

O deploy demora ~1 min: instala deps Python (uv), npm install, `vite build`,
roda migrations e sobe uvicorn. Os logs mostram cada passo:

```bash
databricks apps logs nuclea-modeler --profile <SEU_PROFILE>
```

Procure por `summary: {'applied': N, ...}` — número de migrations
aplicadas com sucesso.

## 7. Acessar

A URL final aparece no `databricks apps get nuclea-modeler`:

```
https://nuclea-modeler-<WORKSPACE_ID>.cloud.databricksapps.com
```

Login obrigatório via SSO do workspace. O primeiro usuário a entrar pode
precisar receber role `ADMIN` no app (via `/admin/roles` se já tiver acesso,
ou inserindo manualmente em `user_roles` Delta).

## 8. (Opcional) Genie e Dashboard externos

Após o app estar rodando:

- **Lakeview dashboard**: `databricks/dashboards/nuclea_modeler_dashboard.json` —
  substitua o `stable_classic_pg4xe1_catalog.data_catalog_app` por
  `<seu_catalog>.<seu_schema>` antes de criar via
  `databricks lakeview create`.

- **Genie Space**: siga `databricks/dashboards/GENIE_SETUP.md`. Tabelas a
  anexar usam o mesmo padrão `<catalog>.<schema>.<tabela>`.

## Troubleshooting

| Sintoma | Causa | Fix |
|---|---|---|
| `[migrations] FAILED ... SCHEMA_NOT_FOUND` | SP do app não tem CREATE SCHEMA no catalog | passo 5 |
| `Provided OAuth token does not have required scopes: postgres` | Resource `nuclea-lakebase` não declarado em `app.yml` | adicione o bloco e re-deploy |
| `[migrations] DRIFT detected` | Mesmo arquivo SQL com hash diferente do registrado | normal após upgrade; o app continua. Revise a migration manualmente |
| Dashboard / DER vazio após deploy | Schema criado mas seeds não rodaram | rode `databricks apps logs` e procure erros nas migrations 003/004/009 |
| 401 em todos os endpoints | SSO força auth, browser sem cookie | abrir no mesmo workspace logado |

## Atualizações

Quando publicarmos uma nova versão do app:

```bash
git pull origin main
databricks sync . /Workspace/Users/<seu-user>/nuclea-modeler --profile <SEU_PROFILE>
databricks apps deploy nuclea-modeler --source-code-path /Workspace/Users/<seu-user>/nuclea-modeler --profile <SEU_PROFILE>
```

Migrations novas aplicam automaticamente no pre-uvicorn (rastreadas em
`schema_migrations` por checksum, então não duplicam).

## Estado armazenado pelo app

Todo estado vai pro Unity Catalog em `<CATALOG>.<SCHEMA>` — 18+ tabelas Delta
(systems, entities, attributes, relationships, reconciliation_tickets,
extractions, audit_log, etc). **Não há banco operacional externo** — sem
Postgres, Redis, etc. Backup do app = `DEEP CLONE` ou `BACKUP` do schema.
