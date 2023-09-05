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
	@if [ "$(USING_PDM)" ]; then $(PDM) update; fi
	@echo "=> Dependencies Updated"
	$(ENV_PREFIX)pre-commit autoupdate
	@echo "=> Updated Pre-commit"

# =============================================================================
# Developer Utils
# =============================================================================
.PHONY: install-pdm
install-pdm: 										## Install latest version of PDM
	@curl -sSL https://pdm.fming.dev/dev/install-pdm.py | python3 -
 
install:											## Install the project and
	@if ! $(PDM) --version > /dev/null; then echo '=> Installing PDM'; $(MAKE) install-pdm; fi
	@if [ "$(VENV_EXISTS)" ]; then echo "=> Removing existing virtual environment"; fi
	if [ "$(VENV_EXISTS)" ]; then $(MAKE) destroy; fi
	if [ "$(VENV_EXISTS)" ]; then $(MAKE) clean; fi
	if [ "$(USING_PDM)" ]; then $(PDM) config venv.in_project true && python3 -m venv --copies .venv && . $(ENV_PREFIX)/activate && $(ENV_PREFIX)/pip install -U wheel setuptools cython pip; fi
	if [ "$(USING_PDM)" ]; then $(PDM) install -G:all; fi 
	@echo "=> Install complete! Note: If you want to re-install re-run 'make install'"


clean: 												## Cleanup temporary build artifacts
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .hypothesis
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -f {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.ipynb_checkpoints' -exec rm -rf {} +
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf coverage.json
	rm -rf htmlcov/
	rm -rf .pytest_cache
	rm -rf tests/.pytest_cache
	rm -rf tests/**/.pytest_cache
	rm -rf .mypy_cache
	find tools/downloads -type f -delete
	$(MAKE) docs-clean

destroy: 											## Destroy the virtual environment
	rm -rf .venv
 
# =============================================================================
# Tests, Linting, Coverage
# =============================================================================
.PHONY: lint
lint: 												## Runs pre-commit hooks; includes ruff linting, codespell, black
	$(ENV_PREFIX)pre-commit run --all-files

.PHONY: test
test:  												## Run the tests
	$(ENV_PREFIX)pytest tests

.PHONY: coverage
coverage:  											## Run the tests and generate coverage report
	$(ENV_PREFIX)pytest tests --cov=app
	$(ENV_PREFIX)coverage html
	$(ENV_PREFIX)coverage xml

.PHONY: check-all
check-all: lint test coverage 						## Run all linting, tests, and coverage checks

# =============================================================================
# Docs
# =============================================================================
.PHONY: docs-install
docs-install: 										## Install docs dependencies
	$(PDM) install --group docs

docs-clean: 										## Dump the existing built docs
	rm -rf docs/_build

docs-serve: docs-clean 								## Serve the docs locally
	$(ENV_PREFIX)sphinx-autobuild docs docs/_build/ -j auto --watch app --watch docs --watch tests --watch CONTRIBUTING.rst --port 8002

docs: docs-clean 									## Dump the existing built docs and rebuild them
	$(ENV_PREFIX)sphinx-build -M html docs docs/_build/ -E -a -j auto --keep-going

 