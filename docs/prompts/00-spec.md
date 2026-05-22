# 00 — Spec original recebida

**Data:** 2026-05-22
**Autor:** Cliente (Núclea — Tribo de Dados / CdE)
**Arquivo autoritativo:** [`../spec/especificacao_funcional_databricks_app_catalogo_dados.md`](../spec/especificacao_funcional_databricks_app_catalogo_dados.md)

## Resumo

Especificação funcional v1.0 — define 10 módulos para um Databricks App nativo de catálogo e modelagem de dados, operando sobre HINT/HEXT/PROD e espelhando o modelo publicado no Unity Catalog.

## Diretrizes adicionais transmitidas verbalmente

> "O aplicativo é da Nuclea, use o branding e seus melhores skills de UX para construir esse app"
>
> "Entenda tudo e crie um plano militar para executar"
>
> "Crie todos os objetos no meu ambiente databricks, não rode nada local"
>
> "alem disso crie esse projeto no meu git pessoal e junto um prompt registry sobre as etapas"
>
> "o repo tem q se [pri]vado"

## Decisões iniciais alinhadas

| Tema | Decisão | Trade-off avaliado |
|------|---------|-------------------|
| Workspace Databricks | `svc @ fevm-stable-classic-pg4xe1` | Único profile válido no momento |
| Framework | **APX (FastAPI + React)** | Streamlit/Dash seriam mais rápidos mas APX dá UX/branding superior |
| Estratégia | **MVP iterativo** | Big-bang teria mais risco; esqueleto+stubs adiaria valor |
| Repo | `lfmed/nuclea-modeler` **privado** | Cliente; não pode ser público |
| UC | Schema dentro de `stable_classic_pg4xe1_catalog.data_catalog_app` | Cria CATALOG novo exigiria privilégios de metastore admin |
| Branding | Pesquisa oficial + paleta institucional Núclea (placeholder magenta/roxo + amarelo) | Site oficial bloqueia scraping (Akamai); validar visualmente após deploy |
