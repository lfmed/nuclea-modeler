# Genie Space — Núclea Modeler

A API de criação programática do Genie exige um schema fechado/não-documentado.
A criação via UI leva 2 minutos. Passo-a-passo:

## 1. Criar o space

1. Abra: https://fevm-stable-classic-pg4xe1.cloud.databricks.com/genie
2. Clique em **+ New space** (ou **Novo space**)
3. Em "Warehouse", escolha **stable_classic_pg4xe1** (`b8e52268d9828bdd`)
4. Em "Tables", adicione as 9 tabelas do schema do app:

```
stable_classic_pg4xe1_catalog.data_catalog_app.systems
stable_classic_pg4xe1_catalog.data_catalog_app.entities
stable_classic_pg4xe1_catalog.data_catalog_app.attributes
stable_classic_pg4xe1_catalog.data_catalog_app.relationships
stable_classic_pg4xe1_catalog.data_catalog_app.reconciliation_tickets
stable_classic_pg4xe1_catalog.data_catalog_app.extractions
stable_classic_pg4xe1_catalog.data_catalog_app.lakebase_sandboxes
stable_classic_pg4xe1_catalog.data_catalog_app.glossary_terms
stable_classic_pg4xe1_catalog.data_catalog_app.audit_log
```

5. **Title**: `Núclea Modeler — Catálogo de Dados`
6. **Description**: `Genie space para consultar o catálogo de dados do app Núclea Modeler — sistemas, entidades, atributos, relacionamentos, tickets e extrações.`

## 2. Adicionar contexto (Instructions)

Em "Instructions" cole:

```
Você é um analista que conhece a estrutura do catálogo de dados do Núclea Modeler.

Tabelas principais:
- `systems`: sistemas de origem (modelos de dados). Cada sistema tem environment (DEV/HINT/PRD), technology, domain.
- `entities`: tabelas/views catalogadas. Cada entity pertence a um system_id. Marca is_shared=true entities que podem ser referenciadas cross-system.
- `attributes`: colunas das entities. is_primary_key, native_data_type, is_nullable.
- `relationships`: FKs/associações entre entities. rel_type (1:1, 1:N, N:M), source_entity_id, target_entity_id.
- `reconciliation_tickets`: tickets de mudança em status OPEN/APPROVED/APPLIED/REJECTED. source_type LAKEBASE_ROUNDTRIP/DDL_IMPORT/MANUAL.
- `extractions`: histórico de engenharia reversa. status SUCCESS/FAILED/PARTIAL.
- `audit_log`: trilha imutável de mutações. Inclui actor_email, action, object_type, object_id, before_json, after_json, occurred_at.

Exemplos de perguntas:
- Quantos sistemas estão em produção?
- Quais sistemas têm mais entidades?
- Quantos tickets abertos por sistema?
- Top 10 entidades com mais relacionamentos.
```

## 3. Sample questions (opcional)

Adicione perguntas-modelo pra ajudar usuários novos:

- Quantos sistemas estão cadastrados, agrupados por ambiente?
- Quais são os 10 sistemas com mais entidades?
- Quantos tickets de reconciliação estão abertos no momento?
- Qual foi a última extração executada com sucesso?
- Quais entidades estão marcadas como compartilhadas (is_shared=true)?
- Quantos relacionamentos existem entre as tabelas de cada sistema?

## 4. Publish

Clica **Save** e depois **Publish** pra dar acesso ao time. Permissões via *Share*.
