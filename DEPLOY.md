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

## 3. Crie o secret scope e a chave de cifra (obrigatório para Conexões)

O app cifra a senha de cada conexão de banco (Conexões → Nova conexão) com uma
**chave-mestra** guardada em Databricks Secrets. Sem ela, salvar uma conexão com
senha falha com *"Chave de cifra indisponível"* — o app nunca grava senha em texto puro.

```bash
databricks secrets create-scope nuclea-modeler --profile <SEU_PROFILE>

# Gera a chave (Fernet) e grava no secret `conn_enc_key`
KEY=$(python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
databricks secrets put-secret nuclea-modeler conn_enc_key --string-value "$KEY" --profile <SEU_PROFILE>
```

- Se mudou `NUCLEA_SECRETS_SCOPE` no `app.yml`, use o mesmo nome aqui e no passo 5.
- **Não troque nem apague essa chave depois:** as senhas já salvas deixam de abrir
  e as conexões precisam ser recadastradas. Não precisa guardar cópia — ela fica no secret.
- O READ do service principal do app no scope é dado no **passo 5** (o SP só
  existe depois do passo 4).

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

-- No schema (após primeira run que cria). Necessário p/ **anexos**: as
-- migrations criam um Volume gerenciado `attachments` no próprio schema do app
-- e o app escreve/lê arquivos nele. ALL PRIVILEGES cobre CREATE/WRITE VOLUME.
GRANT ALL PRIVILEGES ON SCHEMA <CATALOG_NAME>.nuclea_modeler TO `<SP_APPLICATION_ID>`;
```

O `<SP_APPLICATION_ID>` é o UUID que `databricks apps create` retornou.

**Leitura da chave de cifra (obrigatório para Conexões).** O app lê a chave do
passo 3 com o próprio SP — dê READ no scope:

```bash
databricks secrets put-acl nuclea-modeler <SP_APPLICATION_ID> READ --profile <SEU_PROFILE>
```

Se o app já estiver no ar, não precisa reiniciar nem re-deployar: a próxima
tentativa de salvar a conexão já encontra a chave.

### Grants extras por funcionalidade

| Funcionalidade | Grant necessário | Quando |
|---|---|---|
| **Anexos** (documentos em tabelas/modelos) | `ALL PRIVILEGES ON SCHEMA` do app (acima) — cobre `CREATE VOLUME` + `WRITE VOLUME` | ao usar anexos |
| **Materializar modelo em Delta** (sync com "Materializar") | `USE CATALOG` + `USE SCHEMA` + `CREATE TABLE` + `MODIFY` no **catálogo/schema destino** que o cliente escolher (pode ser diferente do catálogo do app) | ao materializar |

```sql
-- Só se for usar "Materializar em Delta" para um catálogo destino <ALVO>:
GRANT USE CATALOG ON CATALOG <ALVO> TO `<SP_APPLICATION_ID>`;
GRANT USE SCHEMA, CREATE TABLE, MODIFY ON SCHEMA <ALVO>.<SCHEMA_DESTINO> TO `<SP_APPLICATION_ID>`;
```

**O app SOBE mesmo sem esses grants** — eles só habilitam os recursos:
- Anexos: o Volume é criado sob demanda no 1º upload; sem `CREATE VOLUME` o upload
  retorna `502` com a orientação do grant, mas o resto do app funciona normal.
  (A migration `016` cria só a tabela de metadados — nunca o Volume — então o
  boot/migrations nunca dependem desse grant.)
- Materialização: sem os grants no catálogo destino, o sync retorna `ERROR`/`SKIPPED`
  por objeto, sem derrubar o app.

> **Atualização de uma instância já existente:** as migrations novas (`015`
> aditiva `ALTER ... ADD COLUMNS` em `entities`; `016` `CREATE TABLE IF NOT EXISTS`)
> são **aditivas e não destrutivas** — não alteram nem apagam dados existentes, e
> as migrations `001–014` não mudaram (sem re-run). Deploy é seguro sobre dados
> em produção.

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
