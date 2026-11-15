COMPOSE ?= $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
DEMO_COMPOSE = $(COMPOSE) -f docker-compose.yml -f docker-compose.demo.yml

.PHONY: help up up-lite down build test test-cov test-smoke lint format migrate migrate-new logs clean dev ui-build ui-dev demo demo-up demo-down demo-reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start all services
	$(COMPOSE) up -d

up-lite: ## Start lite mode (backend + postgres only)
	$(COMPOSE) -f docker-compose.lite.yml up -d

down: ## Stop all services
	$(COMPOSE) down

build: ## Rebuild backend image
	$(COMPOSE) build backend

test: ## Run test suite (excluding the standalone smoke test)
	PYTHONPATH=. pytest tests/ --ignore=tests/smoke -v

test-cov: ## Run tests with coverage
	PYTHONPATH=. pytest tests/ --ignore=tests/smoke -v --cov=backend --cov-report=html

test-smoke: ## Run the Docker-free end-to-end smoke test
	PYTHONPATH=. pytest tests/smoke -v

lint: ## Run linter
	ruff check .

format: ## Auto-format code
	ruff format .

migrate: ## Run database migrations
	alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new msg="add column")
	alembic revision --autogenerate -m "$(msg)"

logs: ## Follow backend logs
	$(COMPOSE) logs -f backend

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml

dev: ## Run backend in dev mode
	PYTHONPATH=. uvicorn backend.main:app --reload --port 8000

ui-build: ## Build React dashboard into backend/static (served at /ui)
	cd landing-page && VITE_BUILD_SERVE=fastapi npm run build
	@echo "Dashboard built. Start the backend with 'make dev' to access http://localhost:8000/ui"

ui-dev: ## Run React dashboard dev server with API proxy to localhost:8000
	cd landing-page && npm run dev

demo: ## Seed the local metadata DB with mock data (no Docker demo stack)
	PYTHONPATH=. python3 scripts/generate_mock_data.py
	@echo "Mock data loaded. Run 'make dev' to start the server."

demo-up: ## Start the full demo stack and seed it
	$(DEMO_COMPOSE) up -d --build

demo-down: ## Stop the demo stack and delete its volumes
	$(DEMO_COMPOSE) down -v

demo-reset: ## Recreate and reseed the demo stack from scratch
	$(DEMO_COMPOSE) down -v
	$(DEMO_COMPOSE) up -d --build
