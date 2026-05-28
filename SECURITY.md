# Política de Segurança — Núclea Modeler

## Reportando uma vulnerabilidade

**Por favor não abra issue pública** para vulnerabilidades. Use um dos canais privados:

- **E-mail:** leandro.medeiros@databricks.com
- **GitHub Security Advisory:** [Reportar privadamente](https://github.com/lfmed/nuclea-modeler/security/advisories/new)

Inclua:
1. Descrição do impacto observado / hipotético
2. Passos para reproduzir (curl, payload, contexto)
3. Versão do app afetada (`/api/version`) e ambiente (dev/staging/prod)
4. `error_id` e `request_id` se disponível
5. Patch sugerido (opcional)

**Tempo de resposta esperado:** primeira resposta em até **3 dias úteis**.
Triagem + plano de correção em até **10 dias úteis** para alto/crítico.

## Escopo

**Em escopo:**
- O código deste repositório (`lfmed/nuclea-modeler`)
- A deploy live em `nuclea-modeler-*.aws.databricksapps.com`
- Dependências diretas (vide `requirements.txt` + `package.json`)

**Fora de escopo:**
- Plataforma Databricks Apps (reportar à Databricks via SSC)
- Unity Catalog / Delta Lake (idem)
- Vulnerabilidades em browsers ou OS dos usuários
- Engenharia social / phishing
- Ataques físicos

## Defesa em profundidade (atualizado v0.2.1)

| Camada | Mecanismo |
|---|---|
| **Auth** | Databricks SSO (OAuth). Sem auth local. |
| **Authorization** | RBAC com 4 papéis (`VIEWER`, `STEWARD`, `ARCHITECT`, `ADMIN`). `require_role()` decorator em rotas sensíveis. |
| **Input validation** | Pydantic em todo endpoint. `_require_ident()` para identifiers SQL não-parametrizáveis. **Size caps:** DDL upload 5 MB, .erx XML upload 10 MB (cap parser DoS). |
| **XML parsing** | `defusedxml` (não stdlib `xml.etree`) em todo parser .erx — bloqueia XXE, billion-laughs, DTD recursion. |
| **SQL injection** | 100% das queries com input do usuário usam `delta.param()` (binding nomeado `:name`). f-strings com input do usuário são bloqueadas em CI via ruff custom rule. |
| **XSS** | React escapa por default; sem `dangerouslySetInnerHTML` em código próprio. |
| **CSRF** | SameSite cookies via Databricks SSO; CORS opt-in via `NUCLEA_CORS_ALLOW_ORIGINS`. |
| **Clickjacking** | `X-Frame-Options: DENY` em todas as responses. |
| **MIME sniffing** | `X-Content-Type-Options: nosniff`. |
| **HSTS** | `Strict-Transport-Security` condicional a HTTPS (via `x-forwarded-proto`). |
| **Rate limit** | Sliding window por (IP, rota) em endpoints quentes (search 60/min, extraction 20/5min, sync 10/5min). |
| **Secrets** | Databricks Secrets API. Nunca em código, env vars ou logs. |
| **Audit** | Toda mutação em `/api/*` registrada em `audit_log` Delta com actor, request_id, before/after. |
| **Error handling** | Exception handler global sanitiza output. Stack trace só vai para log, nunca response. Cliente recebe `error_id` para correlação. |
| **Dep scanning** | Dependabot semanal (Python + npm + GitHub Actions). PRs auto-criados, majors em PR separado. |
| **Secret scanning** | TruffleHog v3 em todo PR (diff) e push (full tree). Pre-commit hook local catches before push. |

## Onde os secrets vivem

| Tipo | Local |
|---|---|
| Credenciais ODBC (HINT/HEXT/PROD) | Databricks Secrets, scope `NUCLEA_SECRETS_SCOPE` (default `nuclea-modeler`) |
| Tokens REST | Databricks Secrets, mesmo scope |
| OAuth M2M do app | Service principal do Databricks App (auto, sem chave acessível) |
| PATs de dev | `.env` local, nunca commitado (`.gitignore` bloqueia) |

Rotação: atualizar valor no Secrets API → re-testar conexão em `/connections/{id}/test`. App lê sem cache.

## Variáveis hardening

| Var | Recomendação produção |
|---|---|
| `NUCLEA_LOG_JSON` | `true` (correlação por request_id estruturada) |
| `NUCLEA_MIGRATIONS_AUTO_APPLY` | `true` (sem janela de drift) |
| `NUCLEA_CORS_ALLOW_ORIGINS` | (vazio — same-origin only) |
| `NUCLEA_FEATURE_*` | gradualmente, com observação |

## Modelo de ameaça (resumo)

**Threat actors considerados:**
- Usuário interno mal-intencionado (steward com ambição de architect)
- Script abusivo (engenheiro automatizando algo sem limite)
- Comprometimento de conta SSO via phishing externo

**Threat actors fora de escopo:**
- Estado-nação / APT (proteção nesse nível é responsabilidade Databricks)
- Insider com acesso físico ao workspace cluster

**Controles principais:**
- RBAC mínimo para cada operação (apply ticket = ADMIN; publish version = ARCHITECT+ADMIN)
- Audit log imutável (Delta TimeTravel preserva)
- Rate limit por IP em endpoints quentes
- Sem secrets em logs (sanitização em exception handler)
- Exceptions nunca vazam stack para usuário

## Histórico de vulnerabilidades

| Data | Categoria | Detalhe | Status |
|---|---|---|---|
| 2026-05-28 | XXE (CWE-20, bandit B314) | `xml.etree.ElementTree.fromstring` no parser `.erx` do Embarcadero (upload do usuário) era vulnerável a XML External Entity attacks, billion-laughs DoS e DTD recursion. Detectado pelo bandit hard-gate em CI. Substituído por `defusedxml.ElementTree`. | ✅ Corrigido em [v0.2.1](https://github.com/lfmed/nuclea-modeler/releases/tag/v0.2.1). Recomendado criar [Security Advisory privado](https://github.com/lfmed/nuclea-modeler/security/advisories/new) via UI para tracking formal. |

## Agradecimentos

Se um pesquisador reportar uma vulnerabilidade válida e quiser ser creditado,
adicionaremos aqui após o patch ser publicado.
