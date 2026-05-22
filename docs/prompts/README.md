# Prompt Registry — Nuclea Modeler

> Histórico vivo dos prompts, decisões e comandos usados para construir o app, fase por fase.

## Por que isso existe

Este projeto está sendo construído em colaboração com um assistente de IA (Claude / Claude Code). Para garantir **reprodutibilidade, auditoria e onboarding rápido de novos colaboradores**, cada fase do trabalho é registrada aqui contendo:

1. **Prompt(s)** enviados ao assistente
2. **Decisões** tomadas em conjunto (e os trade-offs)
3. **Comandos** executados no ambiente Databricks / Git / local
4. **Diffs / artefatos** produzidos (referências aos commits)
5. **Aprendizados** e ajustes para iterações futuras

## Índice

| # | Arquivo | Fase | Status |
|---|---------|------|--------|
| 00 | [00-spec.md](00-spec.md) | Spec original recebida do cliente | ✅ |
| 01 | [01-plano-militar.md](01-plano-militar.md) | Plano de execução consolidado | ✅ |
| 10 | [10-fase0-bootstrap.md](10-fase0-bootstrap.md) | Bootstrap: repo, scaffold, UC, recursos | 🟡 em curso |
| 20 | [20-fase1-mvp.md](20-fase1-mvp.md) | MVP: M1 + M2 + M3 + M9 + deploy | ⏳ |
| 30 | [30-fase2-governanca.md](30-fase2-governanca.md) | M5 + M6 + M8 + M10 | ⏳ |
| 40 | [40-fase3-visualizacao.md](40-fase3-visualizacao.md) | M7 + M4 | ⏳ |
| 90 | [90-cross-rbac-audit.md](90-cross-rbac-audit.md) | RBAC, auditoria, busca global | ⏳ |

## Convenções

- **Cada arquivo abre com um cabeçalho** contendo: fase, objetivo, status, autor primário, datas
- **Prompts citados literalmente** entre cercas tríplices ` ``` ` — preserva pontuação e nuances
- **Decisões críticas viram ADRs** em `docs/adr/` e são referenciadas aqui por número (ADR-NNNN)
- **Commits relevantes** são referenciados por hash curto
- **Linguagem:** português brasileiro (como o resto do produto)
