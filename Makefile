# Núclea Modeler — atalhos de devloop.
#
# Auto-documented: `make` ou `make help` lista todos os alvos.
# Targets baseados em GNU Make 3+. Compatível com Linux/macOS.

.DEFAULT_GOAL := help
.PHONY: help install dev backend frontend test test-cov lint format build deploy migrate \
        migrate-cli backup perf snapshot clean health docs-serve pre-commit-install \
        pre-commit-run upgrade-deps tag-list

# ─── Variáveis ──────────────────────────────────────────────────────────────

PYTHON ?= python3
UV ?= uv
BUN ?= bun
APP_BASE ?= http://localhost:8000
LIVE_URL ?= https://nuclea-modeler-7474646973581105.aws.databricksapps.com

# ─── Help (default) ─────────────────────────────────────────────────────────

help: ## Lista todos os alvos disponíveis
	@echo "Núclea Modeler — Makefile"
	@echo ""
	@echo "Uso: make <alvo>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─── Setup ──────────────────────────────────────────────────────────────────

setup: ## Setup completo onboarding (verifica ferramentas + cria .env + install)
	bash scripts/setup.sh

install: ## Instala todas as dependências (Python + frontend)
	$(UV) venv
	$(UV) pip install -e ".[dev]"
	$(UV) pip install "psycopg[binary]>=3.3.4" "pyodbc>=5.3.0"
	$(BUN) install

pre-commit-install: ## Instala os hooks de pre-commit
	$(UV) tool install pre-commit
	pre-commit install

pre-commit-run: ## Roda os hooks de pre-commit em tudo
	pre-commit run --all-files

# ─── Dev loop ───────────────────────────────────────────────────────────────

dev: ## Sobe backend + frontend em paralelo
	@echo "Backend → http://localhost:8000 · Frontend → http://localhost:5173"
	@$(MAKE) -j 2 backend frontend

backend: ## Sobe apenas o backend (uvicorn --reload)
	$(UV) run uvicorn nuclea_modeler.backend.app:app --reload --app-dir src --host 0.0.0.0 --port 8000

frontend: ## Sobe apenas o frontend (Vite dev)
	$(BUN) run dev

# ─── Qualidade ──────────────────────────────────────────────────────────────

test: ## Roda os testes (sem coverage gate)
	$(UV) run pytest tests/ -q

test-cov: ## Roda os testes com coverage (gate 60% conforme pyproject)
	$(UV) run pytest tests/

lint: ## Lint Python (ruff) + tsc TypeScript
	$(UV) run ruff check src/ tests/ scripts/
	$(BUN) run tsc

format: ## Auto-formatar Python (ruff format)
	$(UV) run ruff format src/ tests/ scripts/
	$(UV) run ruff check --fix src/ tests/ scripts/

# ─── Build & Deploy ─────────────────────────────────────────────────────────

build: ## Build de produção do frontend (gera src/nuclea_modeler/__dist__/)
	$(BUN) run build

deploy: ## Deploy via Databricks Asset Bundle (target svc)
	databricks bundle deploy -p svc
	databricks bundle run nuclea-modeler-app -p svc

# ─── Operacional ────────────────────────────────────────────────────────────

migrate: ## Aplica migrations pendentes via CLI (não-startup)
	$(UV) run $(PYTHON) -m nuclea_modeler.backend.core.migrations

migrate-cli: migrate ## alias

backup: ## Backup snapshot das tabelas Delta para Volume UC. Exige VOLUME=/Volumes/...
ifndef VOLUME
	$(error VOLUME não definido. Uso: make backup VOLUME=/Volumes/main/default/nuclea_backups)
endif
	$(UV) run $(PYTHON) -m scripts.backup --volume $(VOLUME)

perf: ## Smoke test de latência. Override BASE_URL=... opcionalmente
	$(UV) run $(PYTHON) -m scripts.perf_smoke --base $(or $(BASE_URL),$(APP_BASE))

snapshot: ## Regenera docs/openapi.json a partir do código atual
	$(UV) run $(PYTHON) -m scripts.dump_openapi

# ─── Diagnóstico ────────────────────────────────────────────────────────────

health: ## Curl no /api/health da deploy live
	@curl -s "$(LIVE_URL)/api/health" | python3 -m json.tool

tag-list: ## Lista tags com data
	@git tag --sort=-creatordate --format='%(refname:short) %(creatordate:short) %(subject)'

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean: ## Remove caches Python + node_modules + dist
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml
	rm -rf node_modules src/nuclea_modeler/__dist__/assets
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ─── Misc ───────────────────────────────────────────────────────────────────

upgrade-deps: ## Sobe deps dev locais (sem mexer em prod). Útil pós Dependabot merge.
	$(UV) pip install -e ".[dev]" --upgrade
	$(BUN) update
