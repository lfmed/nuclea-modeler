# Arquitetura — Núclea Modeler

Diagramas Mermaid renderizados nativamente pelo GitHub. Para edição visual:
copie o bloco no [Mermaid Live Editor](https://mermaid.live).

## 1. Visão de alto nível (componentes)

```mermaid
flowchart TB
    subgraph User["👤 Usuário"]
      Browser[Browser]
    end

    subgraph DBX["☁️ Databricks Apps Platform"]
      direction TB
      subgraph App["📦 Núclea Modeler (single process)"]
        direction TB

        subgraph FE["🎨 Frontend"]
          UI[React 19 + TanStack Router + shadcn/ui]
        end

        subgraph BE["⚙️ Backend FastAPI"]
          direction TB
          MW{{Middleware Chain<br/>RequestId → Security → RateLimit → Audit → Metrics}}
          Routes[Routers por módulo<br/>10 módulos + audit/search/admin]
          Core[core/<br/>delta · sql · features · migrations]
          Testers[connections/testers<br/>pyodbc + httpx]
        end
      end

      Warehouse[(SQL Warehouse<br/>serverless)]
      UC[(Unity Catalog<br/>Delta Lake)]
      Lakebase[(Lakebase Postgres<br/>sandbox)]
      Secrets[/Databricks Secrets/]
    end

    subgraph External["🌐 Sistemas externos"]
      HINT[HINT - banco real]
      HEXT[HEXT]
      PROD[PROD]
    end

    Browser -->|HTTPS + SSO| UI
    UI -->|/api/* same-origin| MW
    MW --> Routes
    Routes --> Core
    Routes --> Testers
    Core -->|SQL params :name| Warehouse
    Warehouse --> UC
    Testers -->|psycopg| Lakebase
    Testers -.->|ODBC| HINT
    Testers -.->|ODBC| HEXT
    Testers -.->|REST| PROD
    Testers -->|read| Secrets
    Routes -.->|sync COMMENT+TAGS| UC

    classDef user fill:#fef3c7,stroke:#f59e0b
    classDef ext fill:#fee2e2,stroke:#dc2626
    classDef dbx fill:#ede9fe,stroke:#7c3aed
    classDef storage fill:#dbeafe,stroke:#2563eb

    class Browser user
    class HINT,HEXT,PROD ext
    class Warehouse,UC,Lakebase storage
```

## 2. Request lifecycle

Como uma chamada `POST /api/entities` atravessa a stack:

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant RID as RequestIdMiddleware
    participant SEC as SecurityHeaders
    participant RL as RateLimit
    participant AUD as AuditMiddleware
    participant MET as MetricsMiddleware
    participant RT as Router (/api/entities)
    participant DEP as Delta Helpers
    participant WH as SQL Warehouse
    participant DELTA as Delta UC

    U->>RID: POST /api/entities {payload}
    RID->>RID: gera X-Request-ID (12 chars uuid)
    RID->>SEC: forward
    SEC->>RL: forward
    RL->>RL: bucket por (IP, route)
    alt limite excedido
      RL-->>U: 429 + Retry-After
    else dentro do limite
      RL->>AUD: forward
      AUD->>AUD: captura body (NON-GET)
      AUD->>MET: forward
      MET->>RT: forward + start timer
      RT->>RT: Pydantic validation
      RT->>DEP: delta.insert(table, row)
      DEP->>WH: INSERT INTO ... :params
      WH->>DELTA: write Delta files
      DELTA-->>WH: ok
      WH-->>DEP: SUCCEEDED
      DEP-->>RT: row id
      RT-->>MET: 201 + body
      MET->>MET: stats[route, "2xx"]++
      MET->>AUD: forward
      AUD->>AUD: persiste audit_log (request_id, before, after)
      AUD-->>U: 201 + X-Request-ID + headers
    end
```

## 3. Modelo Delta (resumo)

Tabelas principais do `data_catalog_app` schema (25 tabelas no total). Relações
lógicas — não há FK constraints reais no Delta, validação acontece no app.

```mermaid
erDiagram
    SYSTEMS ||--o{ CONNECTIONS : "tem"
    SYSTEMS ||--o{ ENTITIES : "agrupa"
    SYSTEMS ||--o{ MODEL_VERSIONS : "versiona"
    SYSTEMS ||--o{ EXTRACTIONS : "reversa"
    SYSTEMS ||--o{ RECONCILIATION_TICKETS : "tickets"
    SYSTEMS ||--o{ RELATIONSHIPS : "DER"

    ENTITIES ||--o{ ATTRIBUTES : "contém"
    ENTITIES ||--o{ ENTITY_FLAGS : "tagged"
    ATTRIBUTES ||--o{ ATTRIBUTE_FLAGS : "tagged"
    ATTRIBUTES ||--o{ GLOSSARY_MAPPINGS : "mapeia"

    GLOSSARY_TERMS ||--o{ GLOSSARY_MAPPINGS : "vincula"
    FLAGS ||--o{ ENTITY_FLAGS : "aplicada"
    FLAGS ||--o{ ATTRIBUTE_FLAGS : "aplicada"

    ENTITIES ||--o{ LINEAGE_UPSTREAM : "origem"
    ENTITIES ||--o{ LINEAGE_DOWNSTREAM : "consumo"

    ENTITIES ||--o{ VIEWS_CATALOG : "se VIEW"
    ENTITIES ||--o{ PROCEDURES_CATALOG : "lógicamente"
    ENTITIES ||--o{ TRIGGERS_CATALOG : "logicamente"
    ENTITIES ||--o{ SEQUENCES_CATALOG : "logicamente"

    LAKEBASE_SANDBOXES ||--o{ EXTRACTIONS : "fonte"
    RECONCILIATION_TICKETS ||--|| EXTRACTIONS : "origem do diff"

    SYSTEMS {
        string system_id PK
        string system_name
        string domain
        string technology
    }
    ENTITIES {
        string entity_id PK
        string system_id FK
        string schema_name
        string technical_name
        string logical_name
        string entity_type
        string criticality
    }
    ATTRIBUTES {
        string attribute_id PK
        string entity_id FK
        string technical_name
        string native_data_type
        bool is_primary_key
    }
    RELATIONSHIPS {
        string relationship_id PK
        string source_entity_id FK
        string target_entity_id FK
        string rel_type
    }
    FLAGS {
        string flag_id PK
        string flag_key
        string category
        bool is_system
    }
    MODEL_VERSIONS {
        string version_id PK
        string system_id FK
        string version_number
        string status
        text snapshot_json
    }
```

## 4. Auth & permissões

```mermaid
flowchart LR
    User[Usuário] -->|SSO Databricks| OAuth[OAuth Token]
    OAuth -->|sql scope via app.yml resource| AppSP[App Service Principal]
    OAuth -.->|OBO se necessário| UserClient[Workspace Client OBO]

    AppSP -->|reads/writes Delta| Warehouse[SQL Warehouse]
    AppSP -->|psycopg + scope postgres| Lakebase[Lakebase Sandbox]
    AppSP -->|Secrets API| Secrets[Databricks Secrets]

    UserClient -->|identity propagation| Audit[audit_log row]

    subgraph RBAC["RBAC interno (user_roles Delta)"]
      direction LR
      VIEWER[VIEWER]
      STEWARD[STEWARD]
      ARCHITECT[ARCHITECT]
      ADMIN[ADMIN]
    end

    VIEWER -->|listar| ALL["📖 Read-only"]
    STEWARD -->|+ aprovar termos| GLOSS["📚 Glossário"]
    ARCHITECT -->|+ publish versões + apply tickets| MOD["✏️ Modelagem"]
    ADMIN -->|+ /api/audit + /api/metrics + RBAC| ALL2["🔧 Admin"]

    classDef role fill:#fef3c7,stroke:#f59e0b
    class VIEWER,STEWARD,ARCHITECT,ADMIN role
```

## 5. Deploy

```mermaid
flowchart LR
    Dev[👨‍💻 Dev local] -->|git push| GH[GitHub]
    GH -->|CI verde| Main[main branch]
    Main -->|databricks bundle deploy -p svc| DBX[Databricks Apps]
    DBX -->|startup lifespan| MIG[Migrations runner]
    MIG -->|aplica SQL pendente| UC[(Unity Catalog)]
    DBX -->|uvicorn workers=2| App[Núclea Modeler running]

    GH -.->|Dependabot semanal| Updates[PRs auto-criadas]
    GH -.->|CodeQL scheduled| SAST[Security tab]
    GH -.->|Release tag| Versions[GitHub Releases]
```

## Onde editar

- **Componentes de alto nível:** edite o bloco em **§1**.
- **Novo módulo:** adicione node + edge no §1, e seção no `docs/spec/`.
- **Nova tabela Delta:** atualize §3 + crie migration em `databricks/sql/`.
- **Novo papel RBAC:** §4 + `backend/rbac/service.py`.

Para preview offline: `mermaid-cli` (`bunx mmdc -i system.md -o out.png`).
