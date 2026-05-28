# ADR-0004 — Quality gates evolution & lessons learned

**Status:** Aceito
**Data:** 2026-05-28
**Decisor:** Leandro Medeiros
**Contexto:** Após v0.2.1 (security patch release dedicado a um único bug XXE descoberto via bandit hard-gate), formalizamos o padrão de evolução de quality gates no CI.

## A descoberta que motivou este ADR

Em 2026-05-28, durante revisão geral, o usuário perguntou *"vi vários errors de workflow, preciso me preocupar?"*. A investigação revelou:

1. Vários `cancelled` — comportamento esperado do `concurrency: cancel-in-progress`
2. CodeQL `failure` — repo privado sem GitHub Advanced Security (esperado)
3. CI `failure` — bug nos testes que eu mesmo escrevi (fix local)

Mas o tópico evoluiu para *"o bandit está warn-only desde o Sprint 0, está realmente sendo útil?"*. Ao tornar bandit hard-gate (`continue-on-error: false`), ele detectou **CWE-20 XXE no parser .erx do Embarcadero** — uma vulnerabilidade real, severity Medium, confidence **High**.

A vulnerabilidade estava lá desde a v0.1.0 (MVP). Ninguém viu em code review. **O quality gate em warn-only não detectou porque o operador não lia os warnings.**

## Decisão

### 1. Lifecycle padrão de um quality gate

Todo novo gate entra com a seguinte trajetória:

```
[A] warn-only/continue-on-error      ← introdução, fase de triagem
       │
       │  (operador audita findings, classifica false-positives, fixa real positives,
       │   adiciona skips justificados ao config)
       ▼
[B] hard-gate                        ← bloqueia PR com novos findings
       │
       │  (eventualmente alguns skips podem ser revistos e removidos
       │   se a lógica subjacente mudar)
       ▼
[C] hard-gate + stricter config      ← maturidade, gate confiável
```

**Tempo médio observado A → B:** 1-2 sprints (dependendo do tamanho da baseline).

### 2. Critérios para promover A → B

Antes de remover `continue-on-error: true`, o operador deve:

1. **Auditar TODOS os findings atuais** — sem exceção.
2. **Classificar:**
   - **Real positive:** corrigir agora (não skip).
   - **False positive estável:** adicionar a `skips` com **comentário explicando POR QUÊ**.
   - **False positive temporário:** TODO no código + issue no GitHub, NÃO skip permanente.
3. **Commit a baseline** dos skips no config (pyproject, ruff, eslint, etc).
4. **Remover** `continue-on-error: true`.
5. **Comunicar** no PR description: "Bandit/CodeQL/etc agora é hard-gate. Skips documentados em X."

### 3. Critérios para skip permanente

Adicione um skip apenas se:
- ✅ Há **comentário de 1-3 linhas explicando** por que é seguro (não apenas "ignored")
- ✅ Você revisou **TODOS os sites** atualmente afetados pelo gate (não só os que dispararam)
- ✅ Existe **mecanismo alternativo** que cobre o risco (ex: bandit B608 está OK porque temos `delta.param()` + `_require_ident()`)

Anti-pattern: skip "porque é ruidoso". Se é ruidoso ao ponto de querer skipar, vale revisar o config (severity, confidence) ou substituir a ferramenta.

### 4. Sequência cronológica dos nossos gates

| Sprint | Gate | Estado |
|---|---|---|
| v0.1.0 MVP | tests rodando | informal (não em CI) |
| v0.2.0 Sprint 0 | ruff lint | hard-gate desde sempre |
| v0.2.0 Sprint 0 | pytest | hard-gate desde sempre |
| v0.2.0 Sprint 0 | tsc | warn-only (legacy errors) |
| v0.2.0 Sprint 0 | bundle size | warn (não bloqueia) |
| v0.2.0 Sprint 0 | TruffleHog | hard-gate desde sempre |
| v0.2.0 Sprint 0 | ruff format | warn-only (não havia rodado format) |
| v0.2.0 Sprint 0 | pytest-cov | hard-gate ≥60% |
| v0.2.0 Sprint 0 | bandit | warn-only (baseline não auditada) |
| v0.2.0 Sprint 0 | OpenAPI snapshot | warn-only (stub committed) |
| v0.2.0 mid | tsc | **promovido hard-gate** (cleanup feito) |
| **v0.2.1** | **bandit** | **promovido hard-gate (achou XXE)** ✅ |
| **v0.2.1** | **OpenAPI snapshot** | **promovido hard-gate condicional** |
| **v0.2.1** | **deps-sync (novo)** | **hard-gate desde criação** |
| **v0.2.1** | **pytest-cov** | **promovido ≥75%** (real ~81%) |
| **v0.2.1** | **ruff format** | **promovido hard-gate** (drift validado em CI matrix) |

### 5. Achados reais que justificaram a abordagem

| Gate | Achado real | Sprint |
|---|---|---|
| tsc | 9 unused imports + 1 type mismatch | v0.2.0 cleanup |
| bandit (B314) | **XXE no parser .erx** (uploaded files = untrusted input) | v0.2.1 |
| deps-sync | `psycopg`/`pyodbc` ausentes do pyproject.toml runtime deps | v0.2.1 |
| pytest-cov 60% | nada (baseline real 81%) | v0.2.0 |

## Consequências

**Boas:**
- Skips passam a ter justificativa rastreável (auditável)
- Lifecycle bem definido para novos contributors (nada de "por que isso é warn-only?")
- Cada gate promovido pega um bug real eventualmente (B314 foi o exemplo extremo)
- ROI alto: o tempo para auditar baseline é menor que o tempo perdido com bugs não detectados

**Aceitas:**
- Promover gate exige sprint dedicado (não dá pra fazer rapidinho num PR de feature)
- Skips listados em config precisam de manutenção (revisar se ainda fazem sentido)

## Não-objetivos (deliberadamente fora de escopo)

- **Adicionar TODOS os linters disponíveis** — cada gate adicionado é dívida operacional. Adicionar só quando claramente cobre risco real.
- **Stop-the-world auditoria periódica** — auditoria acontece ao promover (warn → hard). Manter "sempre limpo" é responsabilidade do contributor que adicionou o código.

## Como aplicar este ADR

**Para adicionar um gate novo:**
1. PR com workflow + `continue-on-error: true`
2. Operador audita output em alguns dias
3. PR seguinte: skips documentados em config + remove `continue-on-error`
4. Atualizar este ADR com a entrada na tabela cronológica

**Para promover gate existente:**
1. Verificar baseline output local: `make lint` ou `make test`
2. Se há findings, classificar (real / false-positive)
3. Real positives → PR de fix
4. False-positives → PR com skip + comentário justificativo
5. PR final: `continue-on-error: false`

## Arquivos relevantes

- `.github/workflows/ci.yml` — workflow principal
- `pyproject.toml` — config ruff + bandit + pytest-cov
- `scripts/dump_openapi.py` — snapshot freeze + drift detection
- `scripts/check_deps_sync.py` — gate novo desta sprint
