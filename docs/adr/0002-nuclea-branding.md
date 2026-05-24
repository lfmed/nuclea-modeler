# ADR-0002 — Branding oficial Núclea (paleta + tipografia)

**Status:** Aceito
**Data:** 2026-05-24
**Decisor:** Leandro Medeiros

## Contexto

O cliente solicitou explicitamente usar o branding oficial da Núclea. A primeira tentativa de paleta foi um placeholder magenta/violeta inferido da identidade FutureBrand 2022. Em seguida o cliente apontou os sites de referência:

- https://ri.nuclea.com.br/ (Relações com Investidores) — acessível
- https://www.nuclea.com.br/ — bloqueado por Akamai (403)

O site RI é hospedado em CDN `mziq.com` (WordPress) e foi possível baixar o `style.css` do tema (`mziq_nuclea_ri/style.css`, 223KB) com user-agent de browser real.

## Captura

Cores extraídas (frequência decrescente no CSS oficial):

| Token | Hex | Uso |
|-------|-----|-----|
| `--nuclea-primary` | **#832ED9** | Roxo Núclea (botões, links, headings ativos) |
| `--nuclea-accent` | **#DBED1F** | Amarelo-lime Núclea (acentos, callouts, highlight) |
| `--nuclea-surface` | **#F9F5FF** | Lavender white (backgrounds suaves) |
| `--nuclea-foreground` | **#383737** | Texto principal |
| Sec. green | #5A645A, #00bb00 | Tons secundários (ok/success) |
| Destructive | #dc3232 / #FFABAB | Erro/atenção |

Tipografia (per stylesheet do tema):

| Uso | Fonte oficial | Fallback web |
|-----|--------------|--------------|
| Display/headings | **Bahnschrift** (Microsoft) | DM Sans, Inter, system-ui |
| Body | **Arial Nova** (Microsoft) | Inter, Helvetica Neue, Arial |

Microsoft fonts não são livres para auto-host. Estratégia: declarar a fonte oficial primeiro no font-stack para usuários Windows / com acesso ao font; fallbacks open-source para todos os outros.

## Decisão

Adotar paleta oficial em `globals.css` via tokens OKLCH (para suportar dark mode bem):

```css
--nuclea-primary: oklch(0.51 0.27 305);  /* #832ED9 */
--nuclea-accent:  oklch(0.91 0.20 117);  /* #DBED1F */
--nuclea-surface: oklch(0.98 0.01 305);  /* #F9F5FF */
```

Logo atualizado para usar `#832ED9` (com gradient para `#6B1FB8`) + dot em `#DBED1F`.

## Consequências

- App tem identidade alinhada com a marca oficial Núclea
- Dark mode permanece coerente (acent yellow continua brilhante; primary fica um pouco mais claro)
- Microsoft fonts: fallback funciona; UX visual no Windows com Bahnschrift instalado fica idêntica
- Caso queiramos os fonts auto-hospedados, precisamos comprar licença para `Bahnschrift` + `Arial Nova` (~US$ 35-200 por face) ou usar substitutos open-source declarados explicitamente

## Alternativas consideradas

- **DM Sans + Inter como primária:** mais consistente cross-platform, mas perde aderência à marca
- **Inter monolítica:** ótima legibilidade, mas tipografia neutra demais para uma marca financeira
