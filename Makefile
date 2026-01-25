.PHONY: setup install lint fix format clean run help

PYTHON = uv run python
MODULE = obsi_diff

# 1. Capture everything after 'run'
# $(wordlist 2, ...) grabs all words starting from the second position
RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Initial project setup
	uv sync --group dev
	uv run pre-commit install

lint: ## Run ruff linter
	uv run ruff check .

fix: ## Run ruff and automatically fix issues
	uv run ruff check . --fix --unsafe-fixes
	uv run ruff format .

run: ## Run the app (Usage: make run interact --refresh)
	@$(PYTHON) -m $(MODULE) $(RUN_ARGS) || if [ $$? -eq 2 ]; then exit 0; else exit $$?; fi

%:
	@:
