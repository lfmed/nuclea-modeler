# ADR-0001 — Stack: APX (FastAPI + React) sobre Streamlit/Dash

**Status:** Aceito
**Data:** 2026-05-22
**Decisor:** Leandro Medeiros (com aval do produto)

## Contexto

A especificação (`docs/spec/`) recomenda explicitamente Streamlit ou Dash como frameworks-padrão para Databricks Apps. A app tem dez módulos com requisitos não-triviais de UX:

- DER interativo (canvas, drag, zoom)
- Diff visual lado-a-lado de versões
- Forms ricos com auto-save
- Grafos de linhagem
- Busca global < 1s
- Branding institucional Núclea

Streamlit é ótimo para dashboards e prototipagem, mas sofre com:
- Re-render full-page a cada interação
- Tipagem fraca entre frontend/backend
- Controle de layout limitado
- Difícil customizar branding profundamente

Dash dá mais flexibilidade mas continua sendo um framework "data-app-first", não um stack web completo.

## Decisão

Adotar **APX** (template oficial Databricks Solutions Architects) como stack:

- **Backend:** FastAPI + Pydantic + uv
- **Frontend:** React 18 + TanStack Router + shadcn/ui + Tailwind + Bun + Vite
- **Tipos:** OpenAPI auto-gerado do backend para o frontend
- **Type check:** basedpyright (backend) + tsc (frontend)

## Consequências

### Positivas
- UX profissional comparável a SaaS comercial (shadcn é estado-da-arte)
- Branding e tema totalmente customizáveis
- Tipos sincronizados — quebras de contrato pegam em build time
- Componentização real do frontend → fácil manter ao escalar para 10 módulos
- Stack moderno → mais fácil onboarding de devs frontend

### Negativas
- Curva de aprendizado maior que Streamlit
- Cada feature exige código em duas linguagens (Python + TS)
- DevOps ligeiramente mais complexo (dois processos em dev)
- APX ainda é projeto novo — risco de breaking changes (mitigado pelo pin de versão)

## Alternativas consideradas

| Alternativa | Por que não |
|------------|-------------|
| Streamlit | UX e branding insuficientes para 10 módulos |
| Dash | Idem; melhor que Streamlit mas ainda subóptimo para forms ricos |
| Flask + Jinja | Stack legado; sem componentização moderna |
| Next.js + FastAPI standalone | Mais flexível mas perde a integração APX↔Databricks Apps |
