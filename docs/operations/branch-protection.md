# Branch protection — `main`

Guia para configurar branch protection rules em `main` no GitHub. Esses
settings vivem fora do repo (não há arquivo committável que defina branch
protection), então este documento é a fonte da verdade.

## Configuração recomendada

Settings → Branches → Add branch protection rule → Branch name pattern: `main`

### ✅ Require a pull request before merging

- ✅ **Require approvals**: 1 (ou 2 quando time crescer)
- ✅ **Dismiss stale pull request approvals when new commits are pushed**
- ✅ **Require review from Code Owners** (lê `.github/CODEOWNERS`)
- ☐ Require approval of the most recent reviewable push *(opcional, atrasa devloop)*

### ✅ Require status checks to pass before merging

- ✅ **Require branches to be up to date before merging**
- Status checks obrigatórios (todos do workflow `ci.yml`):
  - `Python (ruff + pytest)`
  - `Frontend (build + bundle size)`
  - `Secret scan`

### ✅ Require conversation resolution before merging

- ✅ Garante que comentários de review foram resolvidos antes do merge.

### ✅ Require signed commits

- ✅ **Opcional mas recomendado**. Exige GPG/SSH sign nos commits.
- Como configurar localmente:
  ```bash
  git config --global user.signingkey <key-id>
  git config --global commit.gpgsign true
  ```
- Vide [docs do GitHub](https://docs.github.com/en/authentication/managing-commit-signature-verification).

### ✅ Require linear history

- ✅ Sem merge commits. Use squash & merge ou rebase & merge.
- Reflete a convenção de Conventional Commits do projeto.

### ✅ Do not allow bypassing the above settings

- ✅ Admins também respeitam as regras. Evita "consertinhos rápidos" em main.

### ❌ Allow force pushes

- ❌ **NUNCA** habilitar.

### ❌ Allow deletions

- ❌ **NUNCA** habilitar para `main`.

## Configuração via GitHub CLI (alternativa à UI)

Como o GitHub não permite definir branch protection via arquivo no repo,
um setup-script abaixo pode ser usado uma vez quando provisionar o repo:

```bash
gh api repos/lfmed/nuclea-modeler/branches/main/protection \
  --method PUT \
  --header "Accept: application/vnd.github+json" \
  -F required_status_checks[strict]=true \
  -F 'required_status_checks[contexts][]=Python (ruff + pytest)' \
  -F 'required_status_checks[contexts][]=Frontend (build + bundle size)' \
  -F 'required_status_checks[contexts][]=Secret scan' \
  -F enforce_admins=true \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F required_pull_request_reviews[dismiss_stale_reviews]=true \
  -F required_pull_request_reviews[require_code_owner_reviews]=true \
  -F required_conversation_resolution=true \
  -F required_linear_history=true \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

> Requer permissão de admin no repo.

## Verificar status atual

```bash
gh api repos/lfmed/nuclea-modeler/branches/main/protection 2>&1 | jq
```

Se retornar `404 Not Found`, branch protection ainda não foi configurada.

## Exceções

Nenhuma. Se um hotfix precisar entrar rápido:
1. Abra PR mesmo assim
2. Marque label `hotfix`
3. CI passa em 30-40s
4. Self-review/aprove + merge

Não vale a pena bypass — economia em 30s não compensa risco de quebrar
production sem CI.

## Auditoria

Branch protection bypasses ficam em `Settings → Audit log`. Filtrar por
`action:protected_branch.*` para histórico completo.
