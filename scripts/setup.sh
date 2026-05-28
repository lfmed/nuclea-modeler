#!/usr/bin/env bash
# Núclea Modeler — setup script idempotente para dev novo.
#
# Uso:
#   bash scripts/setup.sh
#
# O que faz:
#   1. Verifica ferramentas obrigatórias (uv, bun, git, databricks CLI)
#   2. Cria .env a partir de .env.example se não existir
#   3. Instala deps Python (uv) + frontend (bun)
#   4. Instala pre-commit hooks (opcional)
#   5. Valida que `make help` funciona
#
# Idempotente: rodar várias vezes não quebra nada.

set -euo pipefail

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ─── Pré-flight ─────────────────────────────────────────────────────────────

info() { echo -e "${GREEN}→${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

info "Repo root: $REPO_ROOT"

# ─── Ferramentas obrigatórias ──────────────────────────────────────────────

check_tool() {
    local cmd="$1"
    local install_hint="$2"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        warn "$cmd não encontrado. Install: $install_hint"
        return 1
    else
        info "$cmd ✓ ($($cmd --version 2>&1 | head -1))"
        return 0
    fi
}

info "Verificando ferramentas obrigatórias..."

missing=0
check_tool git "https://git-scm.com" || missing=$((missing+1))
check_tool uv "curl -LsSf https://astral.sh/uv/install.sh | sh" || missing=$((missing+1))
check_tool bun "curl -fsSL https://bun.sh/install | bash" || missing=$((missing+1))

if [ "$missing" -gt 0 ]; then
    fail "Faltam $missing ferramentas. Instale e re-execute."
fi

# Opcionais — warn mas não falha
info "Verificando ferramentas opcionais..."
check_tool databricks "pip install databricks-cli" || warn "  (Apenas se for fazer deploy)"
check_tool make "(Já vem com macOS / build-essential no Linux)" || warn "  (Makefile targets indisponíveis sem)"

# ─── .env ────────────────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        info "Criando .env a partir de .env.example..."
        cp .env.example .env
        warn "EDITE .env e preencha DATABRICKS_TOKEN (PAT) antes de rodar o app."
    else
        warn ".env.example não encontrado — pulando criação de .env"
    fi
else
    info ".env já existe ✓"
fi

# ─── Python deps ────────────────────────────────────────────────────────────

if [ ! -d ".venv" ]; then
    info "Criando venv (uv)..."
    uv venv
else
    info ".venv existe ✓"
fi

info "Instalando dependências Python..."
uv pip install -e ".[dev]" --quiet
info "  ✓ runtime + dev installed"

# Optional drivers — não falha se houver erro de compilação
info "Instalando drivers opcionais (psycopg, pyodbc)..."
uv pip install "psycopg[binary]>=3.3.4" --quiet 2>&1 | tail -3 || warn "  psycopg falhou (precisa headers libpq)"
uv pip install "pyodbc>=5.3.0" --quiet 2>&1 | tail -3 || warn "  pyodbc falhou (precisa unixodbc-dev em Linux)"

# ─── Frontend deps ──────────────────────────────────────────────────────────

if [ -f "package.json" ]; then
    info "Instalando dependências frontend (bun)..."
    bun install --silent
    info "  ✓ node_modules pronto"
else
    warn "package.json não encontrado — pulando frontend"
fi

# ─── Pre-commit hooks (opcional) ────────────────────────────────────────────

if command -v pre-commit >/dev/null 2>&1; then
    if [ ! -f ".git/hooks/pre-commit" ]; then
        info "Instalando pre-commit hooks..."
        pre-commit install
    else
        info "pre-commit hooks já instalados ✓"
    fi
else
    warn "pre-commit não encontrado (uv tool install pre-commit). Hooks pulados."
fi

# ─── Sanity check ───────────────────────────────────────────────────────────

if command -v make >/dev/null 2>&1; then
    info "Testando 'make help'..."
    make help >/dev/null 2>&1 && info "  ✓ Makefile funcional"
fi

info "Validando que o pacote Python importa..."
uv run python -c "import nuclea_modeler; print('  ✓ nuclea_modeler v' + nuclea_modeler.__version__)"

# ─── Final ──────────────────────────────────────────────────────────────────

cat <<'EOF'

──────────────────────────────────────────
🎉 Setup completo!

Próximos passos:
  1. Edite .env e preencha DATABRICKS_TOKEN
  2. Para subir dev local:  make dev
  3. Para testes:           make test-cov
  4. Para deploy:           make deploy

Documentação:
  • Getting Started:  docs/tutorial/getting-started.md (20min, primeiro dia)
  • Architecture:     docs/architecture/system.md (Mermaid diagrams)
  • Como contribuir:  CONTRIBUTING.md

Bom desenvolvimento! 🚀
EOF
