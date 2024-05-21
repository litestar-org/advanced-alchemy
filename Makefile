SHELL := /bin/bash
# =============================================================================
# Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
USING_PDM		=	$(shell grep "tool.pdm" pyproject.toml && echo "yes")
ENV_PREFIX		=	$(shell python3 -c "if __import__('pathlib').Path('.venv/bin/pip').exists(): print('.venv/bin/')")
VENV_EXISTS		=	$(shell python3 -c "if __import__('pathlib').Path('.venv/bin/activate').exists(): print('yes')")
PDM_OPTS 		?=
PDM 			?= 	pdm $(PDM_OPTS)

.EXPORT_ALL_VARIABLES:


.PHONY: help
help: 		   										## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: upgrade
upgrade:       										## Upgrade all dependencies to the latest stable versions
	@echo "=> Updating all dependencies"
	@if [ "$(USING_PDM)" ]; then $(PDM) update; fi
	@echo "=> Dependencies Updated"
	@$(ENV_PREFIX)pre-commit autoupdate
	@echo "=> Updated Pre-commit"

# =============================================================================
# Developer Utils
# =============================================================================
.PHONY: install-pdm
install-pdm: 										## Install latest version of PDM
	@curl -sSLO https://pdm.fming.dev/install-pdm.py && \
	curl -sSL https://pdm.fming.dev/install-pdm.py.sha256 | shasum -a 256 -c - && \
	python3 install-pdm.py

install:											## Install the project and
	@if ! $(PDM) --version > /dev/null; then echo '=> Installing PDM'; $(MAKE) install-pdm; fi
	@if [ "$(VENV_EXISTS)" ]; then echo "=> Removing existing virtual environment"; fi
	@if [ "$(VENV_EXISTS)" ]; then $(MAKE) destroy; fi
	@if [ "$(VENV_EXISTS)" ]; then $(MAKE) clean; fi
	@if [ "$(USING_PDM)" ]; then $(PDM) config venv.in_project true && python3 -m venv --copies .venv && . $(ENV_PREFIX)/activate && $(ENV_PREFIX)/pip install --quiet -U wheel setuptools cython mypy build pip; fi
	@if [ "$(USING_PDM)" ]; then $(PDM) use -f .venv && $(PDM) install -d -G:all; fi
	@echo "=> Install complete! Note: If you want to re-install re-run 'make install'"


clean: 												## Cleanup temporary build artifacts
	@echo "=> Cleaning working directory"
	@if [ "$(USING_PDM)" ]; then $(PDM) run pre-commit clean; fi
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ -rf dist/ .eggs/
	@find . -name '*.egg-info' -exec rm -rf {} +
	@find . -name '*.egg' -exec rm -f {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*~' -exec rm -f {} +
	@find . -name '__pycache__' -exec rm -rf {} +
	@find . -name '.ipynb_checkpoints' -exec rm -rf {} +
	@rm -rf .coverage coverage.xml coverage.json htmlcov/ .pytest_cache tests/.pytest_cache tests/**/.pytest_cache .mypy_cache .unasyncd_cache/
	@$(MAKE) docs-clean

destroy: 											## Destroy the virtual environment
	@rm -rf .venv

.PHONY: refresh-lockfiles
refresh-lockfiles:                                 ## Sync lockfiles with requirements files.
	pdm update --update-reuse --group :all

.PHONY: lock
lock:                                             ## Rebuild lockfiles from scratch, updating all dependencies
	pdm update --update-eager --group :all

# =============================================================================
# Tests, Linting, Coverage
# =============================================================================
.PHONY: lint
lint: 												## Runs pre-commit hooks; includes ruff linting and codespell
	@echo "=> Running pre-commit process"
	@$(ENV_PREFIX)pre-commit run --all-files
	@echo "=> Pre-commit complete"

.PHONY: coverage
coverage:  											## Run the tests and generate coverage report
	@echo "=> Running tests with coverage"
	@make test
	@echo "=> Generating coverage report"
	@$(ENV_PREFIX)coverage html
	@$(ENV_PREFIX)coverage xml
	@echo "=> Coverage report generated"

.PHONY: test
test:  												## Run the tests
	@echo "=> Running test cases"
	@$(ENV_PREFIX)pytest tests -m 'not asyncmy and not asyncpg and not psycopg_async and not psycopg_sync and not oracledb_async and not oracledb_sync and not spanner and not mssql_async and not mssql_sync and not cockroachdb_async and not cockroachdb_sync' -n 2
	@echo "=> Tests complete"

.PHONY: test-all
test-all:  												## Run the tests
	@echo "=> Running all test cases"
	@$(ENV_PREFIX)pytest tests -m '' -n 2
	@echo "=> Tests complete"

.PHONY: test-asyncpg
test-asyncpg:
	$(ENV_PREFIX)pytest tests -m='integration and asyncpg'

.PHONY: test-psycopg-async
test-psycopg-async:
	$(ENV_PREFIX)pytest tests -m='integration and psycopg_async'

.PHONY: test-psycopg-sync
test-psycopg-sync:
	$(ENV_PREFIX)pytest tests -m='integration and psycopg_sync'

.PHONY: test-asyncmy
test-asyncmy:
	$(ENV_PREFIX)pytest tests -m='integration and asyncmy'

.PHONY: test-oracledb-sync
test-oracledb-sync:
	$(ENV_PREFIX)pytest tests -m='integration and oracledb_sync'

.PHONY: test-oracledb-async
test-oracledb-async:
	$(ENV_PREFIX)pytest tests -m='integration and oracledb_async'

.PHONY: test-duckdb
test-duckdb:
	$(ENV_PREFIX)pytest tests -m='integration and duckdb'

.PHONY: test-spanner
test-spanner:
	$(ENV_PREFIX)pytest tests -m='integration and spanner'

.PHONY: test-mssql-sync
test-mssql-sync:
	$(ENV_PREFIX)pytest tests -m='integration and mssql_sync'

.PHONY: test-mssql-async
test-mssql-async:
	$(ENV_PREFIX)pytest tests -m='integration and mssql_async'

.PHONY: test-cockroachdb-sync
test-cockroachdb-sync:
	$(ENV_PREFIX)pytest tests -m='integration and cockroachdb_sync'

.PHONY: test-cockroachdb-async
test-cockroachdb-async:
	$(ENV_PREFIX)pytest tests -m='integration and cockroachdb_async'

.PHONY: test-all-databases
test-all-databases:
	$(ENV_PREFIX)pytest tests -m='integration'

.PHONY: check-all
check-all: lint test coverage 						## Run all linting, tests, and coverage checks

# =============================================================================
# Docs
# =============================================================================
.PHONY: docs-install
docs-install: 										## Install docs dependencies
	@echo "=> Installing documentation dependencies"
	@$(PDM) install --group docs
	@echo "=> Installed documentation dependencies"

docs-clean: 										## Dump the existing built docs
	@echo "=> Cleaning documentation build assets"
	@rm -rf docs/_build
	@echo "=> Removed existing documentation build assets"

docs-serve: docs-clean 								## Serve the docs locally
	@echo "=> Serving documentation"
	$(ENV_PREFIX)sphinx-autobuild docs docs/_build/ -j auto --watch advanced_alchemy --watch docs --watch tests --watch CONTRIBUTING.rst --port 8002

docs: docs-clean 									## Dump the existing built docs and rebuild them
	@echo "=> Building documentation"
	@$(ENV_PREFIX)sphinx-build -M html docs docs/_build/ -E -a -j auto --keep-going

changelog:
	@echo "=> Generating changelog"
	@$(ENV_PREFIX)git-cliff -c pyproject.toml -o docs/changelog.rst --github-repo litestar-org/advanced-alchemy --github-token $(GITHUB_TOKEN)
