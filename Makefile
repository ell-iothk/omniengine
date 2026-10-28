# Makefile: one-word commands for everyday tasks, used the same way locally and in CI.
# Run `make help` to list targets. Recipe lines MUST be indented with a TAB, not spaces.

# Targets below are commands, not files; .PHONY stops make from looking for files with these names.
.PHONY: help setup lint format test check pull-model verify-model

# Running plain `make` shows the help text.
.DEFAULT_GOAL := help

help: ## Show this list of targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install dependencies exactly as locked in uv.lock and the git pre-commit hook
	uv sync --locked
	uv run pre-commit install

lint: ## Check style, common bugs and types without changing any file
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format: ## Fix what ruff can fix automatically and reformat the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the tests that need no GPU (the same set CI runs)
	uv run pytest -m "not gpu"

check: lint test ## Everything CI runs: lint, tests, then every pre-commit hook on all files
	uv run pre-commit run --all-files

pull-model: ## Download the model set in .env into OMNIENGINE_MODELS_DIR if missing, then verify it
	uv run --env-file .env python -m omniengine.models pull

verify-model: ## Check the model folder against the pinned revision, without downloading anything
	uv run --env-file .env python -m omniengine.models verify
