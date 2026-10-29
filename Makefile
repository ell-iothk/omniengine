# Makefile: one-word commands for everyday tasks, used the same way locally and in CI.
# Run `make help` to list targets. Recipe lines MUST be indented with a TAB, not spaces.

# Targets below are commands, not files; .PHONY stops make from looking for files with these names.
.PHONY: help setup lint format test check pull-model verify-model up down logs ps smoke chat test-gpu
# Running plain `make` shows the help text.
.DEFAULT_GOAL := help

help: ## Show this list of targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install dependencies exactly as locked in uv.lock and the git pre-commit hook
	uv sync --locked
	uv run pre-commit install

# The last line fills compose.yaml from .env.example, not .env, so a variable missing there fails.
lint: ## Check style, common bugs, types and compose.yaml without changing any file
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	docker compose --env-file .env.example config --quiet

format: ## Fix what ruff can fix automatically and reformat the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the tests that need no GPU (the same set CI runs)
	uv run pytest -m "not gpu"

check: lint test ## Everything CI runs: lint, tests, then every pre-commit hook on all files
	uv run pre-commit run --all-files

pull-model: ## Download the model set in .env into OMNIENGINE_MODELS_DIR if missing, then verify it
	uv run --env-file .env omniengine models pull

verify-model: ## Check the model folder against the pinned revision, without downloading anything
	uv run --env-file .env omniengine models verify

# --- Serving stack (needs .env, the GPU, and no other vLLM server running) ---------------------

up: ## Start vLLM in the background and wait up to 15 minutes until it reports healthy
	docker compose up --detach --wait --wait-timeout 900

down: ## Stop and remove the vLLM container; models, volumes and the image stay
	docker compose down

logs: ## Follow vLLM's log (Ctrl+C stops following, the server keeps running)
	docker compose logs --follow --tail 200 vllm

ps: ## Show the container's state and health
	docker compose ps

smoke: ## Check the running server like an agent: health, models, chat, tools, JSON output
	uv run --env-file .env omniengine smoke

chat: ## Talk to the served model in the terminal (/exit leaves); the quickest demo
	uv run --env-file .env omniengine chat

test-gpu: ## Run the tests marked gpu against the running server (start it with make up)
	uv run --env-file .env pytest -m gpu
