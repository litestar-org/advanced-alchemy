SHELL := /bin/bash
# =============================================================================
# Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
.EXPORT_ALL_VARIABLES:
MAKEFLAGS += --no-print-directory

# Define colors and formatting
BLUE := $(shell printf "\033[1;34m")
GREEN := $(shell printf "\033[1;32m")
RED := $(shell printf "\033[1;31m")
YELLOW := $(shell printf "\033[1;33m")
NC := $(shell printf "\033[0m")
INFO := $(shell printf "$(BLUE)ℹ$(NC)")
OK := $(shell printf "$(GREEN)✓$(NC)")
WARN := $(shell printf "$(YELLOW)⚠$(NC)")
ERROR := $(shell printf "$(RED)✖$(NC)")

# =============================================================================
# Help
# =============================================================================
.PHONY: help
help:                                               ## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# =============================================================================
# Developer Utils
# =============================================================================
.PHONY: install-uv
install-uv:                                         ## Install latest version of uv
	@echo "${INFO} Installing UV... 🧪"
	@curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
	@echo "${OK} UV installed successfully ✨"

.PHONY: install
install: destroy clean                              ## Install the project, dependencies, and pre-commit for local development
	@echo "${INFO} Starting fresh installation... 🧙‍♂️"
	@uv python pin 3.12 >/dev/null 2>&1
	@uv sync --all-extras --dev
	@echo "${OK} Dependencies installed 🧪 ✨"

.PHONY: upgrade
upgrade:                                            ## Upgrade all dependencies to the latest stable versions
	@echo "${INFO} Updating all dependencies... 🔄"
	@uv lock --upgrade
	@uv run pre-commit autoupdate
	@echo "${OK} Dependencies and pre-commit hooks updated 🔄 ✨"

.PHONY: clean
clean:                                              ## Cleanup temporary build artifacts
	@echo "${INFO} Cleaning working directory... 🧹"
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ dist/ .eggs/ \
		.find . -name '*.egg-info' -exec rm -rf {} + \
		.find . -type f --name '*.egg' -exec rm -f {} + \
		.find . -name '*.pyc' -exec rm -f {} + \
		.find . -name '*.pyo' -exec rm -f {} + \
		.find . -name '*~' -exec rm -f {} + \
		.find . -name '__pycache__' -exec rm -rf {} + \
		.find . -name '.ipynb_checkpoints' -exec rm -rf {} + \
		.rm -rf .coverage coverage.xml coverage.json htmlcov/ .pytest_cache tests/.pytest_cache .mypy_cache .unasyncd_cache/
	@$(MAKE) docs-clean
	@echo "${OK} Cleaned working directory 🧹 ✨"

.PHONY: destroy
destroy:                                            ## Destroy the virtual environment
	@echo "${INFO} Destroying virtual environment... 🧪 🗑️"
	@uv run pre-commit clean >/dev/null 2>&1
	@rm -rf .venv
	@echo "${OK} Virtual environment destroyed 🗑️ ✨"

.PHONY: lock
lock:                                              ## Rebuild lockfiles from scratch, updating all dependencies
	@echo "${INFO} Rebuilding lockfiles... 🔄"
	@uv lock --upgrade >/dev/null 2>&1
	@echo "${OK} Lockfiles updated 🔒 ✨"

# =============================================================================
# Tests, Linting, Coverage
# =============================================================================
.PHONY: mypy
mypy:                                              ## Run mypy
	@echo "${INFO} Running mypy... 🔍"
	@uv run dmypy run
	@echo "${OK} Mypy checks passed ✨"

.PHONY: mypy-nocache
mypy-nocache:                                      ## Run Mypy without cache
	@echo "${INFO} Running mypy without cache... 🔍"
	@uv run mypy
	@echo "${OK} Mypy checks passed ✨"

.PHONY: pyright
pyright:                                           ## Run pyright
	@echo "${INFO} Running pyright... 🔍"
	@uv run pyright
	@echo "${OK} Pyright checks passed ✨"

.PHONY: type-check
type-check: mypy pyright                           ## Run all type checking
	@echo "${OK} Type checks completed ✅"

.PHONY: pre-commit
pre-commit:                                        ## Runs pre-commit hooks; includes ruff formatting and linting, codespell
	@echo "${INFO} Running pre-commit checks... 🔎"
	@uv run pre-commit run --color=always --all-files
	@echo "${OK} Pre-commit checks passed ✨"

.PHONY: slotscheck
slotscheck:                                        ## Run slotscheck
	@echo "${INFO} Running slots check... 🧪"
	@uv run slotscheck
	@echo "${OK} Slots check passed ✨"

.PHONY: fix
fix:                                               ## Run formatting scripts
	@echo "${INFO} Running code formatters... 🔧"
	@uv run ruff check --fix --unsafe-fixes
	@echo "${OK} Code formatting complete ✨"

.PHONY: lint
lint: pre-commit type-check slotscheck             ## Run all linting
	@echo "${OK} Linting completed ✅"

.PHONY: coverage
coverage:                                          ## Run the tests and generate coverage report
	@echo "${INFO} Running tests with coverage... 📊"
	@uv run pytest tests --cov -n auto
	@uv run coverage html
	@uv run coverage xml
	@echo "${OK} Coverage report generated ✨"

.PHONY: test
test:                                              ## Run the tests
	@echo "${INFO} Running test cases... 🧪"
	@uv run pytest tests -m 'not asyncmy and not asyncpg and not psycopg_async and not psycopg_sync and not oracledb_async and not oracledb_sync and not spanner and not mssql_async and not mssql_sync and not cockroachdb_async and not cockroachdb_sync' -n 2
	@echo "${OK} Tests passed ✅"

.PHONY: test-all
test-all:                                          ## Run all tests
	@echo "${INFO} Running all test cases... 🧪"
	@uv run pytest tests -m '' -n 2
	@echo "${OK} All tests passed ✅"

.PHONY: check-all
check-all: lint test-all coverage                  ## Run all linting, tests, and coverage checks
	@echo "${OK} All checks passed ✅✨"

# =============================================================================
# Docs
# =============================================================================
.PHONY: docs-clean
docs-clean:                                        ## Dump the existing built docs
	@echo "${INFO} Cleaning documentation build assets... 🧹"
	@rm -rf docs/_build >/dev/null 2>&1
	@echo "${OK} Documentation assets cleaned ✨"

.PHONY: docs-serve
docs-serve: docs-clean                             ## Serve the docs locally
	@echo "${INFO} Starting documentation server... 📚"
	@uv run sphinx-autobuild docs docs/_build/ -j auto --watch advanced_alchemy --watch docs --watch tests --watch CONTRIBUTING.rst --port 8002

.PHONY: docs
docs: docs-clean                                   ## Dump the existing built docs and rebuild them
	@echo "${INFO} Building documentation... 📝"
	@uv run sphinx-build -M html docs docs/_build/ -E -a -j auto -W --keep-going
	@echo "${OK} Documentation built successfully ✨"

.PHONY: docs-linkcheck
docs-linkcheck:                                    ## Run the link check on the docs
	@echo "${INFO} Checking documentation links... 🔗"
	@uv run sphinx-build -b linkcheck ./docs ./docs/_build -D linkcheck_ignore='http://.*','https://.*' >/dev/null 2>&1
	@echo "${OK} Link check complete ✅"

.PHONY: docs-linkcheck-full
docs-linkcheck-full:                               ## Run the full link check on the docs
	@echo "${INFO} Running full link check... 🔗"
	@uv run sphinx-build -b linkcheck ./docs ./docs/_build -D linkcheck_anchors=0 >/dev/null 2>&1
	@echo "${OK} Full link check complete ✅"

# =============================================================================
# Local Infrastructure
# =============================================================================

.PHONY: start-infra
start-infra:                                        ## Start local containers
	@echo "${INFO} Starting local infrastructure... 🚀"
	@docker compose -f docker-compose.infra.yml up -d --force-recreate >/dev/null 2>&1
	@echo "${OK} Infrastructure is ready 🧪✨"

.PHONY: stop-infra
stop-infra:                                         ## Stop local containers
	@echo "${INFO} Stopping infrastructure... 🛑"
	@docker compose -f docker-compose.infra.yml down >/dev/null 2>&1
	@echo "${OK} Infrastructure stopped 🛑✨"

.PHONY: wipe-infra
wipe-infra:                                        ## Remove local container info
	@echo "${INFO} Wiping infrastructure... 🧹"
	@docker compose -f docker-compose.infra.yml down -v --remove-orphans >/dev/null 2>&1
	@echo "${OK} Infrastructure wiped clean ✨"

.PHONY: infra-logs
infra-logs:                                        ## Tail development infrastructure logs
	@echo "${INFO} Tailing infrastructure logs... 📋"
	@docker compose -f docker-compose.infra.yml logs -f
