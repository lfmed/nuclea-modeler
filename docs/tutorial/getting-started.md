# Getting Started — Núclea Modeler

Tutorial passo-a-passo para o seu **primeiro dia** com o app. Estimativa: 20 minutos.

Pré-requisitos:
- Conta no workspace Databricks da Núclea
- Papel **VIEWER** ou superior (peça ao admin)
- Acesso à URL: `https://nuclea-modeler-7474646973581105.aws.databricksapps.com`

---

## 0. Abra o app

1. Acesse a URL acima no Chrome/Firefox.
2. Login automático via SSO Databricks.
3. Na primeira visita, o **Welcome Tour** abre automaticamente — siga os 5 passos
   ou clique em **Pular**. Você pode refazer depois em `Help → Refazer tour`.

> 💡 Não vê o sidebar? Clique no botão hamburger ou pressione `Ctrl+B` / `⌘+B`.

---

## 1. Cadastre um Sistema (5 min)

Sistemas são **fontes** — bancos de dados ou APIs que o catálogo vai
documentar. Ex: `SAP_ERP`, `CRM_SALESFORCE`, `DW_PRINCIPAL`.

### Pelo UI

1. Sidebar → **Entidades** (sistemas ficam no header da página de entidades).
2. Clique em **"Novo sistema"** no canto superior direito.
3. Preencha:
   - **Nome:** `CRM_NUCLEA`
   - **Domínio:** `Comercial`
   - **Tecnologia:** `PostgreSQL` (ou `SQL Server`, `Oracle`...)
   - **Time owner:** `tribo-comercial@nuclea`
4. Salvar.

### Por API (alternativa)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "$BASE/api/systems" \
  -d '{
    "system_name": "CRM_NUCLEA",
    "domain": "Comercial",
    "technology": "PostgreSQL",
    "owner_team": "tribo-comercial@nuclea"
  }'
```

> 🎯 **Por que faz isso primeiro?** Sistema é o agrupador. Toda entidade, conexão,
> versão, ticket fica vinculado a um sistema. Sem sistema, nada começa.

---

## 2. Conecte ao banco real (3 min)

### 2a. Adicione credenciais ao Databricks Secrets

```bash
# Via Databricks CLI
databricks secrets put-secret nuclea-modeler crm_db_user
# Cole o usuário, Ctrl+D
databricks secrets put-secret nuclea-modeler crm_db_pass
# Cole a senha
```

Default scope = `nuclea-modeler` (var `NUCLEA_SECRETS_SCOPE`).

### 2b. Cadastre a conexão no app

Sidebar → **Conexões** → **"Cadastrar primeira conexão"**:

| Campo | Valor exemplo |
|---|---|
| **Alias** | `CRM Prod` |
| **Ambiente** | `PROD` |
| **Sistema** | `CRM_NUCLEA` (criado em §1) |
| **Tipo** | `ODBC` (ou `REST` para APIs) |
| **Driver** | `PostgreSQL Unicode` |
| **Host** | `crm.internal.nuclea` |
| **Porta** | `5432` |
| **Database** | `crm_prod` |
| **Secret key user** | `crm_db_user` |
| **Secret key pass** | `crm_db_pass` |

### 2c. Teste

Botão **"Testar"** na linha da conexão. Status fica verde + latência.
Falha? veja `last_test_error` na lista de conexões.

---

## 3. Engenharia reversa: traga o schema (5 min)

Você tem **3 caminhos**:

### Opção A — Importar `.erx` do ER/Studio (recomendado se já existe modelo)

Sidebar → **Extrações** → aba **Embarcadero** → upload do arquivo `.erx`.

Resultado: entidades + atributos importados, com PKs e tipos preservados.

### Opção B — Engenharia reversa via Lakebase Sandbox (round-trip)

Pré-requisito: ter um sandbox Lakebase conectado (sidebar **Lakebase Sandbox**).

Sidebar → **Extrações** → aba **Lakebase** → selecione sandbox + sistema + schemas.

### Opção C — Importar DDL (SQL) diretamente

Sidebar → **Extrações** → aba **DDL** → cole o SQL ou faça upload.

Dialetos suportados: ANSI, T-SQL, PL/SQL, PostgreSQL, MySQL, Spark SQL.

> 🎯 **O que acontece?** O app compara o schema com o catálogo, detecta o que
> é novo/alterado/removido, e abre um **Ticket de Reconciliação** automaticamente.

---

## 4. Aprove o Ticket (2 min)

Sidebar → **Tickets** → seu ticket recém-aberto.

Tela mostra:
- **Diff visual:** entidades novas (verde), alteradas (amarelo), removidas (vermelho)
- Quem disparou, quando, qual extração originou
- Cada entidade expansível com seus atributos

Fluxo (requer papel `ARCHITECT` ou `ADMIN`):
1. **Aprovar** — marca o diff como reviewado, ainda não aplica
2. **Aplicar** — cria entidades + atributos no catálogo
3. (alternativa) **Rejeitar** com motivo — fecha sem aplicar

Audit log registra cada ação automaticamente.

---

## 5. Documente uma entidade (2 min)

Sidebar → **Entidades** → clique numa linha.

Tela de detalhe permite editar:
- **Logical name** (nome de negócio: "Cliente Pessoa Física")
- **Description (Markdown)** — descrição rica com listas, headings, links
- **Business owner** (pessoa do negócio responsável)
- **Technical owner** (pessoa de TI responsável)
- **Criticality** (HIGH / MEDIUM / LOW)
- **Domain** — só selecione, não digite livre
- **Tags** — palavras-chave separadas por vírgula

Aba **Atributos** lista todas as colunas. Edite uma:
- **Logical name** ("CPF do Titular")
- **Description** ("Documento de identificação fiscal")
- **Business rule** ("11 dígitos numéricos, sem formatação")
- **Glossary term** — vincula a um termo do dicionário corporativo

---

## 6. Aplique flags LGPD (1 min)

Numa entidade ou atributo, aba **Flags** → **"Aplicar flag"** → escolha
`LGPD - Dado Pessoal`.

App **propaga automaticamente** flags LGPD de coluna para a entidade-pai
(regra spec §4.5.2), garantindo que tabelas com qualquer coluna LGPD aparecem
nos relatórios de compliance.

---

## 7. Visualize o DER (1 min)

Sidebar → **Diagrama** → selecione o sistema.

Layout automático via Dagre. Drag entidades para reorganizar. Arrastar uma
aresta entre duas tabelas cria um relacionamento.

> 💡 Clique numa aresta para ver detalhes do relacionamento (cardinalidade,
> tipo FK, regra de delete/update).

---

## 8. Publique uma versão (2 min)

Sidebar → **Versões** → **"Publicar nova versão"** (requer ARCHITECT/ADMIN).

Preencha:
- **Título:** `Q2 2026 — adição CRM`
- **Changelog** (Markdown): liste o que mudou
- **Tornar ativa** ✅

App congela um **snapshot JSON imutável** do modelo. Em incidente, restaure
em 1 clique.

---

## 9. Sincronize com Unity Catalog (1 min)

Versão publicada? Hora de propagar para o catálogo nativo do Databricks.

Sidebar → **Sync** → selecione sistema + catálogo destino.

**Dry-run primeiro** para ver o que vai mudar. Depois aplique. Resultado:
todas as tabelas do UC ganham `COMMENT` e `TAGS` (domain, criticality,
business_owner, LGPD) visíveis no Catalog Explorer nativo.

---

## 10. Próximos passos

- [Roteiro de demo para arquitetos](../demo/jornada-arquiteto-de-dados.html) — 6 cenários do dia-a-dia
- [API Recipes (curl)](../api/RECIPES.md) — automatizar via scripts
- [CONTRIBUTING](../../CONTRIBUTING.md) — adicionar features ao app
- `Help` (sidebar) — guia in-app sempre disponível
- [Architecture](../architecture/system.md) — entender a stack

## Atalhos de teclado

| Tecla | Ação |
|---|---|
| `⌘+K` / `Ctrl+K` | Abrir busca global |
| `Ctrl+B` / `⌘+B` | Toggle sidebar |
| `Tab` (primeiro) | Skip-to-content |
| `Esc` | Fechar modal/sheet |

## Dúvidas?

- Abra `Help` no sidebar
- Reporte issue: [GitHub Issues](https://github.com/lfmed/nuclea-modeler/issues/new/choose)
- Vulnerabilidade: [Security Advisory](https://github.com/lfmed/nuclea-modeler/security/advisories/new) (privado)
