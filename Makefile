.PHONY: setup install lint fix format clean run help

PYTHON = uv run python
SCRIPT = main.py

# Logic to grab everything after 'run'
# Usage: make run list-versions
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

run: ## Pass-through to main.py (Usage: make run <command> [args])
	@$(PYTHON) $(SCRIPT) $(RUN_ARGS) || if [ $$? -eq 2 ]; then exit 0; else exit $$?; fi

clean: ## Cleanup cache and local artifacts
	docker rm -f $$(docker ps -aq --filter "name=obsidian-") 2>/dev/null || true
	rm -f *.css *.tar .obsidian_cache.json

# Catch-all to prevent Make from complaining about script arguments
%:
	@:
