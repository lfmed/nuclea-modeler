# 40 — Madrugada "God Mode" Multi-Agente

**Data:** 2026-05-23 → 2026-05-24
**Modo:** Execução autônoma com PRs paralelos
**Resultado:** 7 PRs entregues, todos mergeados no `main`

## Briefing da madrugada (literal)

> "vou dormir, siga em god mode, me pergunte algumas coisas e avance o maximo que puder, sempre que houve uma diferença capturada na reconciliaçao, deve ser abert um ticket tratado na propria aplicacao para alguem aceitar e tratar essa nove versao."

> "ja que sao diferentes prs, crie multiagentes para fazer mais rapido, seja inteligente"

> "Capture o branding da nuclea nos sites: https://ri.nuclea.com.br/. https://www.nuclea.com.br/. ajuste o app para ter esse brading."

> "vá validando tudo ao terminar"

## Decisões tomadas (perguntas iniciais)

| # | Pergunta | Resposta |
|---|----------|----------|
| 1 | Fluxo do ticket de reconciliação | **OPEN → APPROVED → APPLIED** (+ REJECTED) |
| 2 | RBAC ticket — quem aprova? | **Só Data Architect / Steward** (com fallback Admin) |
| 3 | M2 — ODBC real ou mock? | **ODBC real com Lakebase como banco-piloto** |
| 4 | Git flow | **PRs separados por módulo** |

## Estratégia

1. Construir a **fundação** (tickets-rbac) e mergear ANTES dos paralelos — outros módulos dependem dela.
2. Capturar **branding oficial Núclea** scrapeando `ri.nuclea.com.br` (`www.nuclea.com.br` bloqueado por Akamai).
3. Disparar **5 agentes paralelos** em git worktrees isolados para módulos independentes:
   - M9 Sync UC
   - M5 Flagueamento LGPD
   - M6 Dicionário Corporativo
   - M8 Versionamento + Diff
   - M10 Exportação DDL
4. Eu (orquestrador) faria **Lakebase + M2** localmente, que dependem de tickets-rbac (M2 abre ticket de reconciliação automaticamente).
5. Mergear PRs em sequência com rebase + resolução de conflitos em `app.py` e `lib/api.ts`.
6. Deploy final + validação.

## Branding oficial capturado

Da CSS do tema RI Núclea (https://cdn-sites-assets.mziq.com/wp-content/themes/mziq_nuclea_ri/style.css):

| Token | Hex | Uso |
|-------|-----|-----|
| `--nuclea-primary` | `#832ED9` | Roxo Núclea (botões, links, chips primários) |
| `--nuclea-accent` | `#DBED1F` | Amarelo-lime (acentos, dots, callouts) |
| `--nuclea-surface` | `#F9F5FF` | Lavender white (backgrounds suaves) |
| `--nuclea-foreground` | `#383737` | Texto principal |

Tipografia:
- **Display:** Bahnschrift (fallback DM Sans, Inter)
- **Body:** Arial Nova (fallback Inter, Helvetica Neue, Arial)

Detalhes em [`docs/adr/0002-nuclea-branding.md`](../adr/0002-nuclea-branding.md).

## PRs entregues

| # | PR | Módulo | Linhas | Agente |
|---|----|----|--------|--------|
| 1 | [#1](https://github.com/lfmed/nuclea-modeler/pull/1) | Tickets + RBAC + Branding | ~1500 | Orquestrador |
| 2 | [#2](https://github.com/lfmed/nuclea-modeler/pull/2) | M9 Sync Unity Catalog | ~800 | Agente A |
| 3 | [#3](https://github.com/lfmed/nuclea-modeler/pull/3) | M5 Flagueamento LGPD | ~900 | Agente B |
| 4 | [#4](https://github.com/lfmed/nuclea-modeler/pull/4) | M10 Exportação DDL | ~1200 | Agente C |
| 5 | [#5](https://github.com/lfmed/nuclea-modeler/pull/5) | M6 Dicionário Corporativo | ~1100 | Agente D |
| 6 | [#6](https://github.com/lfmed/nuclea-modeler/pull/6) | M8 Versionamento + Diff | ~1000 | Agente E |
| 7 | [#7](https://github.com/lfmed/nuclea-modeler/pull/7) | M2 Eng. Reversa + Lakebase Sandbox | ~1600 | Orquestrador |

**Total:** ~8.100 linhas de código em uma noite.

## Estado final do app (Fase 2 quase 100%)

| Módulo | Status | Notas |
|--------|--------|-------|
| M1 Conexões | ✅ Real | ODBC/REST/DDL CRUD + test (teste real ODBC entra com drivers) |
| M2 Engenharia Reversa | ✅ Real | Lakebase via psycopg + parser DDL via sqlglot |
| M3 Documentação | ✅ Real | Entidades + atributos + tags |
| M4 DER | ⏳ Pendente | Fase 3 — visualização gráfica |
| M5 Flagueamento | ✅ Real | 21 flags pré-seeded + LGPD propagation |
| M6 Dicionário | ✅ Real | Termos + mapeamentos + fluxo aprovação |
| M7 Linhagem | ⏳ Pendente | Fase 3 |
| M8 Versionamento | ✅ Real | Snapshots imutáveis + diff lado-a-lado |
| M9 Sync UC | ✅ Real | COMMENT + TAGS via SDK, dry-run, histórico |
| M10 Export DDL | ✅ Real | 6 dialetos hand-rolled |
| M-LB Lakebase | ✅ Real | CRUD sandboxes + Postgres via OAuth token |
| Tickets | ✅ Real | OPEN → APPROVED → APPLIED com RBAC |

## Aprendizados da noite

1. **Worktrees isolados destravam paralelismo.** Cada agente em sua árvore git, sem conflito durante a execução. Conflitos só na hora do merge — manageable.

2. **Mesmo files compartilhados (app.py, api.ts) conflitam consistentemente.** Resolução manual sequencial é rápida porque cada PR adiciona em região distinta. Padrão: copiar `main` como base e re-appendar a nova seção.

3. **`api.ts` cresceu ~5×** (de ~250 linhas pré-tickets para ~1200+ linhas). Vai precisar quebrar em módulos por feature em algum momento — mas single-file mantém OpenAPI codegen futuro mais simples.

4. **Bloqueio IP ACL do workspace pode interromper deploy.** Aconteceu no final da madrugada. Resolvido aguardando ou pedindo desbloqueio. Como o app continua rodando, é só impacto em deploys.

5. **Branding oficial é hospedado em CDN WordPress (mziq.com).** Site institucional foi bloqueado por Akamai mas o RI cedeu. CSS público traz cores + fontes exatas.

## Próximos passos

- ⏭️ **M4 DER + M7 Linhagem** — Fase 3 (visualizações avançadas)
- ⏭️ **F-Cross #17** — RBAC global por endpoint + audit_log middleware + busca global
- ⏭️ **Testes** — pytest + playwright básicos
- ⏭️ **Edit pages** — connections, entities, sandboxes (PUT endpoints existem, falta UI)
