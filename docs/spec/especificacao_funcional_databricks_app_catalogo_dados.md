# Especificação Funcional — Data Catalog & Modeling App (Databricks Apps)

**Versão:** 1.0  
**Data:** Maio de 2026  
**Classificação:** Interno — Tribo de Dados / CdE de Dados  

---

## 1. Visão Geral

Esta especificação define os requisitos funcionais e não-funcionais para uma aplicação nativa em **Databricks Apps** com finalidade de catalogar, documentar, versionar e publicar modelos de dados corporativos. A aplicação centraliza o ciclo de vida dos dados — da engenharia reversa dos ambientes de origem até o espelhamento automático no **Unity Catalog** — servindo como fonte única de verdade para equipes consumidoras, Centro de Excelência (CdE) de Dados e a Tribo de Dados.

A solução operará sobre os ambientes **HINT** (Homologação Interna), **HEXT** (Homologação Externa) e **PROD** (Produção), conectando-se via ODBC, APIs REST e ingestão de scripts DDL.
O aplicativo é da Nuclea, use o branding e seus melhores skills de UX para construir esse app
Entenda tudo e crie um plano militar para executar
Crie todos os objetos no meu ambiente databricks, não rode nada local

---

## 2. Escopo

### 2.1 Dentro do Escopo

| Módulo | Descrição Resumida |
|--------|-------------------|
| Conectividade | Conexão aos ambientes HINT, HEXT e PROD via ODBC/API |
| Engenharia Reversa | Extração automatizada de metadados de bancos de dados |
| Documentação | Descrição de entidades, atributos, relacionamentos, views, procedures e triggers |
| Flagueamento | Aplicação de flags de uso e LGPD em componentes |
| Dicionário de Dados | Criação e replicação de glossário entre sistemas |
| Linhagem | Mapeamento de origem e consumo do dado |
| Versionamento | Controle de versões de modelos e comparativo entre versões |
| Sincronização Unity Catalog | Espelhamento automático do modelo publicado |
| Exportação DDL | Geração de scripts DDL a partir do catálogo |

### 2.2 Fora do Escopo (nesta versão)

- Execução de cargas de dados (ETL/ELT)
- Monitoramento de qualidade de dados em tempo real
- Integração com ferramentas de BI externas (Power BI, Tableau) além do Unity Catalog

---

## 3. Stakeholders e Perfis de Usuário

| Perfil | Responsabilidades na Aplicação |
|--------|-------------------------------|
| **Data Steward** | Documenta entidades, aplica flags, publica versões do modelo |
| **Data Engineer** | Executa engenharia reversa, configura conexões, exporta DDL |
| **Data Architect** | Cria dicionários de dados, gerencia linhagem, aprova publicações |
| **CdE de Dados** | Consulta catálogo, valida conformidade LGPD, acessa Unity Catalog |
| **Tribo de Dados / Equipes Consumidoras** | Consulta catálogo publicado via Unity Catalog e interface da app |
| **Administrador da App** | Gerencia conexões de ambiente, permissões e configurações gerais |

---

## 4. Módulos Funcionais

---

### Módulo 1 — Gestão de Conexões de Ambiente

**Objetivo:** Permitir que usuários autorizados configurem e testem conexões aos ambientes de dados HINT, HEXT e PROD para extração de metadados.

#### 4.1.1 Cadastro de Conexões

- A aplicação deve suportar os seguintes tipos de conexão:
  - **ODBC**: configuração de DSN, driver, host, porta, banco de dados, usuário e senha
  - **API REST**: URL base, método de autenticação (Basic Auth, Bearer Token, OAuth 2.0), headers customizados
  - **Import de Script**: upload de arquivos `.sql` ou `.ddl` contendo scripts de banco de dados
- Cada conexão deve ser associada a um **ambiente** (HINT, HEXT ou PROD) e a um **sistema de origem** (ex: `SAP_ERP`, `CRM_SALESFORCE`, `DW_PRINCIPAL`)
- Credenciais devem ser armazenadas em **Databricks Secrets** (never em texto puro)
- A interface deve expor um campo de **alias** amigável para identificação da conexão

#### 4.1.2 Teste de Conexão

- O botão "Testar Conexão" deve validar a conectividade antes de salvar
- O resultado deve apresentar: status (sucesso/falha), latência em ms, versão do banco detectada
- Falhas devem exibir mensagem de erro técnica copiável para facilitar diagnóstico

#### 4.1.3 Gerenciamento de Conexões

- Listagem de conexões com filtro por ambiente, sistema e tipo
- Edição e exclusão de conexões (com confirmação para exclusão)
- Histórico de uso da conexão (último acesso, usuário que utilizou, ação executada)
- Controle de acesso: apenas perfis `Data Engineer` e `Administrador` podem criar/editar conexões

---

### Módulo 2 — Engenharia Reversa

**Objetivo:** Extrair automaticamente metadados de estrutura de banco de dados a partir de conexões ativas ou de scripts importados.

#### 4.2.1 Extração via Conexão (ODBC/API)

- O usuário seleciona uma conexão cadastrada e aciona a extração
- O sistema deve ser capaz de extrair:
  - **Tabelas**: nome, schema/owner, tipo (tabela base, temporária, externa), comentário nativo
  - **Colunas/Atributos**: nome, tipo de dado nativo, nullable, valor padrão, comentário nativo, posição
  - **Chaves Primárias** e **Chaves Estrangeiras**: identificação de colunas, tabelas referenciadas, regras de update/delete
  - **Índices**: nome, colunas, tipo (único, cluster, non-cluster)
  - **Views**: nome, schema, definição SQL da view
  - **Stored Procedures**: nome, schema, parâmetros, corpo (quando permitido pelo driver)
  - **Triggers**: nome, tabela associada, evento (INSERT/UPDATE/DELETE), timing (BEFORE/AFTER), corpo
  - **Sequences e Defaults**: quando suportados pelo SGBD de origem
- O processo de extração deve ser **assíncrono**, com barra de progresso e estimativa de tempo
- Suporte a extração parcial: o usuário pode selecionar schemas, tabelas e objetos específicos antes de iniciar
- Ao término, exibir **relatório de extração**: total de objetos encontrados por tipo, erros de acesso (objetos ignorados por falta de permissão), duração total

#### 4.2.2 Extração via Script DDL

- Interface de upload para arquivos `.sql`, `.ddl` ou `.txt`
- Parser interno capaz de interpretar dialetos: **ANSI SQL**, **T-SQL (SQL Server)**, **PL/SQL (Oracle)**, **PostgreSQL**, **MySQL/MariaDB**, **SparkSQL/Hive**
- O parser deve extrair os mesmos metadados listados no item 4.2.1 a partir das instruções CREATE TABLE, CREATE VIEW, CREATE PROCEDURE, etc.
- Erros de parsing devem ser listados com número de linha e fragmento do código para correção manual
- O usuário pode combinar extração por conexão e por script para o mesmo sistema de origem

#### 4.2.3 Reconciliação de Extração

- Quando uma extração é feita sobre um sistema que já possui um modelo catalogado, o sistema deve:
  - Identificar **novos objetos** (presentes na extração, ausentes no catálogo)
  - Identificar **objetos removidos** (presentes no catálogo, ausentes na extração)
  - Identificar **objetos alterados** (estrutura divergente entre extração e catálogo)
- Exibir um **diff visual** por objeto antes de aplicar a reconciliação
- A reconciliação deve ser confirmada pelo usuário — nunca automática sem revisão

---

### Módulo 3 — Documentação de Componentes

**Objetivo:** Prover interface rica para documentação completa de todos os componentes extraídos ou criados manualmente no catálogo.

#### 4.3.1 Documentação de Entidades (Tabelas)

- Campos editáveis por entidade:
  - **Nome lógico** (nome de negócio, diferente do nome técnico)
  - **Descrição de negócio** (texto livre, suporte a Markdown)
  - **Domínio de negócio** (ex: Financeiro, RH, Logística) — seleção via lista controlada
  - **Owner de negócio** (responsável pela entidade)
  - **Owner técnico** (time responsável pela manutenção)
  - **Tags de classificação** (labels livres, ex: `master-data`, `transacional`, `referência`)
  - **Criticidade** (Alta / Média / Baixa)
  - **Notas adicionais** (campo livre para informações complementares)

#### 4.3.2 Documentação de Atributos (Colunas)

- Campos editáveis por atributo:
  - **Nome lógico** (nome de negócio)
  - **Descrição** (texto livre)
  - **Exemplo de valor** (valor representativo para facilitar compreensão)
  - **Regra de negócio** (descreve validações ou transformações associadas)
  - **Referência a dicionário de dados** (vínculo ao conceito no glossário corporativo)
  - **Flags** (descritas no Módulo 5)

#### 4.3.3 Documentação de Views

- Campos adicionais além dos comuns a entidades:
  - **Propósito** (por que a view existe, quem a utiliza)
  - **SQL de definição** (exibição com syntax highlighting, editável para documentação — não altera o banco)
  - **Tabelas base relacionadas** (gerado automaticamente pelo parser, editável manualmente)

#### 4.3.4 Documentação de Procedures e Triggers

- Campos adicionais:
  - **Descrição do comportamento** (o que o objeto faz em linguagem de negócio)
  - **Entradas e saídas** (parâmetros documentados individualmente)
  - **Sistemas dependentes** (quais sistemas chamam esse objeto)
  - **Código-fonte** (exibição com syntax highlighting para referência, não editável pela app)
  - **Nível de risco de alteração** (Crítico / Moderado / Baixo)

#### 4.3.5 Documentação de Relacionamentos

- O usuário pode criar, editar ou remover relacionamentos entre entidades do catálogo
- Cada relacionamento deve ter:
  - **Tipo**: 1:1, 1:N, N:M, herança
  - **Cardinalidade** (opcional/obrigatório em cada extremidade)
  - **Colunas participantes** (chave de origem → chave de destino)
  - **Descrição da regra de relacionamento**
  - **Origem do relacionamento**: extraído automaticamente (FK) ou documentado manualmente

---

### Módulo 4 — Diagrama Entidade-Relacionamento (DER) *(Requisito Não Mandatório)*

**Objetivo:** Representação visual interativa dos modelos de dados.

#### 4.4.1 Geração Automática de Diagrama

- Após extração ou documentação, o sistema deve ser capaz de gerar automaticamente um **DER**
- O diagrama deve ser renderizado com uma biblioteca de diagramação (ex: Mermaid, D3.js, ou similar)
- Suporte a modelos relacionais e representação simplificada de modelos não-relacionais (coleções/documentos)

#### 4.4.2 Funcionalidades do Canvas de Diagrama

- Arrastar e posicionar entidades manualmente (layout persistido por modelo/versão)
- Zoom in/out e pan no canvas
- Exibir/ocultar atributos por entidade (modo compacto e modo expandido)
- Filtrar entidades por domínio, tag, ou texto livre
- Clicar em entidade ou relacionamento para abrir painel lateral de detalhes/edição
- Exportar o diagrama como imagem (PNG, SVG) ou como arquivo de diagrama (JSON)

#### 4.4.3 Layouts e Representações

- Suporte a **layout automático** (algoritmo hierárquico, circular ou força-dirigida)
- Indicação visual de entidades com flags LGPD ativas (ícone ou cor de destaque no cabeçalho da entidade)
- Agrupamento visual por domínio de negócio (subgraph/swimlane)

---

### Módulo 5 — Flagueamento de Componentes

**Objetivo:** Permitir a marcação de componentes de banco de dados com flags categorizadas para controle de uso, privacidade e conformidade.

#### 4.5.1 Tipos de Flags

| Categoria | Exemplos de Flags |
|-----------|-------------------|
| **LGPD / Privacidade** | `dados-pessoais`, `dados-sensiveis`, `titular-identificado`, `anonimizado`, `pseudonimizado`, `base-legal-consentimento`, `base-legal-contrato`, `base-legal-obrigacao-legal`, `retencao-definida` |
| **Uso do Dado** | `dado-master`, `dado-transacional`, `dado-historico`, `dado-calculado`, `depreciado`, `em-migração`, `uso-restrito`, `uso-publico-interno` |
| **Qualidade** | `dado-critico`, `sem-validacao`, `validado-negocio`, `inconsistencia-conhecida` |
| **Personalizada** | Administrador pode criar novas flags por categoria |

#### 4.5.2 Aplicação de Flags

- Flags podem ser aplicadas a nível de: **tabela**, **coluna/atributo** individual
- Uma mesma entidade ou atributo pode receber múltiplas flags de categorias distintas
- A aplicação de flags deve registrar: **usuário**, **data/hora**, **versão do modelo** em que foi aplicada
- Flags do tipo LGPD requerem preenchimento obrigatório do campo **"Justificativa"**
- Flags `dados-pessoais` e `dados-sensiveis` devem propagar automaticamente uma sinalização visual para a entidade pai (nível de tabela) quando aplicadas a uma coluna

#### 4.5.3 Auditoria de Flags

- Log imutável de todas as alterações de flags (quem adicionou, quem removeu, data)
- Exportação de relatório de flags LGPD por sistema, domínio ou entidade

---

### Módulo 6 — Dicionário de Dados Corporativo

**Objetivo:** Criar e gerenciar um glossário centralizado de conceitos de dados que pode ser vinculado a atributos em múltiplos sistemas.

#### 4.6.1 Criação de Termos do Dicionário

- Cada termo do dicionário deve conter:
  - **Nome canônico** (termo oficial)
  - **Definição de negócio** (texto em linguagem acessível)
  - **Sinônimos** (termos equivalentes usados em outros sistemas)
  - **Domínio de negócio**
  - **Tipo de dado conceitual** (ex: Identificador, Valor Monetário, Data, Indicador Booleano, Texto Livre)
  - **Exemplos de valores válidos**
  - **Owner do conceito** (pessoa ou área responsável pela definição)
  - **Status** (Rascunho / Em Revisão / Aprovado / Depreciado)

#### 4.6.2 Vínculo a Atributos (Mapeamento de Equivalências)

- Um termo do dicionário pode ser vinculado a N atributos em N sistemas diferentes
- A interface deve exibir, para cada termo, a lista de todos os atributos vinculados com: sistema, tabela, coluna, ambiente
- Ao vincular, o sistema verifica se o tipo de dado nativo do atributo é compatível com o tipo conceitual do termo e exibe alerta se houver divergência
- A descrição do termo aprovado pode ser herdada pelo atributo vinculado (com opção de override)

#### 4.6.3 Governança do Dicionário

- Fluxo de aprovação: rascunho → em revisão → aprovado
- Apenas perfis `Data Architect` ou `Data Steward` com permissão de aprovação podem transitar para "Aprovado"
- Notificação automática (no workspace Databricks) ao responsável do término quando uma revisão é solicitada

---

### Módulo 7 — Linhagem do Dado

**Objetivo:** Mapear a origem, transformações e consumo dos dados catalogados, complementando a linhagem nativa do Unity Catalog.

#### 4.7.1 Linhagem de Origem (Upstream)

- O usuário pode documentar para cada entidade:
  - **Sistema de origem** (sistema que alimenta a entidade)
  - **Entidade de origem** (tabela/endpoint/arquivo de origem)
  - **Tipo de integração** (CDC, batch, API pull, API push, arquivo)
  - **Periodicidade** (tempo real, diária, semanal, sob demanda)
  - **Transformações aplicadas** (descrição textual das regras de transformação)
  - **Pipeline associado** (link para job Databricks, notebook, pipeline DLT)

#### 4.7.2 Linhagem de Consumo (Downstream)

- O usuário pode registrar quais sistemas, aplicações ou dashboards consomem cada entidade:
  - **Sistema consumidor** (nome do sistema ou aplicação)
  - **Tipo de consumo** (leitura direta, API, relatório, modelo ML)
  - **Equipe responsável** pelo sistema consumidor
  - **SLA de dependência** (criticidade da dependência)
- Integração com a **linhagem nativa do Unity Catalog** via API do Databricks para complementar automaticamente os consumidores detectados em runtime

#### 4.7.3 Visualização da Linhagem

- Grafo interativo mostrando: origens → entidade central → consumidores
- Profundidade de navegação configurável (1, 2 ou N níveis)
- Filtro por ambiente (HINT/HEXT/PROD)
- Exportação do grafo como imagem e como JSON estruturado

---

### Módulo 8 — Versionamento de Modelos

**Objetivo:** Manter histórico de versões dos modelos de dados catalogados e permitir comparação entre versões para identificar mudanças.

#### 4.8.1 Criação de Versões

- O sistema deve manter um **rascunho de trabalho** (work in progress) editável
- O usuário pode **publicar uma versão** a qualquer momento, criando um snapshot imutável
- Cada versão publicada deve ter:
  - **Número de versão** (gerado automaticamente, ex: `v1.0`, `v1.1`, `v2.0`)
  - **Título/descrição da versão** (changelog resumido)
  - **Data/hora de publicação**
  - **Usuário publicador**
  - **Status**: Publicado / Depreciado / Ativo (apenas uma versão por sistema pode ser Ativa)

#### 4.8.2 Comparativo entre Versões (Diff)

- Interface de comparação lado a lado entre duas versões selecionadas
- O sistema deve identificar e categorizar automaticamente as diferenças:

| Tipo de Mudança | Exemplos |
|----------------|----------|
| **Adição** | Nova tabela, nova coluna, novo relacionamento, nova flag |
| **Remoção** | Tabela removida, coluna removida, relacionamento excluído |
| **Alteração de estrutura** | Mudança de tipo de dado, nullable, nome técnico |
| **Alteração de documentação** | Mudança de descrição, domínio, flags, dicionário |

- O diff deve ser exibido com indicadores visuais claros (verde para adições, vermelho para remoções, amarelo para alterações)
- Exportação do relatório de diferenças em PDF ou CSV

#### 4.8.3 Restauração de Versão

- Usuário com perfil `Data Architect` pode **restaurar** uma versão anterior como novo rascunho de trabalho
- A restauração não sobrescreve histórico — cria uma nova entrada de rascunho baseada na versão restaurada

---

### Módulo 9 — Sincronização com Unity Catalog

**Objetivo:** Espelhar automaticamente o modelo de dados publicado no Unity Catalog, mantendo descrições, flags e metadados de negócio acessíveis a todas as equipes consumidoras.

#### 4.9.1 Estratégia de Espelhamento

- O espelhamento ocorre automaticamente ao **publicar uma versão ativa** de um modelo
- O sistema mapeia os objetos do catálogo para objetos correspondentes no Unity Catalog:
  - Entidade → **Table** no Unity Catalog
  - Atributo → **Column** no Unity Catalog
  - Schema de origem → **Schema** no Unity Catalog
- **Tipagens não são espelhadas**: os tipos de dados utilizados no Unity Catalog são os nativos da plataforma Databricks (StringType, LongType, etc.), não os tipos do banco de origem. A app não sobrescreve tipos definidos no catálogo Unity.

#### 4.9.2 Metadados Sincronizados

| Metadado na App | Destino no Unity Catalog |
|----------------|------------------------|
| Nome lógico (tabela) | `COMMENT` na tabela |
| Descrição de negócio (tabela) | `COMMENT` na tabela (append ou replace, configurável) |
| Nome lógico (coluna) | `COMMENT` na coluna |
| Descrição (coluna) + exemplo de valor | `COMMENT` na coluna |
| Flags LGPD e de uso | **Tags** do Unity Catalog (`uc.tag.*`) |
| Domínio de negócio | Tag `uc.tag.domain` |
| Criticidade | Tag `uc.tag.criticality` |
| Owner de negócio | Tag `uc.tag.business_owner` |
| Referência ao dicionário | Tag `uc.tag.glossary_term` |

#### 4.9.3 Mecanismo de Sincronização

- Sincronização via **Databricks SDK** e Unity Catalog REST API (ALTER TABLE SET TBLPROPERTIES, ALTER TABLE CHANGE COLUMN)
- O processo de sincronização é executado como um **Databricks Job** em segundo plano, com log de execução acessível na app
- Conflitos de sincronização (metadados editados diretamente no Unity Catalog fora da app) devem ser detectados e reportados ao usuário, com opção de sobrescrever ou ignorar
- Suporte à sincronização incremental (apenas objetos alterados desde a última publicação)

#### 4.9.4 Rastreabilidade da Sincronização

- Log de sincronização por versão publicada: objetos sincronizados, objetos com erro, tempo de execução
- Indicação visual na app de quais objetos estão "em sincronia" ou "desatualizados" em relação ao Unity Catalog

---

### Módulo 10 — Exportação de Scripts DDL

**Objetivo:** Gerar scripts DDL a partir dos modelos catalogados para documentação, migração ou recriação de estruturas.

#### 4.10.1 Geração de DDL

- O usuário pode selecionar: sistema, versão do modelo, schemas e objetos específicos para exportação
- O sistema deve gerar scripts nos seguintes dialetos:
  - **ANSI SQL** (padrão)
  - **T-SQL** (SQL Server / Azure SQL)
  - **PL/SQL** (Oracle)
  - **PostgreSQL**
  - **MySQL**
  - **SparkSQL / Delta Lake** (padrão para integração com Databricks)
- O DDL gerado deve incluir: CREATE TABLE, colunas com tipos, PKs, FKs, índices (quando disponíveis), COMMENTs (com as descrições documentadas na app)

#### 4.10.2 Opções de Exportação

- Incluir ou excluir comentários de documentação no DDL
- Gerar com ou sem esquemas qualificados (ex: `schema.tabela` vs. `tabela`)
- Opção de incluir instruções DROP (IF EXISTS) antes dos CREATE
- Exportar como arquivo `.sql` único ou como arquivo por objeto

#### 4.10.3 Preview de DDL

- Preview com syntax highlighting antes de realizar o download
- Possibilidade de copiar o DDL para a área de transferência diretamente da interface

---

## 5. Requisitos Não-Funcionais

### 5.1 Plataforma e Infraestrutura

- A aplicação deve ser desenvolvida como um **Databricks App** nativo, utilizando um dos frameworks suportados: **Streamlit** (recomendado pela simplicidade) ou **Dash** (recomendado para interatividade avançada do DER)
- Toda a persistência de dados da aplicação deve utilizar tabelas **Delta Lake** no Unity Catalog, dentro de um catalog dedicado (ex: `data_catalog_app`)
- Segredos e credenciais devem ser armazenados exclusivamente via **Databricks Secrets**
- O compute da aplicação deve utilizar **SQL Warehouse serverless** para consultas ao catálogo e um **Job Cluster** para tarefas de sincronização pesadas

### 5.2 Segurança e Controle de Acesso

- Autenticação via **SSO corporativo** integrado ao Databricks (sem login separado)
- Autorização baseada em perfis (RBAC), com os perfis definidos na seção 3
- Todas as operações devem ser auditadas: usuário, ação, timestamp, objeto afetado
- Dados em trânsito: HTTPS/TLS 1.3
- Credenciais de conexão: criptografadas em repouso via Databricks Secrets

### 5.3 Performance

- Carregamento da listagem de objetos do catálogo: < 3 segundos para catálogos com até 10.000 objetos
- Processo de engenharia reversa para bancos com até 500 tabelas: < 5 minutos
- Sincronização incremental com Unity Catalog: < 2 minutos para até 200 objetos alterados
- Interface deve ser responsiva durante processos assíncronos (extração, sincronização) sem travar a navegação

### 5.4 Disponibilidade e Observabilidade

- Logs estruturados (JSON) de todas as operações críticas, persistidos em tabela Delta no Unity Catalog
- Alertas automáticos via Databricks Workflows em caso de falha na sincronização com Unity Catalog
- A aplicação deve exibir status de saúde das conexões de ambiente na tela inicial (dashboard de status)

### 5.5 Usabilidade

- Interface em **português brasileiro**
- Navegação principal via menu lateral com atalhos por módulo
- Suporte a busca global (por nome de entidade, atributo, termo do dicionário) com resultado em < 1 segundo
- Telas de cadastro devem salvar rascunhos automaticamente a cada 30 segundos para evitar perda de dados

---

## 6. Arquitetura de Dados da Aplicação

As tabelas abaixo devem ser criadas no Unity Catalog no catalog `data_catalog_app`:

| Tabela | Descrição |
|--------|-----------|
| `connections` | Conexões de ambientes cadastradas |
| `systems` | Sistemas de origem catalogados |
| `model_versions` | Versões publicadas de modelos |
| `entities` | Tabelas/entidades catalogadas |
| `attributes` | Colunas/atributos catalogados |
| `relationships` | Relacionamentos entre entidades |
| `views_catalog` | Views catalogadas |
| `procedures_catalog` | Procedures catalogadas |
| `triggers_catalog` | Triggers catalogadas |
| `flags` | Definição de flags disponíveis |
| `entity_flags` | Aplicação de flags a entidades |
| `attribute_flags` | Aplicação de flags a atributos |
| `glossary_terms` | Termos do dicionário de dados |
| `glossary_mappings` | Vínculos entre termos e atributos |
| `lineage_upstream` | Linhagem de origem |
| `lineage_downstream` | Linhagem de consumo |
| `sync_log` | Log de sincronizações com Unity Catalog |
| `audit_log` | Log imutável de auditoria geral |

---

## 7. Integrações Externas

| Sistema | Tipo de Integração | Finalidade |
|---------|--------------------|------------|
| **Unity Catalog** | Databricks SDK / REST API | Espelhamento de metadados |
| **Databricks Workflows** | REST API / SDK | Execução assíncrona de jobs (extração, sincronização) |
| **Databricks Secrets** | SDK | Armazenamento seguro de credenciais |
| **SGBD via ODBC** | PyODBC / unixODBC | Engenharia reversa de bancos relacionais |
| **APIs de sistemas origem** | HTTP REST | Engenharia reversa via API |
| **SSO Corporativo** | SAML 2.0 / OAuth 2.0 via Databricks | Autenticação de usuários |

---

## 8. Premissas e Restrições

- Os ambientes HINT, HEXT e PROD devem ter conectividade de rede ao Databricks Apps (VPC peering ou link direto já configurados pela equipe de infraestrutura)
- Os usuários da aplicação devem ter permissões adequadas de leitura nos bancos de origem para a engenharia reversa (sem necessidade de permissões de escrita)
- A aplicação não realiza escrita nos bancos de dados de origem — é exclusivamente de leitura e catalogação
- O Unity Catalog deve estar habilitado no workspace Databricks e os usuários devem ter permissão `USE CATALOG` e `MODIFY` nos schemas relevantes para a sincronização

---

## 9. Critérios de Aceite por Módulo

| Módulo | Critério de Aceite Principal |
|--------|------------------------------|
| Conectividade | Conexão ODBC e API testadas com sucesso para HINT, HEXT e PROD |
| Engenharia Reversa | Extração de tabelas, colunas, FKs, views, procedures e triggers validada em banco de referência |
| Documentação | Todos os campos de uma entidade e seus atributos preenchíveis e persistidos corretamente |
| Flagueamento | Flags LGPD aplicadas a colunas e visíveis no nível da tabela; log de auditoria gerado |
| Dicionário | Termo aprovado vinculado a atributos de 2+ sistemas distintos, com herança de descrição funcionando |
| Linhagem | Grafo upstream/downstream renderizado corretamente e exportável |
| Versionamento | Publicação de versão cria snapshot imutável; diff entre v1 e v2 exibe todas as mudanças corretamente |
| Unity Catalog | Publicação de versão ativa sincroniza descrições e tags no Unity Catalog em < 2 minutos |
| Exportação DDL | DDL gerado em dialeto SparkSQL/Delta e T-SQL é sintaticamente válido e inclui comentários de documentação |
| DER *(não-mandatório)* | Diagrama gerado automaticamente após extração; entidades arrastáveis e exportáveis como PNG |

---

## 10. Glossário

| Termo | Definição no Contexto |
|-------|----------------------|
| **HINT** | Ambiente de Homologação Interna |
| **HEXT** | Ambiente de Homologação Externa |
| **PROD** | Ambiente de Produção |
| **Engenharia Reversa** | Processo de extração automática de metadados de estrutura a partir de um banco de dados existente |
| **DER** | Diagrama Entidade-Relacionamento |
| **Unity Catalog** | Serviço de governança de dados unificado do Databricks |
| **Flag** | Marcador categórico aplicado a um componente de banco para indicar características ou restrições |
| **Dicionário de Dados** | Glossário centralizado de conceitos de dados com definições de negócio |
| **Linhagem** | Rastreamento do fluxo de dados desde a origem até os sistemas consumidores |
| **CdE** | Centro de Excelência de Dados |
| **Tribo de Dados** | Agrupamento de equipes de dados da organização |
| **DDL** | Data Definition Language — linguagem para definição de estruturas de banco de dados |
| **LGPD** | Lei Geral de Proteção de Dados Pessoais (Lei nº 13.709/2018) |
